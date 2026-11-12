"""FHIR4DS_REQUIRE_CPP must be strict on BOTH failure shapes.

Iteration 17 / Domain 10 HISTORIAN. The flag documents itself as
"make this mismatch fatal", but it was only honoured when the bundled file for
a SUPPORTED DuckDB line was missing. On a wholly unsupported line
(`_bundled_extension_filename()` returns None) the loader logged at INFO and
silently degraded to the Python UDFs — so a CI/production job that set the flag
to guarantee the native engine could run entirely on the fallback.
"""
from __future__ import annotations

import duckdb
import pytest


@pytest.mark.parametrize("fake_version", ["1.4.2", "3.1.0"])
def test_unsupported_duckdb_line_is_fatal_under_require_cpp(monkeypatch, fake_version):
    import fhir4ds

    monkeypatch.setenv("FHIR4DS_REQUIRE_CPP", "1")
    monkeypatch.setattr(duckdb, "__version__", fake_version)
    con = duckdb.connect()
    with pytest.raises(RuntimeError, match="bundles binaries for the 1.5.x and 2.0.x lines"):
        fhir4ds.register(con)


@pytest.mark.parametrize("fake_version", ["1.4.2", "3.1.0"])
def test_unsupported_duckdb_line_still_falls_back_without_the_flag(monkeypatch, fake_version):
    import fhir4ds

    monkeypatch.delenv("FHIR4DS_REQUIRE_CPP", raising=False)
    monkeypatch.setattr(duckdb, "__version__", fake_version)
    con = duckdb.connect()
    assert fhir4ds.register(con) == {"fhirpath_cpp": False, "cql_cpp": False}
