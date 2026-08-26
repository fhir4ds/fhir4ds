"""Parity tests for FHIRPath extension() handling in DuckDB UDFs."""

from __future__ import annotations

import json

import duckdb

from fhir4ds.fhirpath.duckdb import register_fhirpath
from fhir4ds.fhirpath.duckdb.udf import fhirpath_json_udf, fhirpath_scalar, fhirpath_text_udf


def _connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register_fhirpath(con)
    return con


def test_standalone_extension_value_matches_python_fallback() -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "extension": [
                {
                    "url": "u",
                    "valueString": "x",
                }
            ],
        }
    )
    expression = "extension('u').value"

    con = _connection()
    try:
        cpp = con.execute(
            "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?)",
            [resource, expression, resource, expression, resource, expression],
        ).fetchone()
        py = (
            fhirpath_scalar(resource, expression),
            fhirpath_text_udf(resource, expression),
            fhirpath_json_udf(resource, expression),
        )
        assert cpp == py
        assert cpp == (["x"], "x", '["x"]')
    finally:
        con.close()


def test_unsigned_bundled_extension_falls_back_with_warning(caplog) -> None:
    """SOF-VD-11 QA-001 regression.

    ``allow_unsigned_extensions`` cannot be enabled after the database is
    running, so a plain ``duckdb.connect()`` must fall back to the Python
    UDFs (not error) and surface an actionable warning naming the connect
    config. The old code attempted a ``SET allow_unsigned_extensions``
    retry that DuckDB always rejects mid-session (dead branch).
    """
    import logging
    from pathlib import Path

    import fhir4ds.fhirpath.duckdb.extension as ext_module

    bundled = (
        Path(ext_module.__file__).parent / "extensions" / "fhirpath.duckdb_extension"
    )
    if not bundled.exists() or not duckdb.__version__.startswith("1.5."):
        import pytest

        pytest.skip("bundled unsigned C++ extension not present for this build")

    con = duckdb.connect()  # deliberately WITHOUT allow_unsigned_extensions
    try:
        with caplog.at_level(logging.WARNING, logger=ext_module._logger.name):
            native_active = ext_module.register_fhirpath(con)
        assert native_active is False
        # Python fallback UDFs must be registered and functional.
        assert con.execute(
            "SELECT fhirpath('{\"resourceType\":\"Patient\",\"id\":\"1\"}', 'id')"
        ).fetchone() == (["1"],)
        warning_text = " ".join(r.message for r in caplog.records)
        assert "allow_unsigned_extensions" in warning_text
        # No dead mid-session SET is attempted: the connection remains usable
        # and the extension was not half-loaded.
        assert not ext_module._is_cpp_extension_loaded(con)
    finally:
        con.close()
