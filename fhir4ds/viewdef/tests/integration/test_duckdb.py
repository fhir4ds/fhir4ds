"""
Integration tests for sqlonfhirpy with duckdb-fhirpath extension.

These tests verify the end-to-end flow:
1. Parse ViewDefinitions using sqlonfhirpy
2. Generate SQL queries
3. Execute queries against DuckDB with the fhirpath extension
4. Verify results match expected output
"""

import datetime
import json
import pytest
import sys
from pathlib import Path

# Add parent package paths for imports

import duckdb
from fhir4ds.fhirpath.duckdb import register_fhirpath
from ...parser import parse_view_definition
from ...generator import SQLGenerator
from ...errors import ValidationError
from ...types import ColumnType, JoinType
from ...metadata import SHAREABLE_VIEWDEFINITION_PROFILE, VIEWDEFINITION_RESOURCE_TYPE


@pytest.fixture
def connection():
    """Create a DuckDB in-memory connection with FHIRPath extension registered."""
    con = duckdb.connect()
    register_fhirpath(con)
    yield con
    con.close()


@pytest.fixture
def generator():
    """Create a SQL generator instance."""
    return SQLGenerator()


def _forced_python_connection(monkeypatch):
    """Create a DuckDB connection that bypasses the bundled C++ extension."""
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(con) is False
    return con


def _execute_view(con, view, resources):
    vd = parse_view_definition(view)
    sql = SQLGenerator().generate(vd)
    con.execute("CREATE TABLE patients (resource JSON)")
    for resource in resources:
        con.execute("INSERT INTO patients VALUES (?)", [json.dumps(resource)])
    return con.execute(sql).fetchall()


def _execute_shared_view(con, view, resources):
    vd = parse_view_definition(view)
    sql = SQLGenerator(source_table="resources").generate(vd)
    con.execute("CREATE OR REPLACE TABLE resources (resource JSON)")
    for resource in resources:
        con.execute("INSERT INTO resources VALUES (?)", [json.dumps(resource)])
    return con.execute(sql).fetchall()


def _execute_shared_view_json(con, view, resource_jsons):
    vd = parse_view_definition(view)
    sql = SQLGenerator(source_table="resources").generate(vd)
    con.execute("CREATE OR REPLACE TABLE resources (resource JSON)")
    for resource_json in resource_jsons:
        con.execute("INSERT INTO resources VALUES (?::JSON)", [resource_json])
    return con.execute(sql).fetchall()


def test_root_where_numeric_results_do_not_satisfy_boolean_true_native_and_fallback(monkeypatch):
    """SQL-on-FHIR where keeps only FHIRPath results that are exactly Boolean true."""
    view = {
        "resource": "Observation",
        "select": [{"column": [{"path": "id", "name": "id", "type": "id"}]}],
        "where": [{"path": "valueInteger"}],
    }
    resources = [
        {"resourceType": "Observation", "id": "one", "valueInteger": 1},
        {"resourceType": "Observation", "id": "zero", "valueInteger": 0},
        {"resourceType": "Observation", "id": "two", "valueInteger": 2},
        {"resourceType": "Observation", "id": "missing"},
    ]

    native = duckdb.connect(config={"allow_unsigned_extensions": True})
    if register_fhirpath(native) is not True:
        native.close()
        pytest.skip("native FHIRPath extension not available")
    fallback = _forced_python_connection(monkeypatch)
    try:
        assert _execute_shared_view(native, view, resources) == []
        assert _execute_shared_view(fallback, view, resources) == []
    finally:
        native.close()
        fallback.close()


def test_root_where_literal_one_does_not_satisfy_boolean_true_native_and_fallback(monkeypatch):
    """A valid non-Boolean FHIRPath literal is not a true where constraint."""
    view = {
        "resource": "Observation",
        "select": [{"column": [{"path": "id", "name": "id", "type": "id"}]}],
        "where": [{"path": "1"}],
    }
    resources = [
        {"resourceType": "Observation", "id": "one", "valueInteger": 1},
        {"resourceType": "Observation", "id": "zero", "valueInteger": 0},
    ]

    native = duckdb.connect(config={"allow_unsigned_extensions": True})
    if register_fhirpath(native) is not True:
        native.close()
        pytest.skip("native FHIRPath extension not available")
    fallback = _forced_python_connection(monkeypatch)
    try:
        assert _execute_shared_view(native, view, resources) == []
        assert _execute_shared_view(fallback, view, resources) == []
    finally:
        native.close()
        fallback.close()


def test_observation_decimal_column_quantity_value_native_and_fallback(monkeypatch):
    """Observation views can project Quantity.value as a decimal in both UDF paths."""
    view = {
        "resource": "Observation",
        "where": [{"path": "status = 'final'"}],
        "select": [
            {
                "column": [
                    {"path": "id", "name": "id", "type": "id"},
                    {"path": "valueQuantity.value", "name": "value", "type": "decimal"},
                ]
            }
        ],
    }
    resources = [
        {
            "resourceType": "Observation",
            "id": "bp",
            "status": "final",
            "valueQuantity": {
                "value": 120.5,
                "unit": "mmHg",
                "system": "http://unitsofmeasure.org",
                "code": "mm[Hg]",
            },
        },
        {
            "resourceType": "Observation",
            "id": "draft",
            "status": "preliminary",
            "valueQuantity": {"value": 80, "unit": "mmHg"},
        },
    ]

    native = duckdb.connect(config={"allow_unsigned_extensions": True})
    if register_fhirpath(native) is not True:
        native.close()
        pytest.skip("native FHIRPath extension not available")
    fallback = _forced_python_connection(monkeypatch)
    try:
        expected = [("bp", 120.5)]
        assert _execute_shared_view(native, view, resources) == expected
        assert _execute_shared_view(fallback, view, resources) == expected
    finally:
        native.close()
        fallback.close()


def test_official_boundary_decimal_runner_native_and_fallback(monkeypatch):
    """View Runner preserves JSON decimal precision for boundary functions."""
    resources = [
        {
            "resourceType": "Observation",
            "id": "o1",
            "status": "final",
            "valueQuantity": {"value": 1.0},
        },
        {"resourceType": "Observation", "id": "o2", "status": "final"},
    ]
    low_view = {
        "resource": "Observation",
        "select": [
            {
                "column": [
                    {"path": "id", "name": "id", "type": "id"},
                    {
                        "path": "value.ofType(Quantity).value.lowBoundary()",
                        "name": "decimal",
                        "type": "decimal",
                    },
                ]
            }
        ],
    }
    high_view = {
        "resource": "Observation",
        "select": [
            {
                "column": [
                    {"path": "id", "name": "id", "type": "id"},
                    {
                        "path": "value.ofType(Quantity).value.highBoundary()",
                        "name": "decimal",
                        "type": "decimal",
                    },
                ]
            }
        ],
    }

    native = duckdb.connect(config={"allow_unsigned_extensions": True})
    if register_fhirpath(native) is not True:
        native.close()
        pytest.skip("native FHIRPath extension not available")
    fallback = _forced_python_connection(monkeypatch)
    try:
        assert _execute_shared_view(native, low_view, resources) == [
            ("o1", 0.95),
            ("o2", None),
        ]
        assert _execute_shared_view(fallback, low_view, resources) == [
            ("o1", 0.95),
            ("o2", None),
        ]
        assert _execute_shared_view(native, high_view, resources) == [
            ("o1", 1.05),
            ("o2", None),
        ]
        assert _execute_shared_view(fallback, high_view, resources) == [
            ("o1", 1.05),
            ("o2", None),
        ]
    finally:
        native.close()
        fallback.close()


def test_official_boundary_temporal_and_root_where_runner_native_and_fallback(monkeypatch):
    """View Runner keeps native/fallback parity for typed boundaries and root where()."""
    resources = [
        {"resourceType": "Observation", "id": "dt", "valueDateTime": "2010-10-10"},
        {"resourceType": "Observation", "id": "tm", "valueTime": "12:34"},
        {"resourceType": "Observation", "id": "int12", "valueInteger": 12},
        {"resourceType": "Observation", "id": "int10", "valueInteger": 10},
        {"resourceType": "Patient", "id": "p1", "birthDate": "1970-06"},
    ]
    views = [
        (
            {
                "resource": "Observation",
                "select": [
                    {
                        "column": [
                            {"path": "id", "name": "id", "type": "id"},
                            {
                                "path": "value.ofType(dateTime).lowBoundary()",
                                "name": "datetime",
                                "type": "dateTime",
                            },
                        ]
                    }
                ],
            },
            [
                ("dt", "2010-10-10T00:00:00.000+14:00"),
                ("tm", None),
                ("int12", None),
                ("int10", None),
            ],
        ),
        (
            {
                "resource": "Observation",
                "select": [
                    {
                        "column": [
                            {"path": "id", "name": "id", "type": "id"},
                            {
                                "path": "value.ofType(time).highBoundary()",
                                "name": "time",
                                "type": "time",
                            },
                        ]
                    }
                ],
            },
            [("dt", None), ("tm", "12:34:59.999"), ("int12", None), ("int10", None)],
        ),
        (
            {
                "resource": "Patient",
                "select": [
                    {
                        "column": [
                            {"path": "id", "name": "id", "type": "id"},
                            {"path": "birthDate.lowBoundary()", "name": "date", "type": "date"},
                        ]
                    }
                ],
            },
            [("p1", "1970-06-01")],
        ),
        (
            {
                "resource": "Observation",
                "select": [{"column": [{"path": "id", "name": "id", "type": "id"}]}],
                "where": [{"path": "where(value.ofType(integer) > 11).exists()"}],
            },
            [("int12",)],
        ),
    ]

    native = duckdb.connect(config={"allow_unsigned_extensions": True})
    if register_fhirpath(native) is not True:
        native.close()
        pytest.skip("native FHIRPath extension not available")
    fallback = _forced_python_connection(monkeypatch)
    try:
        for view, expected in views:
            assert _execute_shared_view(native, view, resources) == expected
            assert _execute_shared_view(fallback, view, resources) == expected
    finally:
        native.close()
        fallback.close()


def test_expression_valued_non_primitive_column_type_errors_native_and_fallback(monkeypatch):
    """Non-primitive expression results require matching column.type declarations."""
    resources = [
        {
            "resourceType": "Observation",
            "id": "obs-1",
            "status": "final",
            "code": {
                "coding": [
                    {"system": "http://loinc.org", "code": "1234-5"},
                    {"system": "http://snomed.info/sct", "code": "67890"},
                ]
            },
        }
    ]
    untyped_view = {
        "resource": "Observation",
        "select": [
            {
                "column": [
                    {
                        "path": "code.coding.where(system = 'http://loinc.org')",
                        "name": "coding",
                    }
                ]
            }
        ],
    }
    declared_string_view = {
        "resource": "Observation",
        "select": [
            {
                "column": [
                    {
                        "path": "code.coding.where(system = 'http://loinc.org')",
                        "name": "coding",
                        "type": "string",
                    }
                ]
            }
        ],
    }

    native = duckdb.connect(config={"allow_unsigned_extensions": True})
    if register_fhirpath(native) is not True:
        native.close()
        pytest.skip("native FHIRPath extension not available")
    fallback = _forced_python_connection(monkeypatch)
    try:
        for con in (native, fallback):
            with pytest.raises(Exception, match="non-primitive outputs require column.type"):
                _execute_shared_view(con, untyped_view, resources)
            with pytest.raises(Exception, match="declared type string"):
                _execute_shared_view(con, declared_string_view, resources)
    finally:
        native.close()
        fallback.close()


