"""Slice-2 tests: upstream P-value pinning, fuzzy comparators, engine fuzzy
integration (fuzzy rule evaluation, match_type, DOB +/-1 day, nickname
equivalence)."""

from __future__ import annotations

import duckdb
import pytest

from fhir4ds.matching import (
    CATEGORY1_RULES,
    FUZZY_NAME_MIN_LEN,
    create_matching_tables,
    damerau_le1,
    dob_fuzzy_matches,
    index_patient,
    match_patient,
    name_fuzzy_match,
    register_matching_macros,
)
from fhir4ds.matching.rules import EXACT, FUZZY


# ---------------------------------------------------------------------------
# P-value pinning fixture (upstream cms-hte-patient-matching v3.4.0)
# ---------------------------------------------------------------------------

# (rule_id, fields with modes, p_collision exact, p_collision fuzzy,
#  p_fuzzy_fields) — transcribed from upstream table2_rules.py +
# collision.py (Table-3 u products), fetched 2026-11-17.
PINNED: list[tuple[str, tuple[tuple[str, str], ...], float, float, frozenset[str]]] = [
    ("01", (("first", FUZZY), ("last", FUZZY), ("dob", FUZZY), ("street_line", FUZZY)), 3.0e-13, 9.0e-13, frozenset({"first", "last"})),
    ("02", (("first", EXACT), ("last", FUZZY), ("dob", FUZZY), ("phone", EXACT)), 1.0e-14, 2.0e-14, frozenset({"last"})),
    ("03", (("first", FUZZY), ("last", FUZZY), ("dob", FUZZY), ("email", EXACT)), 1.0e-14, 3.0e-14, frozenset({"first", "last"})),
    ("04", (("first", FUZZY), ("last", EXACT), ("dob", EXACT), ("ssn4", EXACT)), 1.0e-12, 1.5e-12, frozenset({"first"})),
    ("05", (("first", EXACT), ("last", FUZZY), ("dob", EXACT), ("ssn4", EXACT)), 1.0e-12, 2.0e-12, frozenset({"last"})),
    ("06", (("first", FUZZY), ("last", EXACT), ("dob", EXACT), ("itin4", EXACT)), 1.0e-12, 1.5e-12, frozenset({"first"})),
    ("07", (("first", EXACT), ("last", FUZZY), ("dob", EXACT), ("itin4", EXACT)), 1.0e-12, 2.0e-12, frozenset({"last"})),
    ("08", (("first", EXACT), ("dob", EXACT), ("mbi", EXACT)), 2.0e-12, 2.0e-12, frozenset()),
    ("09", (("first", EXACT), ("dob", EXACT), ("legal_id", EXACT)), 2.0e-12, 2.0e-12, frozenset()),
    ("10", (("last", FUZZY), ("dob", FUZZY), ("legal_id", EXACT)), 5.0e-13, 1.0e-12, frozenset({"last"})),
    ("11", (("first", EXACT), ("dob", EXACT), ("phone", EXACT)), 2.0e-12, 2.0e-12, frozenset()),
    ("12", (("first", EXACT), ("dob", EXACT), ("email", EXACT)), 2.0e-12, 2.0e-12, frozenset()),
    ("13", (("first", EXACT), ("phone", EXACT), ("ssn4", EXACT)), 2.0e-12, 2.0e-12, frozenset()),
    ("14", (("first", EXACT), ("phone", EXACT), ("itin4", EXACT)), 2.0e-12, 2.0e-12, frozenset()),
    ("15", (("first", EXACT), ("email", EXACT), ("ssn4", EXACT)), 2.0e-12, 2.0e-12, frozenset()),
    ("16", (("first", EXACT), ("email", EXACT), ("itin4", EXACT)), 2.0e-12, 2.0e-12, frozenset()),
    ("17", (("phone", EXACT), ("mbi", EXACT)), 1.0e-12, 1.0e-12, frozenset()),
    ("18", (("phone", EXACT), ("legal_id", EXACT)), 1.0e-12, 1.0e-12, frozenset()),
    ("19", (("email", EXACT), ("mbi", EXACT)), 1.0e-12, 1.0e-12, frozenset()),
    ("20", (("email", EXACT), ("legal_id", EXACT)), 1.0e-12, 1.0e-12, frozenset()),
    ("21", (("legal_id", EXACT), ("mbi", EXACT)), 1.0e-12, 1.0e-12, frozenset()),
    ("22", (("namespace_id", EXACT),), 1.0e-15, 1.0e-15, frozenset()),
    ("23", (("first", EXACT), ("dob", EXACT), ("member_id", EXACT)), 2.0e-12, 2.0e-12, frozenset()),
    ("24", (("last", FUZZY), ("dob", FUZZY), ("member_id", EXACT)), 5.0e-13, 1.0e-12, frozenset({"last"})),
    ("25", (("phone", EXACT), ("member_id", EXACT)), 1.0e-12, 1.0e-12, frozenset()),
    ("26", (("email", EXACT), ("member_id", EXACT)), 1.0e-12, 1.0e-12, frozenset()),
    ("27", (("first", FUZZY), ("last", EXACT), ("dob", EXACT), ("subscriber_id", EXACT)), 1.0e-12, 1.5e-12, frozenset({"first"})),
    ("28", (("first", EXACT), ("last", FUZZY), ("dob", EXACT), ("subscriber_id", EXACT)), 1.0e-12, 2.0e-12, frozenset({"last"})),
    ("30", (("last", FUZZY), ("dob", EXACT), ("phone", EXACT)), 5.0e-13, 1.0e-12, frozenset({"last"})),
]


