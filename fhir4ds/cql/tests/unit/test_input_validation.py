"""Regression tests for QA-006/007/008 — None-safety on public API entry points."""

import pytest


def test_parse_cql_rejects_non_string():
    from fhir4ds.cql import parse_cql

    with pytest.raises(TypeError, match="cql_text must be a string"):
        parse_cql(None)


def test_parse_cql_rejects_empty_string():
    from fhir4ds.cql import parse_cql

    with pytest.raises(ValueError, match="non-empty string"):
        parse_cql("   ")


# ---------------------------------------------------------------------------
# QA-007: evaluate_measure(conn=None) must raise TypeError
# ---------------------------------------------------------------------------

def test_evaluate_measure_rejects_none_conn():
    """evaluate_measure must raise TypeError when conn is None (QA-007)."""
    from fhir4ds.cql import evaluate_measure

    with pytest.raises(TypeError, match="Expected a DuckDB connection for 'conn'"):
        evaluate_measure(library_path="dummy.cql", conn=None)


def test_evaluate_measure_wrapper_rejects_none_conn():
    """Top-level evaluate_measure wrapper must also reject conn=None (QA-007)."""
    from fhir4ds.measure import evaluate_measure

    with pytest.raises(TypeError, match="Expected a DuckDB connection for 'conn'"):
        evaluate_measure(library_path="dummy.cql", conn=None)


def test_evaluate_measure_rejects_invalid_audit_mode(tmp_path):
    import duckdb
    from fhir4ds.cql import evaluate_measure

    cql_file = tmp_path / "Measure.cql"
    cql_file.write_text("library Measure\nusing FHIR version '4.0.1'\ncontext Patient\ndefine IP: true")
    con = duckdb.connect()
    try:
        with pytest.raises(ValueError, match="audit_mode must be one of"):
            evaluate_measure(str(cql_file), con, audit_mode="invalid")
    finally:
        con.close()


def test_evaluate_measure_rejects_string_patient_ids(tmp_path):
    import duckdb
    from fhir4ds.cql import evaluate_measure

    cql_file = tmp_path / "Measure.cql"
    cql_file.write_text("library Measure\nusing FHIR version '4.0.1'\ncontext Patient\ndefine IP: true")
    con = duckdb.connect()
    try:
        with pytest.raises(TypeError, match="patient_ids must be a list"):
            evaluate_measure(str(cql_file), con, patient_ids="patient-1")
    finally:
        con.close()


def test_evaluate_measure_threads_audit_mode_to_translator(tmp_path, monkeypatch):
    import duckdb
    import fhir4ds.cql.translator as translator_module
    from fhir4ds.cql import evaluate_measure

    seen = {}

    class FakeTranslator:
        def __init__(self, **kwargs):
            seen.update(kwargs)

        def translate_library_to_population_sql(self, **kwargs):
            return "SELECT 'patient-1' AS patient_id"

    cql_file = tmp_path / "Measure.cql"
    cql_file.write_text("library Measure\nusing FHIR version '4.0.1'\ncontext Patient\ndefine IP: true")
    monkeypatch.setattr(translator_module, "CQLToSQLTranslator", FakeTranslator)

    con = duckdb.connect()
    try:
        result = evaluate_measure(str(cql_file), con, audit_mode="population")
    finally:
        con.close()

    assert seen["audit_mode"] is True
    assert seen["audit_expressions"] is False
    assert result["patient_id"].tolist() == ["patient-1"]


def test_evaluate_measure_missing_udf_catalog_error_is_not_rewritten(tmp_path, monkeypatch):
    import duckdb
    import fhir4ds.cql.translator as translator_module
    from fhir4ds.cql import evaluate_measure

    class FakeTranslator:
        def __init__(self, **kwargs):
            pass

        def translate_library_to_population_sql(self, **kwargs):
            return "SELECT in_valueset(resource, 'code', 'http://example.org/vs') FROM resources"

    cql_file = tmp_path / "Measure.cql"
    cql_file.write_text("library Measure\nusing FHIR version '4.0.1'\ncontext Patient\ndefine IP: true")
    monkeypatch.setattr(translator_module, "CQLToSQLTranslator", FakeTranslator)

    con = duckdb.connect()
    try:
        con.execute("CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR)")
        with pytest.raises(duckdb.CatalogException, match="in_valueset"):
            evaluate_measure(str(cql_file), con)
    finally:
        con.close()


# ---------------------------------------------------------------------------
# QA-008: register(None) must raise TypeError
# ---------------------------------------------------------------------------

def test_register_rejects_none_con():
    """register must raise TypeError when con is None (QA-008)."""
    from fhir4ds.core import register

    with pytest.raises(TypeError, match="Expected a DuckDB connection for 'con'"):
        register(None)