def test_view_runner_resource_and_reference_keys_native_and_fallback(monkeypatch):
    """SQL-on-FHIR View Runner key helpers work in native and fallback UDFs."""
    view = {
        "resource": "Observation",
        "select": [
            {
                "column": [
                    {"path": "getResourceKey()", "name": "observation_key", "type": "string"},
                    {
                        "path": "subject.getReferenceKey(Patient)",
                        "name": "patient_key",
                        "type": "string",
                    },
                    {
                        "path": "subject.getReferenceKey(Observation)",
                        "name": "wrong_type_key",
                        "type": "string",
                    },
                ]
            }
        ],
    }
    resources = [
        {
            "resourceType": "Observation",
            "id": "obs-1",
            "status": "final",
            "subject": {"reference": "Patient/pat-1"},
        }
    ]

    native = duckdb.connect(config={"allow_unsigned_extensions": True})
    if register_fhirpath(native) is not True:
        native.close()
        pytest.skip("native FHIRPath extension not available")
    fallback = _forced_python_connection(monkeypatch)
    try:
        expected = [("Observation/obs-1", "Patient/pat-1", None)]
        assert _execute_shared_view(native, view, resources) == expected
        assert _execute_shared_view(fallback, view, resources) == expected
    finally:
        native.close()
        fallback.close()


def test_shareable_metadata_does_not_change_execution_native_and_fallback(monkeypatch):
    """Canonical metadata/profile fields are retained but ignored by SQL execution."""
    view = {
        "resourceType": VIEWDEFINITION_RESOURCE_TYPE,
        "id": "ShareablePatient",
        "meta": {"profile": [SHAREABLE_VIEWDEFINITION_PROFILE]},
        "url": "https://example.org/ViewDefinition/shareable-patient",
        "version": "1.0.0",
        "name": "shareable_patient",
        "status": "draft",
        "fhirVersion": ["4.0"],
        "resource": "Patient",
        "select": [
            {
                "column": [
                    {"path": "getResourceKey()", "name": "patient_key", "type": "string"},
                    {"path": "gender", "name": "gender", "type": "code"},
                ]
            }
        ],
    }
    resources = [{"resourceType": "Patient", "id": "pat-1", "gender": "female"}]

    native = duckdb.connect(config={"allow_unsigned_extensions": True})
    if register_fhirpath(native) is not True:
        native.close()
        pytest.skip("native FHIRPath extension not available")
    fallback = _forced_python_connection(monkeypatch)
    try:
        vd = parse_view_definition(view)
        assert vd.to_dict()["url"] == view["url"]
        expected = [("Patient/pat-1", "female")]
        assert _execute_shared_view(native, vd.to_dict(), resources) == expected
        assert _execute_shared_view(fallback, vd.to_dict(), resources) == expected
    finally:
        native.close()
        fallback.close()