class TestPinnedRuleTable:
    def test_all_29_rules_pinned(self):
        assert len(PINNED) == 29
        assert len(CATEGORY1_RULES) == 29

    def test_rule_tuples_match_upstream(self):
        by_id = {r.rule_id: r for r in CATEGORY1_RULES}
        for rule_id, fields, p_exact, p_fuzzy, p_fuzzy_fields in PINNED:
            rule = by_id[rule_id]
            assert rule.fields == fields, f"rule {rule_id} field drift"
            assert rule.p_collision == pytest.approx(p_exact), f"rule {rule_id} exact P drift"
            assert rule.p_collision_fuzzy == pytest.approx(p_fuzzy), f"rule {rule_id} fuzzy P drift"
            assert rule.p_fuzzy_fields == p_fuzzy_fields, f"rule {rule_id} fuzzy-field drift"
            assert not rule.p_estimated, f"rule {rule_id} still flagged estimated"

    def test_rule_ids_follow_upstream_numbering(self):
        # rule 29 was removed upstream: ids are 01-28 plus 30
        assert {r.rule_id for r in CATEGORY1_RULES} == {
            f"{i:02d}" for i in range(1, 29)
        } | {"30"}

    def test_all_rules_within_approval_threshold_exact(self):
        for r in CATEGORY1_RULES:
            # ULP tolerance: float products like .02*1e-4*1e-6 land a hair above
            assert r.p_collision <= 2.0e-12 or r.p_collision == pytest.approx(2.0e-12)
            assert r.p_collision_fuzzy <= 2.0e-12 or r.p_collision_fuzzy == pytest.approx(2.0e-12)


# ---------------------------------------------------------------------------
# damerau_le1
# ---------------------------------------------------------------------------


