"""End-to-end smoke test for the ``fhir4ds-serve`` container.

Not a pytest module on purpose: it needs a working Docker daemon and a few
minutes, which unit runs must not depend on. Run it directly:

    python3 fhir4ds/serve/tests/container_smoke.py            # build + run
    python3 fhir4ds/serve/tests/container_smoke.py --no-build # reuse the image

It builds the image from the repository root, runs it against the committed
fixtures mounted at ``/data``, and exercises every surface the container is
supposed to serve:

* ``GET /health`` and ``GET /metadata`` (both operations plus ``$cql``);
* ``POST /Library`` + ``GET /Library/{id}`` round-trip;
* ``POST /Library/{id}/$sqlquery-run`` in ndjson, csv, fhir and with ``_limit``;
* ``POST /ViewDefinition/$run`` (inline ViewDefinition);
* ``POST /fhir/$cql`` (the conformance facade);
* one required-parameter 400, and the ``hf://`` dataset source answer;
* ``docker stop`` shutdown (SIGTERM) with a clean exit code;
* ``docker history`` carrying no token.

Exit code 0 means every check passed; the transcript goes to stdout.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
FIXTURES = REPO_ROOT / "fhir4ds" / "serve" / "tests" / "fixtures"

CHECKS: list[tuple[str, bool, str]] = []


def say(message: str) -> None:
    print(message, flush=True)


def check(name: str, passed: bool, detail: str = "") -> bool:
    CHECKS.append((name, passed, detail))
    say(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return passed


def docker(*args: str, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *args],
        capture_output=capture,
        text=True,
        check=False,
    )


def build(image: str) -> bool:
    say(f"== docker build -f deploy/docker/fhir4ds-serve/Dockerfile -t {image} .")
    result = docker(
        "build",
        "-f",
        "deploy/docker/fhir4ds-serve/Dockerfile",
        "-t",
        image,
        ".",
        capture=False,
    )
    return check("image builds", result.returncode == 0, f"exit {result.returncode}")


def start(image: str, name: str, port: int, data: pathlib.Path) -> bool:
    docker("rm", "-f", name)
    say(f"== docker run -p {port}:7860 -v {data}:/data:ro {image}")
    result = docker(
        "run",
        "-d",
        "--name",
        name,
        "-p",
        f"{port}:7860",
        "-v",
        f"{data}:/data:ro",
        image,
        "python",
        "-m",
        "fhir4ds.serve",
        "--host",
        "0.0.0.0",
        "--port",
        "7860",
        "--data-root",
        "/data",
        "--resources",
        "/data",
        "--log-config",
        "/app/uvicorn-log.json",
    )
    if result.returncode != 0:
        return check("container starts", False, result.stderr.strip()[:300])
    check("container starts", True, result.stdout.strip()[:12])
    return True


def wait_for_health(base: str, timeout: float = 180.0) -> bool:
    say(f"== waiting for {base}/health")
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base}/health", timeout=5) as response:
                if response.status == 200:
                    return check("health is up", True, json.loads(response.read())["status"])
        except Exception as exc:  # noqa: BLE001 - poll until the deadline
            last = str(exc)
        time.sleep(2)
    return check("health is up", False, last[:200])


def call(base: str, path: str, body: dict | None = None, accept: str | None = None):
    """Call an endpoint; return (status, headers, body bytes)."""
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/fhir+json"}
    if accept:
        headers["Accept"] = accept
    request = urllib.request.Request(
        f"{base}{path}", data=data, headers=headers, method="POST" if data else "GET"
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()


def parameters(*entries: dict) -> dict:
    return {"resourceType": "Parameters", "parameter": list(entries)}


#: Input parameters the SqlOnFhirExample Library declares (and requires).
SQLONFHIR_PARAMETERS = (
    ("patient_id", "Patient/pt-1"),
    ("from_date", "2024-01-01"),
    ("to_date", "2024-12-31"),
)


def run_body(*extras: dict, values: tuple[tuple[str, str], ...] = SQLONFHIR_PARAMETERS) -> dict:
    """Build a ``$sqlquery-run`` body: operation parameters + nested values."""
    nested = {"resourceType": "Parameters", "parameter": [
        {"name": name, "valueString": value} for name, value in values
    ]}
    return parameters(*extras, {"name": "parameters", "resource": nested})


def run_checks(base: str) -> None:
    say("== GET /health")
    status, _, body = call(base, "/health")
    health = json.loads(body)
    check(
        "health 200",
        status == 200 and health.get("status") == "ok",
        json.dumps(health)[:120],
    )

    say("== GET /metadata")
    status, _, body = call(base, "/metadata")
    document = json.loads(body)
    resources = {entry["type"]: entry for entry in document["rest"][0]["resource"]}
    operations = {
        name: {op["name"] for op in resources[name]["operation"]}
        for name in resources
    }
    check("metadata fhirVersion 4.0.1", document["fhirVersion"] == "4.0.1")
    check("metadata Library sqlquery-run", "sqlquery-run" in operations.get("Library", set()))
    check(
        "metadata ViewDefinition run",
        "run" in operations.get("ViewDefinition", set()),
    )
    system_operations = {op["name"] for op in document["rest"][0].get("operation", [])}
    check("metadata system cql", "cql" in system_operations, str(sorted(system_operations)))

    # Seed the registries from the fixtures.
    viewdefinition = json.loads((FIXTURES / "viewdefinitions" / "patient-view.json").read_text())
    library = json.loads(
        (FIXTURES / "libraries" / "Library-SqlOnFhirExample.json").read_text()
    )
    blood_pressure = json.loads(
        (FIXTURES / "libraries" / "Library-BloodPressureViewSqlView.json").read_text()
    )

    say("== POST /ViewDefinition, POST /Library")
    for resource in (viewdefinition, blood_pressure, library):
        status, _, body = call(base, f"/{resource['resourceType']}", resource)
        if not check(f"POST /{resource['resourceType']} {resource['id']}", status in (200, 201), str(status)):
            say(body[:400].decode(errors="replace"))

    status, _, body = call(base, "/Library/SqlOnFhirExample")
    check("GET /Library/SqlOnFhirExample round-trip", status == 200 and b"SqlOnFhirExample" in body)

    say("== POST /Library/SqlOnFhirExample/$sqlquery-run (default ndjson)")
    status, headers, body = call(base, "/Library/SqlOnFhirExample/$sqlquery-run", run_body())
    rows = body.decode().strip().splitlines()
    check(
        "ndjson rows from mounted data",
        status == 200 and headers.get("content-type", "").startswith("application/x-ndjson") and len(rows) == 2,
        f"{status}, {len(rows)} rows",
    )

    say("== _format=csv")
    status, headers, body = call(
        base, "/Library/SqlOnFhirExample/$sqlquery-run",
        run_body({"name": "_format", "valueCode": "csv"}),
    )
    check(
        "csv header + rows",
        status == 200
        and headers.get("content-type", "").startswith("text/csv")
        and body.decode().splitlines()[0].startswith("patient_id,"),
        body.decode().splitlines()[0][:60] if body else "",
    )

    say("== _format=fhir")
    status, _, body = call(
        base, "/Library/SqlOnFhirExample/$sqlquery-run",
        run_body({"name": "_format", "valueCode": "fhir"}),
    )
    document = json.loads(body)
    check(
        "fhir Parameters row/part",
        status == 200
        and document["resourceType"] == "Parameters"
        and document["parameter"][0]["name"] == "row"
        and document["parameter"][0]["part"][0]["name"] == "patient_id",
    )

    say("== _limit=1")
    status, _, body = call(
        base, "/Library/SqlOnFhirExample/$sqlquery-run",
        run_body({"name": "_limit", "valueInteger": 1}),
    )
    check("_limit caps rows", status == 200 and len(body.decode().strip().splitlines()) == 1)

    say("== POST /ViewDefinition/$run (inline)")
    status, _, body = call(
        base,
        "/ViewDefinition/$run",
        parameters({"name": "viewResource", "resource": viewdefinition}),
    )
    check("inline ViewDefinition runs", status == 200 and b"Smith" in body, str(status))

    say("== POST /fhir/$cql")
    status, headers, body = call(
        base,
        "/fhir/$cql",
        parameters({"name": "expression", "valueString": "1 + 1"}),
    )
    document = json.loads(body)
    check(
        "cql facade evaluates",
        status == 200
        and headers.get("content-type", "").startswith("application/fhir+json")
        and document["parameter"][0]["valueInteger"] == 2,
        json.dumps(document)[:120],
    )

    say("== 400 case: missing required parameter")
    status, _, body = call(
        base,
        "/Library/SqlOnFhirExample/$sqlquery-run",
        run_body(values=(("patient_id", "Patient/pt-1"), ("to_date", "2024-12-31"))),
    )
    document = json.loads(body)
    check(
        "missing parameter is 400 OperationOutcome",
        status == 400 and document["resourceType"] == "OperationOutcome",
        json.dumps(document)[:160],
    )

    say("== source=hf://datasets/fhir4ds/bulk-publish-demo-data")
    status, _, body = call(
        base,
        "/ViewDefinition/patient-view/$run",
        parameters(
            {"name": "source", "valueString": "hf://datasets/fhir4ds/bulk-publish-demo-data"}
        ),
    )
    document = json.loads(body)
    diagnostics = document.get("issue", [{}])[0].get("diagnostics", "")
    check(
        "hf:// answered with a clear OperationOutcome",
        status == 400 and document["resourceType"] == "OperationOutcome" and "phase 3" in diagnostics,
        f"{status}: {diagnostics[:120]}",
    )
    status, _, _ = call(base, "/health")
    check("server survives the hf:// source", status == 200)


def stop_and_inspect(name: str, image: str) -> None:
    say("== docker stop (SIGTERM)")
    started = time.time()
    result = docker("stop", "-t", "20", name)
    elapsed = round(time.time() - started, 1)
    check("docker stop returns", result.returncode == 0, f"{elapsed}s")

    inspect = docker("inspect", "--format", "{{.State.ExitCode}}", name)
    check("uvicorn exits cleanly (code 0)", inspect.stdout.strip() == "0", inspect.stdout.strip())

    logs = docker("logs", name)
    check(
        "uvicorn logs go to stdout",
        "Uvicorn running on http://" in logs.stdout,
        "uvicorn startup line on stdout",
    )

    history = docker("history", "--no-trunc", image)
    check("image history carries no token", "token" not in history.stdout.lower())

    docker("rm", "-f", name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="fhir4ds-serve:phase2")
    parser.add_argument("--name", default="fhir4ds-serve-smoke")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--no-build", action="store_true")
    parser.add_argument("--keep", action="store_true", help="leave the container running")
    args = parser.parse_args()

    base = f"http://127.0.0.1:{args.port}"

    if not args.no_build and not build(args.image):
        return 1
    if not start(args.image, args.name, args.port, FIXTURES / "resources"):
        return 1
    try:
        if not wait_for_health(base):
            say("== container logs")
            say(docker("logs", args.name).stdout[-3000:])
            return 1
        run_checks(base)
    finally:
        if not args.keep:
            stop_and_inspect(args.name, args.image)

    failures = [name for name, passed, _ in CHECKS if not passed]
    say("")
    say(f"== {len(CHECKS) - len(failures)}/{len(CHECKS)} checks passed")
    if failures:
        say("failed: " + ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