class TestSimplePatientView:
    """Test simple patient view with columns."""

    def test_basic_columns(self, connection, generator):
        """Test extracting basic patient columns."""
        # Create test data
        patient = {
            "resourceType": "Patient",
            "id": "patient-123",
            "gender": "male",
            "active": True
        }
        connection.execute("CREATE TABLE patients (resource JSON)")
        connection.execute("INSERT INTO patients VALUES (?)", [json.dumps(patient)])

        # Generate SQL from ViewDefinition
        vd_json = json.dumps({
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "id", "name": "pid"},
                    {"path": "gender", "name": "gender"}
                ]
            }]
        })
        vd = parse_view_definition(vd_json)
        sql = generator.generate(vd)

        # Execute and verify
        result = connection.execute(sql).fetchall()
        assert len(result) == 1
        assert result[0][0] == "patient-123"  # pid
        assert result[0][1] == "male"  # gender

    def test_multiple_patients(self, connection, generator):
        """Test with multiple patient records."""
        # Create test data
        patients = [
            {"resourceType": "Patient", "id": f"patient-{i}", "gender": "male" if i % 2 == 0 else "female"}
            for i in range(5)
        ]
        connection.execute("CREATE TABLE patients (resource JSON)")
        for p in patients:
            connection.execute("INSERT INTO patients VALUES (?)", [json.dumps(p)])

        # Generate SQL
        vd_json = json.dumps({
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "id", "name": "pid"},
                    {"path": "gender", "name": "gender"}
                ]
            }]
        })
        vd = parse_view_definition(vd_json)
        sql = generator.generate(vd)

        # Execute and verify
        result = connection.execute(sql).fetchall()
        assert len(result) == 5
        ids = [row[0] for row in result]
        assert "patient-0" in ids
        assert "patient-4" in ids

    def test_typed_columns(self, connection, generator):
        """Test columns with type hints."""
        patient = {
            "resourceType": "Patient",
            "id": "patient-1",
            "birthDate": "1990-01-15"
        }
        connection.execute("CREATE TABLE patients (resource JSON)")
        connection.execute("INSERT INTO patients VALUES (?)", [json.dumps(patient)])

        vd_json = json.dumps({
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "id", "name": "pid", "type": "string"},
                    {"path": "birthDate", "name": "birth_date", "type": "date"}
                ]
            }]
        })
        vd = parse_view_definition(vd_json)
        sql = generator.generate(vd)

        result = connection.execute(sql).fetchall()
        assert len(result) == 1
        assert result[0][0] == "patient-1"
        # ViewDef type hints are not yet applied as SQL CASTs;
        # birthDate comes back as a string from fhirpath_text.
        assert result[0][1] == "1990-01-15"

    def test_constant_literal_boundaries_match_native_and_fallback(self, monkeypatch):
        """Constants are substituted only outside FHIRPath literals and escaped as FHIRPath."""
        patient = {
            "resourceType": "Patient",
            "id": "patient-1",
            "name": [{"family": "O'Reilly"}],
        }
        view = {
            "resource": "Patient",
            "constant": [
                {"name": "idx", "valueInteger": 1},
                {"name": "target", "valueString": "O'Reilly"},
            ],
            "select": [{
                "column": [
                    {"path": "'%idx'", "name": "literal", "type": "string"},
                    {
                        "path": "name.where(family = %target).family",
                        "name": "family",
                        "type": "string",
                    },
                ]
            }],
        }

        native = duckdb.connect(config={"allow_unsigned_extensions": True})
        if register_fhirpath(native) is not True:
            native.close()
            pytest.skip("Bundled C++ FHIRPath extension is not available")
        fallback = _forced_python_connection(monkeypatch)
        try:
            assert _execute_view(native, view, [patient]) == [("%idx", "O'Reilly")]
            assert _execute_view(fallback, view, [patient]) == [("%idx", "O'Reilly")]
        finally:
            native.close()
            fallback.close()

    def test_collection_true_output_matches_native_and_fallback(self, monkeypatch):
        """collection=true columns return multi-value list output in both backends."""
        patient = {
            "resourceType": "Patient",
            "id": "pt1",
            "name": [
                {"family": "Alpha", "given": ["A", "B"]},
                {"family": "Beta", "given": ["C"]},
            ],
        }
        view = {
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "id", "name": "id", "type": "id"},
                    {"path": "name.family", "name": "family", "type": "string", "collection": True},
                    {"path": "name.given", "name": "given", "type": "string", "collection": True},
                ]
            }],
        }

        native = duckdb.connect(config={"allow_unsigned_extensions": True})
        if register_fhirpath(native) is not True:
            native.close()
            pytest.skip("Bundled C++ FHIRPath extension is not available")
        fallback = _forced_python_connection(monkeypatch)
        try:
            expected = [("pt1", ["Alpha", "Beta"], ["A", "B", "C"])]
            assert sorted(_execute_shared_view(native, view, [patient])) == expected
            assert sorted(_execute_shared_view(fallback, view, [patient])) == expected
        finally:
            native.close()
            fallback.close()

    def test_primitive_typed_collection_output_matches_native_and_fallback(self, monkeypatch):
        """collection=true primitive type declarations preserve list element types."""
        observation = {
            "resourceType": "Observation",
            "id": "obs1",
            "active": True,
            "component": [
                {"valueInteger": 1, "interpretation": [{"coding": [{"code": "ok"}]}]},
                {"valueInteger": 2, "interpretation": [{"coding": [{"code": "bad"}]}]},
            ],
        }
        view = {
            "resource": "Observation",
            "select": [{
                "column": [
                    {"path": "id", "name": "id", "type": "id"},
                    {
                        "path": "component.value",
                        "name": "values",
                        "type": "http://hl7.org/fhir/StructureDefinition/integer",
                        "collection": True,
                    },
                    {
                        "path": "component.select(value.exists())",
                        "name": "has_interp",
                        "type": "boolean",
                        "collection": True,
                    },
                ]
            }],
        }

        native = duckdb.connect(config={"allow_unsigned_extensions": True})
        if register_fhirpath(native) is not True:
            native.close()
            pytest.skip("Bundled C++ FHIRPath extension is not available")
        fallback = _forced_python_connection(monkeypatch)
        try:
            expected = [("obs1", [1, 2], [True, True])]
            assert _execute_shared_view(native, view, [observation]) == expected
            assert _execute_shared_view(fallback, view, [observation]) == expected
        finally:
            native.close()
            fallback.close()

    def test_non_collection_multivalue_errors_native_and_fallback(self, monkeypatch):
        """collection=false columns report runtime multi-value violations."""
        patient = {
            "resourceType": "Patient",
            "id": "pt1",
            "name": [{"family": "Alpha"}, {"family": "Beta"}],
        }
        view = {
            "resource": "Patient",
            "select": [{
                "column": [{"path": "name.family", "name": "family", "type": "string"}]
            }],
        }

        native = duckdb.connect(config={"allow_unsigned_extensions": True})
        if register_fhirpath(native) is not True:
            native.close()
            pytest.skip("Bundled C++ FHIRPath extension is not available")
        fallback = _forced_python_connection(monkeypatch)
        try:
            with pytest.raises(Exception, match="ViewDefinition column 'family'"):
                _execute_shared_view(native, view, [patient])
            with pytest.raises(Exception, match="ViewDefinition column 'family'"):
                _execute_shared_view(fallback, view, [patient])
        finally:
            native.close()
            fallback.close()

    def test_type_uri_and_mismatch_reporting_native_and_fallback(self, monkeypatch):
        """FHIR type URIs route correctly and mismatches become execution errors."""
        observation = {
            "resourceType": "Observation",
            "id": "obs1",
            "code": {"coding": [{"system": "http://loinc.org", "code": "1234-5"}]},
        }
        patient = {"resourceType": "Patient", "id": "pt1", "gender": "female"}
        typed_complex = {
            "resource": "Observation",
            "select": [{
                "column": [{
                    "path": "code",
                    "name": "code",
                    "type": "http://hl7.org/fhir/StructureDefinition/CodeableConcept",
                }]
            }],
        }
        missing_complex_type = {
            "resource": "Observation",
            "select": [{"column": [{"path": "code", "name": "code"}]}],
        }
        primitive_mismatch = {
            "resource": "Patient",
            "select": [{"column": [{"path": "gender", "name": "gender_as_int", "type": "integer"}]}],
        }

        native = duckdb.connect(config={"allow_unsigned_extensions": True})
        if register_fhirpath(native) is not True:
            native.close()
            pytest.skip("Bundled C++ FHIRPath extension is not available")
        fallback = _forced_python_connection(monkeypatch)
        try:
            native_rows = _execute_shared_view(native, typed_complex, [observation])
            fallback_rows = _execute_shared_view(fallback, typed_complex, [observation])
            assert native_rows == fallback_rows
            assert native_rows[0][0].startswith("[{")

            with pytest.raises(Exception, match="non-primitive outputs require column.type"):
                _execute_shared_view(native, missing_complex_type, [observation])
            with pytest.raises(Exception, match="non-primitive outputs require column.type"):
                _execute_shared_view(fallback, missing_complex_type, [observation])
            with pytest.raises(Exception, match="gender_as_int"):
                _execute_shared_view(native, primitive_mismatch, [patient])
            with pytest.raises(Exception, match="gender_as_int"):
                _execute_shared_view(fallback, primitive_mismatch, [patient])
        finally:
            native.close()
            fallback.close()

    def test_non_simple_primitive_type_mismatch_errors_native_and_fallback(self, monkeypatch):
        """Declared primitive types are enforced for non-navigation FHIRPath expressions."""
        patient = {"resourceType": "Patient", "id": "pt1"}
        valid_system_integer = {
            "resource": "Patient",
            "select": [{"column": [{"path": "1", "name": "one", "type": "integer"}]}],
        }
        string_literal_as_integer = {
            "resource": "Patient",
            "select": [{"column": [{"path": "'abc'", "name": "bad_int", "type": "integer"}]}],
        }
        integer_literal_as_string = {
            "resource": "Patient",
            "select": [{"column": [{"path": "1", "name": "bad_string", "type": "string"}]}],
        }

        native = duckdb.connect(config={"allow_unsigned_extensions": True})
        if register_fhirpath(native) is not True:
            native.close()
            pytest.skip("Bundled C++ FHIRPath extension is not available")
        fallback = _forced_python_connection(monkeypatch)
        try:
            assert _execute_shared_view(native, valid_system_integer, [patient]) == [(1,)]
            assert _execute_shared_view(fallback, valid_system_integer, [patient]) == [(1,)]
            for con in (native, fallback):
                with pytest.raises(Exception, match="bad_int"):
                    _execute_shared_view(con, string_literal_as_integer, [patient])
                with pytest.raises(Exception, match="bad_string"):
                    _execute_shared_view(con, integer_literal_as_string, [patient])
        finally:
            native.close()
            fallback.close()

    def test_element_id_type_uri_executes_native_and_fallback(self, monkeypatch):
        """FHIR element-ID type notation is valid for non-primitive column output."""
        observation = {
            "resourceType": "Observation",
            "id": "obs1",
            "referenceRange": [
                {"low": {"value": 1, "unit": "mg"}, "high": {"value": 2, "unit": "mg"}},
                {"low": {"value": 3, "unit": "mg"}, "high": {"value": 4, "unit": "mg"}},
            ],
        }
        view = {
            "resource": "Observation",
            "select": [{
                "column": [{
                    "path": "referenceRange",
                    "name": "reference_range",
                    "type": "Observation.referenceRange",
                    "collection": True,
                }]
            }],
        }

        native = duckdb.connect(config={"allow_unsigned_extensions": True})
        if register_fhirpath(native) is not True:
            native.close()
            pytest.skip("Bundled C++ FHIRPath extension is not available")
        fallback = _forced_python_connection(monkeypatch)
        try:
            native_rows = _execute_shared_view(native, view, [observation])
            fallback_rows = _execute_shared_view(fallback, view, [observation])

            assert native_rows == fallback_rows
            values = native_rows[0][0]
            assert len(values) == 2
            assert json.loads(values[0])["low"]["value"] == 1
            assert json.loads(values[1])["high"]["value"] == 4
        finally:
            native.close()
            fallback.close()

    def test_this_nonprimitive_type_errors_native_and_fallback(self, monkeypatch):
        """$this cannot silently serialize complex nodes when type is unset or primitive."""
        patient = {
            "resourceType": "Patient",
            "id": "pt1",
            "name": [{"family": "Alpha"}, {"family": "Beta"}],
        }
        untyped_whole_resource = {
            "resource": "Patient",
            "select": [{"column": [{"path": "$this", "name": "whole"}]}],
        }
        name_as_string = {
            "resource": "Patient",
            "select": [{
                "forEach": "name",
                "column": [{"path": "$this", "name": "name_as_string", "type": "string"}],
            }],
        }

        native = duckdb.connect(config={"allow_unsigned_extensions": True})
        if register_fhirpath(native) is not True:
            native.close()
            pytest.skip("Bundled C++ FHIRPath extension is not available")
        fallback = _forced_python_connection(monkeypatch)
        try:
            for con in (native, fallback):
                with pytest.raises(Exception, match="non-primitive outputs require column.type"):
                    _execute_shared_view(con, untyped_whole_resource, [patient])
                with pytest.raises(Exception, match="name_as_string"):
                    _execute_shared_view(con, name_as_string, [patient])
        finally:
            native.close()
            fallback.close()

    def test_nested_unionall_default_context_matches_fallback(self, monkeypatch):
        """Nested unionAll is processed through default-$this select wrappers."""
        patient = {
            "resourceType": "Patient",
            "id": "pt1",
            "gender": "female",
        }
        parent_and_union = {
            "resource": "Patient",
            "select": [{
                "column": [{"path": "id", "name": "id", "type": "id"}],
                "select": [{
                    "unionAll": [
                        {"column": [{"path": "id", "name": "value", "type": "string"}]},
                        {"column": [{"path": "gender", "name": "value", "type": "string"}]},
                    ],
                }],
            }],
        }
        deep_wrapped_union = {
            "resource": "Patient",
            "select": [{
                "select": [{
                    "select": [{
                        "unionAll": [
                            {"column": [{"path": "id", "name": "value", "type": "string"}]},
                            {"column": [{"path": "gender", "name": "value", "type": "string"}]},
                        ],
                    }],
                }],
            }],
        }

        normal = duckdb.connect(config={"allow_unsigned_extensions": True})
        normal_loaded_native = register_fhirpath(normal) is True
        fallback = _forced_python_connection(monkeypatch)
        try:
            expected_parent = [("pt1", "female"), ("pt1", "pt1")]
            expected_deep = [("female",), ("pt1",)]

            assert sorted(_execute_shared_view(normal, parent_and_union, [patient])) == expected_parent
            assert sorted(_execute_shared_view(fallback, parent_and_union, [patient])) == expected_parent
            assert sorted(_execute_shared_view(normal, deep_wrapped_union, [patient])) == expected_deep
            assert sorted(_execute_shared_view(fallback, deep_wrapped_union, [patient])) == expected_deep

            # If the bundled native extension is available, the normal path is
            # native; otherwise it still exercises public registration apart
            # from the forced fallback connection.
            assert isinstance(normal_loaded_native, bool)
        finally:
            normal.close()
            fallback.close()

    def test_nested_select_cross_product_matches_native_and_fallback(self, monkeypatch):
        """Sibling nested selects cross-join while inheriting parent context."""
        patient = {
            "resourceType": "Patient",
            "id": "pt1",
            "name": [
                {"family": "F1", "given": ["G1", "G2"]},
                {"family": "F2", "given": ["H1"]},
            ],
            "telecom": [
                {"system": "phone"},
                {"system": "email"},
            ],
        }
        view = {
            "resource": "Patient",
            "select": [{
                "column": [{"path": "id", "name": "id", "type": "id"}],
                "select": [
                    {
                        "forEach": "name",
                        "column": [{"path": "family", "name": "family", "type": "string"}],
                        "select": [{
                            "forEach": "given",
                            "column": [{"path": "$this", "name": "given", "type": "string"}],
                        }],
                    },
                    {
                        "forEach": "telecom",
                        "column": [{"path": "system", "name": "system", "type": "code"}],
                    },
                ],
            }],
        }

        native = duckdb.connect(config={"allow_unsigned_extensions": True})
        if register_fhirpath(native) is not True:
            native.close()
            pytest.skip("Bundled C++ FHIRPath extension is not available")
        fallback = _forced_python_connection(monkeypatch)
        try:
            expected = [
                ("pt1", "F1", "G1", "email"),
                ("pt1", "F1", "G1", "phone"),
                ("pt1", "F1", "G2", "email"),
                ("pt1", "F1", "G2", "phone"),
                ("pt1", "F2", "H1", "email"),
                ("pt1", "F2", "H1", "phone"),
            ]
            assert sorted(_execute_shared_view(native, view, [patient])) == expected
            assert sorted(_execute_shared_view(fallback, view, [patient])) == expected
        finally:
            native.close()
            fallback.close()

    def test_foreach_builtin_variables_match_native_and_fallback(self, monkeypatch):
        """Iterator contexts keep current focus, root resource, and row index distinct."""
        patient = {
            "resourceType": "Patient",
            "id": "pt-root",
            "name": [
                {"family": "Fam1", "given": ["A", "B"]},
                {"family": "Fam2", "given": ["C"]},
            ],
        }
        view = {
            "resource": "Patient",
            "select": [{
                "forEach": "name",
                "column": [
                    {"path": "%context.family", "name": "family", "type": "string"},
                    {"path": "%resource.id", "name": "resource_id", "type": "id"},
                    {"path": "%rootResource.id", "name": "root_id", "type": "id"},
                    {"path": "%rowIndex", "name": "name_index", "type": "integer"},
                ],
                "select": [{
                    "forEach": "given",
                    "column": [
                        {"path": "%context", "name": "given", "type": "string"},
                        {"path": "%resource.id", "name": "inner_resource_id", "type": "id"},
                        {"path": "%rowIndex", "name": "given_index", "type": "integer"},
                    ],
                }],
            }],
        }

        native = duckdb.connect(config={"allow_unsigned_extensions": True})
        if register_fhirpath(native) is not True:
            native.close()
            pytest.skip("Bundled C++ FHIRPath extension is not available")
        fallback = _forced_python_connection(monkeypatch)
        try:
            expected = [
                ("Fam1", "pt-root", "pt-root", 0, "A", "pt-root", 0),
                ("Fam1", "pt-root", "pt-root", 0, "B", "pt-root", 1),
                ("Fam2", "pt-root", "pt-root", 1, "C", "pt-root", 0),
            ]
            assert sorted(_execute_shared_view(native, view, [patient])) == expected
            assert sorted(_execute_shared_view(fallback, view, [patient])) == expected
        finally:
            native.close()
            fallback.close()

    def test_row_index_declared_integer_has_integer_sql_type_native_and_fallback(self, monkeypatch):
        """%rowIndex is a SQL-on-FHIR integer and declared integer columns cast to INT."""
        patient = {
            "resourceType": "Patient",
            "id": "pt-root",
            "name": [{"family": "Fam1"}, {"family": "Fam2"}],
        }
        view = {
            "resource": "Patient",
            "select": [{
                "forEach": "name",
                "column": [
                    {"path": "%rowIndex", "name": "name_index", "type": "integer"},
                    {"path": "family", "name": "family", "type": "string"},
                ],
            }],
        }

        def row_index_type(con):
            vd = parse_view_definition(view)
            sql = SQLGenerator(source_table="resources").generate(vd)
            con.execute("CREATE OR REPLACE TABLE resources (resource JSON)")
            con.execute("INSERT INTO resources VALUES (?)", [json.dumps(patient)])
            return con.execute(f"SELECT typeof(name_index) FROM ({sql}) q LIMIT 1").fetchone()

        native = duckdb.connect(config={"allow_unsigned_extensions": True})
        if register_fhirpath(native) is not True:
            native.close()
            pytest.skip("Bundled C++ FHIRPath extension is not available")
        fallback = _forced_python_connection(monkeypatch)
        try:
            assert row_index_type(native) == ("INTEGER",)
            assert row_index_type(fallback) == ("INTEGER",)
        finally:
            native.close()
            fallback.close()

    def test_iterator_primitive_type_guards_match_native_and_fallback(self, monkeypatch):
        """Iterator aliases preserve declared primitive column types."""
        integer_components = [
            {
                "resourceType": "Observation",
                "id": "obs-int",
                "component": [
                    {"valueInteger": 1},
                    {"valueInteger": 2},
                ],
            }
        ]
        mixed_components = [
            {
                "resourceType": "Observation",
                "id": "obs-mixed",
                "component": [
                    {"valueInteger": 1},
                    {"valueBoolean": True},
                ],
            }
        ]
        valid_this_integer = {
            "resource": "Observation",
            "select": [{
                "forEach": "component.value",
                "column": [{"path": "$this", "name": "value", "type": "integer"}],
            }],
        }
        this_integer_as_string = {
            "resource": "Observation",
            "select": [{
                "forEach": "component.value",
                "column": [{"path": "$this", "name": "bad_string", "type": "string"}],
            }],
        }
        relative_value_as_string = {
            "resource": "Observation",
            "select": [{
                "forEach": "component",
                "column": [{"path": "value", "name": "bad_string", "type": "string"}],
            }],
        }

        def value_type(con):
            vd = parse_view_definition(valid_this_integer)
            sql = SQLGenerator(source_table="resources").generate(vd)
            con.execute("CREATE OR REPLACE TABLE resources (resource JSON)")
            con.execute("INSERT INTO resources VALUES (?)", [json.dumps(integer_components[0])])
            return (
                con.execute(sql).fetchall(),
                con.execute(f"SELECT typeof(value) FROM ({sql}) q LIMIT 1").fetchone(),
            )

        native = duckdb.connect(config={"allow_unsigned_extensions": True})
        if register_fhirpath(native) is not True:
            native.close()
            pytest.skip("Bundled C++ FHIRPath extension is not available")
        fallback = _forced_python_connection(monkeypatch)
        try:
            assert value_type(native) == ([(1,), (2,)], ("INTEGER",))
            assert value_type(fallback) == ([(1,), (2,)], ("INTEGER",))

            for con in (native, fallback):
                with pytest.raises(Exception, match="bad_string"):
                    _execute_shared_view(con, this_integer_as_string, integer_components)
                with pytest.raises(Exception, match="bad_string"):
                    _execute_shared_view(con, relative_value_as_string, mixed_components)
        finally:
            native.close()
            fallback.close()

    def test_row_index_rejects_incompatible_declared_type(self):
        """%rowIndex is integer-valued and cannot be declared as a string column."""
        view = {
            "resource": "Observation",
            "select": [{
                "forEach": "component",
                "column": [{"path": "%rowIndex", "name": "bad_index", "type": "string"}],
            }],
        }

        with pytest.raises(ValidationError, match="%rowIndex"):
            SQLGenerator(source_table="resources").generate(parse_view_definition(view))

    def test_foreach_complex_builtin_variable_paths_match_native_and_fallback(self, monkeypatch):
        """Leading built-in variables keep their target context for full FHIRPath expressions."""
        patient = {
            "resourceType": "Patient",
            "id": "pt-root",
            "name": [
                {"family": "RootFam", "given": ["R1"]},
                {"family": "OtherFam", "given": ["R2"]},
            ],
            "contact": [
                {"name": {"family": "Contact1", "given": ["C1"]}},
                {"name": {"family": "Contact2", "given": ["C2"]}},
            ],
        }
        view = {
            "resource": "Patient",
            "select": [{
                "forEach": "contact",
                "column": [
                    {"path": "%context.name.family.first()", "name": "contact_family", "type": "string"},
                    {"path": "%resource.name.family.first()", "name": "root_family", "type": "string"},
                    {"path": "%rootResource.name.family.first()", "name": "root_family_2", "type": "string"},
                ],
                "select": [{
                    "forEach": "%resource.name.where(family = 'RootFam')",
                    "column": [
                        {"path": "%context.family.first()", "name": "iterated_root_family", "type": "string"},
                    ],
                }],
            }],
        }

        native = duckdb.connect(config={"allow_unsigned_extensions": True})
        if register_fhirpath(native) is not True:
            native.close()
            pytest.skip("Bundled C++ FHIRPath extension is not available")
        fallback = _forced_python_connection(monkeypatch)
        try:
            expected = [
                ("Contact1", "RootFam", "RootFam", "RootFam"),
                ("Contact2", "RootFam", "RootFam", "RootFam"),
            ]
            assert sorted(_execute_shared_view(native, view, [patient])) == expected
            assert sorted(_execute_shared_view(fallback, view, [patient])) == expected
        finally:
            native.close()
            fallback.close()

    def test_row_index_embedded_expressions_match_native_and_fallback(self, monkeypatch):
        """%rowIndex works inside FHIRPath column and select where expressions."""
        patient = {
            "resourceType": "Patient",
            "id": "pt-root",
            "name": [
                {"family": "Smith", "given": ["John", "James"]},
                {"family": "Jones", "given": ["Jane"]},
            ],
        }
        view = {
            "resource": "Patient",
            "select": [{
                "forEach": "name",
                "where": [{"path": "%rowIndex = 1"}],
                "column": [
                    {
                        "path": "iif(%rowIndex = 1, given.first(), family)",
                        "name": "selected_value",
                        "type": "string",
                    },
                    {"path": "%rowIndex", "name": "name_index", "type": "integer"},
                ],
            }],
        }

        native = duckdb.connect(config={"allow_unsigned_extensions": True})
        if register_fhirpath(native) is not True:
            native.close()
            pytest.skip("Bundled C++ FHIRPath extension is not available")
        fallback = _forced_python_connection(monkeypatch)
        try:
            expected = [("Jane", 1)]
            assert _execute_shared_view(native, view, [patient]) == expected
            assert _execute_shared_view(fallback, view, [patient]) == expected
        finally:
            native.close()
            fallback.close()

    def test_embedded_root_variables_inside_iterator_match_native_and_fallback(self, monkeypatch):
        """Root-only %resource/%rootResource expressions route to the root resource."""
        patient = {
            "resourceType": "Patient",
            "id": "pt-root",
            "name": [
                {"family": "Smith"},
                {"family": "Jones"},
            ],
        }
        view = {
            "resource": "Patient",
            "select": [{
                "forEach": "name",
                "column": [{
                    "path": "iif(%rowIndex = 0, %resource.id, %rootResource.id)",
                    "name": "root_id",
                    "type": "id",
                }],
            }],
        }

        native = duckdb.connect(config={"allow_unsigned_extensions": True})
        if register_fhirpath(native) is not True:
            native.close()
            pytest.skip("Bundled C++ FHIRPath extension is not available")
        fallback = _forced_python_connection(monkeypatch)
        try:
            expected = [("pt-root",), ("pt-root",)]
            assert _execute_shared_view(native, view, [patient]) == expected
            assert _execute_shared_view(fallback, view, [patient]) == expected
        finally:
            native.close()
            fallback.close()

    def test_foreach_mixed_builtin_variable_paths_fail_before_silent_misrouting(self):
        """Mixed root/current built-ins need a multi-context evaluator, not a wrong single input."""
        view = {
            "resource": "Patient",
            "select": [{
                "forEach": "contact",
                "column": [{
                    "path": "%resource.name.where(family = %context.name.family).family",
                    "name": "matching_family",
                    "type": "string",
                }],
            }],
        }

        vd = parse_view_definition(view)
        with pytest.raises(ValidationError, match="mixes built-in ViewDefinition contexts"):
            SQLGenerator(source_table="resources").generate(vd)

    def test_embedded_mixed_builtin_variable_paths_fail_before_silent_misrouting(self):
        """Non-leading mixed root/current built-ins must not evaluate against one JSON input."""
        view = {
            "resource": "Patient",
            "select": [{
                "forEach": "name",
                "column": [{
                    "path": "iif(%rowIndex = 0, %resource.id, family)",
                    "name": "value",
                    "type": "string",
                }],
            }],
        }

        vd = parse_view_definition(view)
        with pytest.raises(ValidationError, match="mixes built-in ViewDefinition contexts"):
            SQLGenerator(source_table="resources").generate(vd)


