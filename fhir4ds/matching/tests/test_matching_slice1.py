"""Slice-1 tests: normalizers, extraction, store, rule table, exact engine."""

from __future__ import annotations

import duckdb
import pytest

from fhir4ds.matching import (
    CATEGORY1_RULES,
    MatchResult,
    create_matching_tables,
    exact_candidates,
    extract_patient_fields,
    index_patient,
    match_patient,
    nickname_set,
    norm_date,
    norm_name_parts,
    norm_phone,
    norm_text,
    parse_suffix,
    register_matching_macros,
    suffix_conflict,
)
from fhir4ds.matching import __version__ as matching_version


# ---------------------------------------------------------------------------
# norm_text
# ---------------------------------------------------------------------------


class TestNormText:
    def test_diacritic_fold(self):
        assert norm_text("Müller") == "muller"

    def test_punctuation_and_case(self):
        assert norm_text("O'Brien-Smith, Jr.") == "obriensmith jr"
        assert norm_text("  St.   Louis ") == "st louis"

    def test_empty_and_none(self):
        assert norm_text(None) is None
        assert norm_text("   ") is None
        assert norm_text("!!!") is None

    def test_unicode_fullwidth(self):
        # NFKD also folds fullwidth forms
        assert norm_text("ＡＢＣ") == "abc"


# ---------------------------------------------------------------------------
# norm_phone
# ---------------------------------------------------------------------------


class TestNormPhone:
    def test_basic_formatting(self):
        assert norm_phone("(206) 555-0123") == "2065550123"
        assert norm_phone("206-555-0123") == "2065550123"

    def test_leading_country_code(self):
        assert norm_phone("1-206-555-0123") == "2065550123"
        assert norm_phone("+12065550123") == "2065550123"

    def test_placeholders_rejected(self):
        assert norm_phone("555-555-5555") is None
        assert norm_phone("000-000-0000") is None
        assert norm_phone("111-111-1111") is None  # all same digit
        assert norm_phone("9999999999") is None

    def test_invalid_lengths(self):
        assert norm_phone("206555012") is None  # 9 digits
        assert norm_phone("20655501234") is None  # 11 not starting with 1
        assert norm_phone("") is None
        assert norm_phone(None) is None


# ---------------------------------------------------------------------------
# norm_date
# ---------------------------------------------------------------------------


class TestNormDate:
    def test_valid(self):
        assert norm_date("1980-02-29") == "1980-02-29"

    def test_partial_and_malformed(self):
        assert norm_date("1980-02") is None
        assert norm_date("1980/02/01") is None
        assert norm_date("1980-13-01") is None
        assert norm_date("1980-02-30") is None
        assert norm_date(None) is None

    def test_future_rejected(self):
        assert norm_date("2099-01-01") is None

    def test_over_120y_rejected(self):
        assert norm_date("1890-01-01") is None

    def test_as_of_determinism_carve_out(self):
        """AMUX-134 review: ``as_of`` pins the wall-clock reference so the
        future/>120y rejections are deterministic."""
        import datetime as dt

        pinned = dt.date(2030, 6, 1)
        # future relative to the pinned date, valid relative to today
        assert norm_date("2030-06-02", as_of=pinned) is None
        assert norm_date("2030-06-01", as_of=pinned) == "2030-06-01"
        # past relative to the pinned date
        assert norm_date("2030-05-31", as_of=pinned) == "2030-05-31"
        # >120y relative to the pinned date only
        assert norm_date("1920-06-01", as_of=pinned) == "1920-06-01"
        assert norm_date("1920-06-01", as_of=dt.date(2050, 1, 1)) is None
        # default still works (today's wall clock)
        assert norm_date("1980-02-29") == "1980-02-29"


# ---------------------------------------------------------------------------
# names, suffixes, nicknames
# ---------------------------------------------------------------------------


class TestNames:
    def test_suffix_split(self):
        assert norm_name_parts("Smith Jr.") == (["smith"], ["jr"])
        assert norm_name_parts("John Smith III") == (["john", "smith"], ["iii"])

    def test_parse_suffix(self):
        assert parse_suffix("Jr.") == "jr"
        assert parse_suffix("SR") == "sr"
        assert parse_suffix("IV") == "iv"
        assert parse_suffix("V.") == "v"
        assert parse_suffix("Smith") is None

    def test_placeholders(self):
        assert norm_name_parts("John Doe") is None
        assert norm_name_parts("Test Patient") is None
        assert norm_name_parts("Baby Boy") is None
        assert norm_name_parts("Baby Girl") is None
        assert norm_name_parts("Jane Doe") is None

    def test_suffix_conflict(self):
        assert suffix_conflict(["jr"], ["sr"]) is True
        assert suffix_conflict(["jr"], ["jr"]) is False
        assert suffix_conflict([], ["sr"]) is False
        assert suffix_conflict(["ii"], []) is False

    def test_nickname_sets(self):
        assert "bob" in nickname_set("Robert")
        assert "robert" in nickname_set("Bob")
        assert nickname_set("Robert") is nickname_set("Bob")
        # unknown names are singletons containing themselves
        assert nickname_set("Xyzzy") == frozenset({"xyzzy"})
        assert len(nickname_set("Elizabeth")) >= 4


