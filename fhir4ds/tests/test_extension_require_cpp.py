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


class TestLoadFailureIsFatalUnderRequireCpp:
    """D10-EXPLORER (v0.0.26): the flag must ALSO be honoured when a bundle is
    PRESENT but cannot be loaded — a corrupt/truncated binary or a failed
    staging step previously logged a warning and silently returned False even
    with FHIR4DS_REQUIRE_CPP=1, so strict-mode jobs ran on the fallback."""

    def _force_suffix_staging(self, monkeypatch):
        # Route the fhirpath loader through the suffix-staging branch on any
        # host (the 2.0 slot always carries a version-suffixed filename).
        monkeypatch.setattr(duckdb, "__version__", "2.0.0")

    def test_corrupt_bundle_load_failure_is_fatal(self, monkeypatch, tmp_path):
        import fhir4ds
        import fhir4ds.fhirpath.duckdb.extension as fp_ext

        self._force_suffix_staging(monkeypatch)
        truncated = tmp_path / "fhirpath.duckdb_extension"
        truncated.write_bytes(b"not-a-real-binary")
        monkeypatch.setattr(fp_ext, "_staged_load_path", lambda _p: truncated)
        monkeypatch.setenv("FHIR4DS_REQUIRE_CPP", "1")
        con = duckdb.connect(config={"allow_unsigned_extensions": True})
        with pytest.raises(RuntimeError, match="failed to load bundled C\\+\\+ extension"):
            fhir4ds.register(con)

    def test_corrupt_bundle_load_failure_falls_back_without_flag(
        self, monkeypatch, tmp_path
    ):
        import fhir4ds
        import fhir4ds.fhirpath.duckdb.extension as fp_ext

        self._force_suffix_staging(monkeypatch)
        truncated = tmp_path / "fhirpath.duckdb_extension"
        truncated.write_bytes(b"not-a-real-binary")
        monkeypatch.setattr(fp_ext, "_staged_load_path", lambda _p: truncated)
        monkeypatch.delenv("FHIR4DS_REQUIRE_CPP", raising=False)
        con = duckdb.connect(config={"allow_unsigned_extensions": True})
        result = fhir4ds.register(con)
        assert result["fhirpath_cpp"] is False

    def test_staging_failure_is_fatal(self, monkeypatch):
        import fhir4ds
        import fhir4ds.fhirpath.duckdb.extension as fp_ext

        self._force_suffix_staging(monkeypatch)

        def _boom(_path):
            raise OSError("read-only cache dir")

        monkeypatch.setattr(fp_ext, "_staged_load_path", _boom)
        monkeypatch.setenv("FHIR4DS_REQUIRE_CPP", "1")
        con = duckdb.connect(config={"allow_unsigned_extensions": True})
        with pytest.raises(RuntimeError, match="failed to stage"):
            fhir4ds.register(con)

    def test_staging_failure_falls_back_without_flag(self, monkeypatch):
        import fhir4ds
        import fhir4ds.fhirpath.duckdb.extension as fp_ext

        self._force_suffix_staging(monkeypatch)

        def _boom(_path):
            raise OSError("read-only cache dir")

        monkeypatch.setattr(fp_ext, "_staged_load_path", _boom)
        monkeypatch.delenv("FHIR4DS_REQUIRE_CPP", raising=False)
        con = duckdb.connect(config={"allow_unsigned_extensions": True})
        result = fhir4ds.register(con)
        assert result["fhirpath_cpp"] is False
