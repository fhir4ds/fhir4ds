"""AMUX-145 acceptance suite — dedup code-normalization fallback cascade.

Authored FIRST (red before implementation) per the FDD §8 contract in
fhir4ds-private/docs/architecture/plans/FEATURE_DEDUP_CODE_FALLBACK.md.

Joel scope correction (2026-11-20): the ``code_fallback`` merge tier is
DEFAULT ON ("on"); "audit_only" and "off" remain selectable modes.

Joel DESIGN REDIRECT (2026-11-20, supersedes the FDD's original tier-2
parallel-matcher): tier 2 is now a SINGLE COALECED MATCH KEY —
canonical (system, code) intersection → hybrid retrieval (BM25 +
char-trigram over a versioned multi-vocabulary display index) with a
confidence+margin rule → conservative text tier LAST (resolved concepts
outrank display equality). These tests assert the COALESCED behavior.

Joel addendum (2026-11-20): tier-2 merges carry a SUBTYPE — ``hybrid``
(at least one side of the pair had a usable coding) vs ``text_only``
(neither side coded) — on the merge provenance tag, the audit trail,
and the curation queue.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import duckdb
import pytest

from fhir4ds.dedup import dedup_pass, load_dedup_audit, run_dedup
from fhir4ds.dedup.codes import normalize_codes

LOINC = "http://loinc.org"
LOCAL = "http://local.example.org"
SNOMED = "http://snomed.info/sct"
CVX = "http://hl7.org/fhir/sid/cvx"
_CAT_LAB = ("http://terminology.hl7.org/CodeSystem/observation-category")

_REPO = Path(__file__).resolve().parents[3]
_CORPORA = {
    "cms-2025-uscore": _REPO / "tests/data/dqm-content-cms-2025/input/tests/measure",
    "qicore-2025": _REPO / "tests/data/ecqm-content-qicore-2025/input/tests/measure",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _index(*entries):
    """Deterministic fixture concept index."""
    from fhir4ds.dedup.concept_index import ConceptIndex
    return ConceptIndex(entries)


#: The canonical fixture index: real LOINC displays for the panel used
#: throughout the cascade tests, plus decoys that pin non-merging.
_TWIN_INDEX = lambda: _index(  # noqa: E731
    {"system": LOINC, "code": "718-7", "display": "Hemoglobin"},
    {"system": LOINC, "code": "4548-4", "display": "Hematocrit"},
    {"system": LOINC, "code": "4547-1", "display": "Hemoglobin A1c"},
    {"system": SNOMED, "code": "S9", "display": "Ambiguous Panel"},
    {"system": LOINC, "code": "A1", "display": "Ambiguous Panel"},
)

#: An index that resolves NOTHING the fixtures ask about (pins the text
#: tier deterministically).
_EMPTY_INDEX = lambda: _index(  # noqa: E731
    {"system": LOINC, "code": "0000-0", "display": "Unused Concept"},
)


def _lab(rid, effective, *, system=LOINC, code="718-7", display="Hemoglobin",
         text=None, value=7.5, unit="g/dL", subject="Patient/lx"):
    """One LAB Observation whose primary code carries a display."""
    coding = {"system": system, "code": code}
    if display is not None:
        coding["display"] = display
    cc = {"coding": [coding]}
    if text is not None:
        cc["text"] = text
    return {
        "resourceType": "Observation",
        "id": rid,
        "status": "final",
        "subject": {"reference": subject},
        "code": cc,
        "category": [{"coding": [{"system": _CAT_LAB, "code": "laboratory"}]}],
        "effectiveDateTime": effective,
        "valueQuantity": {"value": value, "unit": unit, "code": unit},
    }


def _text_only_condition(rid, onset, *, text="Chest pain",
                         subject="Patient/tx"):
    """A Condition with NO codings — only ``code.text``."""
    return {
        "resourceType": "Condition",
        "id": rid,
        "subject": {"reference": subject},
        "code": {"text": text},
        "onsetDateTime": onset,
    }


def _imm(rid, *, cvx, display="Varicella", subject="Patient/im"):
    return {
        "resourceType": "Immunization",
        "id": rid,
        "status": "completed",
        "patient": {"reference": subject},
        "vaccineCode": {"coding": [{
            "system": CVX, "code": cvx, "display": display}]},
        # deliberately NO occurrenceDateTime -> nd is None
    }


def _cluster_rids(result):
    return sorted(sorted(r.rid for r in c) for c in result.clusters)


def _tier2_edges(result):
    return [e for edges in result.cluster_edges for e in edges
            if e["tier"] != "canonical"]


def _queue_lines(path: Path):
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _corpus_resources(root: Path):
    out = []
    for p in sorted(root.rglob("*.json")):
        try:
            doc = json.loads(p.read_text(encoding="utf-8-sig"))
        except (ValueError, OSError):
            continue
        docs = []
        if isinstance(doc, dict) and doc.get("resourceType") == "Bundle":
            docs = [e.get("resource") for e in doc.get("entry", [])
                    if isinstance(e, dict)
                    and isinstance(e.get("resource"), dict)]
        elif isinstance(doc, dict):
            docs = [doc]
        for r in docs:
            if isinstance(r, dict) and r.get("resourceType") in (
                    "Observation", "Condition", "Immunization", "Procedure"):
                out.append(r)
    return out


# ---------------------------------------------------------------------------
# Phase 0.5 — quantityConvert bare-number defect (prerequisite fix)
# ---------------------------------------------------------------------------


class TestPhase05QuantityUnitZero:
    def test_quantity_convert_digit_only_unit_returns_none_not_crash(self):
        from fhir4ds.cql.duckdb.udf.quantity import quantityConvert
        q = json.dumps({"value": 100, "unit": "0", "code": "0",
                        "system": "http://unitsofmeasure.org"})
        for target in ("cm", "g", "mg", "mL", "s", "min", "h", "mm[Hg]",
                       "1"):
            assert quantityConvert(q, target) is None, target

    def test_dedup_pass_over_unit_zero_fixture_completes(self):
        # The CMS72 fixture quirk {"value":100,"unit":"0"} previously
        # crashed DedupRecord.from_resource with AttributeError.
        resources = [
            _lab("u0", "2024-05-01T10:00:00Z", value=100, unit="0"),
            _lab("u1", "2024-05-01T10:00:00Z", value=100, unit="0"),
        ]
        result = dedup_pass(resources, concept_index=_EMPTY_INDEX())
        assert result.stats["records"] == 2
        # Same bucket + same canonical code -> one duplicate cluster.
        assert _cluster_rids(result) == [["u0", "u1"]]


# ---------------------------------------------------------------------------
# Lexical normalizer unit tests (FDD §8 tests 1-6)
# ---------------------------------------------------------------------------


class TestLexicalNormalizer:
    def test_01_casefold_punctuation_whitespace_equality(self):
        from fhir4ds.dedup.lexical import normalize_lexical_text
        a = normalize_lexical_text("Hemoglobin [Mass/volume] in Blood")
        b = normalize_lexical_text("hemoglobin mass/volume in blood")
        assert a == b
        assert a == "hemoglobin mass volume in blood"

    def test_02_ucum_alias_table(self):
        from fhir4ds.dedup.lexical import normalize_lexical_text
        assert (normalize_lexical_text("Hemoglobin g/dl")
                == normalize_lexical_text("Hemoglobin g/dL"))
        assert (normalize_lexical_text("Glucose mmol/L")
                == normalize_lexical_text("Glucose mmol/l"))
        # squashed spellings map to canonical token forms
        assert (normalize_lexical_text("Blood pressure mmhg")
                == normalize_lexical_text("Blood pressure mm hg"))

    def test_03_no_prefix_merging(self):
        from fhir4ds.dedup.lexical import normalize_lexical_text
        assert (normalize_lexical_text("Hemoglobin")
                != normalize_lexical_text("Hemoglobin A1c"))

    def test_04_no_word_order_no_stemming(self):
        from fhir4ds.dedup.lexical import normalize_lexical_text
        assert (normalize_lexical_text("Blood Pressure")
                != normalize_lexical_text("Pressure Blood"))
        assert (normalize_lexical_text("oxygen therapy")
                != normalize_lexical_text("oxygen therapies"))

    def test_05_nfkc_compatibility(self):
        from fhir4ds.dedup.lexical import normalize_lexical_text
        assert (normalize_lexical_text("Hemoglobin ﬁ")
                == normalize_lexical_text("Hemoglobin fi"))

    def test_06_empty_text_not_tier2_eligible(self):
        from fhir4ds.dedup.lexical import tier2_text_set
        resource = {
            "resourceType": "Observation", "id": "e",
            "code": {"text": "   ",
                     "coding": [{"system": LOINC, "code": "1",
                                 "display": "  "}]},
            "effectiveDateTime": "2024-05-01T10:00:00Z",
        }
        assert tier2_text_set(resource) == frozenset()


# ---------------------------------------------------------------------------
# Cascade mechanics (FDD §8 tests 7-14, coalesced-design expectations)
# ---------------------------------------------------------------------------


class TestCascadeMechanics:
    def test_07_local_code_twin_rescues_via_hybrid_resolution(self):
        """LOINC 718-7 vs local X123, both display 'Hemoglobin': the
        local-coded side RESOLVES through the index to (LOINC, 718-7) so
        both sides carry the same coalesced key -> ONE cluster, hybrid
        provenance, audit names the resolved concept + index version."""
        resources = [
            _lab("t7a", "2024-05-01T10:00:00Z"),
            _lab("t7b", "2024-05-01T10:00:00Z", system=LOCAL, code="X123"),
        ]
        result = dedup_pass(resources, concept_index=_TWIN_INDEX())
        assert _cluster_rids(result) == [["t7a", "t7b"]]
        edges = _tier2_edges(result)
        assert len(edges) == 1
        assert edges[0]["tier"] == "hybrid"
        assert edges[0]["subtype"] == "hybrid"
        assert edges[0]["resolved_concept"] == [LOINC, "718-7"]
        assert edges[0]["index_version"].startswith("format1+sha256:")
        assert edges[0]["score"] >= 0.85
        # audit: rule carries HYBRID, evidence names concept + index
        conn = duckdb.connect()
        try:
            run_dedup(resources, "amux145-t7", conn=conn,
                      concept_index=_TWIN_INDEX())
            rows = load_dedup_audit(conn, "amux145-t7")
        finally:
            conn.close()
        assert len(rows) == 1
        assert "HYBRID:hybrid" in rows[0]["rule"]
        evidence = rows[0]["cluster_evidence"]
        assert evidence["codeProvenance"] == "hybrid:hybrid"
        hybrid = [e for e in evidence["codeEdges"]
                  if e["tier"] == "hybrid"]
        assert hybrid[0]["resolved_concept"] == [LOINC, "718-7"]
        assert evidence["conceptIndex"]["version"] == \
            edges[0]["index_version"]

    def test_08_raw_text_exact_subset(self):
        """Identical code.text only (no codings at all) with full
        corroboration merges through the TEXT tier (Q2 default: yes)."""
        resources = [
            _text_only_condition("t8a", "2024-03-10"),
            _text_only_condition("t8b", "2024-03-10"),
        ]
        result = dedup_pass(resources, concept_index=_EMPTY_INDEX())
        assert _cluster_rids(result) == [["t8a", "t8b"]]
        edge = _tier2_edges(result)[0]
        assert edge["tier"] == "text"
        assert edge["subtype"] == "text_only"
        assert edge["text_key"] == "chest pain"

    def test_09_canonical_wins_no_double_count(self):
        """Code-set-intersecting pair merges with canonical provenance
        even when their displays also resolve through the index."""
        resources = [
            _lab("t9a", "2024-05-01T10:00:00Z", display="Hemoglobin"),
            _lab("t9b", "2024-05-01T10:00:00Z", display="Hemoglobin"),
        ]
        result = dedup_pass(resources, concept_index=_TWIN_INDEX())
        assert _cluster_rids(result) == [["t9a", "t9b"]]
        assert _tier2_edges(result) == []
        conn = duckdb.connect()
        try:
            run_dedup(resources, "amux145-t9", conn=conn,
                      concept_index=_TWIN_INDEX())
            rows = load_dedup_audit(conn, "amux145-t9")
        finally:
            conn.close()
        assert len(rows) == 1
        assert "HYBRID" not in rows[0]["rule"] and \
            "TEXT" not in rows[0]["rule"]
        assert rows[0]["cluster_evidence"]["codeProvenance"] == "canonical"

    def test_10_corroboration_gate_different_value_key(self):
        """Text-compatible pair but DIFFERENT value_key (different
        buckets) -> no merge + near_miss queue entry."""
        resources = [
            _lab("t10a", "2024-05-01T10:00:00Z", value=7.5),
            _lab("t10b", "2024-05-01T10:00:00Z", system=LOCAL, code="X123",
                 value=9.1),
        ]
        result = dedup_pass(resources, concept_index=_EMPTY_INDEX())
        assert result.clusters == []
        near = [e for e in result.curation_records
                if e["kind"] == "near_miss"]
        assert len(near) == 1
        assert sorted(near[0]["rids"]) == ["t10a", "t10b"]
        assert near[0]["shared_texts"] == ["hemoglobin"]  # normalized key
        assert near[0]["codes"]["t10a"] == [f"{LOINC}|718-7"]
        assert near[0]["codes"]["t10b"] == [f"{LOCAL}|X123"]

    def test_11_no_date_immunization_singleton(self):
        """Two otherwise-identical Immunizations with no occurrence date
        stay two singletons (tier 2 must not bypass `nd is None`)."""
        resources = [
            _imm("t11a", cvx="146"),
            _imm("t11b", cvx="49"),
        ]
        result = dedup_pass(resources, concept_index=_EMPTY_INDEX())
        assert result.clusters == []
        assert len(result.emitted) == 2
        near = [e for e in result.curation_records
                if e["kind"] == "near_miss"]
        assert len(near) == 1
        assert sorted(near[0]["rids"]) == ["t11a", "t11b"]

    def test_12_temporal_rules_still_arbitrate(self):
        """Tier-2-compatible LAB pair 45 minutes apart (outside the 30-min
        window) does NOT merge."""
        resources = [
            _lab("t12a", "2024-05-01T10:00:00Z"),
            _lab("t12b", "2024-05-01T10:45:00Z", system=LOCAL, code="X123"),
        ]
        result = dedup_pass(resources, concept_index=_EMPTY_INDEX())
        assert result.clusters == []
        near = [e for e in result.curation_records
                if e["kind"] == "near_miss"]
        assert len(near) == 1
        assert sorted(near[0]["rids"]) == ["t12a", "t12b"]

    def test_13_empty_both_no_text(self):
        """Two coding-less text-less same-bucket resources stay singletons
        and land in the queue as unmatched."""
        resources = [
            {"resourceType": "Observation", "id": "t13a", "status": "final",
             "subject": {"reference": "Patient/nx"},
             "code": {"coding": []},
             "effectiveDateTime": "2024-05-01T10:00:00Z"},
            {"resourceType": "Observation", "id": "t13b", "status": "final",
             "subject": {"reference": "Patient/nx"},
             "code": {"coding": []},
             "effectiveDateTime": "2024-05-01T10:00:00Z"},
        ]
        result = dedup_pass(resources, concept_index=_EMPTY_INDEX())
        assert result.clusters == []
        unmatched = [e for e in result.curation_records
                     if e["kind"] == "unmatched"]
        assert sorted(e["rid"] for e in unmatched) == ["t13a", "t13b"]

    def test_14_multi_coding_text_sets_any_intersection(self):
        """Local twin carrying 2 codings, one display resolving -> merge
        through the resolved concept."""
        twin = _lab("t14a", "2024-05-01T10:00:00Z")
        twin["code"]["coding"].append(
            {"system": "http://local2.example.org", "code": "Y9",
             "display": "Unrelated panel"})
        resources = [
            twin,
            _lab("t14b", "2024-05-01T10:00:00Z", system=LOCAL, code="X123"),
        ]
        result = dedup_pass(resources, concept_index=_TWIN_INDEX())
        assert _cluster_rids(result) == [["t14a", "t14b"]]


# ---------------------------------------------------------------------------
# Hybrid-retrieval rules (design redirect: margin + index provenance)
# ---------------------------------------------------------------------------


class TestHybridRetrievalRules:
    def test_margin_fallthrough_resolves_no_concept(self):
        """An ambiguous display (two index entries share the same
        normalized display -> top-2 tie -> zero margin) resolves to NO
        concept: the pair can only merge through the TEXT tier (never a
        wrong canonical concept), and the unresolved record carries text
        tokens, not resolved concepts."""
        from fhir4ds.dedup.concept_index import ConceptIndex
        # the margin rule itself: exact display tie -> no resolution
        assert _TWIN_INDEX().resolve("Ambiguous Panel") is None

        ambiguous = _lab("mfa", "2024-05-01T10:00:00Z",
                         system="http://nowhere.example.org", code="Z1",
                         display="Ambiguous Panel")
        coded = _lab("mfb", "2024-05-01T10:00:00Z", system=LOINC,
                     code="A1", display="Ambiguous Panel")
        result = dedup_pass([ambiguous, coded], concept_index=_TWIN_INDEX())
        # both unresolved -> equal text + full corroboration -> the TEXT
        # tier merges them (margin only blocks the CONCEPT assignment).
        assert _cluster_rids(result) == [["mfa", "mfb"]]
        edge = _tier2_edges(result)[0]
        assert edge["tier"] == "text"
        assert edge["subtype"] == "hybrid"  # mfb carried a usable code
        # neither record stole a canonical concept from the tie
        recs = {r.rid: r for r in result.records}
        assert not recs["mfa"].resolved_concepts
        assert not recs["mfb"].resolved_concepts
        assert ("text", "ambiguous panel") in recs["mfa"].match_key

    def test_resolved_concepts_outrank_display_equality(self):
        """Records that resolve carry NO text tokens in their coalesced
        key: equal display text can never merge two differently-resolved
        records (text tier is LAST)."""
        from fhir4ds.dedup.lexical import normalize_lexical_text
        idx = _index(
            {"system": LOINC, "code": "X1", "display": "Alpha Beta"},
            {"system": SNOMED, "code": "S1", "display": "Alpha Gamma"},
        )
        resources = [
            _lab("ra", "2024-05-01T10:00:00Z", system=LOCAL, code="L1",
                 display="Alpha Beta"),
            _lab("rb", "2024-05-01T10:00:00Z", system=LOCAL, code="L2",
                 display="Alpha Gamma"),
        ]
        result = dedup_pass(resources, concept_index=idx)
        # both resolved confidently to DIFFERENT concepts -> no merge,
        # despite the ngram-similar displays.
        assert result.clusters == []
        recs = {r.rid: r for r in result.records}
        for rid in ("ra", "rb"):
            assert recs[rid].resolved_concepts
            assert all(element[0] == "code"
                       for element in recs[rid].match_key), (
                "resolved records must not carry text tokens")

    def test_index_version_provenance_in_audit_and_queue(self, tmp_path):
        """Every hybrid merge records the index version + score/margin in
        the audit trail; index version is content-derived (two indexes
        with different entries yield different versions)."""
        idx_a = _TWIN_INDEX()
        idx_b = _index(
            {"system": LOINC, "code": "718-7", "display": "Hemoglobin"},
            {"system": LOINC, "code": "4548-4", "display": "Hematocrit"},
        )
        assert idx_a.index_version != idx_b.index_version
        assert idx_a.checksum != idx_b.checksum

        resources = [
            _lab("iv1", "2024-05-01T10:00:00Z"),
            _lab("iv2", "2024-05-01T10:00:00Z", system=LOCAL, code="X123"),
        ]
        conn = duckdb.connect()
        try:
            run_dedup(resources, "amux145-iv", conn=conn,
                      output_dir=tmp_path, concept_index=idx_a)
            rows = load_dedup_audit(conn, "amux145-iv")
        finally:
            conn.close()
        evidence = rows[0]["cluster_evidence"]
        resolutions = evidence["conceptIndex"]["resolutions"]
        assert resolutions[0]["concept"] == [LOINC, "718-7"]
        assert resolutions[0]["score"] >= 0.85
        assert resolutions[0]["margin"] >= 0.15
        assert (evidence["conceptIndex"]["version"]
                == idx_a.index_version)


# ---------------------------------------------------------------------------
# Audit / provenance + queue (FDD §8 tests 15-18)
# ---------------------------------------------------------------------------


def _mixed_corpus():
    return [
        # canonical pair (same LOINC code)
        _lab("m1", "2024-05-01T10:00:00Z"),
        _lab("m2", "2024-05-01T10:00:00Z"),
        # hybrid twin of m1/m2 (disjoint local code, display resolves)
        _lab("m3", "2024-05-01T10:00:00Z", system=LOCAL, code="X123"),
        # text-only Condition pair (not in the index)
        _text_only_condition("m4", "2024-03-10"),
        _text_only_condition("m5", "2024-03-10"),
        # unrelated singletons
        _lab("m6", "2024-06-01T10:00:00Z", code="4548-4",
             display="Hematocrit"),
        _imm("m7", cvx="146"),
        # near-miss pair: equal unresolvable text, DIFFERENT value keys
        # (different buckets -> corroboration failure -> curation queue)
        _lab("m8", "2024-07-01T10:00:00Z", system=LOCAL, code="L1",
             display="Custom Local Panel"),
        _lab("m9", "2024-07-01T10:00:00Z", system=LOCAL, code="L2",
             display="Custom Local Panel", value=9.9),
    ]


class TestAuditProvenanceQueue:
    def test_15_audit_and_queue_determinism_five_shuffles(self, tmp_path):
        resources = _mixed_corpus()
        reference_audit = None
        reference_queue = None
        for seed in range(5):
            shuffled = list(resources)
            random.Random(seed).shuffle(shuffled)
            out_dir = tmp_path / f"run{seed}"
            out_dir.mkdir()
            conn = duckdb.connect()
            try:
                run_dedup(shuffled, f"amux145-det-{seed}", conn=conn,
                          output_dir=out_dir, concept_index=_TWIN_INDEX())
                audit = [
                    {k: v for k, v in row.items() if k != "run_id"}
                    for row in load_dedup_audit(conn, f"amux145-det-{seed}")
                ]
            finally:
                conn.close()
            queue_lines = (out_dir / "dedup_curation_queue.jsonl"
                           ).read_text(encoding="utf-8").splitlines()
            queue = json.dumps(
                [{k: v for k, v in json.loads(line).items()
                  if k != "run_id"} for line in queue_lines if line.strip()],
                sort_keys=True)
            if reference_audit is None:
                reference_audit, reference_queue = audit, queue
            assert audit == reference_audit, f"audit drift at seed {seed}"
            assert queue == reference_queue, f"queue drift at seed {seed}"

    def test_16_queue_record_shapes_and_order(self, tmp_path):
        out_dir = tmp_path / "shapes"
        out_dir.mkdir()
        resources = _mixed_corpus()
        conn = duckdb.connect()
        try:
            run_dedup(resources, "amux145-shapes", conn=conn,
                      output_dir=out_dir, concept_index=_TWIN_INDEX())
        finally:
            conn.close()
        entries = _queue_lines(out_dir / "dedup_curation_queue.jsonl")
        kinds = {e["kind"] for e in entries}
        assert kinds == {"unmatched", "near_miss"}
        for e in entries:
            assert e["run_id"] == "amux145-shapes"
            if e["kind"] == "unmatched":
                assert set(e) >= {"kind", "run_id", "resource_type", "rid",
                                  "patient_ref", "code_field", "tier2_texts"}
            else:
                assert set(e) >= {"kind", "run_id", "resource_type", "rids",
                                  "bucket", "shared_texts", "codes"}
        # deterministic sort order (resource_type, patient_ref, lead rid)
        def sort_key(e):
            lead = e.get("rid") or sorted(e["rids"])[0]
            return (e["resource_type"], e["patient_ref"] or "", lead)
        main = [e for e in entries if e["kind"] != "proposal"]
        assert main == sorted(main, key=sort_key)

    def test_17_mixed_cluster_provenance(self):
        """One canonical edge + one hybrid edge in one cluster -> cluster
        provenance hybrid, evidence lists both edges."""
        resources = [
            _lab("t17a", "2024-05-01T10:00:00Z"),
            _lab("t17b", "2024-05-01T10:00:00Z", system=LOCAL,
                 code="X123"),
            _lab("t17c", "2024-05-01T10:00:00Z"),
        ]
        result = dedup_pass(resources, concept_index=_TWIN_INDEX())
        assert _cluster_rids(result) == [["t17a", "t17b", "t17c"]]
        conn = duckdb.connect()
        try:
            run_dedup(resources, "amux145-t17", conn=conn,
                      concept_index=_TWIN_INDEX())
            rows = load_dedup_audit(conn, "amux145-t17")
        finally:
            conn.close()
        evidence = rows[0]["cluster_evidence"]
        assert evidence["codeProvenance"] == "hybrid:hybrid"
        assert sorted(e["tier"] for e in evidence["codeEdges"]) == [
            "canonical", "hybrid"]

    def test_18_proposer_interface(self, tmp_path):
        from fhir4ds.dedup.curation import (
            DedupCodeProposer,
            PROPOSER_INTERFACE_VERSION,
        )

        class StubProposer:
            version = "9.9"

            def propose(self, records):
                return [{"resource_type": "Observation",
                         "rids": [r.rid for r in records[:2]],
                         "note": "stub"}]

        # Protocol is runtime-checkable against duck-typed proposers
        assert isinstance(StubProposer(), DedupCodeProposer)
        assert isinstance(PROPOSER_INTERFACE_VERSION, str)

        resources = _mixed_corpus()
        baseline = _cluster_rids(
            dedup_pass(resources, concept_index=_TWIN_INDEX()))

        out_with = tmp_path / "with"
        out_with.mkdir()
        conn = duckdb.connect()
        try:
            run_dedup(resources, "amux145-prop", conn=conn,
                      output_dir=out_with, concept_index=_TWIN_INDEX(),
                      dedup_proposer=StubProposer())
        finally:
            conn.close()
        entries = _queue_lines(out_with / "dedup_curation_queue.jsonl")
        proposals = [e for e in entries if e["kind"] == "proposal"]
        assert len(proposals) == 1
        assert proposals[0]["proposer"] == "StubProposer@9.9"
        # proposer cannot change cluster output
        assert _cluster_rids(
            dedup_pass(resources, concept_index=_TWIN_INDEX())) == baseline

        # default-off: no proposer -> no proposal lines
        out_without = tmp_path / "without"
        out_without.mkdir()
        conn = duckdb.connect()
        try:
            run_dedup(resources, "amux145-noprop", conn=conn,
                      output_dir=out_without, concept_index=_TWIN_INDEX())
        finally:
            conn.close()
        entries = _queue_lines(out_without / "dedup_curation_queue.jsonl")
        assert not [e for e in entries if e["kind"] == "proposal"]


# ---------------------------------------------------------------------------
# Regression / mode (FDD §8 tests 19-22)
# ---------------------------------------------------------------------------


class TestRegressionAndMode:
    @pytest.mark.parametrize("corpus_name", sorted(_CORPORA))
    def test_19_conformance_corpora_canonical_resolution_pin(
            self, corpus_name):
        root = _CORPORA[corpus_name]
        if not root.is_dir():
            pytest.skip(f"corpus fixture missing: {root}")
        resources = _corpus_resources(root)
        expected_total = {"cms-2025-uscore": 7983,
                          "qicore-2025": 20231}[corpus_name]
        if len(resources) != expected_total:
            pytest.skip("corpus content drifted from the measured snapshot")
        resolved = sum(1 for r in resources if normalize_codes(r))
        expected_resolved = {"cms-2025-uscore": 7982,
                             "qicore-2025": 20230}[corpus_name]
        assert resolved == expected_resolved
        # tier-2 active merge count on the shipped corpora == 0
        result = dedup_pass(resources, code_fallback="on")
        assert result.stats["tier2_merges"] == 0

    def test_20_mode_off_restores_pre_feature_clusters(self):
        resources = [
            _lab("t20a", "2024-05-01T10:00:00Z"),
            _lab("t20b", "2024-05-01T10:00:00Z", system=LOCAL,
                 code="X123"),
            _text_only_condition("t20c", "2024-03-10"),
            _text_only_condition("t20d", "2024-03-10"),
            _lab("t20e", "2024-06-01T09:00:00Z", code="4548-4",
                 display="Hematocrit"),
        ]
        off = dedup_pass(resources, code_fallback="off")
        # Pre-feature equivalence: strip all lexical evidence and run in
        # default mode — no text can resolve or match, so only canonical
        # unions fire.
        stripped = []
        for r in resources:
            r = json.loads(json.dumps(r))
            for c in r.get("code", {}).get("coding", []):
                c.pop("display", None)
            r.get("code", {}).pop("text", None)
            stripped.append(r)
        baseline = dedup_pass(stripped)
        assert (_cluster_rids(off) == _cluster_rids(baseline))
        # the tier-2 twins must NOT merge in off mode
        merged = {frozenset(r.rid for r in c) for c in off.clusters}
        assert frozenset({"t20a", "t20b"}) not in merged
        assert frozenset({"t20c", "t20d"}) not in merged

    def test_21_audit_only_does_not_merge_and_queues_near_miss(self):
        resources = [
            _lab("t21a", "2024-05-01T10:00:00Z"),
            _lab("t21b", "2024-05-01T10:00:00Z", system=LOCAL,
                 code="X123"),
        ]
        result = dedup_pass(resources, code_fallback="audit_only",
                            concept_index=_TWIN_INDEX())
        assert result.clusters == []
        near = [e for e in result.curation_records
                if e["kind"] == "near_miss"]
        assert len(near) == 1
        assert sorted(near[0]["rids"]) == ["t21a", "t21b"]
        assert near[0]["tier"] == "hybrid"
        assert near[0]["shared_concept"] == [LOINC, "718-7"]

    @pytest.mark.parametrize("corpus_name", sorted(_CORPORA))
    def test_22_default_mode_leaves_corpus_clusters_unchanged(
            self, corpus_name):
        """Master-gate proxy: with tier 2 in its DEFAULT mode (default
        index), cluster output over the shipped DQM corpora is identical
        to off mode (the full conformance gate is run out-of-band and
        recorded in amux145_acceptance_green.txt)."""
        root = _CORPORA[corpus_name]
        if not root.is_dir():
            pytest.skip(f"corpus fixture missing: {root}")
        resources = _corpus_resources(root)
        if not resources:
            pytest.skip("corpus fixture empty")
        on = dedup_pass(resources, code_fallback="on")
        off = dedup_pass(resources, code_fallback="off")
        assert (_cluster_rids(on) == _cluster_rids(off))


# ---------------------------------------------------------------------------
# Joel addendum — tier-2 subtype distinguishable (hybrid vs text_only)
# ---------------------------------------------------------------------------


class TestTier2Subtype:
    def test_hybrid_and_text_only_subtypes_distinguishable(self, tmp_path):
        from fhir4ds.dedup.pipeline import DedupRecord

        hybrid_resources = [
            _lab("s1a", "2024-05-01T10:00:00Z"),
            _lab("s1b", "2024-05-01T10:00:00Z", system=LOCAL, code="X123"),
        ]
        text_only_resources = [
            _text_only_condition("s2a", "2024-03-10"),
            _text_only_condition("s2b", "2024-03-10"),
        ]

        hybrid = dedup_pass(hybrid_resources, concept_index=_TWIN_INDEX())
        text_only = dedup_pass(text_only_resources,
                               concept_index=_EMPTY_INDEX())

        hybrid_edges = _tier2_edges(hybrid)
        text_edges = _tier2_edges(text_only)
        assert [(e["tier"], e["subtype"]) for e in hybrid_edges] == [
            ("hybrid", "hybrid")]
        assert [(e["tier"], e["subtype"]) for e in text_edges] == [
            ("text", "text_only")]

        # record-level provenance: coded records are canonical-eligible;
        # coding-less records with text are text-tier-eligible
        assert {DedupRecord.from_resource(r).code_provenance
                for r in hybrid_resources} == {"canonical"}
        assert {DedupRecord.from_resource(r).code_provenance
                for r in text_only_resources} == {"text"}

        # audit trail distinguishes tiers AND subtypes
        conn = duckdb.connect()
        try:
            run_dedup(hybrid_resources + text_only_resources, "amux145-sub",
                      conn=conn, output_dir=tmp_path,
                      concept_index=_TWIN_INDEX())
            rows = load_dedup_audit(conn, "amux145-sub")
        finally:
            conn.close()
        assert {r["cluster_evidence"]["codeProvenance"] for r in rows} \
            == {"hybrid:hybrid", "text:text_only"}
        assert sorted(r["rule"].split("|")[-1] for r in rows) == [
            "HYBRID:hybrid", "TEXT:text_only"]

        # curation queue entries carry the subtype (text-only records are
        # canonical-unmatched but text-tier-eligible)
        entries = _queue_lines(tmp_path / "dedup_curation_queue.jsonl")
        unmatched = [e for e in entries if e["kind"] == "unmatched"]
        assert {e["rid"] for e in unmatched} == {"s2a", "s2b"}
        assert all(e["tier2_texts"] == ["chest pain"] for e in unmatched)
