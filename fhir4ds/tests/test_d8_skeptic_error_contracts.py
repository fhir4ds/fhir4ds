"""Domain 8 SKEPTIC (v0.0.26) error-contract regressions.

Red-first evidence: the pre-fix probe
(.temp/qa/d8_skeptic_v0026/probe1.py) recorded raw KeyError /
TypeError / AttributeError leaks from piqi and raw
``duckdb.ConnectionException: Connection Error: Connection already
closed!`` from matching/dedup public entry points; realism sat at
``__version__ == "0.0.1"`` (test_version.py red).
"""

from __future__ import annotations

import duckdb
import pytest

import fhir4ds.dedup as dedup
import fhir4ds.matching as matching
import fhir4ds.piqi as piqi


def _closed():
    con = duckdb.connect()
    con.close()
    return con


def _patient(pid="p1"):
    return {"resourceType": "Patient", "id": pid,
            "name": [{"family": "Doe"}], "birthDate": "1990-01-01"}


class TestPiqiTypedErrorContractsD8Skeptic:
    """QA-D8S-001: piqi lookups and run_* inputs raise typed errors."""

    def test_registry_unknown_names_raise_actionable_value_errors(self):
        with pytest.raises(ValueError, match="unknown PIQI view"):
            piqi.get_view("bogus-view")
        with pytest.raises(ValueError, match="unknown PIQI library"):
            piqi.get_sam("bogus-sam")
        with pytest.raises(ValueError, match="unknown PIQI library"):
            piqi.get_rubric("bogus-rubric")

    def test_registry_non_string_names_raise_type_errors(self):
        with pytest.raises(TypeError, match="view name must be a str"):
            piqi.get_view(None)
        with pytest.raises(TypeError, match="SAM instance id must be a str"):
            piqi.get_sam(None)
        with pytest.raises(TypeError, match="rubric name must be a str"):
            piqi.get_rubric(42)

    def test_run_sam_malformed_dict_is_typed_not_keyerror(self):
        con = duckdb.connect()
        with pytest.raises(ValueError, match="non-empty string keys"):
            piqi.run_sam(con, {"id": "x", "resourceType": "Library"})
        with pytest.raises(ValueError, match="non-empty string keys"):
            piqi.run_sam(con, {"url": "http://x/y"})

    def test_run_sam_wrong_type_is_typed_not_attributeerror(self):
        con = duckdb.connect()
        for bad in (42, None, ["x"], ("a",)):
            with pytest.raises(TypeError, match="SAM Library dict"):
                piqi.run_sam(con, bad)

    def test_run_sam_unknown_name_is_actionable(self):
        con = duckdb.connect()
        with pytest.raises(ValueError, match="unknown PIQI library"):
            piqi.run_sam(con, "totally-bogus-sam")

    def test_run_parameterized_sam_validates_sam_and_parameters(self):
        con = duckdb.connect()
        with pytest.raises(TypeError, match="build_parameterized_sam"):
            piqi.run_parameterized_sam(con, "labresult-resultvalue-ispopulated",
                                       {"x": 1})
        good = {"id": "piqi-sam-x", "url": "http://example/x",
                "parameter": []}
        with pytest.raises(TypeError, match="parameters must be a dict"):
            piqi.run_parameterized_sam(con, good, "not-a-dict")

    def test_evaluate_rubric_wrong_type_is_typed(self):
        con = duckdb.connect()
        with pytest.raises(TypeError, match="rubric must be"):
            piqi.evaluate_rubric(con, 42)
        with pytest.raises(ValueError, match="unknown PIQI library"):
            piqi.evaluate_rubric(con, "no-such-rubric")


class TestClosedConnectionWrapD8Skeptic:
    """QA-D8S-002: matching/dedup/piqi public entry points wrap the raw
    DuckDB closed-connection message (INV-8 pattern)."""

    def test_matching_entry_points_wrap_closed_connection(self):
        cc = _closed()
        for action, fn in [
            ("match patient", lambda: matching.match_patient(cc, _patient())),
            ("index patient", lambda: matching.index_patient(cc, _patient())),
            ("matching tables", lambda: matching.create_matching_tables(cc)),
            ("linkage tables", lambda: matching.create_linkage_tables(cc)),
            ("audit tables", lambda: matching.create_audit_tables(cc)),
            ("exact candidates",
             lambda: matching.exact_candidates(cc, "last", "Doe")),
            ("ingest", lambda: matching.match_on_ingest(
                cc, [_patient()], "r1")),
        ]:
            with pytest.raises(duckdb.ConnectionException,
                               match="DuckDB connection is closed") as ei:
                fn()
            assert "Cannot" in str(ei.value), action

    def test_matching_entry_points_reject_non_connections(self):
        for fn in [lambda: matching.match_patient(None, _patient()),
                   lambda: matching.create_matching_tables("conn"),
                   lambda: matching.exact_candidates(42, "last", "Doe")]:
            with pytest.raises(TypeError, match="DuckDB connection"):
                fn()

    def test_dedup_run_wraps_closed_connection_before_work(self):
        cc = _closed()
        obs = {"resourceType": "Observation", "id": "o1",
               "status": "final",
               "code": {"coding": [{"system": "http://loinc.org",
                                    "code": "8867-4"}]},
               "subject": {"reference": "Patient/p1"},
               "effectiveDateTime": "2024-01-01T10:00:00",
               "valueQuantity": {"value": 72, "unit": "min"}}
        with pytest.raises(duckdb.ConnectionException,
                           match="Cannot run dedup"):
            dedup.run_dedup([obs, dict(obs, id="o2")], "r1", conn=cc)
        with pytest.raises(duckdb.ConnectionException,
                           match="Cannot run encounter dedup"):
            dedup.run_encounter_dedup([obs, dict(obs, id="o2")], "r1",
                                      conn=cc)

    def test_piqi_load_views_wraps_closed_connection(self):
        with pytest.raises(duckdb.ConnectionException,
                           match="Cannot load PIQI views"):
            piqi.load_piqi_views(_closed())
        with pytest.raises(TypeError, match="DuckDB connection"):
            piqi.load_piqi_views(None)

    def test_open_connection_still_works(self):
        con = duckdb.connect()
        matching.create_matching_tables(con)
        result = matching.match_patient(con, _patient())
        assert result.outcome == "no_match"
        assert dedup.run_dedup([], "r1", conn=con).stats["run_id"] == "r1"


class TestRealismVersionLockstepD8Skeptic:
    """QA-D8S-003: realism __version__ must track the package root."""

    def test_realism_version_matches_root(self):
        import fhir4ds
        import fhir4ds.realism as realism

        assert realism.__version__ == fhir4ds.__version__
