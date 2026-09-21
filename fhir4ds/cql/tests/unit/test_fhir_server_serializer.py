"""Tests for CQL result to FHIR Parameters serialization."""

from __future__ import annotations

from decimal import Decimal

import pytest

from fhir4ds.cql.fhir_server.result_serializer import serialize_value
from fhir4ds.cql.fhir_server.types import CQLFacadeError, CQLResultMetadata, CQLTypeRef


def _meta(type_name: str) -> CQLResultMetadata:
    return CQLResultMetadata(cql_type=type_name, type_ref=CQLTypeRef.parse(type_name))


def test_primitive_serialization():
    assert serialize_value("return", True, CQLTypeRef.parse("Boolean")) == [
        {"name": "return", "valueBoolean": True}
    ]
    assert serialize_value("return", Decimal("1.25"), CQLTypeRef.parse("Decimal")) == [
        {"name": "return", "valueDecimal": 1.25}
    ]
    assert serialize_value("return", "hello", CQLTypeRef.parse("String")) == [
        {"name": "return", "valueString": "hello"}
    ]


def test_temporal_serialization_strips_cql_markers():
    assert serialize_value("return", "2024-01-01", CQLTypeRef.parse("Date")) == [
        {"name": "return", "valueDate": "2024-01-01"}
    ]
    assert serialize_value("return", "2016T", CQLTypeRef.parse("DateTime")) == [
        {"name": "return", "valueDateTime": "2016"}
    ]
    assert serialize_value("return", "2014-01-01", CQLTypeRef.parse("DateTime")) == [
        {"name": "return", "valueDateTime": "2014-01-01"}
    ]
    assert serialize_value("return", "T10:15:30", CQLTypeRef.parse("Time")) == [
        {"name": "return", "valueTime": "10:15:30"}
    ]
    assert serialize_value("return", "T14:30:00.0", CQLTypeRef.parse("Time")) == [
        {"name": "return", "valueTime": "14:30:00.000"}
    ]


def test_quantity_ratio_code_concept_serialization():
    quantity = '{"value":5,"code":"mg","system":"http://unitsofmeasure.org","unit":"mg"}'
    assert serialize_value("return", quantity, CQLTypeRef.parse("Quantity")) == [
        {
            "name": "return",
            "valueQuantity": {
                "value": 5,
                "unit": "mg",
                "system": "http://unitsofmeasure.org",
                "code": "mg",
            },
        }
    ]
    ratio = '{"numerator":{"value":1,"code":"mg"},"denominator":{"value":2,"code":"mg"}}'
    assert serialize_value("return", ratio, CQLTypeRef.parse("Ratio"))[0]["valueRatio"][
        "numerator"
    ]["unit"] == "mg"
    code = '{"system":"http://loinc.org","code":"123","display":"Test"}'
    assert serialize_value("return", code, CQLTypeRef.parse("Code")) == [
        {
            "name": "return",
            "valueCoding": {
                "system": "http://loinc.org",
                "code": "123",
                "display": "Test",
            },
        }
    ]
    concept = '{"codes":[{"system":"http://loinc.org","code":"123"}],"display":"Test"}'
    assert serialize_value("return", concept, CQLTypeRef.parse("Concept")) == [
        {
            "name": "return",
            "valueCodeableConcept": {
                "coding": [{"system": "http://loinc.org", "code": "123"}],
                "text": "Test",
            },
        }
    ]

def test_interval_list_tuple_and_empty_serialization():
    interval = '{"low": "1", "high": "10", "lowClosed": true, "highClosed": true}'
    param = serialize_value("return", interval, CQLTypeRef.parse("Interval<Integer>"))[0]
    assert param["part"] == [
        {"name": "lowClosed", "valueBoolean": True},
        {"name": "low", "valueInteger": 1},
        {"name": "highClosed", "valueBoolean": True},
        {"name": "high", "valueInteger": 10},
    ]
    assert param["extension"][0]["valueString"] == "Interval<Integer>"

    assert serialize_value("return", [1, 2], CQLTypeRef.parse("List<Integer>")) == [
        {"name": "return", "valueInteger": 1},
        {"name": "return", "valueInteger": 2},
    ]
    nested = serialize_value("return", [[1, 2]], CQLTypeRef.parse("List<List<Integer>>"))
    assert nested == [
        {
            "name": "return",
            "part": [
                {"name": "element", "valueInteger": 1},
                {"name": "element", "valueInteger": 2},
            ],
        }
    ]

    tuple_param = serialize_value(
        "return",
        '{"a":1,"b":"x"}',
        CQLTypeRef.parse("Tuple{a: Integer, b: String}"),
    )[0]
    assert tuple_param["part"] == [
        {"name": "a", "valueInteger": 1},
        {"name": "b", "valueString": "x"},
    ]

    empty = serialize_value("return", [], CQLTypeRef.parse("List<Integer>"), _meta("List<Integer>"))[0]
    assert empty["_valueBoolean"]["extension"][0]["url"].endswith("cqf-isEmptyList")