class TestPrefixMixedFocusOperandSpecSofVd09Historian:
    """SOF-VD-09 HISTORIAN QA-001: expressions PREFIXED with %rootResource/%resource
    whose binary-operator operands reference the current focus must fail loud.

    Per Process(S,N), columns evaluate as fhirpath(col.path, f) with f the
    iterated focus while %rootResource/%resource track the root resource. A
    focus-rooted operand after a root-variable prefix previously evaluated
    silently against the WRONG JSON input (returning wrong/null data) instead
    of raising the same "mixes built-in ViewDefinition contexts" error the
    reverse ordering raises.
    """

    PATIENT = {
        "resourceType": "Patient",
        "id": "pt-root",
        "gender": "female",
        "active": True,
        "name": [
            {"given": ["Alice"], "use": "official"},
            {"given": ["Eve"], "use": "nickname"},
        ],
    }

    @pytest.mark.parametrize("path", [
        "%rootResource.gender & given.first()",
        "%resource.gender & given.first()",
        "%rootResource.gender = given.first()",
        "%rootResource.gender = 'female' and (use = 'official')",
    ])
    def test_prefix_focus_operand_fails_loud(self, path):
        view = {
            "resource": "Patient",
            "select": [{
                "forEach": "name",
                "column": [{"path": path, "name": "c", "type": "string"}],
            }],
        }
        vd = parse_view_definition(view)
        with pytest.raises(ValidationError, match="mixes built-in ViewDefinition contexts"):
            SQLGenerator(source_table="resources").generate(vd)

    @pytest.mark.parametrize("path,expected", [
        ("%rootResource.gender", [("female",), ("female",)]),
        ("%resource.gender", [("female",), ("female",)]),
        ("%rootResource.name.first().given.first()", [("Alice",), ("Alice",)]),
        ("%rootResource.name.where(use = 'official').given.first()",
         [("Alice",), ("Alice",)]),
        ("%rootResource.gender = 'female'", [("true",), ("true",)]),
        ("%rootResource.active = true", [("true",), ("true",)]),
    ])
    def test_pure_continuation_and_literal_operands_still_work(self, monkeypatch, path, expected):
        """Continuations, function args, and literal operands must keep evaluating."""
        view = {
            "resource": "Patient",
            "select": [{
                "forEach": "name",
                "column": [{"path": path, "name": "c"}],
            }],
        }
        native = duckdb.connect(config={"allow_unsigned_extensions": True})
        register_fhirpath(native)
        fallback = _forced_python_connection(monkeypatch)
        try:
            assert _execute_shared_view(native, view, [self.PATIENT]) == expected
            assert _execute_shared_view(fallback, view, [self.PATIENT]) == expected
        finally:
            native.close()
            fallback.close()

    def test_extension_where_prefix_focus_operand_fails_loud(self):
        view = {
            "resource": "Patient",
            "select": [{
                "forEach": "name",
                "where": [{"path": "%rootResource.gender = 'female' and (use = 'official')"}],
                "column": [{"path": "given.first()", "name": "g", "type": "string"}],
            }],
        }
        vd = parse_view_definition(view)
        with pytest.raises(ValidationError, match="mixes built-in ViewDefinition contexts"):
            SQLGenerator(source_table="resources").generate(vd)