# ---------------------------------------------------------------------------
# extraction
# ---------------------------------------------------------------------------

PATIENT = {
    "resourceType": "Patient",
    "id": "p1",
    "name": [{"use": "official", "family": "Müller", "given": ["Robert", "Jr."]}],
    "birthDate": "1955-05-05",
    "telecom": [
        {"system": "phone", "value": "(206) 555-0123"},
        {"system": "email", "value": "Bob.Müller@Example.COM"},
    ],
    "address": [{"line": ["123 Main St., Apt 4"]}],
    "identifier": [
        {"system": "http://hl7.org/fhir/sid/us-ssn", "value": "123-45-6789"},
        {"system": "http://example.org/mbi", "value": "1EG4-TE5-MK73"},
        {"system": "https://payer.example.org/member-id", "value": "M-99881"},
        {"system": "urn:example:driver-license", "value": "WDL-ABC-123"},
    ],
}


class TestExtraction:
    def test_full_fixture(self):
        f = extract_patient_fields(PATIENT)
        assert f["first"] == ["robert"]
        assert f["last"] == ["muller"]
        assert f["suffix"] == ["jr"]
        assert f["dob"] == ["1955-05-05"]
        assert f["phone"] == ["2065550123"]
        assert f["email"] == ["bob.muller@example.com"]
        assert f["street_line"] == ["123 main st apt 4"]
        assert f["ssn4"] == ["6789"]
        assert f["mbi"] == ["1eg4te5mk73"]
        assert f["member_id"] == ["m99881"]
        # unclassified system-scoped identifier -> namespace_id pair
        assert f["namespace_id"] == ["urn:example:driver-license::wdlabc123"]

    def test_itin_last4(self):
        p = {"identifier": [{"system": "http://example.org/itin", "value": "912-88-9999"}]}
        assert extract_patient_fields(p)["itin4"] == ["9999"]

    def test_subscriber(self):
        p = {"identifier": [{"system": "https://payer.example.org/subscriberId", "value": "S-1"}]}
        assert extract_patient_fields(p)["subscriber_id"] == ["s1"]

    def test_placeholder_name_dropped(self):
        p = {"name": [{"family": "Doe", "given": ["John"]}], "birthDate": "1990-01-01"}
        assert "first" not in extract_patient_fields(p)
        assert "last" not in extract_patient_fields(p)

    def test_pathological_given_entry_skipped(self):
        """AMUX-134 review: ``given: 5`` is skipped, not crashed on."""
        p = {"name": [{"family": "Smith", "given": [5, "Alice"]}]}
        assert extract_patient_fields(p)["first"] == ["alice"]
        p_all_bad = {"name": [{"family": "Smith", "given": [5, None]}]}
        assert "first" not in extract_patient_fields(p_all_bad)

    def test_pathological_address_line_skipped(self):
        """AMUX-134 review: ``line: 42`` is skipped, not crashed on."""
        p = {"address": [{"line": [42, "123 Main St"]}]}
        assert extract_patient_fields(p)["street_line"] == ["123 main st"]
        p_all_bad = {"address": [{"line": [42]}]}
        assert "street_line" not in extract_patient_fields(p_all_bad)

    def test_pathological_non_dict_name_entry_skipped(self):
        """AMUX-134 review: non-dict name entries are skipped, not crashed on."""
        p = {
            "name": [
                "not-a-name",
                5,
                {"use": "official", "family": "Smith", "given": ["Alice"]},
            ]
        }
        fields = extract_patient_fields(p)
        assert fields["first"] == ["alice"]
        assert fields["last"] == ["smith"]

    def test_pathological_non_dict_container_entries_skipped_dom14_skeptic(self):
        """D14 SKEPTIC (v0.0.25): non-dict address/telecom/identifier entries
        are skipped, not crashed on — crash-free normalizer doctrine."""
        p = {
            "address": ["not-an-address", {"line": ["123 Main St"]}],
            "telecom": ["nope", None, 7],
            "identifier": ["x", 3, None],
        }
        fields = extract_patient_fields(p)
        assert fields["street_line"] == ["123 main st"]
        assert "phone" not in fields
        assert "namespace_id" not in fields

    def test_pathological_non_string_identifier_system_skipped_dom14_skeptic(self):
        """D14 SKEPTIC: a non-string identifier ``system`` (dict/number) must
        not reach ``.lower()``; the identifier is treated as system-less."""
        p = {
            "identifier": [
                {"system": {"nested": True}, "value": "V1"},
                {"system": 42, "value": "V2"},
                {"value": "V3"},  # genuinely absent system (existing behavior)
            ]
        }
        fields = extract_patient_fields(p)
        assert "namespace_id" not in fields
        assert "ssn4" not in fields

    def test_pathological_non_string_telecom_value_rejected_dom14_skeptic(self):
        """D14 SKEPTIC: a non-string telecom ``value`` (e.g. a phone stored
        as a number) is rejected, not crashed on."""
        p = {"telecom": [{"system": "phone", "value": 2065550100}]}
        fields = extract_patient_fields(p)
        assert "phone" not in fields

    def test_pathological_non_dict_address_entry_skipped_dom14_skeptic(self):
        p = {"address": ["flat", 9, {"line": ["742 Evergreen Terrace"]}]}
        fields = extract_patient_fields(p)
        assert fields["street_line"] == ["742 evergreen terrace"]

    def test_empty_resource(self):
        assert extract_patient_fields({}) == {}


