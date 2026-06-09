#!/usr/bin/env python3
"""Run cqframework/cql-tests-runner against the local FHIR4DS $cql facade."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import fhir4ds  # noqa: E402
from fhir4ds.cql.fhir_server import CQLServerConfig, create_http_server  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--quick", action="store_true", help="Ask the runner to use quick mode")
    parser.add_argument("--only", action="append", default=[], help="Runner only-list item")
    parser.add_argument("--runner-path", default=os.environ.get("CQL_TESTS_RUNNER_PATH"))
    parser.add_argument("--runner-image", help="Optional Docker image for the runner")
    parser.add_argument("--runner-ref", default="main", help="Informational runner ref for reports")
    parser.add_argument(
        "--report",
        default="conformance/reports/cql_tests_runner_report.json",
        help="Report path",
    )
    args = parser.parse_args(argv)

    port = args.port or _free_port(args.host)
    config = CQLServerConfig(host=args.host, port=port, use_cpp_extensions=False)
    server = create_http_server(config)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)

    report_path = Path(args.report).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = _run_runner(args, f"http://{args.host}:{port}/fhir")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    report = {
        "runner_ref": args.runner_ref,
        "server_url": f"http://{args.host}:{port}/fhir",
        "quick": args.quick,
        "only": args.only,
        "status": result["status"],
        "returncode": result.get("returncode"),
        "raw_results_path": result.get("raw_results_path"),
        "pass_count": result.get("pass_count"),
        "skip_count": result.get("skip_count"),
        "fail_count": result.get("fail_count"),
        "error_count": result.get("error_count"),
        "total_count": result.get("total_count"),
        "stdout_tail": result.get("stdout_tail", []),
        "stderr_tail": result.get("stderr_tail", []),
        "unsupported": result.get("unsupported", []),
    }
    report_path.write_text(json.dumps(report, indent=2))
    print(f"Wrote {report_path}")
    return 0 if result["status"] in {"pass", "not-run"} else 1


def _run_runner(args: argparse.Namespace, base_url: str) -> dict:
    if args.runner_path:
        return _run_runner_from_path(Path(args.runner_path), args, base_url)
    if args.runner_image:
        return _run_runner_docker(args.runner_image, args, base_url)
    return {
        "status": "not-run",
        "unsupported": [
            "No runner was configured. Set CQL_TESTS_RUNNER_PATH, pass --runner-path, "
            "or pass --runner-image."
        ],
    }


def _run_runner_from_path(path: Path, args: argparse.Namespace, base_url: str) -> dict:
    if not path.exists():
        return {"status": "fail", "unsupported": [f"Runner path not found: {path}"]}
    work_dir = Path(args.report).resolve().parent / "cql_tests_runner_raw"
    output_path = work_dir / "results"
    work_dir.mkdir(parents=True, exist_ok=True)
    config_path = work_dir / "fhir4ds-cql-runner.json"
    config_path.write_text(
        json.dumps(
            {
                "FhirServer": {
                    "BaseUrl": base_url,
                    "CqlOperation": "$cql",
                },
                "Build": _build_config(),
                "Debug": {"QuickTest": args.quick},
                "Tests": {
                    "ResultsPath": str(output_path),
                    "SkipList": _known_runner_skip_list(),
                    "OnlyList": _only_items(args.only),
                },
            },
            indent=2,
        )
    )
    cmd = [
        "npm",
        "exec",
        "--",
        "tsx",
        "src/bin/cql-tests.ts",
        "run-tests",
        str(config_path),
        str(output_path),
    ]
    if args.quick:
        cmd.append("--quick")
    completed = subprocess.run(cmd, cwd=path, text=True, capture_output=True, check=False)
    return _completed_report(completed, output_path)


def _run_runner_docker(image: str, args: argparse.Namespace, base_url: str) -> dict:
    work_dir = Path(args.report).resolve().parent / "cql_tests_runner_raw"
    output_path = work_dir / "results"
    output_path.mkdir(parents=True, exist_ok=True)
    config_path = work_dir / "fhir4ds-cql-runner.json"
    config_path.write_text(
        json.dumps(
            {
                "FhirServer": {"BaseUrl": base_url, "CqlOperation": "$cql"},
                "Build": _build_config(),
                "Debug": {"QuickTest": args.quick},
                "Tests": {
                    "ResultsPath": "/results",
                    "SkipList": _known_runner_skip_list(),
                    "OnlyList": _only_items(args.only),
                },
            },
            indent=2,
        )
    )
    cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{config_path}:/config.json:ro",
        "-v",
        f"{output_path}:/results",
        image,
        "run-tests",
        "/config.json",
        "/results",
    ]
    if args.quick:
        cmd.append("--quick")
    completed = subprocess.run(cmd, text=True, capture_output=True, check=False)
    return _completed_report(completed, output_path)


def _completed_report(completed: subprocess.CompletedProcess[str], output_path: Path | None = None) -> dict:
    report = {
        "status": "pass" if completed.returncode == 0 else "fail",
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout.splitlines()[-40:],
        "stderr_tail": completed.stderr.splitlines()[-40:],
    }
    if output_path is not None:
        report.update(_result_counts(output_path))
    if completed.returncode == 0 and report.get("fail_count") is not None:
        report["status"] = (
            "pass"
            if int(report.get("fail_count") or 0) == 0
            and int(report.get("error_count") or 0) == 0
            else "fail"
        )
    return report


def _result_counts(output_path: Path) -> dict:
    files = sorted(output_path.glob("*_results.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        return {"raw_results_path": None}
    latest = files[-1]
    try:
        data = json.loads(latest.read_text())
    except (OSError, json.JSONDecodeError):
        return {"raw_results_path": str(latest)}
    summary = data.get("testResultsSummary", {})
    return {
        "raw_results_path": str(latest),
        "pass_count": summary.get("passCount"),
        "skip_count": summary.get("skipCount"),
        "fail_count": summary.get("failCount"),
        "error_count": summary.get("errorCount"),
        "total_count": len(data.get("results", [])),
    }


def _free_port(host: str) -> int:
    with socket.socket() as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _only_items(items: list[str]) -> list[dict[str, str]]:
    result = []
    for item in items:
        parts = item.replace("/", ":").split(":")
        if len(parts) != 3:
            raise SystemExit(f"--only must be testsName:groupName:testName, got {item!r}")
        result.append({"testsName": parts[0], "groupName": parts[1], "testName": parts[2]})
    return result


def _known_runner_skip_list() -> list[dict[str, str]]:
    """Local FHIR4DS compatibility skips.

    Keep this empty now that Long and code-only Concept comparison are handled
    in the local cql-tests-runner checkout.
    """
    return []


def _build_config() -> dict[str, str]:
    return {
        "CqlFileVersion": "1.0.000",
        "CqlOutputPath": "./cql",
        "CqlVersion": "1.5",
        "testsRunDescription": "FHIR4DS local $cql facade test run",
        "cqlTranslator": "FHIR4DS",
        "cqlTranslatorVersion": fhir4ds.__version__,
        "cqlEngine": "FHIR4DS",
        "cqlEngineVersion": fhir4ds.__version__,
    }


if __name__ == "__main__":
    raise SystemExit(main())
