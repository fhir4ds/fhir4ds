"""Slice-5 tests: SQL-on-FHIR artifacts (ViewDefinition + SQLQuery).

The matching layer surfaces field extraction as a SQL-on-FHIR v2
ViewDefinition (RAW fields — normalization is NOT applied there) and the
exact-rule candidate lookup as a SQLQuery Library over the normalized
``field_values`` index. The Python engine remains the decision authority.

Design reference:
fhir4ds-private/docs/architecture/plans/FEATURE_PATIENT_MATCHING.md
("Architecture — DuckDB-native, no new services").
"""

from __future__ import annotations

import base64
import json

import duckdb
import pytest

import fhir4ds
from fhir4ds.cql.loader.fhir_loader import FHIRDataLoader
from fhir4ds.matching import (
    create_matching_tables,
    extract_patient_fields,
    index_patient,
    norm_text,
)
from fhir4ds.matching.artifacts import (
    ARTIFACTS_DIR,
    EXACT_CANDIDATES_SQLQUERY_PATH,
    PATIENT_MATCH_FIELDS_VD_PATH,
    load_exact_candidates_dict,
    load_exact_candidates_sqlquery,
    load_patient_match_fields_dict,
    load_patient_match_fields_vd,
)
from fhir4ds.sqlquery import SQLQuery, SQLQueryRunner
from fhir4ds.viewdef import ViewDefinition, SQLGenerator, parse_view_definition


# Fixture patients: p1/p2 are exact-rule duplicates (name + DOB after
# normalization), p3 is unique. p1 carries diacritics, formatting and the
# full identifier spread so RAW-vs-normalized fidelity is observable.
PATIENTS = [
    {
        "resourceType": "Patient",
        "id": "p1",
        "name": [{"use": "official", "family": "Müller", "given": ["José", "J"]}],
        "birthDate": "1990-05-01",
        "telecom": [
            {"system": "phone", "value": "(206) 555-0123"},
            {"system": "email", "value": "Jose.Mueller@Example.COM"},
        ],
        "address": [{"line": ["123 Main St.", "Apt 4"], "city": "Seattle"}],
        "identifier": [
            {"system": "http://hl7.org/fhir/sid/us-ssn", "value": "123-45-6789"},
            {"system": "http://example.org/mbi", "value": "1EG4-TE5-MK73"},
            {"system": "urn:oid:member-x", "value": "M-999"},
            {"system": "urn:unknown-system", "value": "ZZ 12"},
        ],
    },
    {
        "resourceType": "Patient",
        "id": "p2",
        "name": [{"family": "Mueller", "given": ["Jose"]}],
        "birthDate": "1990-05-01",
    },
    {
        "resourceType": "Patient",
        "id": "p3",
        "name": [{"family": "Unique", "given": ["Zoe"]}],
        "birthDate": "1950-01-01",
    },
]


@pytest.fixture()
def con():
    """Connection with native/UDF registration, resources table, index."""
    conn = duckdb.connect(config={"allow_unsigned_extensions": True})
    fhir4ds.register(conn)
    loader = FHIRDataLoader(conn)
    loader.load_resources(PATIENTS)
    create_matching_tables(conn)
    for p in PATIENTS:
        index_patient(conn, p)
    yield conn
    conn.close()


def _vd_rows(conn) -> list[dict]:
    vd = load_patient_match_fields_vd()
    sql = SQLGenerator(source_table="resources").generate(vd)
    cur = conn.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _field_values(conn, patient_id: str) -> dict[str, list[str]]:
    rows = conn.execute(
        "SELECT field_name, value FROM field_values WHERE patient_id = ? "
        "ORDER BY field_name, value",
        [patient_id],
    ).fetchall()
    out: dict[str, list[str]] = {}
    for name, value in rows:
        out.setdefault(name, []).append(value)
    return out


# ---------------------------------------------------------------------------
# Artifact registry + parsing (no schema drift)
# ---------------------------------------------------------------------------