def test_open_interval_uses_runner_part_shape():
    param = serialize_value(
        "return",
        '{"low": "1", "high": "10", "lowClosed": false, "highClosed": true}',
        CQLTypeRef.parse("Interval<Integer>"),
    )[0]

    assert param["part"] == [
        {"name": "lowClosed", "valueBoolean": False},
        {"name": "low", "valueInteger": 1},
        {"name": "highClosed", "valueBoolean": True},
        {"name": "high", "valueInteger": 10},
    ]


def test_runtime_structure_overrides_weak_or_wrong_metadata():
    quantity_json = '{"value":15.0,"unit":"mL","code":"mL","system":"http://unitsofmeasure.org"}'
    assert serialize_value("return", quantity_json, CQLTypeRef.parse("Decimal")) == [
        {
            "name": "return",
            "valueQuantity": {
                "value": 15.0,
                "unit": "ml",
                "system": "http://unitsofmeasure.org",
                "code": "ml",
            },
        }
    ]

    uncertainty_json = '{"start":4,"end":5,"lowClosed":true,"highClosed":true}'
    param = serialize_value("return", uncertainty_json, CQLTypeRef.parse("Integer"))[0]
    assert param["part"] == [
        {"name": "lowClosed", "valueBoolean": True},
        {"name": "low", "valueInteger": 4},
        {"name": "highClosed", "valueBoolean": True},
        {"name": "high", "valueInteger": 5},
    ]

    assert serialize_value("return", 120, CQLTypeRef.parse("List<Integer>")) == [
        {"name": "return", "valueInteger": 120}
    ]
    assert serialize_value("return", True, CQLTypeRef.parse("Integer")) == [
        {"name": "return", "valueBoolean": True}
    ]
    assert serialize_value("return", "2012-10-06T", CQLTypeRef.parse("Any")) == [
        {"name": "return", "valueDateTime": "2012-10-06"}
    ]
    assert serialize_value("return", "T20:59:59.999", CQLTypeRef.parse("Any")) == [
        {"name": "return", "valueTime": "20:59:59.999"}
    ]
    assert serialize_value("return", "{'value': 10.0, 'unit': 'g'}", CQLTypeRef.parse("Any")) == [
        {
            "name": "return",
            "valueQuantity": {
                "value": 10.0,
                "unit": "g",
                "system": "http://unitsofmeasure.org",
                "code": "g",
            },
        }
    ]


def test_long_serialization_preserves_literal_text():
    param = serialize_value("return", 9223372036854775807, CQLTypeRef.parse("Long"))[0]

    assert param["valueString"] == "9223372036854775807L"
    assert param["extension"][0]["valueString"] == "System.Long"


def test_malformed_semantic_json_is_serializer_gap():
    with pytest.raises(CQLFacadeError) as exc_info:
        serialize_value("return", "{not-json", CQLTypeRef.parse("Quantity"))

    assert exc_info.value.category == "serializer-gap"


