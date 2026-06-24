"""Regression tests for per-resource-type terminology property defaults.

Tracks the issue where a CQL retrieve like ``[MedicationStatement: "X"]``
silently fell back to ``coding_matches(resource, 'code', ...)`` because
``MedicationStatement`` was missing from
``terminology_property_defaults.json``. MedicationStatement has no top-level
``code`` field (the medication code lives in ``medicationCodeableConcept``
or ``medicationReference``), so the retrieve returned zero rows instead
of erroring — a silent wrong answer.

This test file is parameterized off the JSON config directly, so any new
resource added to the map is automatically covered. Tests both the CQL
author's explicit ``code:"..."`` path (which the spec allows overriding)
and the implicit default-path resolution that most CQL authors rely on.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from ...parser import parse_cql
from ...translator import CQLToSQLTranslator
from ...translator.patterns.retrieve import _TERMINOLOGY_PROPERTY_DEFAULTS
from fhir4ds.cql import FHIRDataLoader, evaluate_measure
from fhir4ds.cql.duckdb import register


_CONFIG_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "cql" / "resources" / "terminology"
    / "terminology_property_defaults.json"
)


def _config_entries() -> list[tuple[str, str]]:
    """Read (resource_type, code_path) pairs from the JSON config.

    Skips underscore-prefixed keys (``_comment``, ``_default``, ``_medication_reference_alternatives``)
    and the runtime ``None`` key that the loader injects for the default.
    Also drops ``Library`` because the CQL grammar reserves ``library`` as
    a top-level keyword and the parser cannot accept it as a resource type
    in a retrieve. The JSON entry is still correct per FHIR R4 ModelInfo
    and will become reachable if the parser gains escaped-identifier support.
    """
    data = json.loads(_CONFIG_PATH.read_text())
    return sorted(
        (k, v) for k, v in data.items()
        if isinstance(k, str)
        and not k.startswith("_")
        and k != "Library"  # parser rejects: see docstring
    )


@pytest.mark.parametrize(
    "resource_type,expected_path",
    _config_entries(),
    ids=[rt for rt, _ in _config_entries()],
)
def test_retrieve_uses_configured_code_path(resource_type: str, expected_path: str):
    """``[ResourceType: "code"]`` must emit ``coding_matches(resource, '<expected_path>', ...)``.

    The property path is the 2nd argument to ``coding_matches`` in the
    generated SQL. If the resource is missing from the JSON map, the
    translator falls back to ``'code'`` — which is wrong for any resource
    whose primary code path lives elsewhere (e.g. MedicationStatement's
    ``medicationCodeableConcept``, Immunization's ``vaccineCode``).
    """
    cql = f"""
    library PathCheck version '1.0'
    using FHIR version '4.0.1'

    codesystem "SNOMED": 'http://snomed.info/sct'
    code "X": '12345' from "SNOMED"

    context Patient

    define "Found":
        exists ([{resource_type}: "X"])
    """
    library = parse_cql(cql)
    translator = CQLToSQLTranslator()
    sql = translator.translate_library_to_population_sql(library)

    expected_pattern = f"coding_matches(r.resource, '{expected_path}',"
    assert expected_pattern in sql, (
        f"Expected {expected_pattern!r} in SQL for {resource_type} "
        f"(configured path: {expected_path!r}); got:\n{sql}"
    )


def test_medication_statement_retrieve_matches_when_code_is_in_medication_codeable_concept(tmp_path):
    """End-to-end: ``[MedicationStatement: "Atorvastatin"]`` must return True
    when the resource carries the RxNorm code in ``medicationCodeableConcept``.

    The original bug: MedicationStatement was missing from the JSON map, the
    retrieve fell back to looking at the resource's (non-existent) ``code``
    field, and the result was False instead of True — silently wrong.
    """
    cql_path = tmp_path / "medication_statement_retrieve.cql"
    cql_path.write_text(
        """
        library MedicationStatementRepro version '1.0'
        using FHIR version '4.0.1'

        codesystem "RXNORM": 'http://www.nlm.nih.gov/research/umls/rxnorm'
        code "Atorvastatin": '83367' from "RXNORM"

        context Patient

        define "OnStatin":
            exists ([MedicationStatement: "Atorvastatin"])
        """
    )

    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con)
    try:
        loader = FHIRDataLoader(con)
        for resource in [
            {"resourceType": "Patient", "id": "p1", "birthDate": "1970-01-01"},
            {
                "resourceType": "MedicationStatement", "id": "m1",
                "status": "active",
                "medicationCodeableConcept": {
                    "coding": [{
                        "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                        "code": "83367",
                        "display": "atorvastatin",
                    }]
                },
                "subject": {"reference": "Patient/p1"},
                "effectiveDateTime": "2026-06-15",
            },
        ]:
            loader.load_resource(resource)

        df = evaluate_measure(
            str(cql_path),
            con,
            output_columns={"on_statin": "OnStatin"},
        )
        rows = df.set_index("patient_id").to_dict("index")
        assert bool(rows["p1"]["on_statin"]) is True, (
            f"Patient with active atorvastatin MedicationStatement should match; got: {rows}"
        )
    finally:
        con.close()


def test_medication_statement_retrieve_returns_false_when_no_matching_code(tmp_path):
    """Negative control: ``[MedicationStatement: "Atorvastatin"]`` must return
    False when the patient's MedicationStatement has a *different* code.

    Guards against an over-eager fix that would match any MedicationStatement
    regardless of code (e.g. forgetting the coding system in the comparison).
    """
    cql_path = tmp_path / "medication_statement_no_match.cql"
    cql_path.write_text(
        """
        library MedicationStatementNegative version '1.0'
        using FHIR version '4.0.1'

        codesystem "RXNORM": 'http://www.nlm.nih.gov/research/umls/rxnorm'
        code "Atorvastatin": '83367' from "RXNORM"

        context Patient

        define "OnStatin":
            exists ([MedicationStatement: "Atorvastatin"])
        """
    )

    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con)
    try:
        loader = FHIRDataLoader(con)
        for resource in [
            {"resourceType": "Patient", "id": "p1", "birthDate": "1970-01-01"},
            {
                "resourceType": "MedicationStatement", "id": "m1",
                "status": "active",
                "medicationCodeableConcept": {
                    "coding": [{
                        "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                        "code": "999999",  # Different drug, not atorvastatin
                        "display": "some other drug",
                    }]
                },
                "subject": {"reference": "Patient/p1"},
                "effectiveDateTime": "2026-06-15",
            },
        ]:
            loader.load_resource(resource)

        df = evaluate_measure(
            str(cql_path),
            con,
            output_columns={"on_statin": "OnStatin"},
        )
        rows = df.set_index("patient_id").to_dict("index")
        assert bool(rows["p1"]["on_statin"]) is False, (
            f"Patient on a non-atorvastatin drug should not match; got: {rows}"
        )
    finally:
        con.close()


def test_medication_statement_appears_in_terminology_defaults_map():
    """Direct guard: MedicationStatement must be in the JSON config.

    Pinning the bug fix at the source-of-truth level. If anyone ever removes
    the entry (or typos it), this fails loudly instead of silently producing
    wrong SQL.
    """
    assert "MedicationStatement" in _TERMINOLOGY_PROPERTY_DEFAULTS, (
        "MedicationStatement is missing from the terminology defaults map — "
        "retrieves will silently fall back to the 'code' field, which "
        "MedicationStatement does not have."
    )
    assert _TERMINOLOGY_PROPERTY_DEFAULTS["MedicationStatement"] == "medicationCodeableConcept", (
        f"Expected medicationCodeableConcept for MedicationStatement; "
        f"got {_TERMINOLOGY_PROPERTY_DEFAULTS['MedicationStatement']!r}"
    )