class TestArtifactsParse:
    def test_artifact_files_exist(self):
        assert PATIENT_MATCH_FIELDS_VD_PATH.is_file()
        assert EXACT_CANDIDATES_SQLQUERY_PATH.is_file()

    def test_vd_parses_with_viewdef_parser(self):
        vd = load_patient_match_fields_vd()
        assert isinstance(vd, ViewDefinition)
        assert vd.resource == "Patient"
        columns = vd.select[0].column
        names = [c.name for c in columns]
        assert names == [
            "patient_id", "first", "last", "dob", "phone", "email", "street",
            "ssn4raw", "ssn4", "mbi", "member_id", "subscriber_id", "legal_id",
            "namespace_id",
        ]
        # Collection columns are declared as such (all except patient_id/dob).
        for col in columns:
            if col.name in ("patient_id", "dob"):
                assert not col.collection
            else:
                assert col.collection, col.name

    def test_vd_dict_roundtrips_through_parser(self):
        # The on-disk JSON stays parseable verbatim — no drift between the
        # artifact and the parser's accepted schema.
        vd = parse_view_definition(json.dumps(load_patient_match_fields_dict()))
        assert isinstance(vd, ViewDefinition)

    def test_sqlquery_parses_with_sqlquery_parser(self):
        sq = load_exact_candidates_sqlquery()
        assert isinstance(sq, SQLQuery)
        assert sq.id == "exact-candidates"
        assert [p.name for p in sq.parameter] == ["patient_id"]
        assert sq.parameter[0].type == "string"
        body = sq.content[0].data
        assert "field_values" in body
        assert "$patient_id" in body

    def test_sqlquery_data_is_valid_base64_verbatim_json(self):
        raw = load_exact_candidates_dict()
        entry = raw["content"][0]
        assert entry["contentType"] == "application/sql;dialect=duckdb"
        decoded = base64.b64decode(entry["data"], validate=True).decode("utf-8")
        assert decoded.strip().startswith("SELECT DISTINCT fv.patient_id")


# ---------------------------------------------------------------------------
# ViewDefinition end-to-end: raw substrate fidelity
# ---------------------------------------------------------------------------


class TestViewDefinitionRawFields:
    def test_generates_and_executes_over_loader_resources_table(self, con):
        rows = _vd_rows(con)
        assert [r["patient_id"] for r in rows] == ["p1", "p2", "p3"]

    def test_raw_columns_match_extract_patient_fields_population(self, con):
        """Same patients, corresponding multivalue contents (raw vs
        normalized is fine — assert the correspondence, not equality)."""
        by_id = {r["patient_id"]: r for r in _vd_rows(con)}
        for p in PATIENTS:
            pid = p["id"]
            extracted = extract_patient_fields(p)
            # first: every normalized engine value must be the norm of a
            # raw VD value (single-token given names in the fixture).
            assert {norm_text(v) for v in by_id[pid]["first"]} == set(extracted.get("first", []))
            assert {norm_text(v) for v in by_id[pid]["last"]} == set(extracted.get("last", []))
            # dob: raw == normalized for valid ISO dates.
            if by_id[pid]["dob"]:
                assert by_id[pid]["dob"] == extracted["dob"][0]
            else:
                assert "dob" not in extracted
            # ssn4: the VD's last-4 expression must equal the normalizer's.
            assert by_id[pid]["ssn4"] == extracted.get("ssn4", [])
            # namespace_id: VD emits the RAW system + value; the normalizer
            # lowercases the system and strips value whitespace.
            raw_ns = by_id[pid]["namespace_id"]
            for raw in raw_ns:
                folded = raw.lower().replace(" ", "")
                assert any(folded == n.replace(" ", "")
                           for n in extracted.get("namespace_id", [])), raw

    def test_raw_fidelity_diacritics_preserved(self, con):
        """VD output is RAW: 'Müller'/'José' stay un-folded while the
        field_values index holds the folded forms."""
        p1 = _vd_rows(con)[0]
        assert "Müller" in p1["last"]
        assert "José" in p1["first"]
        assert p1["phone"] == ["(206) 555-0123"]  # raw formatting kept
        assert p1["email"] == ["Jose.Mueller@Example.COM"]  # raw case kept
        assert p1["street"] == ["123 Main St."]  # punctuation kept
        assert p1["ssn4raw"] == ["123-45-6789"]  # raw identifier kept

    def test_identifier_classes_route_to_dedicated_columns(self, con):
        p1 = _vd_rows(con)[0]
        assert p1["ssn4"] == ["6789"]  # digits-only last-4 (normalized shape)
        assert p1["mbi"] == ["1EG4-TE5-MK73"]
        assert p1["member_id"] == ["M-999"]
        assert p1["subscriber_id"] == []
        assert p1["legal_id"] == []
        # Only the unclassified system-scoped identifier falls through to
        # namespace_id (v1 semantics from extract_patient_fields).
        assert p1["namespace_id"] == ["urn:unknown-system::ZZ 12"]

    def test_empty_patient_emits_empty_collections(self, con):
        p2 = next(r for r in _vd_rows(con) if r["patient_id"] == "p2")
        for col in ("phone", "email", "street", "ssn4raw", "ssn4", "mbi",
                    "member_id", "subscriber_id", "legal_id", "namespace_id"):
            assert p2[col] == [], col