def test_metadata_first_contract_u6():
    """Known metadata is trusted; rescue is failure-driven and per-level."""
    from fhir4ds.cql.fhir_server.types import CQLResultMetadata

    # from_definition_meta prefers the builder-attached cql_type_ref.
    class _Meta:
        cql_type = "Any"
        sql_result_type = "Decimal"

        def __init__(self):
            from fhir4ds.cql.types import CQLTypeRef

            self.cql_type_ref = CQLTypeRef.parse("Quantity")

    metadata = CQLResultMetadata.from_definition_meta("return", _Meta())
    assert metadata.cql_type == "Quantity"
    # Quantity metadata trusted: dict value serializes as valueQuantity,
    # no Integer/Decimal inference overrides.
    param = serialize_value("return", {"value": 5, "unit": "mg"}, metadata.type_ref, metadata)
    assert param[0]["valueQuantity"]["code"] == "mg"

    # Long metadata with an int value is trusted (runtime Integer inference
    # never rescues without a crash): renders the Long literal form.
    param = serialize_value("return", 42, CQLTypeRef.parse("Long"))[0]
    assert param["valueString"] == "42L"

    # String metadata is trusted even for structured-looking string values
    # (VARCHAR is the transport shape for temporals/quantities/codes).
    param = serialize_value("return", '{"value": 5, "unit": "mg"}', CQLTypeRef.parse("String"))
    assert param == [{"name": "return", "valueString": '{"value": 5, "unit": "mg"}'}]

    # Rescue is failure-driven: logs a WARNING and retries once.
    quantity_json = '{"value":15.0,"unit":"mL","code":"mL"}'
    with caplog_context() as captured:
        param = serialize_value("return", quantity_json, CQLTypeRef.parse("Decimal"))
    assert param[0]["valueQuantity"]["unit"] == "ml"
    assert any("rescued by runtime type" in record.getMessage() for record in captured.records)

    # Rescue applies per-level (list elements), recursively.
    mixed = ["2024-01-01", {"start": 4, "end": 5, "lowClosed": True, "highClosed": True}]
    params = serialize_value("return", mixed, CQLTypeRef.parse("List<DateTime>"))
    assert params[0] == {"name": "return", "valueDateTime": "2024-01-01"}
    second = params[1]
    assert second["part"] == [
        {"name": "lowClosed", "valueBoolean": True},
        {"name": "low", "valueInteger": 4},
        {"name": "highClosed", "valueBoolean": True},
        {"name": "high", "valueInteger": 5},
    ]

    # String runtime inference never rescues: malformed JSON under Quantity
    # metadata stays a serializer-gap even though it "looks like" a String.
    with pytest.raises(CQLFacadeError) as exc_info:
        serialize_value("return", "{not-json", CQLTypeRef.parse("Quantity"))
    assert exc_info.value.category == "serializer-gap"


class caplog_context:
    """Minimal logging capture compatible with module-level test functions."""

    def __init__(self):
        import logging
        from contextlib import contextmanager

        self.records = []
        self._handler = logging.Handler()
        self._handler.emit = lambda record: self.records.append(record)
        self._cm = contextmanager(self._ctx)()

    def _ctx(self):
        import logging

        root = logging.getLogger("fhir4ds.cql.fhir_server.result_serializer")
        old_level = root.level
        root.addHandler(self._handler)
        root.setLevel(logging.WARNING)
        try:
            yield self
        finally:
            root.removeHandler(self._handler)
            root.setLevel(old_level)

    def __enter__(self):
        return self._cm.__enter__()

    def __exit__(self, *args):
        return self._cm.__exit__(*args)


def test_metadata_first_rollback_flag_restores_legacy_reconcile():
    """metadata_first=False restores the pre-0.0.16 value-first reconcile.

    Rollback path per the FDD: CQLServerConfig.metadata_first_serialization
    threads serialize_evaluation_result(..., metadata_first=False) which
    reconciles the type from runtime evidence BEFORE dispatch.
    """
    from fhir4ds.cql.fhir_server.result_serializer import serialize_evaluation_result
    from fhir4ds.cql.fhir_server.types import CQLResultMetadata

    from fhir4ds.cql.types import CQLTypeRef

    class _Metadata:
        cql_type = "Decimal"
        definition_name = "return"
        sql_result_type = None
        type_ref = CQLTypeRef.parse("Decimal")

    class _Result:
        metadata = _Metadata()
        value = '{"value":15.0,"unit":"mL","code":"mL"}'

    result = _Result()
    out = serialize_evaluation_result(result, metadata_first=False)
    param = out["parameter"][0]
    # Legacy reconcile promoted the Quantity JSON over Decimal metadata
    # BEFORE dispatch (no crash-and-rescue needed).
    assert param["valueQuantity"]["unit"] == "ml"

    # Metadata-first keeps Decimal trusted -> Decimal branch raises on
    # dict-shaped string parse -> rescue fires (same output, logged).
    with caplog_context() as captured:
        out = serialize_evaluation_result(result, metadata_first=True)
    assert out["parameter"][0]["valueQuantity"]["unit"] == "ml"
    assert any("rescued by runtime type" in r.getMessage() for r in captured.records)

    # Flag plumbing: CQLServerConfig carries the documented default.
    from fhir4ds.cql.fhir_server.types import CQLServerConfig

    assert CQLServerConfig().metadata_first_serialization is True