# ---------------------------------------------------------------------------
# rule table
# ---------------------------------------------------------------------------


class TestRuleTable:
    def test_29_rules_ordered(self):
        assert len(CATEGORY1_RULES) == 29
        keys = [(r.p_collision, r.rule_id) for r in CATEGORY1_RULES]
        assert keys == sorted(keys)

    def test_anchors(self):
        by_id = {r.rule_id: r for r in CATEGORY1_RULES}
        # upstream Table-3 u-probability products (float products carry ULP
        # drift — the values are computed at import like upstream)
        assert by_id["01"].p_collision == pytest.approx(3.0e-13)
        assert by_id["04"].p_collision == pytest.approx(1.0e-12)
        assert by_id["05"].p_collision == pytest.approx(1.0e-12)
        assert by_id["22"].p_collision == pytest.approx(1.0e-15)
        assert by_id["30"].p_collision == pytest.approx(5.0e-13)
        assert not by_id["22"].p_estimated

    def test_first_rule_is_namespace(self):
        # lowest P -> evaluated first
        assert CATEGORY1_RULES[0].rule_id == "22"


# ---------------------------------------------------------------------------
# store + engine end-to-end
# ---------------------------------------------------------------------------


def _conn():
    conn = duckdb.connect()
    create_matching_tables(conn)
    register_matching_macros(conn)
    return conn


DUP_A = {
    "resourceType": "Patient",
    "id": "dup-a",
    "name": [{"use": "official", "family": "Müller", "given": ["Robert"]}],
    "birthDate": "1955-05-05",
    "telecom": [{"system": "phone", "value": "(206) 555-0123"}],
    "address": [{"line": ["123 Main St."]}],
}
DUP_B = {
    "resourceType": "Patient",
    "id": "dup-b",
    "name": [{"use": "official", "family": "Muller", "given": ["Robert"]}],
    "birthDate": "1955-05-05",
    "telecom": [{"system": "phone", "value": "206-555-0123"}],
    "address": [{"line": ["123 MAIN STREET"]}],
}
UNRELATED = {
    "resourceType": "Patient",
    "id": "other",
    "name": [{"use": "official", "family": "Nguyen", "given": ["Thi"]}],
    "birthDate": "1990-11-11",
    "telecom": [{"system": "phone", "value": "212-555-9898"}],
    "address": [{"line": ["99 Oak Rd"]}],
}


class TestStore:
    def test_index_and_candidates(self):
        conn = _conn()
        assert index_patient(conn, DUP_A) > 0
        assert exact_candidates(conn, "last", "muller") == ["dup-a"]
        assert exact_candidates(conn, "phone", "2065550123") == ["dup-a"]
        assert exact_candidates(conn, "first", "nope") == []

    def test_index_idempotent(self):
        conn = _conn()
        index_patient(conn, DUP_A)
        n = conn.execute("SELECT COUNT(*) FROM field_values").fetchone()[0]
        index_patient(conn, DUP_A)
        assert conn.execute("SELECT COUNT(*) FROM field_values").fetchone()[0] == n

    def test_requires_id(self):
        with pytest.raises(ValueError):
            index_patient(_conn(), {"resourceType": "Patient"})

    def test_rejects_non_fhir_id(self):
        """AMUX-134 review: ids must match the FHIR id pattern — protects
        the '|' pair-key used by the linkage table from injection."""
        conn = _conn()
        for bad in ("a|b", "a|Patient/x", "sp ace", "sl/ash", "", "x" * 65, "café"):
            with pytest.raises(ValueError):
                index_patient(
                    conn, {"resourceType": "Patient", "id": bad, "birthDate": "1990-01-01"}
                )
        # legal ids (including all FHIR id punctuation) still index
        assert index_patient(_conn(), DUP_A) > 0