class TestRepeat:
    """Test select.repeat recursive traversal."""

    @staticmethod
    def _native_connection():
        con = duckdb.connect(config={"allow_unsigned_extensions": True})
        if register_fhirpath(con) is not True:
            con.close()
            return None
        return con

    @staticmethod
    def _nested_questionnaire(depth: int):
        item = {"linkId": f"n{depth}", "text": f"Node {depth}"}
        for index in range(depth - 1, -1, -1):
            item = {
                "linkId": f"n{index}",
                "text": f"Node {index}",
                "item": [item],
            }
        return {"resourceType": "QuestionnaireResponse", "id": "deep", "item": [item]}

    @staticmethod
    def _nested_questionnaire_json(depth: int):
        item = '{"linkId":"n%d","text":"Node %d"}' % (depth, depth)
        for index in range(depth - 1, -1, -1):
            item = (
                '{"linkId":"n%d","text":"Node %d","item":[%s]}'
                % (index, index, item)
            )
        return '{"resourceType":"QuestionnaireResponse","id":"deep","item":[%s]}' % item

    def test_repeat_fhirpath_expression_matches_native_and_fallback(self, monkeypatch):
        """repeat entries are full FHIRPath expressions, not literal key chains."""
        resource = {
            "resourceType": "QuestionnaireResponse",
            "id": "qr",
            "item": [
                {
                    "linkId": "keep",
                    "text": "Keep Root",
                    "item": [{"linkId": "target", "text": "Target Child"}],
                },
                {"linkId": "skip"},
            ],
        }
        view = {
            "resource": "QuestionnaireResponse",
            "select": [{
                "repeat": ["item.where(text.exists())"],
                "column": [{"name": "linkId", "path": "linkId", "type": "string"}],
            }],
        }
        expected = [("keep",), ("target",)]

        fallback = _forced_python_connection(monkeypatch)
        try:
            assert _execute_shared_view(fallback, view, [resource]) == expected
        finally:
            fallback.close()

        native = self._native_connection()
        if native is not None:
            try:
                assert _execute_shared_view(native, view, [resource]) == expected
            finally:
                native.close()

    def test_repeat_duplicate_paths_use_union_semantics_native_and_fallback(self, monkeypatch):
        """The same repeated node reached by multiple repeat paths appears once."""
        resource = {
            "resourceType": "QuestionnaireResponse",
            "id": "qr",
            "item": [
                {
                    "linkId": "keep",
                    "item": [{"linkId": "target"}],
                },
                {"linkId": "skip"},
            ],
        }
        view = {
            "resource": "QuestionnaireResponse",
            "select": [{
                "repeat": ["item", "item"],
                "column": [{"name": "linkId", "path": "linkId", "type": "string"}],
            }],
        }
        expected = [("keep",), ("target",), ("skip",)]

        fallback = _forced_python_connection(monkeypatch)
        try:
            assert _execute_shared_view(fallback, view, [resource]) == expected
        finally:
            fallback.close()

        native = self._native_connection()
        if native is not None:
            try:
                assert _execute_shared_view(native, view, [resource]) == expected
            finally:
                native.close()

    def test_repeat_invalid_path_skips_only_that_path_native_and_fallback(self, monkeypatch):
        """Direct repeat UDF keeps native/fallback parity for invalid path entries."""
        resource = {
            "resourceType": "QuestionnaireResponse",
            "item": [{"linkId": "a"}, {"linkId": "b"}],
        }

        def repeat_link_ids(con, paths):
            values = con.execute(
                "SELECT fhirpath_repeat(?, ?)",
                [json.dumps(resource), json.dumps(paths)],
            ).fetchone()[0]
            return [
                (json.loads(value) if isinstance(value, str) else value)["linkId"]
                for value in values
            ]

        fallback = _forced_python_connection(monkeypatch)
        try:
            fallback_invalid_first = repeat_link_ids(fallback, ["item(", "item"])
            fallback_invalid_last = repeat_link_ids(fallback, ["item", "item("])
            assert fallback_invalid_first == ["a", "b"]
            assert fallback_invalid_last == ["a", "b"]
        finally:
            fallback.close()

        native = self._native_connection()
        if native is not None:
            try:
                assert repeat_link_ids(native, ["item(", "item"]) == fallback_invalid_first
                assert repeat_link_ids(native, ["item", "item("]) == fallback_invalid_last
            finally:
                native.close()

    def test_repeat_deep_traversal_matches_native_and_fallback(self, monkeypatch):
        """repeat follows nested paths beyond the former hard-coded depth cap."""
        resource = self._nested_questionnaire(205)
        view = {
            "resource": "QuestionnaireResponse",
            "select": [{
                "repeat": ["item"],
                "column": [{"name": "linkId", "path": "linkId", "type": "string"}],
            }],
        }
        expected = [(f"n{index}",) for index in range(206)]

        fallback = _forced_python_connection(monkeypatch)
        try:
            assert _execute_shared_view(fallback, view, [resource]) == expected
        finally:
            fallback.close()

        native = self._native_connection()
        if native is not None:
            try:
                assert _execute_shared_view(native, view, [resource]) == expected
            finally:
                native.close()

    def test_repeat_deep_raw_json_matches_native_and_fallback(self, monkeypatch):
        """Deep raw JSON repeat traversal should not hit fallback recursion limits."""
        resource_json = self._nested_questionnaire_json(800)
        view = {
            "resource": "QuestionnaireResponse",
            "select": [{
                "repeat": ["item"],
                "column": [{"name": "linkId", "path": "linkId", "type": "string"}],
            }],
        }

        fallback = _forced_python_connection(monkeypatch)
        try:
            fallback_rows = _execute_shared_view_json(fallback, view, [resource_json])
            assert len(fallback_rows) == 801
            assert fallback_rows[0] == ("n0",)
            assert fallback_rows[-1] == ("n800",)
        finally:
            fallback.close()

        native = self._native_connection()
        if native is not None:
            try:
                native_rows = _execute_shared_view_json(native, view, [resource_json])
                assert native_rows == fallback_rows
            finally:
                native.close()

    def test_repeat_extreme_depth_does_not_crash_fallback(self):
        """Recursion-budget raises beyond the inline ceiling must not segfault.

        SOF-VD-07 SKEPTIC QA-001 (2026-08-23): raising sys.setrecursionlimit
        to ~60k for a ~14k-deep resource let the evaluator's per-level
        recursion overflow the 8 MB C stack (CPython <= 3.10 consumes native
        stack per Python frame), crashing the host process. Budgets beyond
        _INLINE_RECURSION_LIMIT_MAX must run on a stack-sized worker thread
        (or degrade to a clean RecursionError), never segfault.
        """
        import threading

        from fhir4ds.fhirpath.duckdb import udf as fhirpath_udf

        depth = 6000  # needed_limit = 6000 * 4 + 1000 = 25000 > 20000 ceiling
        resource_json = self._nested_questionnaire_json(depth)
        limit_before = sys.getrecursionlimit()
        stack_size_before = threading.stack_size()

        result = fhirpath_udf.fhirpath_repeat_udf(resource_json, '["item"]')

        assert len(result) == depth + 1
        # result[0] embeds the whole 6000-deep subtree, so inspect it without
        # a full recursive parse (stdlib json caps at the default limit).
        assert result[0].startswith('{"linkId":"n0"')
        assert json.loads(result[-1])["linkId"] == f"n{depth}"
        # Global interpreter state must be restored.
        assert sys.getrecursionlimit() == limit_before
        assert threading.stack_size() == stack_size_before

    def test_repeat_this_column_context_matches_native_and_fallback(self, monkeypatch):
        """$this-prefixed columns inside repeat evaluate against each repeated node."""
        resource = {
            "resourceType": "QuestionnaireResponse",
            "id": "qr",
            "item": [
                {
                    "linkId": "root-a",
                    "text": "Root A",
                    "answer": [{
                        "valueString": "yes",
                        "item": [{"linkId": "answer-child", "text": "Answer Child"}],
                    }],
                    "item": [{"linkId": "child-a", "text": "Child A"}],
                },
                {"linkId": "root-b", "text": "Root B"},
            ],
        }
        view = {
            "resource": "QuestionnaireResponse",
            "select": [{
                "repeat": ["item", "answer.item"],
                "column": [
                    {"name": "plainLinkId", "path": "linkId", "type": "string"},
                    {"name": "thisLinkId", "path": "$this.linkId", "type": "string"},
                    {"name": "hasText", "path": "$this.text.exists()", "type": "boolean"},
                ],
            }],
        }
        expected = [
            ("root-a", "root-a", True),
            ("child-a", "child-a", True),
            ("answer-child", "answer-child", True),
            ("root-b", "root-b", True),
        ]

        fallback = _forced_python_connection(monkeypatch)
        try:
            assert _execute_shared_view(fallback, view, [resource]) == expected
        finally:
            fallback.close()

        native = self._native_connection()
        if native is not None:
            try:
                assert _execute_shared_view(native, view, [resource]) == expected
            finally:
                native.close()

    def test_repeat_this_expression_matches_native_and_fallback(self, monkeypatch):
        """repeat entries can explicitly navigate from the current focus with $this."""
        resource = {
            "resourceType": "QuestionnaireResponse",
            "id": "qr",
            "item": [{"linkId": "root", "item": [{"linkId": "child"}]}],
        }
        view = {
            "resource": "QuestionnaireResponse",
            "select": [{
                "repeat": ["$this.item"],
                "column": [{"name": "linkId", "path": "linkId", "type": "string"}],
            }],
        }
        expected = [("root",), ("child",)]

        fallback = _forced_python_connection(monkeypatch)
        try:
            assert _execute_shared_view(fallback, view, [resource]) == expected
        finally:
            fallback.close()

        native = self._native_connection()
        if native is not None:
            try:
                assert _execute_shared_view(native, view, [resource]) == expected
            finally:
                native.close()


class TestForEach:
    """Test forEach for array flattening."""

    def test_forEach_names(self, connection, generator):
        """Test flattening patient names with forEach."""
        patient = {
            "resourceType": "Patient",
            "id": "patient-1",
            "name": [
                {"given": ["John", "Q"], "family": "Doe", "use": "official"},
                {"given": ["Johnny"], "family": "Doe", "use": "nickname"}
            ]
        }
        connection.execute("CREATE TABLE patients (resource JSON)")
        connection.execute("INSERT INTO patients VALUES (?)", [json.dumps(patient)])

        # Note: Current SQLGenerator is Phase 2 - forEach generates basic columns only
        # This test documents expected behavior with current implementation
        vd_json = json.dumps({
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "id", "name": "pid"}
                ],
                "forEach": "name",
                "select": [{
                    "column": [
                        {"path": "family", "name": "family_name"},
                        {"path": "given.first()", "name": "given_name"}
                    ]
                }]
            }]
        })
        vd = parse_view_definition(vd_json)
        sql = generator.generate(vd)

        # With current implementation, forEach is not fully handled
        # This test verifies the SQL generates without error
        result = connection.execute(sql).fetchall()
        # Current implementation only extracts top-level columns
        assert len(result) >= 1

    def test_forEach_simple_array(self, connection, generator):
        """Test forEach on a simple array field."""
        # Test with a resource that has a simple array
        patient = {
            "resourceType": "Patient",
            "id": "patient-1",
            "name": [{"given": ["Alice"], "family": "Smith"}]
        }
        connection.execute("CREATE TABLE patients (resource JSON)")
        connection.execute("INSERT INTO patients VALUES (?)", [json.dumps(patient)])

        vd_json = json.dumps({
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "id", "name": "pid"},
                    {"path": "name.family.first()", "name": "family_name"}
                ]
            }]
        })
        vd = parse_view_definition(vd_json)
        sql = generator.generate(vd)

        result = connection.execute(sql).fetchall()
        assert len(result) == 1
        assert result[0][0] == "patient-1"


class TestForEachOrNull:
    """Test forEachOrNull for optional arrays."""

    def test_forEachOrNull_with_data(self, connection, generator):
        """Test forEachOrNull when array has data."""
        patient = {
            "resourceType": "Patient",
            "id": "patient-1",
            "telecom": [
                {"system": "phone", "value": "555-1234", "use": "home"},
                {"system": "email", "value": "test@example.com", "use": "work"}
            ]
        }
        connection.execute("CREATE TABLE patients (resource JSON)")
        connection.execute("INSERT INTO patients VALUES (?)", [json.dumps(patient)])

        vd_json = json.dumps({
            "resource": "Patient",
            "select": [{
                "column": [{"path": "id", "name": "pid"}],
                "forEachOrNull": "telecom",
                "select": [{
                    "column": [
                        {"path": "system", "name": "system"},
                        {"path": "value", "name": "contact_value"}
                    ]
                }]
            }]
        })
        vd = parse_view_definition(vd_json)
        sql = generator.generate(vd)

        # Current implementation generates basic SQL
        result = connection.execute(sql).fetchall()
        assert len(result) >= 1

    def test_forEachOrNull_empty_array(self, connection, generator):
        """Test forEachOrNull when array is empty - should still produce a row."""
        patient = {
            "resourceType": "Patient",
            "id": "patient-no-telecom",
            "telecom": []
        }
        connection.execute("CREATE TABLE patients (resource JSON)")
        connection.execute("INSERT INTO patients VALUES (?)", [json.dumps(patient)])

        vd_json = json.dumps({
            "resource": "Patient",
            "select": [{
                "column": [{"path": "id", "name": "pid"}],
                "forEachOrNull": "telecom",
                "select": [{
                    "column": [{"path": "value", "name": "contact_value"}]
                }]
            }]
        })
        vd = parse_view_definition(vd_json)
        sql = generator.generate(vd)

        # Current implementation generates basic SQL
        result = connection.execute(sql).fetchall()
        # Should have at least one row from the parent
        assert len(result) >= 1


