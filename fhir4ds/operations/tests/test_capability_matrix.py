"""Capability-matrix test: CLI subprocess vs in-process MCP client (FDD §3.8).

Asserts identical normalized envelopes for run_tests on the shared
fixture. The studio leg is added when the studio lands without changing
this fixture.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import subprocess
import sys
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