class TestDamerauLe1:
    def test_equality(self):
        assert damerau_le1("smith", "smith") is True
        assert damerau_le1("", "") is True

    def test_transposition(self):
        assert damerau_le1("mei", "emi") is True
        assert damerau_le1("abc", "acb") is True
        assert damerau_le1("thompson", "thompsno") is True

    def test_insertion(self):
        assert damerau_le1("smith", "smithe") is True
        assert damerau_le1("smithe", "smith") is True

    def test_deletion(self):
        assert damerau_le1("smith", "smit") is True
        assert damerau_le1("smit", "smith") is True

    def test_substitution(self):
        assert damerau_le1("smith", "smath") is True

    def test_distance_2_rejected(self):
        assert damerau_le1("smith", "smart") is False  # 3 diffs
        assert damerau_le1("abcd", "abxy") is False  # 2 non-adjacent... 2 adjacent but not transposed
        assert damerau_le1("abc", "cba") is False  # full reversal
        assert damerau_le1("smith", "msithx") is False  # transpose + insert

    def test_length_gap_rejected(self):
        assert damerau_le1("ab", "abcde") is False
        assert damerau_le1("", "ab") is False

    def test_single_char_gap_edges(self):
        assert damerau_le1("", "a") is True
        assert damerau_le1("a", "") is True
        # gap at the tail
        assert damerau_le1("smath", "smaath") is True
        # gap in the middle
        assert damerau_le1("snith", "smith") is True


# ---------------------------------------------------------------------------
# name_fuzzy_match (nickname + DL interplay, >=5-char gate)
# ---------------------------------------------------------------------------


class TestNameFuzzyMatch:
    def test_exact_and_empty(self):
        assert name_fuzzy_match("robert", "robert") is True
        assert name_fuzzy_match("", "robert") is False
        assert name_fuzzy_match(None, "robert") is False

    def test_nickname_equivalence(self):
        assert name_fuzzy_match("bob", "robert") is True
        assert name_fuzzy_match("robert", "bob") is True
        assert name_fuzzy_match("liz", "elizabeth") is True
        # nickname equivalence works below the 5-char gate
        assert name_fuzzy_match("ed", "eddie") is True

    def test_nickname_no_cross_group(self):
        assert name_fuzzy_match("bob", "roberto") is False  # not a nickname

    def test_dl_fuzzy_at_5_chars(self):
        assert name_fuzzy_match("kirthi", "kirth1") is True  # substitution
        assert name_fuzzy_match("thompsno", "thompson") is True  # transposition

    def test_short_names_do_not_dl_match(self):
        # CMS E.3: DL fuzzy only applies at >= 5 chars on BOTH sides
        assert name_fuzzy_match("joan", "joann") is False  # 4 chars
        assert name_fuzzy_match("amy", "ame") is False
        assert FUZZY_NAME_MIN_LEN == 5

    def test_distance_2_rejected(self):
        assert name_fuzzy_match("roberts", "robersx") is False


# ---------------------------------------------------------------------------
# dob_fuzzy_matches (+/- 1 day)
# ---------------------------------------------------------------------------


class TestDobFuzzy:
    def test_exact_and_pm1(self):
        assert dob_fuzzy_matches("1980-02-29", "1980-02-29") is True
        assert dob_fuzzy_matches("1980-02-29", "1980-03-01") is True
        assert dob_fuzzy_matches("1980-02-29", "1980-02-28") is True

    def test_year_and_month_boundaries(self):
        assert dob_fuzzy_matches("2020-01-01", "2019-12-31") is True
        assert dob_fuzzy_matches("2020-12-31", "2021-01-01") is True

    def test_pm2_rejected(self):
        assert dob_fuzzy_matches("1980-02-29", "1980-03-02") is False
        assert dob_fuzzy_matches("2020-01-01", "2019-12-30") is False

    def test_malformed(self):
        assert dob_fuzzy_matches("not-a-date", "1980-02-29") is False
        assert dob_fuzzy_matches(None, "1980-02-29") is False
        assert dob_fuzzy_matches("", "") is False


# ---------------------------------------------------------------------------
# engine fuzzy integration (end-to-end)
# ---------------------------------------------------------------------------


def _conn():
    conn = duckdb.connect()
    create_matching_tables(conn)
    register_matching_macros(conn)
    return conn