class TestWhereClause:
    """Test WHERE clause filtering."""

    def test_where_simple_condition(self, connection, generator):
        """Test filtering with WHERE clause."""
        patients = [
            {"resourceType": "Patient", "id": "patient-1", "gender": "male", "active": True},
            {"resourceType": "Patient", "id": "patient-2", "gender": "female", "active": True},
            {"resourceType": "Patient", "id": "patient-3", "gender": "male", "active": False},
        ]
        connection.execute("CREATE TABLE patients (resource JSON)")
        for p in patients:
            connection.execute("INSERT INTO patients VALUES (?)", [json.dumps(p)])

        vd_json = json.dumps({
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "id", "name": "pid"},
                    {"path": "gender", "name": "gender"}
                ],
                "where": [{"path": "gender = 'male'"}]
            }]
        })
        vd = parse_view_definition(vd_json)
        sql = generator.generate(vd)

        # Current implementation may not generate WHERE - verify SQL is valid
        result = connection.execute(sql).fetchall()
        assert len(result) >= 1

    def test_top_level_where_string_condition(self, connection, generator):
        """Test filtering with a convenience string where clause."""
        patients = [
            {"resourceType": "Patient", "id": "patient-1", "gender": "male"},
            {"resourceType": "Patient", "id": "patient-2", "gender": "female"},
            {"resourceType": "Patient", "id": "patient-3", "gender": "male"},
        ]
        connection.execute("CREATE TABLE patients (resource JSON)")
        for patient in patients:
            connection.execute("INSERT INTO patients VALUES (?)", [json.dumps(patient)])

        vd_json = json.dumps({
            "resource": "Patient",
            "where": [{"path": "gender = 'male'"}],
            "select": [{
                "column": [
                    {"path": "id", "name": "pid", "type": "id"},
                    {"path": "gender", "name": "gender", "type": "string"},
                ]
            }]
        })
        vd = parse_view_definition(vd_json)
        sql = generator.generate(vd)

        result = connection.execute(sql).fetchall()

        assert result == [
            ("patient-1", "male"),
            ("patient-3", "male"),
        ]

    def test_where_with_fhirpath_function(self, connection, generator):
        """Test WHERE with FHIRPath functions."""
        patients = [
            {"resourceType": "Patient", "id": "patient-1", "birthDate": "2000-01-01"},
            {"resourceType": "Patient", "id": "patient-2", "birthDate": "1950-06-15"},
        ]
        connection.execute("CREATE TABLE patients (resource JSON)")
        for p in patients:
            connection.execute("INSERT INTO patients VALUES (?)", [json.dumps(p)])

        vd_json = json.dumps({
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "id", "name": "pid"},
                    {"path": "birthDate", "name": "dob"}
                ]
            }]
        })
        vd = parse_view_definition(vd_json)
        sql = generator.generate(vd)

        # Execute and verify all patients returned (current impl)
        result = connection.execute(sql).fetchall()
        assert len(result) == 2


class TestConstants:
    """Test constants resolution."""

    def test_constant_string_value(self, connection, generator):
        """Test using string constant in ViewDefinition."""
        patient = {
            "resourceType": "Patient",
            "id": "patient-1",
            "gender": "male"  # Include all queried fields to avoid NULL issues
        }
        connection.execute("CREATE TABLE patients (resource JSON)")
        connection.execute("INSERT INTO patients VALUES (?)", [json.dumps(patient)])

        vd_json = json.dumps({
            "resource": "Patient",
            "constant": [
                {"name": "SourceType", "valueString": "hospital-system"}
            ],
            "select": [{
                "column": [
                    {"path": "id", "name": "pid"}
                ]
            }]
        })
        vd = parse_view_definition(vd_json)
        sql = generator.generate(vd)

        # Current implementation may not fully support constants in path
        result = connection.execute(sql).fetchall()
        assert len(result) >= 1

    def test_constant_code_value(self, connection, generator):
        """Test using code constant in ViewDefinition."""
        patient = {"resourceType": "Patient", "id": "patient-1"}
        connection.execute("CREATE TABLE patients (resource JSON)")
        connection.execute("INSERT INTO patients VALUES (?)", [json.dumps(patient)])

        vd_json = json.dumps({
            "resource": "Patient",
            "constant": [
                {"name": "Status", "valueCode": "active"}
            ],
            "select": [{
                "column": [
                    {"path": "id", "name": "pid"}
                ]
            }]
        })
        vd = parse_view_definition(vd_json)
        sql = generator.generate(vd)

        result = connection.execute(sql).fetchall()
        assert len(result) == 1


class TestUnionAll:
    """Test UNION ALL for combining selects."""

    def test_unionall_basic(self, connection, generator):
        """Test combining multiple selects with UNION ALL."""
        patient = {
            "resourceType": "Patient",
            "id": "patient-1",
            "name": [
                {"given": ["John"], "family": "Doe"},
                {"given": ["Jane"], "family": "Smith"}
            ]
        }
        connection.execute("CREATE TABLE patients (resource JSON)")
        connection.execute("INSERT INTO patients VALUES (?)", [json.dumps(patient)])

        vd_json = json.dumps({
            "resource": "Patient",
            "select": [{
                "column": [{"path": "id", "name": "pid"}],
                "unionAll": [
                    {
                        "column": [
                            {"path": "name[0].family", "name": "family_name"}
                        ]
                    },
                    {
                        "column": [
                            {"path": "name[1].family", "name": "family_name"}
                        ]
                    }
                ]
            }]
        })
        vd = parse_view_definition(vd_json)
        sql = generator.generate(vd)

        result = connection.execute(sql).fetchall()
        assert result == [("patient-1", "Doe"), ("patient-1", "Smith")]
        assert "UNION ALL" in sql

    def test_multiple_top_level_unionall_groups(self, connection, generator):
        """Sibling top-level unionAll groups are cross-joined as select rowsets."""
        patient = {
            "resourceType": "Patient",
            "id": "patient-1",
            "name": [
                {"given": ["John"], "family": "Doe"},
                {"given": ["Jane"], "family": "Smith"},
            ],
        }
        connection.execute("CREATE TABLE patients (resource JSON)")
        connection.execute("INSERT INTO patients VALUES (?)", [json.dumps(patient)])

        vd_json = json.dumps({
            "resource": "Patient",
            "select": [
                {
                    "column": [{"path": "id", "name": "pid"}]
                },
                {
                    "unionAll": [
                        {"column": [{"path": "name[0].family", "name": "family_value"}]},
                        {"column": [{"path": "name[1].family", "name": "family_value"}]},
                    ]
                },
                {
                    "unionAll": [
                        {"column": [{"path": "name[0].given.first()", "name": "given_value"}]},
                        {"column": [{"path": "name[1].given.first()", "name": "given_value"}]},
                    ]
                }
            ]
        })
        vd = parse_view_definition(vd_json)
        sql = generator.generate(vd)

        result = connection.execute(sql).fetchall()

        assert sorted(result) == [
            ("patient-1", "Doe", "Jane"),
            ("patient-1", "Doe", "John"),
            ("patient-1", "Smith", "Jane"),
            ("patient-1", "Smith", "John"),
        ]

    def test_sibling_unionall_groups_cross_join_native_and_fallback(self, monkeypatch):
        """Separate unionAll rowsets compose with sibling select semantics."""
        patients = [
            {"resourceType": "Patient", "id": "p1"},
            {"resourceType": "Patient", "id": "p2"},
        ]
        view = {
            "resource": "Patient",
            "select": [
                {"column": [{"path": "id", "name": "id", "type": "id"}]},
                {
                    "unionAll": [
                        {"column": [{"path": "'A1'", "name": "a", "type": "string"}]},
                        {"column": [{"path": "'A2'", "name": "a", "type": "string"}]},
                    ]
                },
                {
                    "unionAll": [
                        {"column": [{"path": "'B1'", "name": "b", "type": "string"}]},
                        {"column": [{"path": "'B2'", "name": "b", "type": "string"}]},
                    ]
                },
            ],
        }
        expected = sorted([
            ("p1", "A1", "B1"),
            ("p1", "A1", "B2"),
            ("p1", "A2", "B1"),
            ("p1", "A2", "B2"),
            ("p2", "A1", "B1"),
            ("p2", "A1", "B2"),
            ("p2", "A2", "B1"),
            ("p2", "A2", "B2"),
        ])

        normal = duckdb.connect(config={"allow_unsigned_extensions": True})
        register_fhirpath(normal)
        fallback = _forced_python_connection(monkeypatch)
        try:
            assert sorted(_execute_shared_view(normal, view, patients)) == expected
            assert sorted(_execute_shared_view(fallback, view, patients)) == expected
        finally:
            normal.close()
            fallback.close()

    def test_unionall_branch_with_nested_unionall_preserves_columns_native_and_fallback(self, monkeypatch):
        """A branch may combine direct columns with nested unionAll columns."""
        patient = {"resourceType": "Patient", "id": "p1"}
        view = {
            "resource": "Patient",
            "select": [{
                "unionAll": [
                    {
                        "column": [{"path": "'outer1'", "name": "outer", "type": "string"}],
                        "select": [{
                            "unionAll": [
                                {"column": [{"path": "'inner1'", "name": "inner", "type": "string"}]},
                                {"column": [{"path": "'inner2'", "name": "inner", "type": "string"}]},
                            ]
                        }],
                    },
                    {
                        "column": [{"path": "'outer2'", "name": "outer", "type": "string"}],
                        "select": [{
                            "unionAll": [
                                {"column": [{"path": "'inner3'", "name": "inner", "type": "string"}]},
                                {"column": [{"path": "'inner4'", "name": "inner", "type": "string"}]},
                            ]
                        }],
                    },
                ]
            }],
        }
        expected = sorted([
            ("outer1", "inner1"),
            ("outer1", "inner2"),
            ("outer2", "inner3"),
            ("outer2", "inner4"),
        ])

        normal = duckdb.connect(config={"allow_unsigned_extensions": True})
        register_fhirpath(normal)
        fallback = _forced_python_connection(monkeypatch)
        try:
            assert sorted(_execute_shared_view(normal, view, [patient])) == expected
            assert sorted(_execute_shared_view(fallback, view, [patient])) == expected
        finally:
            normal.close()
            fallback.close()

    def test_unionall_primitive_foreach_where_native_and_fallback(self, monkeypatch):
        """Branch-local where predicates can target primitive forEach items."""
        patients = [
            {
                "resourceType": "Patient",
                "id": "p1",
                "contact": [
                    {"name": {"family": "Family", "given": ["keep", "drop"]}},
                    {"name": {"given": ["keep"]}},
                ],
            },
            {"resourceType": "Patient", "id": "p2"},
        ]
        view = {
            "resource": "Patient",
            "select": [
                {"column": [{"path": "id", "name": "id", "type": "id"}]},
                {
                    "forEachOrNull": "contact",
                    "unionAll": [
                        {
                            "where": [{"path": "name.family.exists()"}],
                            "column": [
                                {"path": "name.family", "name": "value", "type": "string"}
                            ],
                        },
                        {
                            "forEach": "name.given",
                            "where": [{"path": "$this = 'keep'"}],
                            "column": [{"path": "$this", "name": "value", "type": "string"}],
                        },
                    ],
                },
            ],
        }
        expected = sorted([
            ("p1", "Family"),
            ("p1", "keep"),
            ("p1", "keep"),
            ("p2", None),
        ])

        normal = duckdb.connect(config={"allow_unsigned_extensions": True})
        register_fhirpath(normal)
        fallback = _forced_python_connection(monkeypatch)
        try:
            assert sorted(_execute_shared_view(normal, view, patients)) == expected
            assert sorted(_execute_shared_view(fallback, view, patients)) == expected
        finally:
            normal.close()
            fallback.close()

    def test_unionall_without_parent_context_generates_sql_union(self, connection, generator):
        """A bare unionAll should produce separate SELECT branches."""
        patient = {
            "resourceType": "Patient",
            "id": "patient-1",
            "gender": "male",
        }
        connection.execute("CREATE TABLE patients (resource JSON)")
        connection.execute("INSERT INTO patients VALUES (?)", [json.dumps(patient)])

        vd_json = json.dumps({
            "resource": "Patient",
            "select": [{
                "unionAll": [
                    {"column": [{"path": "id", "name": "value"}]},
                    {"column": [{"path": "gender", "name": "value"}]},
                ]
            }]
        })
        vd = parse_view_definition(vd_json)
        sql = generator.generate(vd)

        result = connection.execute(sql).fetchall()

        assert result == [("patient-1",), ("male",)]
        assert sql.count("SELECT") == 2
        assert "UNION ALL" in sql


