"""PIQI auto-coding benchmark: before/after AutoCoder on a real corpus.

The repeatable experiment behind the 2026-11-20 blog post, runnable
against any FHIR corpus (developed against the MIMIC-IV-FHIR demo):

1. **Baseline** — PIQI scorecard over a deterministic patient slice of
   the corpus AS-IS (nothing modified).
2. **Census** — how many CodeableConcepts are text-only (no ``coding``
   with a ``code``)? On MIMIC the answer is ~0 (fully coded export),
   which motivates the constructed BEFORE corpus.
3. **BEFORE** — a controlled subset of coded resources has its codings
   STRIPPED (the display text is preserved as ``code.text``, the
   realistic legacy-export shape); the identical rubric is evaluated
   and fails on the coding-dependent SAMs (``Concept_IsComplete``,
   ``Concept_HasCode``, ...).
4. **AutoCoder** — the stripped corpus is augmented in place through
   :class:`fhir4ds.cql.loader.auto_coder.AutoCoder` with an in-process
   medterm4ds endpoint (strict default config: hybrid search,
   ``min_match_grade='certain'``, ``top_k=3``).
5. **AFTER** — identical rubric again; report per-SAM recovery
   (fail→pass), new failures, and GROUND-TRUTH coding accuracy: the
   stripped originals' codings are the gold set, so we can measure
   exact (system,code) recovery, code-only recovery, and coverage.

Determinism: the patient slice is the first N patient ids in sorted
order; stripping walks resources in (resourceType, id) order and caps
per patient in that order. No RNG. Same corpus + arguments ->
byte-identical JSON report (no wall clock; floats rounded).

CLI::

    python3 -m fhir4ds.realism.piqi_autocoding \
        --corpus tests/data/mimic-iv-fhir-demo/.../fhir \
        --output-dir /tmp/jm/piqi-autocoding \
        [--num-patients 12] [--lab-cap 40] [--medicationrequest-cap 20]
        [--skip-autocoding]   # corpus/PIQI legs without medterm4ds

``--skip-autocoding`` still builds and evaluates the BEFORE corpus; it
only skips the augmentation (useful where the medterm4ds index is not
available).
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Optional, Union

from .corpus import load_corpus

# ── deterministic experiment parameters ───────────────────────────────

#: Patient slice size (first N patient ids, sorted).
DEFAULT_NUM_PATIENTS = 12

#: CodeableConcept paths stripped per resource type and the per-patient
#: cap applied in (id) order. VitalSign observations are deliberately
#: NOT stripped — they are the unmodified control class. Condition and
#: Procedure are stripped in full (the mission's named candidates).
#:
#: ``text_from_code`` (MedicationRequest) is for local name-code
#: systems where the code IS the human-readable drug name (MIMIC's
#: ``mimic-medication-name`` codings carry e.g. ``code:
#: "Ondansetron"`` with no display and no ``cc.text``): when no text
#: or display survives the strip, the FIRST coding's ``code`` string
#: is preserved as the query text. Types without the flag keep the
#: skip-if-no-text behavior.
DEFAULT_STRIPPING: dict[str, dict[str, Any]] = {
    "Condition": {"path": "code", "cap": None},
    "Procedure": {"path": "code", "cap": None},
    "MedicationRequest": {"path": "medicationCodeableConcept", "cap": 300,
                          "text_from_code": True},
    # laboratory Observations only; vital-signs Observations stay coded
    "Observation": {"path": "code", "cap": 40,
                    "category": "laboratory"},
}


def _resource_patient_id(resource: dict) -> Optional[str]:
    ref = (resource.get("subject") or resource.get("patient") or {})
    if isinstance(ref, dict):
        reference = ref.get("reference") or ""
        return reference.replace("urn:uuid:", "").split("/")[-1] or None
    return None


def _observation_category(resource: dict) -> str:
    for cat in resource.get("category") or []:
        for coding in cat.get("coding") or []:
            code = coding.get("code")
            if isinstance(code, str) and code:
                return code
    return ""


def build_slice(resources: list[dict], num_patients: int) -> list[dict]:
    """Deterministic slice: the first ``num_patients`` Patient ids
    (sorted) plus every clinical resource whose subject is one of them."""
    patients = sorted(
        r["id"] for r in resources
        if r.get("resourceType") == "Patient" and r.get("id"))
    slice_ids = set(patients[:num_patients])
    if not slice_ids:
        raise ValueError("corpus contains no Patient resources to slice")
    return [r for r in resources
            if (r.get("resourceType") == "Patient"
                and r.get("id") in slice_ids)
            or (_resource_patient_id(r) in slice_ids)]


def census_text_only(resources: list[dict],
                     paths: Optional[dict[str, str]] = None) -> dict:
    """Count coded vs text-only vs absent CodeableConcepts per type.

    "text-only" = the CodeableConcept exists, carries usable text or a
    display, but has no ``coding`` entry with a ``code`` (the AutoCoder
    INV-4 target population).
    """
    if paths is None:
        paths = {"Condition": "code", "Observation": "code",
                 "MedicationRequest": "medicationCodeableConcept",
                 "Procedure": "code", "Medication": "code",
                 "AllergyIntolerance": "code",
                 "Immunization": "vaccineCode"}
    per_type: dict[str, dict[str, int]] = {}

    def bump(rt: str, key: str) -> None:
        per_type.setdefault(rt, {"coded": 0, "text_only": 0, "absent": 0})
        per_type[rt][key] += 1

    for r in resources:
        rt = r.get("resourceType", "?")
        path = paths.get(rt)
        if not path:
            continue
        cc = r.get(path)
        if not isinstance(cc, dict):
            if cc is None:
                bump(rt, "absent")
            continue
        has_code = any(
            isinstance(e, dict) and isinstance(e.get("code"), str)
            and e["code"].strip()
            for e in (cc.get("coding") or []))
        has_text = isinstance(cc.get("text"), str) and cc["text"].strip()
        if has_code:
            bump(rt, "coded")
        elif has_text or any(
                isinstance(e, dict) and e.get("display")
                for e in (cc.get("coding") or [])):
            bump(rt, "text_only")
        else:
            bump(rt, "absent")
    return {"per_type": per_type,
            "text_only_total": sum(v["text_only"]
                                   for v in per_type.values())}


def strip_codings(resources: list[dict],
                  spec: dict[str, dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    """Build the BEFORE corpus: deep-copy and strip codings from the
    controlled subset, preserving the first coding display as ``text``.
    With the spec's ``text_from_code`` flag, name-code systems whose
    coding ``code`` IS the human-readable name (MIMIC medication-name)
    fall back to the first coding's code string when no text/display
    survives — see :data:`DEFAULT_STRIPPING`.

    Returns ``(stripped_resources, gold_records)`` where each gold
    record is ``{"resourceType", "id", "path", "text", "codings"}`` —
    the original codings are the ground truth for recovery scoring.
    Resources are visited in (resourceType, id) order; caps apply per
    patient in that order. Deterministic.
    """
    stripped: list[dict] = []
    gold: list[dict] = []
    per_patient: Counter = Counter()
    for r in sorted(resources, key=lambda x: (x.get("resourceType", ""),
                                              x.get("id", ""))):
        rt = r.get("resourceType")
        conf = spec.get(rt)
        if conf is None:
            continue
        if rt == "Observation" and _observation_category(r) != conf.get(
                "category", "laboratory"):
            continue
        pid = _resource_patient_id(r) or r.get("id") or "?"
        key = (rt, pid)
        cap = conf.get("cap")
        if cap is not None and per_patient[key] >= cap:
            continue
        cc = r.get(conf["path"])
        if not isinstance(cc, dict):
            continue
        codings = [c for c in (cc.get("coding") or [])
                   if isinstance(c, dict) and c.get("code")]
        if not codings:
            continue  # nothing to strip (already text-only / uncoded)
        text = cc.get("text")
        if not (isinstance(text, str) and text.strip()):
            text = next((c.get("display") for c in codings
                         if isinstance(c.get("display"), str)
                         and c["display"].strip()), None)
        if not text and conf.get("text_from_code"):
            # local name-code system (e.g. MIMIC mimic-medication-name):
            # the coding's code string IS the human-readable name
            text = next((c.get("code") for c in codings
                         if isinstance(c.get("code"), str)
                         and c["code"].strip()), None)
        if not text:
            continue  # no query text would survive the strip — skip
        clone = copy.deepcopy(r)
        clone_cc = clone[conf["path"]]
        clone_cc["coding"] = []
        clone_cc["text"] = text
        stripped.append(clone)
        gold.append({"resourceType": rt, "id": r.get("id"),
                     "path": conf["path"], "text": text,
                     "codings": codings})
        per_patient[key] += 1
    return stripped, gold


# ── rubric ────────────────────────────────────────────────────────────

def build_mimic_rubric() -> tuple[dict, list[dict]]:
    """Coding-centric rubric over the PIQI classes MIMIC populates:
    Demographics (birthDate), LabResult, VitalSign (control class),
    Condition, Procedure, Medication."""
    from fhir4ds.piqi.authoring import build_rubric

    def crit(seq, dc, ent, sam, effect="scoring", desc=""):
        return {"sequence": seq, "description": desc, "data_class": dc,
                "entity": ent, "sam": sam, "scoring_effect": effect,
                "weight": 0 if effect == "informational" else 1,
                "criticality": False}

    criteria = [
        crit(1, "Demographics", "birthDate",
             "demographics-birthdate-isvaliddate",
             desc="Patient birthDate is a valid date"),
        crit(10, "LabResult", "test", "labresult-test-hascode",
             desc="Lab test concept carries a coding code"),
        crit(11, "LabResult", "test", "labresult-test-hascodesystem",
             desc="Lab test concept carries a coding system"),
        crit(12, "LabResult", "test", "labresult-test-hasdisplay",
             desc="Lab test concept carries a coding display"),
        crit(13, "LabResult", "test", "labresult-test-iscomplete",
             desc="Lab test concept has one complete coding"),
        crit(14, "LabResult", "resultValue",
             "labresult-resultvalue-ispopulated",
             desc="Lab result value is populated"),
        crit(15, "LabResult", "resultValue",
             "labresult-resultvalue-isnumeric",
             desc="Lab result value is numeric"),
        crit(16, "LabResult", "performedDateTime",
             "labresult-performeddatetime-istimestamp",
             desc="Lab performedDateTime is a timestamp"),
        crit(17, "LabResult", "resultUnit",
             "labresult-resultunit-ispopulated", effect="informational",
             desc="Lab result unit is populated (informational)"),
        crit(18, "LabResult", "interpretation",
             "labresult-interpretation-ispopulated",
             effect="informational",
             desc="Lab interpretation is populated (informational)"),
        crit(20, "VitalSign", "vitalSign", "vitalsign-vitalsign-hascode",
             desc="Vital sign concept carries a coding code (control)"),
        crit(21, "VitalSign", "vitalSign",
             "vitalsign-vitalsign-iscomplete",
             desc="Vital sign concept complete (control)"),
    ]
    # Widen to the full coding family on the auto-coding target classes:
    # Concept_HasCode / HasCodeSystem / HasDisplay / IsComplete plus the
    # SAM that MOVES for mimic-wrapped local-system codings,
    # Concept_HasRecognizedCodeSystem (FHIR4-24 no-strip comparison).
    seq = 30
    for dc, ent, prefix in (
            ("Condition", "condition", "condition-condition"),
            ("Procedure", "procedure", "procedure-procedure"),
            ("Medication", "medication", "medication-medication")):
        criteria.extend([
            crit(seq, dc, ent, f"{prefix}-hascode",
                 desc=f"{dc} concept carries a coding code"),
            crit(seq + 1, dc, ent, f"{prefix}-hascodesystem",
                 desc=f"{dc} concept carries a coding system"),
            crit(seq + 2, dc, ent, f"{prefix}-hasdisplay",
                 desc=f"{dc} concept carries a coding display"),
            crit(seq + 3, dc, ent, f"{prefix}-hasrecognizedcodesystem",
                 desc=f"{dc} concept system is recognized"),
            crit(seq + 4, dc, ent, f"{prefix}-iscomplete",
                 desc=f"{dc} concept has one complete coding"),
        ])
        seq += 10
    criteria.append(
        crit(19, "LabResult", "test",
             "labresult-test-hasrecognizedcodesystem",
             desc="Lab test concept system is recognized (control: LOINC)"))
    criteria.sort(key=lambda c: c["sequence"])
    return build_rubric(
        "mimic-autocoding",
        "MIMIC demo coding-centric rubric (PIQI auto-coding experiment)",
        criteria)


# ── no-strip mode: raw-corpus augmentation statistics ─────────────────

#: CodeableConcept paths reported by :func:`augmentation_stats` (the
#: auto-coding target classes of the no-strip experiment).
RAW_STATS_PATHS: dict[str, str] = {
    "Condition": "code",
    "Procedure": "code",
    "MedicationRequest": "medicationCodeableConcept",
}


def _is_autocoded_coding(coding: dict) -> bool:
    from fhir4ds.cql.loader.autocoding_extension import (
        AUTOCODING_EXTENSION_URLS,
    )
    return any(isinstance(e, dict) and e.get("url") in AUTOCODING_EXTENSION_URLS
               for e in (coding.get("extension") or []))


def augmentation_stats(resources: list[dict],
                       paths: Optional[dict[str, str]] = None) -> dict:
    """Per-class augmentation bookkeeping for the RAW (no-strip) corpus.

    For each auto-coding target class: how many resources are in the
    slice, how many received an autocoding append, and — for the
    unaugmented ones — why the system-aware AutoCoder (FHIR4-24) did
    not touch them: ``inv4_skipped_standard`` (every coding entry uses
    a standard terminology system; INV-4 preserved) vs
    ``mimic_wrapped_eligible`` (non-standard-system coding present but
    no augmentation happened — no query text or no match above the
    grade threshold).
    """
    from fhir4ds.cql.terminology.system_mappings import is_standard_code_system

    paths = paths or RAW_STATS_PATHS
    per_class: dict[str, dict[str, int]] = {}

    def entry(rt: str) -> dict[str, int]:
        return per_class.setdefault(
            rt, {"resources": 0, "augmented": 0,
                 "inv4_skipped_standard": 0, "mimic_wrapped_eligible": 0})

    for r in resources:
        rt = r.get("resourceType")
        path = paths.get(rt)
        if not path:
            continue
        e = entry(rt)
        e["resources"] += 1
        cc = r.get(path)
        if not isinstance(cc, dict):
            continue
        codings = [c for c in cc.get("coding") or []
                   if isinstance(c, dict)]
        if any(_is_autocoded_coding(c) for c in codings):
            e["augmented"] += 1
            continue
        coded_systems = [c.get("system") for c in codings if c.get("code")]
        if not coded_systems:
            continue  # text-only/uncoded and unaugmented: no match found
        if all(isinstance(s, str) and is_standard_code_system(s)
               for s in coded_systems):
            e["inv4_skipped_standard"] += 1
        else:
            e["mimic_wrapped_eligible"] += 1
    return {"per_class": dict(sorted(per_class.items()))}


def append_invariants(originals: list[dict], augmented: list[dict],
                      paths: Optional[dict[str, str]] = None) -> dict:
    """Gold-free quality evidence for the no-strip run: verify the
    AutoCoder APPENDED rather than replaced.

    For each resource present in both lists (joined by (type, id)) the
    original CodeableConcept codings must appear byte-identical and in
    position at the FRONT of the augmented coding list (no extension
    added to them), and every ADDED coding must carry
    ``userSelected == False`` and the autocoding provenance extension.
    """
    paths = paths or RAW_STATS_PATHS
    by_key = {(r.get("resourceType"), r.get("id")): r for r in augmented}
    replaced = user_selected = no_provenance = 0
    violations: list[str] = []
    for o in originals:
        key = (o.get("resourceType"), o.get("id"))
        path = paths.get(key[0])
        if not path:
            continue
        a = by_key.get(key)
        if a is None:
            continue
        o_cc, a_cc = o.get(path), a.get(path)
        if not isinstance(o_cc, dict) or not isinstance(a_cc, dict):
            continue
        o_codings = o_cc.get("coding") or []
        a_codings = a_cc.get("coding") or []
        if a_codings[:len(o_codings)] != o_codings:
            replaced += 1
            if len(violations) < 10:
                violations.append(
                    f"{'/'.join(str(k) for k in key)}: original codings "
                    f"not preserved verbatim at the front of coding[]")
            continue
        for coding in a_codings[len(o_codings):]:
            if coding.get("userSelected") is not False:
                user_selected += 1
            if not _is_autocoded_coding(coding):
                no_provenance += 1
    return {"originals_replaced_or_removed": replaced,
            "appended_without_user_selected_false": user_selected,
            "appended_without_provenance": no_provenance,
            "violations": violations}


# ── evaluation ────────────────────────────────────────────────────────

def _fresh_connection():
    import duckdb
    from fhir4ds.fhirpath.duckdb import register_fhirpath
    conn = duckdb.connect(
        config={"allow_unsigned_extensions": True})
    native = bool(register_fhirpath(conn))
    return conn, native


def _load_resources_table(conn, resources: list[dict]) -> None:
    conn.execute("CREATE OR REPLACE TABLE resources (resource JSON)")
    conn.executemany(
        "INSERT INTO resources VALUES (?)",
        [(json.dumps(r, sort_keys=True),) for r in sorted(
            resources, key=lambda x: (x.get("resourceType", ""),
                                      x.get("id", "")))])


def evaluate_slice(resources: list[dict], rubric) -> dict:
    """Evaluate the rubric over ``resources``; returns a JSON-safe
    scorecard summary plus per-SAM fail counts."""
    from fhir4ds.piqi.scorecard import evaluate_rubric

    if isinstance(rubric, tuple):
        _, criteria_meta = rubric
    else:
        criteria_meta = rubric.get("piqiCriteria") or []
    conn, native = _fresh_connection()
    try:
        _load_resources_table(conn, resources)
        card = evaluate_rubric(conn, rubric, source_table="resources",
                               verbose=True)
    finally:
        conn.close()
    fail_counts = Counter(i.sam_mnemonic for i in card.issues)
    return {
        "piqi_index": card.piqi_index,
        "potential_item_score": card.potential_item_score,
        "total_item_score": card.total_item_score,
        "critical_failure_count": card.critical_failure_count,
        "data_class_frequency": card.data_class_frequency,
        "dimension_rollup": card.dimension_rollup,
        "per_class": per_class_index(card, criteria_meta),
        "failing_sam_counts": dict(sorted(
            fail_counts.items(), key=lambda kv: -kv[1])),
        "fhirpath_native": native,
    }


# ── auto-coding leg ───────────────────────────────────────────────────

def _autocoded_any(resource: dict) -> bool:
    """True if any CodeableConcept anywhere in the resource carries an
    autocoding extension (walks nested dicts/lists generically)."""
    from fhir4ds.cql.loader.autocoding_extension import (
        AUTOCODING_EXTENSION_URL,
    )
    stack = [resource]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            codings = node.get("coding")
            if isinstance(codings, list):
                for coding in codings:
                    if not isinstance(coding, dict):
                        continue
                    for ext in coding.get("extension") or []:
                        if (isinstance(ext, dict)
                                and ext.get("url") == AUTOCODING_EXTENSION_URL):
                            return True
            stack.extend(v for v in node.values()
                         if isinstance(v, (dict, list)))
        elif isinstance(node, list):
            stack.extend(v for v in node if isinstance(v, (dict, list)))
    return False


def run_autocoder(stripped: list[dict], endpoint,
                  min_match_grade: str = "certain",
                  max_passes: int = 3,
                  search_mode: str = "hybrid") -> dict:
    """Augment ``stripped`` in place via the AutoCoder and return engine
    stats. ``endpoint`` is any TerminologyEndpoint. ``min_match_grade``
    selects the strictness arm: 'certain' (shipped default) or e.g.
    'probable' (recall-oriented, FDD-documented trade-off).

    ``max_passes`` re-runs augmentation over resources that received NO
    autocoding (the AutoCoder cache makes repeat passes cheap). This is
    resilience against TRANSIENT endpoint failures — the medterm4ds
    sidecar exhibits an intermittent native crash (SIGSEGV, 2026-11-20),
    and a single failed search leaves that resource permanently uncoded
    within one pass. A pass that adds nothing new stops the loop."""
    import duckdb  # cache table only; standalone connection
    from fhir4ds.cql.loader.auto_coder import AutoCoder, AutoCoderConfig

    cache_conn = duckdb.connect()
    passes = []
    try:
        coder = AutoCoder(endpoint, cache_conn,
                          config=AutoCoderConfig(
                              min_match_grade=min_match_grade,
                              search_mode=search_mode))

        def _uncoded_count() -> int:
            return sum(1 for r in stripped if not _autocoded_any(r))

        prev = _uncoded_count()
        for _ in range(max(1, max_passes)):
            coder.augment_resources(stripped)
            now = _uncoded_count()
            passes.append({"uncoded_after_pass": now})
            if now == prev or now == 0:
                break
            prev = now
        cache_rows = cache_conn.execute(
            f"SELECT count(*) FROM {AutoCoder.CACHE_TABLE}").fetchone()[0]
    finally:
        cache_conn.close()
    return {"cache_rows": int(cache_rows),
            "engine_version": coder._engine_version,
            "search_mode": coder._config.search_mode,
            "min_match_grade": coder._config.min_match_grade,
            "top_k": coder._config.top_k,
            "passes": passes}


def _autocoded_entries(resource: dict, path: str) -> list[dict]:
    from fhir4ds.cql.loader.autocoding_extension import (
        AUTOCODING_EXTENSION_URL,
    )
    cc = resource.get(path) or {}
    out = []
    for coding in cc.get("coding") or []:
        if any(isinstance(e, dict) and e.get("url") == AUTOCODING_EXTENSION_URL
               for e in (coding.get("extension") or [])):
            out.append(coding)
    return out


def gold_accuracy(gold: list[dict], augmented: list[dict]) -> dict:
    """Ground-truth recovery: the stripped codings are gold; measure how
    many autocoded codings reproduce them exactly / by code / by system.

    ``augmented`` must be the SAME objects (mutated in place) that were
    produced alongside ``gold`` — resources are joined by (type, id).
    """
    by_key = {(r.get("resourceType"), r.get("id")): r for r in augmented}
    n = exact = code_only = system_only = top1_exact = covered = 0
    grades: Counter = Counter()
    per_type: Counter = Counter()
    per_type_exact: Counter = Counter()
    for g in gold:
        n += 1
        r = by_key.get((g["resourceType"], g["id"]))
        if r is None:
            continue
        entries = _autocoded_entries(r, g["path"])
        if entries:
            covered += 1
        for e in entries:
            for wrapper in e.get("extension") or []:
                # the autocoding extension is a wrapper: sub-extensions
                # carry the six provenance fields
                for ext in (wrapper.get("extension") or []
                            if isinstance(wrapper, dict) else []):
                    if isinstance(ext, dict) and "match-grade" in str(
                            ext.get("url", "")):
                        grades[ext.get("valueCode") or "?"] += 1
        gold_pairs = {(c.get("system"), c.get("code")) for c in g["codings"]}
        gold_codes = {c.get("code") for c in g["codings"]}
        gold_systems = {c.get("system") for c in g["codings"]}
        rt = g["resourceType"]
        per_type[rt] += 1
        if any((e.get("system"), e.get("code")) in gold_pairs
               for e in entries):
            exact += 1
            per_type_exact[rt] += 1
        elif any(e.get("code") in gold_codes for e in entries):
            code_only += 1
        elif any(e.get("system") in gold_systems for e in entries):
            system_only += 1
        if entries and (entries[0].get("system"),
                        entries[0].get("code")) in gold_pairs:
            top1_exact += 1

    def pct(x: int) -> float:
        return round(x / n * 100.0, 2) if n else 0.0

    return {
        "gold_resources": n,
        "autocoding_coverage": {"n": covered, "pct": pct(covered)},
        "exact_recovery": {"n": exact, "pct": pct(exact)},
        "top1_exact_recovery": {"n": top1_exact, "pct": pct(top1_exact)},
        "code_only_recovery": {"n": code_only, "pct": pct(code_only)},
        "system_only_recovery": {"n": system_only, "pct": pct(system_only)},
        "per_type": {rt: {"stripped": c,
                          "exact": per_type_exact.get(rt, 0)}
                     for rt, c in sorted(per_type.items())},
        "match_grades_written": dict(sorted(grades.items())),
    }


def per_class_index(card, criteria: list[dict]) -> dict:
    """Per-data-class PIQI sub-index for one scorecard leg.

    Wraps the scorecard's ``per_data_class`` rollup (aggregated from
    the scoring criterion rows exactly like the flat totals —
    informational rows excluded) into ``potential`` / ``total`` /
    ``pct_index`` rows. Rubric classes with no scoring rows (absent
    from the corpus, or informational-only criteria) report zeroed
    rows; ordering is sorted by class name (deterministic). ``card``
    is a :class:`PIQIScorecard` or anything with ``per_data_class``.
    """
    out: dict[str, dict] = {}
    for dc in sorted({c["data_class"] for c in criteria}):
        row = card.per_data_class.get(dc, {"potential": 0, "total": 0})
        potential, total = row["potential"], row["total"]
        out[dc] = {"potential": potential, "total": total,
                   "pct_index": round(total / potential * 100.0, 2)
                   if potential else 0.0}
    return out


def recovery_table(before: dict, after: dict) -> dict:
    """Per-SAM fail-count movement between two scorecard summaries."""
    sams = sorted(set(before["failing_sam_counts"])
                  | set(after["failing_sam_counts"]))
    rows = {}
    recovered = new_failures = 0
    for s in sams:
        b = before["failing_sam_counts"].get(s, 0)
        a = after["failing_sam_counts"].get(s, 0)
        rows[s] = {"fail_before": b, "fail_after": a, "delta": a - b}
        if a < b:
            recovered += b - a
        elif a > b:
            new_failures += a - b
    return {"per_sam": rows, "total_fails_recovered": recovered,
            "total_new_failures": new_failures}


# ── unmapped-class documentation ──────────────────────────────────────

def unmapped_classes(resources: list[dict]) -> dict:
    """Corpus resource types the packaged PIQI views do not read."""
    from fhir4ds.piqi.authoring import VIEWS
    covered = {spec["resource"] for spec in VIEWS.values()}
    counts = Counter(r.get("resourceType", "?") for r in resources)
    return {"covered_types": sorted(covered & set(counts)),
            "unmapped": {t: c for t, c in sorted(counts.items())
                         if t not in covered},
            "note": ("Encounter/MedicationAdministration/MedicationDispense/"
                     "MedicationStatement/Specimen/Location/Organization/"
                     "Medication (standalone) have no PIQI data-class view; "
                     "Observation subclasses are captured via the "
                     "laboratory / vital-signs / social-history category "
                     "bindings.")}


# ── orchestration ─────────────────────────────────────────────────────

def run_benchmark(corpus_path: Union[str, Path], output_dir: Union[str, Path],
                   search_mode: str = "hybrid",
                  *, num_patients: int = DEFAULT_NUM_PATIENTS,
                  stripping: Optional[dict] = None,
                  skip_autocoding: bool = False,
                  phase: str = "all",
                  http_base_url: Optional[str] = None,
                  min_match_grade: str = "certain",
                  no_strip: bool = False,
                  _test_endpoint=None) -> dict:
    """Run one phase (or all phases) of the experiment.

    Two modes: **strip** (default; the constructed-BEFORE experiment
    with exact-recovery gold) and **no-strip** (``no_strip=True`` /
    ``--no-strip``; the production path — baseline PIQI on the
    AS-SHIPPED slice, autocoding of the RAW corpus with the DEFAULT
    system-aware AutoCoder, then after PIQI. No exact-recovery gold
    exists there — originals remain in place; quality evidence is the
    appended-not-replaced invariant plus spot-checks).

    Phases exist because the medterm4ds inference stack (torch/SapBERT)
    and the DuckDB native fhirpath extension do not coexist reliably in
    one process (intermittent SIGSEGV, 2026-11-20 run) — the ``autocode``
    phase must therefore run in a process that has NEVER registered the
    native extension, and the ``after`` phase in one that never imports
    medterm4ds:

    * ``piqi`` — slice, census, strip, baseline + before + ceiling
      scorecards; writes ``report.partial.json`` + ``stripped.jsonl`` +
      ``gold.jsonl`` into the output dir.
    * ``autocode`` — loads the saved stripped corpus, augments it via
      the in-process medterm4ds endpoint, writes ``augmented.jsonl`` and
      the ``autocoding`` / ``gold_accuracy`` sections into the partial
      report. Does NOT touch the native extension.
    * ``after`` — recomputes the deterministic slice/strip, swaps in the
      augmented resources, evaluates AFTER, builds the recovery table,
      writes the final ``piqi_autocoding_report.json``.
    * ``all`` — the original single-process path (safe only with
      ``--skip-autocoding``; kept for tests/small corpora).
    """
    stripping = stripping or DEFAULT_STRIPPING
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    corpus = load_corpus(corpus_path)
    slice_resources = build_slice(corpus, num_patients)

    census = census_text_only(slice_resources)
    if no_strip:
        stripped: list[dict] = []
        gold: list[dict] = []
    else:
        stripped, gold = strip_codings(slice_resources, stripping)
    rubric = build_mimic_rubric()

    # The PIQI evaluations register the DuckDB NATIVE fhirpath
    # extension. The `autocode` phase must NEVER run them (see the
    # run_benchmark docstring: torch + native extension = SIGSEGV), and
    # the `after` phase only needs its own evaluation.
    _runs_piqi_legs = phase in ("piqi", "all")

    _, rubric_criteria = rubric
    report: dict[str, Any] = {
        "experiment": "piqi-autocoding",
        "mode": "no_strip" if no_strip else "strip",
        "rubric": [{"sequence": c["sequence"],
                    "data_class": c["data_class"], "sam": c["sam"],
                    "scoring_effect": c["scoring_effect"]}
                   for c in rubric_criteria],
        "corpus_path": str(corpus_path),
        "num_patients": num_patients,
        "stripping_spec": {
            k: {"path": v["path"], "cap": v.get("cap"),
                **({"category": v["category"]} if "category" in v else {}),
                **({"text_from_code": True} if v.get("text_from_code")
                   else {})}
            for k, v in stripping.items()},
        "slice": {
            "resources": len(slice_resources),
            "by_type": dict(sorted(Counter(
                r.get("resourceType", "?")
                for r in slice_resources).items())),
        },
        "text_only_census": census,
        "stripped": (
            {"total": 0,
             "note": ("no-strip mode: the AS-SHIPPED slice is autocoded "
                      "with the default system-aware AutoCoder; there is "
                      "no exact-recovery gold (originals remain in "
                      "place)")}
            if no_strip else
            {"total": len(stripped),
             "unique_query_texts": len({g["text"] for g in gold}),
             "by_type": dict(sorted(Counter(
                 g["resourceType"] for g in gold).items()))}),
        "unmapped_classes": unmapped_classes(slice_resources),
    }

    if _runs_piqi_legs:
        report["baseline"] = evaluate_slice(slice_resources, rubric)

    if _runs_piqi_legs and not no_strip:
        # BEFORE = the slice with stripped resources REPLACING their
        # originals
        stripped_keys = {(g["resourceType"], g["id"]) for g in gold}
        before_corpus = [r for r in slice_resources
                         if (r.get("resourceType"), r.get("id"))
                         not in stripped_keys] + stripped
        report["before"] = evaluate_slice(before_corpus, rubric)

        # CEILING = the BEFORE corpus with the ORIGINAL codings
        # re-attached (text kept): the counterfactual fully-coded corpus
        # the AutoCoder is trying to reconstruct — the maximum
        # recoverable PIQI score.
        ceiling_corpus = copy.deepcopy(before_corpus)
        by_key = {(r.get("resourceType"), r.get("id")): r
                  for r in ceiling_corpus}
        for g in gold:
            r = by_key.get((g["resourceType"], g["id"]))
            if r is not None:
                cc = r.get(g["path"])
                if isinstance(cc, dict):
                    cc["coding"] = copy.deepcopy(g["codings"])
        report["ceiling"] = evaluate_slice(ceiling_corpus, rubric)

    if no_strip:
        if phase == "piqi":
            report["gold_accuracy"] = None
            _dump_jsonl(out / "nostrip_slice.jsonl", slice_resources)
            (out / "report.partial.json").write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8")
            return report

        if phase == "autocode":
            partial_path = out / "report.partial.json"
            report = json.loads(partial_path.read_text(encoding="utf-8"))
            working = _load_jsonl(out / "nostrip_slice.jsonl")
            originals = copy.deepcopy(working)
            endpoint = (_test_endpoint or _make_endpoint(
                http_base_url, breaker_threshold=10 ** 9))
            stats = run_autocoder(working, endpoint,
                                  min_match_grade=min_match_grade,
                                  search_mode=search_mode)
            stats["endpoint"] = ("test_stub" if _test_endpoint else
                                 (http_base_url or "in_process"))
            report["autocoding"] = stats
            report["gold_accuracy"] = None
            report["augmentation"] = augmentation_stats(working)
            report["append_invariants"] = append_invariants(
                originals, working)
            _dump_jsonl(out / "augmented.jsonl", working)
            partial_path.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8")
            return report

        if phase == "after":
            partial_path = out / "report.partial.json"
            report = json.loads(partial_path.read_text(encoding="utf-8"))
            augmented = _load_jsonl(out / "augmented.jsonl")
            augmented_keys = {(r.get("resourceType"), r.get("id"))
                              for r in augmented}
            after_corpus = [
                r for r in slice_resources
                if (r.get("resourceType"), r.get("id"))
                not in augmented_keys] + augmented
            report["after"] = evaluate_slice(after_corpus, rubric)
            report["recovery"] = recovery_table(report["baseline"],
                                                report["after"])
            (out / "piqi_autocoding_report.json").write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8")
            return report

        # phase == "all" (no-strip): single-process path
        if not skip_autocoding:
            endpoint = (_test_endpoint or _make_endpoint(http_base_url))
            stats = run_autocoder(slice_resources, endpoint,
                                  min_match_grade=min_match_grade,
                                  search_mode=search_mode)
            report["autocoding"] = stats
            report["gold_accuracy"] = None
            report["augmentation"] = augmentation_stats(slice_resources)
            report["after"] = evaluate_slice(slice_resources, rubric)
            report["recovery"] = recovery_table(report["baseline"],
                                                report["after"])
        else:
            report["autocoding"] = None
            report["gold_accuracy"] = None
            report["after"] = None
            report["recovery"] = None
        (out / "piqi_autocoding_report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        return report

    if phase == "piqi":
        _dump_jsonl(out / "stripped.jsonl", stripped)
        _dump_jsonl(out / "gold.jsonl", gold)
        (out / "report.partial.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        return report

    if phase == "autocode":
        partial_path = out / "report.partial.json"
        report = json.loads(partial_path.read_text(encoding="utf-8"))
        stripped = _load_jsonl(out / "stripped.jsonl")
        gold = _load_jsonl(out / "gold.jsonl")
        endpoint = _make_endpoint(http_base_url,
                                  breaker_threshold=10 ** 9)
        stats = run_autocoder(stripped, endpoint,
                              min_match_grade=min_match_grade,
                              search_mode=search_mode)
        stats["endpoint"] = (http_base_url or "in_process")
        if not http_base_url:
            from fhir4ds.cql.terminology.in_process_adapter import (
                prefer_terminology_layout,
            )
            stats["medterm4ds_layout"] = prefer_terminology_layout()
        report["autocoding"] = stats
        report["gold_accuracy"] = gold_accuracy(gold, stripped)
        _dump_jsonl(out / "augmented.jsonl", stripped)
        partial_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        return report

    if phase == "after":
        partial_path = out / "report.partial.json"
        report = json.loads(partial_path.read_text(encoding="utf-8"))
        augmented = _load_jsonl(out / "augmented.jsonl")
        stripped_keys = {(r.get("resourceType"), r.get("id"))
                         for r in augmented}
        before_corpus = [
            r for r in slice_resources
            if (r.get("resourceType"), r.get("id")) not in stripped_keys
        ] + augmented
        report["after"] = evaluate_slice(before_corpus, rubric)
        report["recovery"] = recovery_table(report["before"],
                                            report["after"])
        (out / "piqi_autocoding_report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        return report

    # phase == "all": original single-process path
    if not skip_autocoding:
        from fhir4ds.cql.terminology.in_process_adapter import (
            InProcessTerminologyEndpoint,
            prefer_terminology_layout,
        )
        layout = prefer_terminology_layout()
        endpoint = InProcessTerminologyEndpoint()
        stats = run_autocoder(stripped, endpoint,
                              min_match_grade=min_match_grade,
                              search_mode=search_mode)
        stats["medterm4ds_layout"] = layout
        stats["endpoint"] = "in_process"
        report["autocoding"] = stats
        report["gold_accuracy"] = gold_accuracy(gold, stripped)
        report["after"] = evaluate_slice(before_corpus, rubric)
        report["recovery"] = recovery_table(report["before"],
                                            report["after"])
    else:
        report["autocoding"] = None
        report["gold_accuracy"] = None
        report["after"] = None
        report["recovery"] = None

    (out / "piqi_autocoding_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    return report


def _make_endpoint(http_base_url: Optional[str],
                   breaker_threshold: int = 5):
    """Build the augmentation endpoint.

    Default is the in-process medterm4ds engine. ``http_base_url``
    switches to the HTTP sidecar — REQUIRED on hosts where the
    in-process engine (torch + DuckDB in one process) segfaults; run
    ``MEDTERM4DS_DB=<lookup db> python3 -c "from
    medterm4ds.apps.fhir_api import main; main()"`` and pass its FHIR
    root (e.g. ``http://127.0.0.1:8012/fhir``). For benchmark runs the
    breaker threshold is raised so an intermittent sidecar restart
    (auto-restart wrapper) cannot poison the whole run.
    """
    if http_base_url:
        from fhir4ds.cql.terminology.http_adapter import (
            HTTPTerminologyEndpoint,
        )
        return HTTPTerminologyEndpoint(
            http_base_url, breaker_threshold=breaker_threshold)
    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )
    return InProcessTerminologyEndpoint()


def _dump_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def summarize(report: dict) -> str:
    lines = [
        f"PIQI auto-coding experiment — {report['corpus_path']}",
        f"  slice: {report['num_patients']} patients, "
        f"{report['slice']['resources']} resources",
        f"  text-only CodeableConcepts in slice: "
        f"{report['text_only_census']['text_only_total']}",
    ]
    stripped = report.get("stripped") or {}
    if stripped.get("total"):
        lines.append(
            f"  stripped for BEFORE corpus: {stripped['total']} "
            f"({stripped['unique_query_texts']} unique texts)")
    elif report.get("mode") == "no_strip":
        lines.append("  mode: no-strip (raw corpus autocoded in place)")
    for leg in ("baseline", "before", "after", "ceiling"):
        s = report.get(leg)
        if not s:
            continue
        lines.append(
            f"  {leg:8s} PIQI index {s['piqi_index']:6.2f}  "
            f"({s['total_item_score']}/{s['potential_item_score']})")
    rec = report.get("recovery")
    if rec:
        lines.append(f"  recovery: {rec['total_fails_recovered']} fails "
                     f"recovered, {rec['total_new_failures']} new fails")
        if report.get("ceiling") and report.get("after"):
            gap = (report["ceiling"]["total_item_score"]
                   - report["after"]["total_item_score"])
            lines.append(f"  after vs ceiling: {gap} items short of the "
                         "fully-coded counterfactual")
    gold = report.get("gold_accuracy")
    if gold:
        lines.append(
            f"  ground truth: coverage {gold['autocoding_coverage']['pct']}%"
            f"  exact {gold['exact_recovery']['pct']}%"
            f"  top1 exact {gold['top1_exact_recovery']['pct']}%"
            f"  code-only {gold['code_only_recovery']['pct']}%")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="PIQI before/after auto-coding benchmark")
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--num-patients", type=int,
                        default=DEFAULT_NUM_PATIENTS)
    parser.add_argument("--skip-autocoding", action="store_true")
    parser.add_argument(
        "--http-base-url", default=None,
        help=("Use the medterm4ds HTTP sidecar at this FHIR root for the "
              "autocode phase (e.g. http://127.0.0.1:8012/fhir) instead "
              "of the in-process engine — required where torch+DuckDB "
              "in one process segfaults."))
    parser.add_argument(
        "--min-match-grade", default="certain",
        choices=["certain", "exact", "probable", "possible", "broader"],
        help=("AutoCoder threshold arm: 'certain' is the shipped strict "
              "default; 'probable' is the recall-oriented arm."))
    parser.add_argument(
        "--search-mode", default="hybrid",
        choices=["lexical", "hybrid", "semantic"],
        help=("Terminology retrieval mode for the auto-coding arm "
              "(ablation: lexical vs semantic vs hybrid). Default hybrid "
              "matches the shipped AutoCoder default."))
    parser.add_argument(
        "--no-strip", action="store_true",
        help=("Production-path mode: skip the strip phase entirely. Baseline "
              "PIQI on the AS-SHIPPED slice, autocode the RAW corpus with "
              "the DEFAULT system-aware AutoCoder (INV-4 skips only "
              "standard-coded concepts), then after PIQI. No "
              "exact-recovery gold (originals remain in place)."))
    parser.add_argument(
        "--phase", choices=["all", "piqi", "autocode", "after"],
        default="all",
        help=("Phase isolation: medterm4ds (torch) and the DuckDB native "
              "fhirpath extension do not coexist reliably in one process "
              "(intermittent SIGSEGV) — run 'piqi', then 'autocode', then "
              "'after' as separate invocations."))
    args = parser.parse_args(argv)
    skip = args.skip_autocoding or args.phase in ("piqi", "after")
    report = run_benchmark(args.corpus, args.output_dir,
                           num_patients=args.num_patients,
                           skip_autocoding=skip,
                           phase=args.phase,
                           http_base_url=args.http_base_url,
                           min_match_grade=args.min_match_grade,
                           search_mode=args.search_mode,
                           no_strip=args.no_strip)
    if args.phase != "autocode":
        print(summarize(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
