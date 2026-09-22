"""MCP server tool tests via in-process tool-manager calls (U6)."""

from __future__ import annotations

import asyncio
import contextlib
import io

import pytest

pytest.importorskip("mcp")

from fhir4ds.mcp.server import build_server
from fhir4ds.operations.tests.fixtures import (
    MATRIX_CASES,
    MATRIX_LIBRARY,
    MATRIX_OUTPUT_COLUMNS,
    MATRIX_RESOURCES,
)


def _call(server, tool, **arguments):
    async def run():
        return await server._tool_manager.call_tool(tool, arguments=arguments)

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        return asyncio.run(run())


@pytest.fixture()
def server():
    return build_server()


def test_parse_tool(server):
    r = _call(server, "parse_cql_tool", cql_text=MATRIX_LIBRARY)
    assert r["ok"] and r["library_name"] == "MatrixSimple"


def test_translate_tool_uses_bundled_fhirhelpers(server):
    r = _call(
        server, "translate_cql_tool",
        libraries=[{"name": "MatrixSimple", "text": MATRIX_LIBRARY}],
    )
    assert r["ok"] and r["sql"].upper().startswith("WITH")


def test_run_tests_tool_envelope(server):
    r = _call(
        server, "run_tests_tool",
        libraries=[{"name": "MatrixSimple", "text": MATRIX_LIBRARY}],
        dataset={"resources": MATRIX_RESOURCES},
        cases=MATRIX_CASES,
        output_columns=MATRIX_OUTPUT_COLUMNS,
    )
    assert r["schema"] == 1 and r["ok"] is True and r["passed"] is False
    assert r["tests"]["failures"][0]["patient"] == "pt-9"


def test_include_cache_session_continuity(server):
    """Libraries sent once are referenceable by name later (adapter cache)."""
    _call(server, "translate_cql_tool",
          libraries=[{"name": "MatrixSimple", "text": MATRIX_LIBRARY}])
    main_only = [{"name": "MatrixSimple2",
                  "text": MATRIX_LIBRARY.replace("MatrixSimple", "MatrixSimple2")}]
    r = _call(server, "translate_cql_tool", libraries=main_only, main="MatrixSimple2")
    assert r["ok"]  # FHIRHelpers still resolvable (bundled tier, not cache)


def test_missing_main_library_is_not_found(server):
    with pytest.raises(Exception) as excinfo:
        _call(server, "translate_cql_tool",
              libraries=[{"name": "A", "text": "library A"}], main="B")
    assert "not_found" in str(excinfo.value) or "main library" in str(excinfo.value)


def test_unknown_dataset_handle_is_not_found(server):
    with pytest.raises(Exception) as excinfo:
        _call(server, "evaluate_library_tool",
              libraries=[{"name": "MatrixSimple", "text": MATRIX_LIBRARY}],
              dataset={"handle": "ds-nope"})
    assert "ds-nope" in str(excinfo.value)


def test_load_dataset_then_handle_reference(server):
    r = _call(server, "load_dataset_tool", dataset={"resources": MATRIX_RESOURCES})
    assert r["ok"] and r["resource_counts"] == {"Patient": 3}
    handle = r["handle"]
    r2 = _call(
        server, "run_tests_tool",
        libraries=[{"name": "MatrixSimple", "text": MATRIX_LIBRARY}],
        dataset={"handle": handle},
        cases={"schema": 1, "cases": [
            {"patient": "pt-1", "population": "Initial Population", "expect": True}]},
    )
    assert r2["passed"] is True


def test_fhirpath_tool(server):
    r = _call(server, "fhirpath_eval_tool",
              expression="name.given", resource=MATRIX_RESOURCES[0])
    assert r["ok"] and r["results"] == ["Alice"]


def test_explain_tool(server):
    r = _call(
        server, "explain_patient_tool",
        libraries=[{"name": "MatrixSimple", "text": MATRIX_LIBRARY}],
        dataset={"resources": MATRIX_RESOURCES},
        patient_id="pt-1",
        output_columns=MATRIX_OUTPUT_COLUMNS,
    )
    assert r["ok"] and r["populations"]["IPP"] is True


def test_oversized_inline_payload_rejected(server, monkeypatch):
    import fhir4ds.mcp.server as srv

    monkeypatch.setattr(srv, "_MAX_INLINE_BYTES", 100)
    big = [{"resourceType": "Patient", "id": f"p{i}", "notes": "x" * 200}
           for i in range(2)]
    with pytest.raises(Exception) as excinfo:
        _call(server, "load_dataset_tool", dataset={"resources": big})
    assert "NDJSON" in str(excinfo.value) or "5MB" in str(excinfo.value) or "exceeds" in str(excinfo.value)
