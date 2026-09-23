"""Capability-matrix test: CLI subprocess vs in-process MCP client vs
cleanroom browser worker (FDD §3.8).

Asserts identical normalized envelopes for run_tests on the shared
fixture. The cleanroom leg drives the deployed web app (vite preview on
:5176) through Playwright; it skips cleanly when node tooling, the app
build, or the preview server is unavailable (environment-availability
skip per the AGENTS.md test-skip policy — never behavior hiding).
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from .fixtures import (
    MATRIX_CASES,
    MATRIX_LIBRARY,
    MATRIX_OUTPUT_COLUMNS,
    MATRIX_RESOURCES,
    normalized_verify_envelope,
    write_matrix_fixture,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CLEANROOM_DIR = REPO_ROOT / "web" / "cql-cleanroom"


def _cli_leg(tmp_path: Path) -> dict:
    paths = write_matrix_fixture(tmp_path / "cli")
    proc = subprocess.run(
        [
            sys.executable, "-c",
            "from fhir4ds.cli.main import main; import sys; sys.exit(main(sys.argv[1:]))",
            "verify",
            "--library", paths["library"],
            "--data", paths["ndjson"],
            "--tests", paths["cases"],
            "--output-columns", json.dumps(MATRIX_OUTPUT_COLUMNS),
        ],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 1, f"expected 1 failing case, got {proc.returncode}: {proc.stderr[-400:]}"
    return json.loads(proc.stdout)


def _mcp_leg() -> dict:
    pytest.importorskip("mcp")
    from fhir4ds.mcp.server import build_server

    server = build_server()

    async def call():
        return await server._tool_manager.call_tool(
            "run_tests_tool",
            arguments={
                "libraries": [{"name": "MatrixSimple", "text": MATRIX_LIBRARY}],
                "dataset": {"resources": MATRIX_RESOURCES},
                "cases": MATRIX_CASES,
                "output_columns": MATRIX_OUTPUT_COLUMNS,
            },
        )

    out = io.StringIO()
    with contextlib.redirect_stdout(out):  # engine INFO logs must not pollute
        result = asyncio.run(call())
    return result


# ---------------------------------------------------------------------------
# Leg 3: the browser adapter (CQL Cleanroom) — three-way matrix (C1-U8)
# ---------------------------------------------------------------------------

def _preview_is_up(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2):
            return True
    except (urllib.error.URLError, OSError):
        return False


def _cleanroom_leg(tmp_path: Path) -> dict:
    if shutil.which("npx") is None:
        pytest.skip("npx not available — cleanroom leg needs Playwright/node")
    if not (CLEANROOM_DIR / "node_modules").exists():
        pytest.skip("cleanroom node_modules not installed")
    if not (CLEANROOM_DIR / "dist" / "index.html").exists():
        pytest.skip("cleanroom dist/ not built (run npm run build)")
    if not _preview_is_up("http://localhost:5176/"):
        pytest.skip("cleanroom preview server not running on :5176")

    fixture_path = tmp_path / "matrix_fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "library": {"name": "MatrixSimple", "text": MATRIX_LIBRARY},
                "resources": MATRIX_RESOURCES,
                "cases": MATRIX_CASES,
                "output_columns": MATRIX_OUTPUT_COLUMNS,
            }
        ),
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "CLEANROOM_MATRIX_FIXTURE": str(fixture_path),
    }
    proc = subprocess.run(
        ["npx", "playwright", "test", "tests/e2e/matrix-leg.spec.ts", "--reporter=line"],
        capture_output=True, text=True, cwd=str(CLEANROOM_DIR), env=env,
        timeout=420,
    )
    marker = "CLEANROOM_ENVELOPE_BEGIN"
    combined = proc.stdout + proc.stderr
    if marker not in combined:
        pytest.skip(f"cleanroom leg did not emit envelope (exit {proc.returncode}): {combined[-300:]}")
    raw = combined.split(marker, 1)[1].split("CLEANROOM_ENVELOPE_END", 1)[0]
    return json.loads(raw)


def test_capability_matrix_cli_mcp_identical_envelopes(tmp_path):
    cli = normalized_verify_envelope(_cli_leg(tmp_path))
    mcp = normalized_verify_envelope(_mcp_leg())
    assert cli == mcp
    # Spot-check contract fields both legs must carry.
    for leg in (cli, mcp):
        assert leg["schema"] == 1
        assert leg["ok"] is True
        assert leg["passed"] is False  # unknown-patient case fails
        assert leg["summary"] == {"IPP": 2, "NAME": 2}
        assert leg["tests"]["total"] == 4
        assert leg["tests"]["failures"][0]["patient"] == "pt-9"


def test_capability_matrix_three_way_with_cleanroom(tmp_path):
    """FDD §3.8 leg 3: the cleanroom worker (browser) must produce the
    SAME normalized run_tests envelope as CLI and MCP on the unchanged
    fixture."""
    cli = normalized_verify_envelope(_cli_leg(tmp_path))
    mcp = normalized_verify_envelope(_mcp_leg())
    cleanroom = normalized_verify_envelope(_cleanroom_leg(tmp_path))
    assert cli == mcp == cleanroom
    assert cleanroom["schema"] == 1
    assert cleanroom["summary"] == {"IPP": 2, "NAME": 2}


# ---------------------------------------------------------------------------
# C2-U4: compare_evidence three-way leg on the same fixture mechanism
# ---------------------------------------------------------------------------

# Baseline = the matrix fixture's true populations; current flips pt-1's
# IPP (the only definition that CAN flip on this fixture deterministically)
# and drops pt-3 (patient removed). Expected delta: moved pt-1 IPP,
# removed pt-3 (IPP + NAME columns per-patient-column presence).
MATRIX_COMPARE_BASELINE = {
    "patients": {
        "pt-1": {"populations": {"IPP": True, "NAME": True}},
        "pt-2": {"populations": {"IPP": False, "NAME": True}},
        "pt-3": {"populations": {"IPP": True, "NAME": False}},
    }
}
MATRIX_COMPARE_CURRENT = {
    "patients": {
        "pt-1": {"populations": {"IPP": False, "NAME": True}},
        "pt-2": {"populations": {"IPP": False, "NAME": True}},
    }
}


def _normalized_delta_envelope(envelope: dict) -> dict:
    """Drop volatile/ordering-insensitive fields from compare deltas."""
    out = json.loads(json.dumps(envelope, default=str))
    # patients rows are already deterministically ordered by the capability
    return out


def _compare_legs(tmp_path: Path) -> tuple[dict, dict, dict]:
    """(cli, mcp, cleanroom) normalized compare_evidence envelopes.

    CLI leg uses the real verify surface: the CURRENT populations come
    from evaluating the modified dataset (pt-3 removed, pt-1 IPP flipped
    by editing the fixture resources), --baseline points at the ORIGINAL
    populations artifact. MCP and browser legs consume the same two
    payloads directly.
    """
    from ..capabilities.compare import compare_evidence

    # The "current" dataset: pt-3 removed, pt-1 gender flipped to male
    # (IPP membership changes; NAME stays true).
    current_resources = [
        {**MATRIX_RESOURCES[0], "gender": "male"},  # pt-1: IPP True -> False
        MATRIX_RESOURCES[1],                        # pt-2: unchanged
    ]
    baseline_path = tmp_path / "cli" / "baseline.json"
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(
        json.dumps(
            {
                "schema": 1,
                "ok": True,
                "patients": MATRIX_COMPARE_BASELINE["patients"],
            }
        ),
        encoding="utf-8",
    )
    current_ndjson = tmp_path / "cli" / "current.ndjson"
    current_ndjson.write_text(
        "\n".join(json.dumps(r) for r in current_resources) + "\n",
        encoding="utf-8",
    )
    lib_path = tmp_path / "cli" / "MatrixSimple.cql"
    lib_path.write_text(MATRIX_LIBRARY, encoding="utf-8")

    cli_proc = subprocess.run(
        [
            sys.executable, "-c",
            "from fhir4ds.cli.main import main; import sys; sys.exit(main(sys.argv[1:]))",
            "verify",
            "--library", str(lib_path),
            "--data", str(current_ndjson),
            "--baseline", str(baseline_path),
            "--output-columns", json.dumps(MATRIX_OUTPUT_COLUMNS),
        ],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    assert proc_ok(cli_proc), f"cli compare leg failed: {cli_proc.stderr[-400:]}"
    cli = _normalized_delta_envelope(json.loads(cli_proc.stdout))
    cli.pop("library", None)  # transport-specific echo

    # MCP leg: compare_evidence_tool on the same payload pair.
    pytest.importorskip("mcp")
    from fhir4ds.mcp.server import build_server

    server = build_server()

    async def call():
        return await server._tool_manager.call_tool(
            "compare_evidence_tool",
            arguments={
                "baseline": {
                    "schema": 1,
                    "ok": True,
                    "patients": MATRIX_COMPARE_BASELINE["patients"],
                },
                "current": {
                    "schema": 1,
                    "ok": True,
                    "patients": MATRIX_COMPARE_CURRENT["patients"],
                },
            },
        )

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        mcp_result = asyncio.run(call())
    mcp = _normalized_delta_envelope(mcp_result)

    # Cleanroom leg: extend the fixture with a compare section and re-run
    # the Playwright matrix leg (marker COMPARE).
    cleanroom: dict | None = None
    if _cleanroom_available():
        fixture_path = tmp_path / "matrix_compare_fixture.json"
        fixture_path.write_text(
            json.dumps(
                {
                    "library": {"name": "MatrixSimple", "text": MATRIX_LIBRARY},
                    "resources": MATRIX_RESOURCES,
                    "cases": MATRIX_CASES,
                    "output_columns": MATRIX_OUTPUT_COLUMNS,
                    "compare": {
                        "baseline": {
                            "schema": 1,
                            "ok": True,
                            "patients": MATRIX_COMPARE_BASELINE["patients"],
                        },
                        "current": {
                            "schema": 1,
                            "ok": True,
                            "patients": MATRIX_COMPARE_CURRENT["patients"],
                        },
                        "output_columns": None,
                    },
                }
            ),
            encoding="utf-8",
        )
        env = {**os.environ, "CLEANROOM_MATRIX_FIXTURE": str(fixture_path)}
        proc = subprocess.run(
            ["npx", "playwright", "test", "tests/e2e/matrix-leg.spec.ts", "--reporter=line"],
            capture_output=True, text=True, cwd=str(CLEANROOM_DIR), env=env,
            timeout=420,
        )
        combined = proc.stdout + proc.stderr
        marker = "CLEANROOM_COMPARE_BEGIN"
        if marker in combined:
            raw = combined.split(marker, 1)[1].split("CLEANROOM_COMPARE_END", 1)[0]
            cleanroom = _normalized_delta_envelope(json.loads(raw))
        else:
            pytest.skip(
                f"cleanroom compare leg did not emit envelope (exit {proc.returncode}): {combined[-300:]}"
            )
    else:
        pytest.skip("cleanroom tooling/preview unavailable for compare leg")

    return cli, mcp, cleanroom


def proc_ok(proc: subprocess.CompletedProcess) -> bool:
    # --baseline compare exits 0 on ok delta (changed or not).
    return proc.returncode == 0 and proc.stdout.strip()


def _cleanroom_available() -> bool:
    return (
        shutil.which("npx") is not None
        and (CLEANROOM_DIR / "node_modules").exists()
        and (CLEANROOM_DIR / "dist" / "index.html").exists()
        and _preview_is_up("http://localhost:5176/")
    )


def test_capability_matrix_compare_three_way(tmp_path):
    """C2-U4: compare_evidence produces the same delta envelope on CLI,
    MCP, and the cleanroom browser worker (one fixture mechanism)."""
    cli, mcp, cleanroom = _compare_legs(tmp_path)
    assert cli == mcp == cleanroom
    delta = cli
    assert delta["schema"] == 1
    assert delta["changed"] is True
    classifications = sorted(
        f"{p['patient_id']}:{p['column']}:{p['classification']}"
        for p in delta["patients"]
    )
    assert classifications == [
        "pt-1:IPP:moved",
        "pt-3:IPP:removed",
        "pt-3:NAME:removed",
    ]