# Rule 01 fixture: First* + Last* + DOB* + Street Line* (all four fuzzy)
R01_CORPUS = {
    "resourceType": "Patient",
    "id": "r01-a",
    "name": [{"use": "official", "family": "Thompson", "given": ["Robert"]}],
    "birthDate": "1955-05-05",
    "address": [{"line": ["123 Main St."]}],
}
# duplicate: last name transposed (thompson -> thompsno) + DOB off by one day
R01_DUP = {
    "resourceType": "Patient",
    "id": "r01-dup",
    "name": [{"use": "official", "family": "Thompsno", "given": ["Robert"]}],
    "birthDate": "1955-05-06",
    "address": [{"line": ["123 Main St."]}],
}
R01_FAR = {
    "resourceType": "Patient",
    "id": "r01-far",
    "name": [{"use": "official", "family": "Thompxyz", "given": ["Robert"]}],
    "birthDate": "1955-05-08",  # 3 days off
    "address": [{"line": ["123 Main St."]}],
}
UNRELATED = {
    "resourceType": "Patient",
    "id": "other",
    "name": [{"use": "official", "family": "Nguyen", "given": ["Thi"]}],
    "birthDate": "1990-11-11",
    "telecom": [{"system": "phone", "value": "212-555-9898"}],
    "address": [{"line": ["99 Oak Rd"]}],
}


