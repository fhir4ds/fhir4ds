"""Domain 8 SKEPTIC (v0.0.25) — public-boundary typed-error guards.

Public matching/DQM entry points must reject malformed input with typed,
actionable errors instead of leaking AttributeError from internal attribute
access.
"""
import duckdb
import pytest

from fhir4ds.matching import (
    create_matching_tables,
    index_patient,
    match_patient,
    normalize_patient_fields,
)
from fhir4ds.dqm.parser import MeasureParser
from fhir4ds.dqm.errors import MeasureParseError


class TestMatchingPublicBoundaryTypeGuards:
    def test_normalize_patient_fields_rejects_non_dict(self):
        for bad in (None, "Patient", 42, [1, 2]):
            with pytest.raises(TypeError, match=r"patient_resource must be a dict"):
                normalize_patient_fields(bad)

    def test_index_patient_rejects_non_dict(self):
        con = duckdb.connect()
        create_matching_tables(con)
        for bad in (None, "Patient", 42):
            with pytest.raises(TypeError, match=r"patient_resource must be a dict"):
                index_patient(con, bad)

    def test_match_patient_rejects_non_dict(self):
        con = duckdb.connect()
        create_matching_tables(con)
        for bad in (None, "Patient", 42):
            with pytest.raises(TypeError, match=r"patient_resource must be a dict"):
                match_patient(con, bad)

    def test_valid_resource_still_extracts(self):
        fields = normalize_patient_fields(
            {"resourceType": "Patient", "id": "p1", "name": [{"family": "Doe"}]}
        )
        assert fields.get("last") == ["doe"]


class TestDqmMeasureParserGroupShape:
    def test_parse_rejects_non_list_group(self):
        with pytest.raises(MeasureParseError, match=r"group must be a list, got dict"):
            MeasureParser().parse(
                {"resourceType": "Measure", "id": "m1", "group": {"g": 1}}
            )

    def test_parse_rejects_none_and_non_dict(self):
        mp = MeasureParser()
        with pytest.raises(MeasureParseError, match="Cannot parse None"):
            mp.parse(None)
        with pytest.raises(MeasureParseError, match="Expected a dict, got list"):
            mp.parse([1])


class TestBuildMembershipEmptyCorpus:
    def test_empty_index_returns_zero_components(self):
        from fhir4ds.matching import build_membership, create_matching_tables

        con = duckdb.connect()
        create_matching_tables(con)
        assert build_membership(con) == 0

    def test_bare_connection_creates_tables_and_returns_zero(self):
        from fhir4ds.matching import build_membership

        assert build_membership(duckdb.connect()) == 0