class TestEngine:
    def test_match_finds_duplicate(self):
        conn = _conn()
        for p in (DUP_A, UNRELATED):
            index_patient(conn, p)
        result = match_patient(conn, DUP_B)
        assert result.outcome == "match"
        assert result.matched_ids == ("dup-a",)
        # slice 2: fuzzy rules are evaluated; nothing is skipped anymore
        assert result.skipped_rules == ()
        assert result.rule_id == "02"  # First + Last* + DOB* + Phone, all exact here
        assert result.match_type == "exact"
        assert result.confidence is not None and 0 < result.confidence <= 1

    def test_no_match(self):
        conn = _conn()
        for p in (DUP_A, DUP_B):
            index_patient(conn, p)
        result = match_patient(conn, UNRELATED)
        assert result.outcome == "no_match"
        assert result.matched_ids == ()
        assert result.rule_id is None

    def test_determinism(self):
        conn = _conn()
        for p in (DUP_A, DUP_B, UNRELATED):
            index_patient(conn, p)
        r1 = match_patient(conn, DUP_B)
        r2 = match_patient(conn, DUP_B)
        assert r1 == r2  # frozen dataclass equality

    def test_ambiguous(self):
        conn = _conn()
        # two corpus patients sharing first+last+dob+phone -> rule 02 ambiguity
        # (slice 2 corrected table: there is no First+Last+DOB-alone rule)
        a = {
            "resourceType": "Patient",
            "id": "dup-a",
            "name": [{"family": "Muller", "given": ["Robert"]}],
            "birthDate": "1955-05-05",
            "telecom": [{"system": "phone", "value": "206-555-0123"}],
        }
        b = {
            "resourceType": "Patient",
            "id": "dup-c",
            "name": [{"family": "Muller", "given": ["Robert"]}],
            "birthDate": "1955-05-05",
            "telecom": [{"system": "phone", "value": "(206) 555-0123"}],
        }
        for p in (a, b):
            index_patient(conn, p)
        cand = {
            "resourceType": "Patient",
            "id": "cand",
            "name": [{"family": "Müller", "given": ["Robert"]}],
            "birthDate": "1955-05-05",
            "telecom": [{"system": "phone", "value": "2065550123"}],
        }
        result = match_patient(conn, cand)
        assert result.outcome == "ambiguous"
        assert result.matched_ids == ("dup-a", "dup-c")
        assert result.rule_id == "02"

    def test_suffix_conflict_negates(self):
        conn = _conn()
        jr = {
            "resourceType": "Patient",
            "id": "jr",
            "name": [{"family": "Smith", "given": ["John", "Jr."]}],
            "birthDate": "1960-01-01",
            "telecom": [{"system": "phone", "value": "206-555-0123"}],
        }
        index_patient(conn, jr)
        # same last+dob+phone but Sr -> suffix conflict must negate rule 30
        sr = {
            "resourceType": "Patient",
            "id": "sr-cand",
            "name": [{"family": "Smith", "given": ["John", "Sr."]}],
            "birthDate": "1960-01-01",
            "telecom": [{"system": "phone", "value": "2065550123"}],
        }
        result = match_patient(conn, sr)
        assert result.outcome == "no_match"

    def test_namespace_rule_fires_first(self):
        conn = _conn()
        ns = {
            "resourceType": "Patient",
            "id": "ns-a",
            "identifier": [{"system": "urn:x:dl", "value": "WDL-1"}],
        }
        index_patient(conn, ns)
        cand = {
            "resourceType": "Patient",
            "id": "ns-cand",
            "identifier": [{"system": "urn:X:DL", "value": "WDL 1"}],
        }
        result = match_patient(conn, cand)
        assert result.outcome == "match"
        assert result.rule_id == "22"
        assert result.confidence == 1.0 - 1.0e-15
        assert "namespace_id" in result.evidence


def test_version():
    assert matching_version == "0.0.25"  # aligned with root per test_version doctrine