class TestEngineFuzzy:
    def test_rule01_fuzzy_transposition_and_dob_off_by_one(self):
        conn = _conn()
        for p in (R01_CORPUS, UNRELATED):
            index_patient(conn, p)
        result = match_patient(conn, R01_DUP)
        assert result.outcome == "match"
        assert result.rule_id == "01"
        assert result.matched_ids == ("r01-a",)
        assert result.match_type == "fuzzy"
        # fuzzy confidence uses the fuzzy P(collision) figure
        by_id = {r.rule_id: r for r in CATEGORY1_RULES}
        assert result.confidence == pytest.approx(1.0 - by_id["01"].p_collision_fuzzy)
        # evidence records the fuzzy pair
        assert result.evidence["last"] == "thompsno~thompson"
        assert result.evidence["dob"] == "1955-05-06~1955-05-05"
        assert result.evidence["first"] == "robert"  # exact
        assert result.skipped_rules == ()

    def test_rule01_distance2_no_match(self):
        conn = _conn()
        for p in (R01_CORPUS, UNRELATED):
            index_patient(conn, p)
        result = match_patient(conn, R01_FAR)
        assert result.outcome == "no_match"
        assert result.matched_ids == ()

    def test_unrelated_no_match(self):
        conn = _conn()
        for p in (R01_CORPUS, R01_DUP):
            index_patient(conn, p)
        result = match_patient(conn, UNRELATED)
        assert result.outcome == "no_match"

    def test_rule30_fuzzy_last_exact_dob(self):
        # rule 30: Last* + DOB(exact) + Phone — no First Name so rule 02
        # (First + Last* + DOB* + Phone, lower P) cannot preempt it
        conn = _conn()
        corpus = {
            "resourceType": "Patient",
            "id": "r30-a",
            "name": [{"family": "Thompson"}],
            "birthDate": "1955-05-05",
            "telecom": [{"system": "phone", "value": "206-555-0123"}],
        }
        index_patient(conn, corpus)
        dup = {
            "resourceType": "Patient",
            "id": "r30-dup",
            "name": [{"family": "Thompsno"}],
            "birthDate": "1955-05-05",
            "telecom": [{"system": "phone", "value": "(206) 555-0123"}],
        }
        result = match_patient(conn, dup)
        assert result.outcome == "match"
        assert result.rule_id == "30"
        assert result.match_type == "fuzzy"  # last matched fuzzily
        assert result.confidence == pytest.approx(1.0 - 1.0e-12)

        # same but DOB off by one: rule 30 cannot fire (DOB exact); no other
        # rule covers this field set -> no_match
        dup_dob = dict(dup, id="r30-dup2", birthDate="1955-05-06")
        result2 = match_patient(conn, dup_dob)
        assert result2.outcome == "no_match"

    def test_exact_match_reports_exact_type(self):
        conn = _conn()
        corpus = {
            "resourceType": "Patient",
            "id": "ex-a",
            "name": [{"family": "Thompson", "given": ["Robert"]}],
            "birthDate": "1955-05-05",
            "telecom": [{"system": "phone", "value": "206-555-0123"}],
        }
        index_patient(conn, corpus)
        result = match_patient(conn, dict(corpus, id="ex-cand"))
        assert result.outcome == "match"
        assert result.match_type == "exact"

    def test_nickname_fuzzy_in_engine(self):
        # rule 01: first name "bob" vs indexed "robert" via nickname set
        conn = _conn()
        index_patient(conn, R01_CORPUS)
        cand = {
            "resourceType": "Patient",
            "id": "nick-cand",
            "name": [{"family": "Thompson", "given": ["Bob"]}],
            "birthDate": "1955-05-05",
            "address": [{"line": ["123 Main St."]}],
        }
        result = match_patient(conn, cand)
        assert result.outcome == "match"
        assert result.rule_id == "01"
        assert result.match_type == "fuzzy"
        assert result.evidence["first"] == "bob~robert"

    def test_fuzzy_dob_exact_names_via_rule01(self):
        conn = _conn()
        index_patient(conn, R01_CORPUS)
        cand = {
            "resourceType": "Patient",
            "id": "dob-cand",
            "name": [{"family": "Thompson", "given": ["Robert"]}],
            "birthDate": "1955-05-04",  # -1 day, names/street exact
            "address": [{"line": ["123 Main St."]}],
        }
        result = match_patient(conn, cand)
        assert result.outcome == "match"
        assert result.rule_id == "01"
        assert result.match_type == "fuzzy"
        assert result.evidence["dob"] == "1955-05-04~1955-05-05"

    def test_suffix_conflict_negates_fuzzy_match(self):
        conn = _conn()
        jr = {
            "resourceType": "Patient",
            "id": "fz-jr",
            "name": [{"family": "Thompson", "given": ["Robert", "Jr."]}],
            "birthDate": "1955-05-05",
            "address": [{"line": ["123 Main St."]}],
        }
        index_patient(conn, jr)
        sr = {
            "resourceType": "Patient",
            "id": "fz-sr",
            "name": [{"family": "Thomposn", "given": ["Robert", "Sr."]}],
            "birthDate": "1955-05-05",
            "address": [{"line": ["123 Main St."]}],
        }
        # last name "thomposn" (transposition) fuzzy-matches, but Jr vs Sr
        # suffix conflict must negate the rule-01 match
        result = match_patient(conn, sr)
        assert result.outcome == "no_match"

    def test_multiple_values_any_matches(self):
        # a field matches if ANY of the patient's values matches ANY of the
        # candidate's indexed values (names without use=official are all kept)
        conn = _conn()
        corpus = {
            "resourceType": "Patient",
            "id": "multi-a",
            "name": [
                {"family": "Thompsno", "given": ["Robert"]},
                {"family": "Thompson", "given": ["Bob"]},
            ],
            "birthDate": "1955-05-05",
            "address": [{"line": ["123 Main St."]}],
        }
        index_patient(conn, corpus)
        cand = {
            "resourceType": "Patient",
            "id": "multi-cand",
            "name": [{"family": "Thompson", "given": ["Robert"]}],
            "birthDate": "1955-05-05",
            "address": [{"line": ["123 Main St."]}],
        }
        result = match_patient(conn, cand)
        assert result.outcome == "match"
        assert result.rule_id == "01"
        # "thompson" is one of the candidate's indexed last values -> exact
        assert result.match_type == "exact"
        assert result.evidence["last"] == "thompson"