class TestForeachParentColumns:
    """Test parent columns combined with forEach projections."""

    def test_parent_columns_repeat_for_nested_foreach(self, connection, generator):
        patient = {
            "resourceType": "Patient",
            "id": "patient-1",
            "gender": "male",
            "telecom": [
                {"system": "phone", "value": "555-0100"},
                {"system": "email", "value": "a@example.test"},
            ],
        }
        connection.execute("CREATE TABLE patients (resource JSON)")
        connection.execute("INSERT INTO patients VALUES (?)", [json.dumps(patient)])

        vd_json = json.dumps({
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "id", "name": "id"},
                    {"path": "gender", "name": "gender"},
                ],
                "select": [{
                    "forEach": "telecom",
                    "column": [
                        {"path": "system", "name": "system"},
                        {"path": "value", "name": "value"},
                    ],
                }],
            }]
        })
        vd = parse_view_definition(vd_json)
        sql = generator.generate(vd)

        result = connection.execute(sql).fetchall()

        assert result == [
            ("patient-1", "male", "phone", "555-0100"),
            ("patient-1", "male", "email", "a@example.test"),
        ]

    def test_nested_foreach_under_foreachornull_keeps_inner_semantics(self, connection, generator):
        """Nested forEach still drops rows when the child collection is empty."""
        patients = [
            {
                "resourceType": "Patient",
                "id": "patient-1",
                "contact": [
                    {
                        "telecom": [
                            {"system": "phone"},
                            {"system": "email"},
                        ]
                    },
                    {
                        "name": {"family": "NoTelecom"},
                    },
                ],
            },
            {
                "resourceType": "Patient",
                "id": "patient-2",
            },
        ]
        connection.execute("CREATE TABLE patients (resource JSON)")
        for patient in patients:
            connection.execute("INSERT INTO patients VALUES (?)", [json.dumps(patient)])

        vd_json = json.dumps({
            "resource": "Patient",
            "select": [
                {
                    "column": [
                        {"path": "id", "name": "id", "type": "id"},
                    ],
                },
                {
                    "forEachOrNull": "contact",
                    "select": [{
                        "forEach": "telecom",
                        "column": [
                            {"path": "system", "name": "system", "type": "code"},
                        ],
                    }],
                },
            ],
        })
        vd = parse_view_definition(vd_json)
        sql = generator.generate(vd)

        result = sorted(connection.execute(sql).fetchall(), key=lambda row: (row[0], row[1] or ""))

        # Per SQL-on-FHIR v2 Process(S, N) step 3, when the outer
        # forEachOrNull's foci is empty (patient-2 has no contact) the
        # entire selection structure emits exactly ONE null row —
        # including columns produced by the nested forEach. The nested
        # forEach still keeps INNER JOIN semantics for non-empty wrapper
        # foci (contact2 with empty telecom is dropped), so only
        # contact1's telecom rows appear for patient-1.
        assert result == [
            ("patient-1", "email"),
            ("patient-1", "phone"),
            ("patient-2", None),
        ]


class TestForeachOrNullNestedForeachSpecSofVd05Historian:
    """SQL-on-FHIR v2 Process(S, N) step 3 regression coverage.

    When a ``forEachOrNull`` wraps a nested ``forEach`` and the outer
    collection is empty, the entire selection structure must emit
    exactly ONE null row — including columns produced by the nested
    forEach. See https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ViewDefinition.html.
    """

    def test_for_each_or_null_with_nested_for_each_outer_empty_emits_null_row(
        self, connection, generator
    ):
        """QA-005 B3a: outer forEachOrNull empty -> one null row."""
        patients = [
            {"resourceType": "Patient", "id": "p1"},
        ]
        connection.execute("CREATE TABLE patients (resource JSON)")
        for patient in patients:
            connection.execute("INSERT INTO patients VALUES (?)", [json.dumps(patient)])

        vd_json = json.dumps({
            "resource": "Patient",
            "select": [
                {"column": [{"path": "id", "name": "pid"}]},
                {
                    "forEachOrNull": "contact",
                    "select": [
                        {"column": [{"path": "name.family", "name": "cfamily"}]},
                        {
                            "forEach": "telecom",
                            "column": [{"path": "value", "name": "tval"}],
                        },
                    ],
                },
            ],
        })
        vd = parse_view_definition(vd_json)
        sql = generator.generate(vd)

        result = connection.execute(sql).fetchall()

        assert result == [("p1", None, None)]

    def test_for_each_or_null_with_nested_for_each_outer_non_empty_emits_rows(
        self, connection, generator
    ):
        """QA-005 B3a control: outer non-empty -> nested forEach rows."""
        patients = [
            {
                "resourceType": "Patient",
                "id": "p1",
                "contact": [
                    {
                        "name": {"family": "Family"},
                        "telecom": [
                            {"value": "tel-1"},
                            {"value": "tel-2"},
                        ],
                    },
                ],
            },
        ]
        connection.execute("CREATE TABLE patients (resource JSON)")
        for patient in patients:
            connection.execute("INSERT INTO patients VALUES (?)", [json.dumps(patient)])

        vd_json = json.dumps({
            "resource": "Patient",
            "select": [
                {"column": [{"path": "id", "name": "pid"}]},
                {
                    "forEachOrNull": "contact",
                    "select": [
                        {"column": [{"path": "name.family", "name": "cfamily"}]},
                        {
                            "forEach": "telecom",
                            "column": [{"path": "value", "name": "tval"}],
                        },
                    ],
                },
            ],
        })
        vd = parse_view_definition(vd_json)
        sql = generator.generate(vd)

        result = sorted(
            connection.execute(sql).fetchall(),
            key=lambda row: (row[0], row[1] or "", row[2] or ""),
        )

        # The non-empty outer contact is processed normally; the nested
        # forEach produces one row per telecom entry.
        assert result == [
            ("p1", "Family", "tel-1"),
            ("p1", "Family", "tel-2"),
        ]

    def test_for_each_or_null_with_nested_for_each_outer_empty_and_partial_contact(
        self, connection, generator
    ):
        """QA-005 mixed: contact exists without telecom AND contact absent.

        Per spec Process(S, N) step 2, a non-empty contact whose child
        ``forEach:telecom`` is empty must drop the contact row (INNER
        JOIN semantics). Per step 3, a Patient with no contact at all
        must emit one null row.
        """
        patients = [
            {
                "resourceType": "Patient",
                "id": "p1",
                "contact": [
                    {"name": {"family": "Family"}, "telecom": [{"value": "tel-1"}]},
                    {"name": {"family": "NoTelecom"}},
                ],
            },
            {"resourceType": "Patient", "id": "p2"},
        ]
        connection.execute("CREATE TABLE patients (resource JSON)")
        for patient in patients:
            connection.execute("INSERT INTO patients VALUES (?)", [json.dumps(patient)])

        vd_json = json.dumps({
            "resource": "Patient",
            "select": [
                {"column": [{"path": "id", "name": "pid"}]},
                {
                    "forEachOrNull": "contact",
                    "select": [
                        {"column": [{"path": "name.family", "name": "cfamily"}]},
                        {
                            "forEach": "telecom",
                            "column": [{"path": "value", "name": "tval"}],
                        },
                    ],
                },
            ],
        })
        vd = parse_view_definition(vd_json)
        sql = generator.generate(vd)

        result = sorted(
            connection.execute(sql).fetchall(),
            key=lambda row: (row[0], row[1] or "", row[2] or ""),
        )

        # p1: contact1 with telecom emits 1 row; contact2 with empty
        # telecom is dropped (INNER JOIN). p2: no contact -> one null row.
        assert result == [
            ("p1", "Family", "tel-1"),
            ("p2", None, None),
        ]


class TestForeachOrNullNestedRepeatSpecSofVd05Architect:
    """SQL-on-FHIR v2 Process(S, N) step 3 regression coverage for
    ``repeat`` nested under ``forEachOrNull`` (ARCH-003).

    When a ``forEachOrNull`` wraps a nested ``repeat`` and the outer
    collection is empty, the entire selection structure must emit
    exactly ONE null row — including columns produced by the nested
    repeat. See https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ViewDefinition.html.
    """

    def test_for_each_or_null_with_nested_repeat_outer_empty_emits_null_row(
        self, connection, generator
    ):
        """ARCH-003 A: outer forEachOrNull empty -> one null row."""
        patients = [
            {"resourceType": "Patient", "id": "p1"},
        ]
        connection.execute("CREATE TABLE patients (resource JSON)")
        for patient in patients:
            connection.execute("INSERT INTO patients VALUES (?)", [json.dumps(patient)])

        vd_json = json.dumps({
            "resource": "Patient",
            "select": [
                {"column": [{"path": "id", "name": "pid"}]},
                {
                    "forEachOrNull": "contact",
                    "select": [
                        {"column": [{"path": "name.family", "name": "cfamily"}]},
                        {
                            "repeat": ["telecom", "value"],
                            "column": [{"path": "value", "name": "tval"}],
                        },
                    ],
                },
            ],
        })
        vd = parse_view_definition(vd_json)
        sql = generator.generate(vd)

        result = connection.execute(sql).fetchall()

        assert result == [("p1", None, None)]

    def test_for_each_or_null_with_nested_repeat_outer_non_empty_emits_rows(
        self, connection, generator
    ):
        """ARCH-003 A control: outer non-empty -> nested repeat rows."""
        patients = [
            {
                "resourceType": "Patient",
                "id": "p1",
                "contact": [
                    {
                        "name": {"family": "Family"},
                        "telecom": [
                            {"value": "tel-1"},
                            {"value": "tel-2"},
                        ],
                    },
                ],
            },
        ]
        connection.execute("CREATE TABLE patients (resource JSON)")
        for patient in patients:
            connection.execute("INSERT INTO patients VALUES (?)", [json.dumps(patient)])

        vd_json = json.dumps({
            "resource": "Patient",
            "select": [
                {"column": [{"path": "id", "name": "pid"}]},
                {
                    "forEachOrNull": "contact",
                    "select": [
                        {"column": [{"path": "name.family", "name": "cfamily"}]},
                        {
                            "repeat": ["telecom", "value"],
                            "column": [{"path": "value", "name": "tval"}],
                        },
                    ],
                },
            ],
        })
        vd = parse_view_definition(vd_json)
        sql = generator.generate(vd)

        result = sorted(
            connection.execute(sql).fetchall(),
            key=lambda row: (row[0], row[1] or "", row[2] or ""),
        )

        # The non-empty outer contact is processed normally; the nested
        # repeat produces one row per telecom.value entry.
        assert result == [
            ("p1", "Family", "tel-1"),
            ("p1", "Family", "tel-2"),
        ]

    def test_for_each_or_null_with_nested_repeat_outer_empty_and_partial_contact(
        self, connection, generator
    ):
        """ARCH-003 mixed: contact exists without telecom AND contact absent.

        Per spec Process(S, N) step 2, a non-empty contact whose child
        ``repeat:telecom.value`` is empty must drop the contact row
        (INNER JOIN semantics). Per step 3, a Patient with no contact at
        all must emit one null row.
        """
        patients = [
            {
                "resourceType": "Patient",
                "id": "p1",
                "contact": [
                    {"name": {"family": "Family"}, "telecom": [{"value": "tel-1"}]},
                    {"name": {"family": "NoTelecom"}},
                ],
            },
            {"resourceType": "Patient", "id": "p2"},
        ]
        connection.execute("CREATE TABLE patients (resource JSON)")
        for patient in patients:
            connection.execute("INSERT INTO patients VALUES (?)", [json.dumps(patient)])

        vd_json = json.dumps({
            "resource": "Patient",
            "select": [
                {"column": [{"path": "id", "name": "pid"}]},
                {
                    "forEachOrNull": "contact",
                    "select": [
                        {"column": [{"path": "name.family", "name": "cfamily"}]},
                        {
                            "repeat": ["telecom", "value"],
                            "column": [{"path": "value", "name": "tval"}],
                        },
                    ],
                },
            ],
        })
        vd = parse_view_definition(vd_json)
        sql = generator.generate(vd)

        result = sorted(
            connection.execute(sql).fetchall(),
            key=lambda row: (row[0], row[1] or "", row[2] or ""),
        )

        # p1: contact1 with telecom emits 1 row; contact2 with empty
        # telecom is dropped (INNER JOIN). p2: no contact -> one null row.
        assert result == [
            ("p1", "Family", "tel-1"),
            ("p2", None, None),
        ]


