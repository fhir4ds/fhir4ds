"""Evolution v0.0.26 — Domain 14 SKEPTIC regression tests.

Red-first coverage for:
- QA-D14S-001 (HIGH): E-rule band evidence (``a~b|band=...|model=...``)
  broke ``linkage._canonical_evidence`` — the ``|`` annotations migrated
  onto one name token and the canonical form depended on which side was the
  query patient, making stored Linkage artifacts insertion-order-dependent
  via ``match_on_ingest`` (determinism doctrine violation).
- QA-D14S-002 (HIGH): non-Latin names normalize to the empty string in the
  name-embedding runtime, so ANY two distinct non-Latin given names embed
  identically and land in the ``tight`` band — E3 then falsely links two
  distinct individuals sharing DOB + street (the sibling/twin scenario the
  guards exist for; the legacy fuzzy comparators reject the same pair).
- REV-26-003: the band-table calibration invariant was an ``assert``
  (vanishes under ``python -O``); now a typed ``ValueError``.
"""

from __future__ import annotations

import json

import duckdb
import pytest

from fhir4ds.matching import name_embedding, rules as matching_rules
from fhir4ds.matching.engine import match_patient
from fhir4ds.matching.ingest import match_on_ingest
from fhir4ds.matching.linkage import _canonical_evidence, load_linkage_resources
from fhir4ds.matching.store import create_matching_tables, index_patient


def _patient(pid: str, first: str, *, last: str = "Chalmers",
             dob: str = "1974-12-25", phone: str = "555-010-0100",
             address: dict | None = None) -> dict:
    resource: dict = {
        "resourceType": "Patient",
        "id": pid,
        "name": [{"family": last, "given": [first]}],
        "birthDate": dob,
        "telecom": [{"system": "phone", "value": phone}],
    }
    if address is not None:
        resource["address"] = [address]
    return resource


def _fresh_conn() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()
    create_matching_tables(conn)
    return conn


# --- QA-D14S-001: evidence canonicalization ---------------------------------


class TestEruleEvidenceCanonicalization:
    def test_band_evidence_canonicalization_direction_independent(self):
        # "kathryn~jonathan|band=loose|model=m" from either direction must
        # canonicalize to the SAME string, with the annotations staying a
        # pair-level suffix (never migrating onto one name token).
        c1 = _canonical_evidence(
            {"first": "kathryn~jonathan|band=loose|model=m"})
        c2 = _canonical_evidence(
            {"first": "jonathan~kathryn|band=loose|model=m"})
        assert c1 == c2
        assert c1["first"] == "jonathan~kathryn|band=loose|model=m"

    def test_legacy_fuzzy_evidence_canonicalization_unchanged(self):
        c1 = _canonical_evidence({"first": "thompson~thompsno"})
        c2 = _canonical_evidence({"first": "thompsno~thompson"})
        assert c1 == c2 == {"first": "thompsno~thompson"}

    def test_ingest_linkage_order_independent_with_embedding(self):
        # The domain key question: identical patient SETS produce identical
        # Linkage/audit decisions regardless of insertion order.
        a = _patient("p1", "Jonathan")
        b = _patient("p2", "Kathryn")
        stored = {}
        for label, order in (("ab", [a, b]), ("ba", [b, a])):
            conn = _fresh_conn()
            match_on_ingest(conn, order, "run1")
            stored[label] = json.dumps(load_linkage_resources(conn),
                                       sort_keys=True)
        assert stored["ab"] == stored["ba"]
        # and the evidence value keeps the annotation as a pair suffix
        resource = json.loads(stored["ab"])[0]
        evidence = [
            e for e in resource["extension"][0]["extension"]
            if e["url"] == "evidence"
        ][0]["extension"]
        first = [e["valueString"] for e in evidence if e["url"] == "first"][0]
        assert first == (
            "jonathan~kathryn|band=loose|model="
            f"{name_embedding.embedding_model_id()}")


# --- QA-D14S-002: non-Latin names and the embedding bands -------------------


class TestNonLatinNameEmbeddingBands:
    def test_distinct_non_latin_names_have_no_band(self):
        # The model's normalization keeps only a-z; a name with no Latin
        # letters carries NO signal — the band must be None, not `tight`.
        assert name_embedding.name_distance_band("李伟", "李娜") is None
        assert name_embedding.name_distance_band("田中", "李伟") is None
        # one side signal-less is equally vacuous (conservative: no band)
        assert name_embedding.name_distance_band("Li", "李娜") is None
        # Latin names still band (control)
        band = name_embedding.name_distance_band("Kathryn", "Jonathan")
        assert band is not None

    def test_e3_does_not_false_link_non_latin_siblings(self):
        # Twins sharing DOB + street + family name, distinct non-Latin
        # given names: legacy comparators reject; the embedding rules must
        # not link them either.
        conn = _fresh_conn()
        address = {"line": ["10 Oak St"], "city": "Springfield",
                   "state": "IL", "postalCode": "62704"}
        index_patient(conn, _patient("t1", "李伟", last="李",
                                     dob="2000-01-01", phone="555-060-0600",
                                     address=address))
        result = match_patient(
            conn, _patient("t2", "李娜", last="李", dob="2000-01-01",
                           phone="555-060-0600", address=address),
            exclude=frozenset({"t2"}))
        assert result.outcome == "no_match"


# --- REV-26-003: typed calibration invariant --------------------------------


class TestBandTableCalibrationInvariant:
    def test_out_of_budget_band_table_raises_value_error(self, monkeypatch):
        monkeypatch.setattr(
            matching_rules, "BAND_U_VALUES",
            (("mid", 0.034), ("loose", 0.12)))
        with pytest.raises(ValueError, match="tight band must be approvable"):
            matching_rules.embedding_rules()