# ---------------------------------------------------------------------------
# SQLQuery end-to-end: exact-rule candidate lookup
# ---------------------------------------------------------------------------


def _resolver(canonical: str):
    raise KeyError(f"no dependencies declared, cannot resolve {canonical}")


class TestExactCandidatesSQLQuery:
    def test_runner_returns_duplicate_partner(self, con):
        runner = SQLQueryRunner(con, resolver=_resolver)
        # p2 shares exact normalized (first='jose', last='mueller',
        # dob='1990-05-01') rows with p1.
        assert runner.execute(load_exact_candidates_sqlquery(), {"patient_id": "p2"}) == [("p1",)]
        assert runner.execute(load_exact_candidates_sqlquery(), {"patient_id": "p1"}) == [("p2",)]

    def test_runner_unique_patient_returns_empty(self, con):
        runner = SQLQueryRunner(con, resolver=_resolver)
        assert runner.execute(load_exact_candidates_sqlquery(), {"patient_id": "p3"}) == []

    def test_body_parities_python_exact_candidates(self, con):
        """The artifact's SQL must agree with store.exact_candidates for
        every shared (field, value) row of the fixture corpus."""
        from fhir4ds.matching import exact_candidates

        runner = SQLQueryRunner(con, resolver=_resolver)
        artifact = runner.execute(load_exact_candidates_sqlquery(), {"patient_id": "p2"})
        fv = _field_values(con, "p2")
        expected = sorted(
            {
                pid
                for fname, values in fv.items()
                for value in values
                for pid in exact_candidates(con, fname, value)
                if pid != "p2"
            }
        )
        assert artifact == [(pid,) for pid in expected]


# ---------------------------------------------------------------------------
# Consistency doctrine: VD is the RAW substrate, normalization is Python-side
# ---------------------------------------------------------------------------


class TestRawSubstrateVsNormalizedIndex:
    def test_field_values_differs_from_vd_output_by_design(self, con):
        """field_values (normalized) is NOT the VD output (raw) — by design.

        The ViewDefinition (patient_match_fields.vd.json) is the auditable
        RAW substrate; the CMS A-D normalization (diacritic folding, phone
        digit extraction, identifier whitespace stripping) lives in the
        Python normalizer layer (fhir4ds.matching.normalizers) that feeds
        field_values. See
        fhir4ds-private/docs/architecture/plans/FEATURE_PATIENT_MATCHING.md
        (DuckDB-native architecture; Python engine is the decision
        authority).
        """
        p1_vd = _vd_rows(con)[0]
        fv = _field_values(con, "p1")
        # Raw diacritics in the VD, folded in the index.
        assert "Müller" in p1_vd["last"]
        assert fv["last"] == ["muller"]
        # Raw phone formatting in the VD, dialable digits in the index.
        assert p1_vd["phone"] == ["(206) 555-0123"]
        assert fv["phone"] == ["2065550123"]
        # Raw email case in the VD, folded+stripped in the index.
        assert p1_vd["email"] == ["Jose.Mueller@Example.COM"]
        assert fv["email"] == ["jose.mueller@example.com"]
        # Raw street punctuation vs normalized text.
        assert p1_vd["street"] == ["123 Main St."]
        assert fv["street_line"] == ["123 main st"]
        # Raw identifier vs whitespace-stripped normalized identifier.
        assert p1_vd["namespace_id"] == ["urn:unknown-system::ZZ 12"]
        assert fv["namespace_id"] == ["urn:unknown-system::zz12"]