class TestJoins:
    """Test JOINs between resources."""

    def test_join_patient_observation(self, connection, generator):
        """Test joining Patient and Observation resources."""
        # Create patient
        patient = {
            "resourceType": "Patient",
            "id": "patient-1",
            "gender": "male"
        }
        connection.execute("CREATE TABLE patients (resource JSON)")
        connection.execute("INSERT INTO patients VALUES (?)", [json.dumps(patient)])

        # Create observations
        observations = [
            {
                "resourceType": "Observation",
                "id": "obs-1",
                "subject": {"reference": "Patient/patient-1"},
                "status": "final",
                "valueQuantity": {"value": 120, "unit": "mmHg"}
            },
            {
                "resourceType": "Observation",
                "id": "obs-2",
                "subject": {"reference": "Patient/patient-1"},
                "status": "final",
                "valueQuantity": {"value": 80, "unit": "mmHg"}
            }
        ]
        connection.execute("CREATE TABLE observations (resource JSON)")
        for obs in observations:
            connection.execute("INSERT INTO observations VALUES (?)", [json.dumps(obs)])

        # Verify data exists by querying directly
        patient_result = connection.execute("SELECT fhirpath_text(resource, 'id') FROM patients").fetchall()
        assert len(patient_result) == 1

        obs_result = connection.execute("SELECT fhirpath_text(resource, 'id') FROM observations").fetchall()
        assert len(obs_result) == 2

    def test_join_with_view_definition(self, connection, generator):
        """Test ViewDefinition with join specification."""
        # Create patient
        patient = {
            "resourceType": "Patient",
            "id": "patient-1"
        }
        connection.execute("CREATE TABLE patients (resource JSON)")
        connection.execute("INSERT INTO patients VALUES (?)", [json.dumps(patient)])

        # ViewDefinition with join (documenting expected structure)
        vd_json = json.dumps({
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "id", "name": "patient_id"}
                ]
            }],
            "joins": [{
                "name": "observations",
                "resource": "Observation",
                "type": "left",
                "on": [
                    {"path": "subject.reference", "value": "'Patient/' + id"}
                ]
            }]
        })
        vd = parse_view_definition(vd_json)

        # Verify the join was parsed
        assert len(vd.joins) == 1
        assert vd.joins[0].name == "observations"
        assert vd.joins[0].resource == "Observation"
        assert vd.joins[0].type == JoinType.LEFT

        # Current SQL generator generates basic patient query
        sql = generator.generate(vd)
        result = connection.execute(sql).fetchall()
        assert len(result) == 1


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_missing_optional_field(self, connection, generator):
        """Test handling missing optional fields - only query existing fields."""
        patient = {
            "resourceType": "Patient",
            "id": "patient-1"
            # No gender, birthDate, etc.
        }
        connection.execute("CREATE TABLE patients (resource JSON)")
        connection.execute("INSERT INTO patients VALUES (?)", [json.dumps(patient)])

        # Only query fields that exist - NULL handling in UDF requires special handling
        vd_json = json.dumps({
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "id", "name": "pid"}
                ]
            }]
        })
        vd = parse_view_definition(vd_json)
        sql = generator.generate(vd)

        result = connection.execute(sql).fetchall()
        assert len(result) == 1
        assert result[0][0] == "patient-1"

    def test_empty_table(self, connection, generator):
        """Test query on empty table."""
        connection.execute("CREATE TABLE patients (resource JSON)")

        vd_json = json.dumps({
            "resource": "Patient",
            "select": [{
                "column": [{"path": "id", "name": "pid"}]
            }]
        })
        vd = parse_view_definition(vd_json)
        sql = generator.generate(vd)

        result = connection.execute(sql).fetchall()
        assert len(result) == 0

    def test_complex_nested_structure(self, connection, generator):
        """Test accessing deeply nested fields."""
        patient = {
            "resourceType": "Patient",
            "id": "patient-1",
            "address": [{
                "line": ["123 Main St", "Apt 4B"],
                "city": "Springfield",
                "state": "IL",
                "postalCode": "62701"
            }]
        }
        connection.execute("CREATE TABLE patients (resource JSON)")
        connection.execute("INSERT INTO patients VALUES (?)", [json.dumps(patient)])

        vd_json = json.dumps({
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "id", "name": "pid"},
                    {"path": "address.city.first()", "name": "city"},
                    {"path": "address.state.first()", "name": "state"}
                ]
            }]
        })
        vd = parse_view_definition(vd_json)
        sql = generator.generate(vd)

        result = connection.execute(sql).fetchall()
        assert len(result) == 1
        assert result[0][0] == "patient-1"
        assert result[0][1] == "Springfield"
        assert result[0][2] == "IL"

    def test_resource_type_variations(self, connection, generator):
        """Test various FHIR resource types."""
        # Observation
        observation = {
            "resourceType": "Observation",
            "id": "obs-1",
            "status": "final"
        }
        connection.execute("CREATE TABLE observations (resource JSON)")
        connection.execute("INSERT INTO observations VALUES (?)", [json.dumps(observation)])

        vd_json = json.dumps({
            "resource": "Observation",
            "select": [{
                "column": [
                    {"path": "id", "name": "obs_id"},
                    {"path": "status", "name": "status"}
                ]
            }]
        })
        vd = parse_view_definition(vd_json)
        sql = generator.generate(vd)

        result = connection.execute(sql).fetchall()
        assert len(result) == 1
        assert result[0][0] == "obs-1"
        assert result[0][1] == "final"


class TestSQLGeneration:
    """Test SQL generation properties."""

    def test_column_name_preservation(self, connection, generator):
        """Test that column names are preserved in output."""
        patient = {"resourceType": "Patient", "id": "p1", "gender": "female"}
        connection.execute("CREATE TABLE patients (resource JSON)")
        connection.execute("INSERT INTO patients VALUES (?)", [json.dumps(patient)])

        vd_json = json.dumps({
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "id", "name": "MyCustomIdName"},
                    {"path": "gender", "name": "PatientGender"}
                ]
            }]
        })
        vd = parse_view_definition(vd_json)
        sql = generator.generate(vd)

        # Verify column names appear in SQL
        assert "MyCustomIdName" in sql
        assert "PatientGender" in sql

        # Execute and verify column names in result
        result = connection.execute(sql).fetchall()
        assert len(result) == 1

    def test_special_characters_in_path(self, connection, generator):
        """Test handling special characters in FHIRPath."""
        patient = {
            "resourceType": "Patient",
            "id": "patient-with-hyphens",
            "meta": {"lastUpdated": "2024-01-15T10:30:00Z"}
        }
        connection.execute("CREATE TABLE patients (resource JSON)")
        connection.execute("INSERT INTO patients VALUES (?)", [json.dumps(patient)])

        vd_json = json.dumps({
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "id", "name": "pid"},
                    {"path": "meta.lastUpdated", "name": "last_updated"}
                ]
            }]
        })
        vd = parse_view_definition(vd_json)
        sql = generator.generate(vd)

        result = connection.execute(sql).fetchall()
        assert len(result) == 1
        assert result[0][0] == "patient-with-hyphens"

    def test_sql_is_valid_duckdb_syntax(self, connection, generator):
        """Test that generated SQL is valid DuckDB syntax."""
        patient = {"resourceType": "Patient", "id": "p1", "gender": "male"}
        connection.execute("CREATE TABLE patients (resource JSON)")
        connection.execute("INSERT INTO patients VALUES (?)", [json.dumps(patient)])

        vd_json = json.dumps({
            "resource": "Patient",
            "select": [{
                "column": [
                    {"path": "id", "name": "pid"},
                    {"path": "gender", "name": "gender"}
                ]
            }]
        })
        vd = parse_view_definition(vd_json)
        sql = generator.generate(vd)

        # Should not raise exception - all queried fields exist
        result = connection.execute(sql).fetchall()
        assert result is not None


class TestViewDefinitionValidation:
    """Test ViewDefinition parsing and validation."""

    def test_parse_minimal_definition(self, generator):
        """Test parsing minimal valid ViewDefinition."""
        vd_json = json.dumps({
            "resource": "Patient",
            "select": [{
                "column": [{"path": "id", "name": "pid"}]
            }]
        })
        vd = parse_view_definition(vd_json)

        assert vd.resource == "Patient"
        assert len(vd.select) == 1
        assert len(vd.select[0].column) == 1
        assert vd.select[0].column[0].path == "id"
        assert vd.select[0].column[0].name == "pid"

    def test_parse_with_all_features(self, generator):
        """Test parsing ViewDefinition with all features."""
        vd_json = json.dumps({
            "resource": "Patient",
            "name": "PatientView",
            "description": "A view of patient data",
            "constant": [
                {"name": "SystemUrl", "valueString": "http://example.org"}
            ],
            "select": [{
                "column": [
                    {"path": "id", "name": "pid", "type": "string"},
                    {"path": "gender", "name": "gender", "type": "code"}
                ],
                "forEach": "name",
                "where": [{"path": "gender = 'male'"}]
            }],
            "joins": [{
                "name": "obs",
                "resource": "Observation",
                "type": "left",
                "on": [{"path": "subject", "value": "Patient/%context.id"}]
            }]
        })
        vd = parse_view_definition(vd_json)

        assert vd.name == "PatientView"
        assert vd.description == "A view of patient data"
        assert len(vd.constants) == 1
        assert vd.constants[0].name == "SystemUrl"
        assert len(vd.joins) == 1
        assert vd.joins[0].resource == "Observation"

    def test_column_type_preservation(self, generator):
        """Test that column types are preserved."""
        vd_json = json.dumps({
            "resource": "Observation",
            "select": [{
                "column": [
                    {"path": "id", "name": "id", "type": "string"},
                    {"path": "value", "name": "val", "type": "integer"},
                    {"path": "active", "name": "is_active", "type": "boolean"},
                    {"path": "score", "name": "score", "type": "decimal"}
                ]
            }]
        })
        vd = parse_view_definition(vd_json)

        columns = vd.select[0].column
        assert columns[0].type == ColumnType.STRING
        assert columns[1].type == ColumnType.INTEGER
        assert columns[2].type == ColumnType.BOOLEAN
        assert columns[3].type == ColumnType.DECIMAL


def test_boolean_constant_column_without_type_native_and_fallback(monkeypatch):
    """SQL-on-FHIR v2: column.type is only required for non-primitive returns.

    A bare boolean-constant column path (``%Flag`` resolving to ``true`` or
    ``false``) returns the FHIR primitive Boolean, so it must execute without
    a declared column type. Regression guard for the runtime type guard that
    previously mis-classified the boolean literal as non-primitive output.
    """
    view = {
        "resource": "Patient",
        "constant": [{"name": "Flag", "valueBoolean": True}],
        "select": [{"column": [{"path": "%Flag", "name": "flag"}]}],
    }
    resources = [{"resourceType": "Patient", "id": "p1"}]

    native = duckdb.connect(config={"allow_unsigned_extensions": True})
    if register_fhirpath(native) is not True:
        native.close()
        pytest.skip("native FHIRPath extension not available")
    fallback = _forced_python_connection(monkeypatch)
    try:
        assert _execute_shared_view(native, view, resources) == [("true",)]
        assert _execute_shared_view(fallback, view, resources) == [("true",)]
    finally:
        native.close()
        fallback.close()


def test_boolean_constant_false_column_without_type_native_and_fallback(monkeypatch):
    """Same guard for the ``false`` literal branch of the boolean constant."""
    view = {
        "resource": "Patient",
        "constant": [{"name": "Flag", "valueBoolean": False}],
        "select": [{"column": [{"path": "%Flag", "name": "flag"}]}],
    }
    resources = [{"resourceType": "Patient", "id": "p1"}]

    native = duckdb.connect(config={"allow_unsigned_extensions": True})
    if register_fhirpath(native) is not True:
        native.close()
        pytest.skip("native FHIRPath extension not available")
    fallback = _forced_python_connection(monkeypatch)
    try:
        assert _execute_shared_view(native, view, resources) == [("false",)]
        assert _execute_shared_view(fallback, view, resources) == [("false",)]
    finally:
        native.close()
        fallback.close()
