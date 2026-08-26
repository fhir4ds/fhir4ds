"""QA-014: evaluate_measure pre-flight UDF registration guard (0.0.12 campaign)."""

from __future__ import annotations

import duckdb
import pytest

from fhir4ds.cql import evaluate_measure

_CQL = (
    "library D version '1.0.0'\n"
    "using FHIR version '4.0.1'\n"
    "context Patient\n"
    "define \"Born\": exists(Patient.birthDate)\n"
)


@pytest.fixture
def library(tmp_path):
    lib = tmp_path / "D.cql"
    lib.write_text(_CQL)
    return str(lib)


def _bare_connection_with_resources():
    con = duckdb.connect(":memory:")
    con.execute(
        "CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, "
        "resource JSON, patient_ref VARCHAR)"
    )
    return con


def test_bare_connection_catalog_error_doctrine(library):
    """Adjudicated doctrine: bare connections are supported; missing-UDF
    catalog errors surface raw (see test_input_validation
    .test_evaluate_measure_missing_udf_catalog_error_is_not_rewritten)."""
    con = _bare_connection_with_resources()
    with pytest.raises(duckdb.CatalogException):
        evaluate_measure(library, conn=con, output_columns={"Born": "Born"})


def test_closed_connection_error_preserved(library):
    con = _bare_connection_with_resources()
    con.close()
    with pytest.raises(duckdb.ConnectionException, match="closed"):
        evaluate_measure(library, conn=con, output_columns={"Born": "Born"})


def test_registered_connection_still_evaluates(library):
    import fhir4ds
    from fhir4ds.cql.loader.fhir_loader import FHIRDataLoader

    con = fhir4ds.create_connection()
    FHIRDataLoader(con).load_resource(
        {"resourceType": "Patient", "id": "p1", "birthDate": "1990-01-01"}
    )
    df = evaluate_measure(library, conn=con, output_columns={"Born": "Born"})
    assert len(df) == 1 and bool(df["Born"].iloc[0])


# --- QA-015/QA-016: user-input boundary validation (0.0.12 campaign) ---

def test_unknown_output_definition_raises_value_error(library):
    import duckdb as _db

    con = fhir4ds_conn()
    with pytest.raises(ValueError, match="NoSuchDef"):
        evaluate_measure(library, conn=con, output_columns={"x": "NoSuchDef"})


def test_unknown_parameter_name_raises_type_error(library):
    con = fhir4ds_conn()
    with pytest.raises(TypeError, match="not declared"):
        evaluate_measure(
            library, conn=con,
            output_columns={"Born": "Born"},
            parameters={"Typo": 1},
        )


def fhir4ds_conn():
    import fhir4ds
    return fhir4ds.create_connection()


def test_parameters_type_guard(library):
    """QA-019: parameters must be a dict (typed error, not AttributeError)."""
    con = fhir4ds_conn()
    with pytest.raises(TypeError, match="parameters must be a dict"):
        evaluate_measure(library, conn=con, parameters="not-a-dict")
