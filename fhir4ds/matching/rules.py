"""Category-1 match rule table (port of the CMS deterministic rule set).

Ported from icanbwell/cms-hte-patient-matching
(CMS Patient Matching Proposal v3.4.0, Apache-2.0), files
`patient_matching/matching/table2_rules.py` and `.../collision.py`
(fetched 2026-11-17, branch main).

Slice 2 P-value pinning: every rule's P(collision) is computed at import
from the upstream Table-3 u-probability table (`FIELD_U_PROBS` below) via
the upstream `p_collision` product, so the pinned values are exactly the
upstream numbers — no `p_estimated` entries remain.

Slice-2 field-combination correction: slice 1 carried approximate field
combinations for rules where the study had not been transcribed. Slice 2
replaces ALL 29 rule field sets with the upstream v3.4.0 combinations
rule-for-rule (e.g. upstream rule 02 is First + Last* + DOB* + Phone, not
First+Last+DOB+Street; upstream has NO First+Last+DOB-alone rule — it fails
the 2e-12 approval threshold). Rule ids follow upstream numbering; rule 29
was removed by CMS upstream, so ids run 01-28 plus 30 (29 rules).

Field modes are `exact` or `fuzzy`: fuzzy names = nickname equivalence or
Damerau-Levenshtein <= 1 (>= 5 chars, CMS E.3); fuzzy DOB = +/- 1 day.
`p_fuzzy_fields` names which fields take their fuzzy u-probability in the
fuzzy P(collision) product (upstream `fuzzy_fields`); DOB has no fuzzy
u-value upstream (Table 3), so DOB* contributes its exact u to both
figures. Rules are ordered P(collision) ascending, ties by rule id —
deterministic.

`max_fuzzy_fields` is transcribed for documentation parity with upstream;
this engine does not enforce a simultaneous-fuzzy cap (each F-marked field
is verified exact-first, then fuzzy, per the AMUX-134 slice-2 design).

fhir4ds deviation from upstream table2 (Joel-approved 2026-11-17): rule 30
sibling guard. Upstream rule 30 (Last Name* + DOB + Phone) carries no
twin/sibling disambiguation, so siblings sharing a household phone, last
name, and DOB link as the same person. fhir4ds adds optional per-rule
``guards`` — rule 30 carries ``("ssn4_agreement", "first_name_agreement")``:
after field verification passes, the pair is dropped from the rule when
BOTH sides have non-empty ssn4 sets that are disjoint, or BOTH sides have
non-empty first-name sets with no cross-pair match (exact, nickname set, or
fuzzy per ``name_fuzzy_match``). A guard failure only skips the rule for
that pair — it is not a hard negation; any other rule may still fire.
Fields, modes, and P-values are unchanged from upstream.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from . import name_embedding

__all__ = [
    "MatchRule",
    "CATEGORY1_RULES",
    "EXACT",
    "FUZZY",
    "EMBED",
    "FIELD_U_PROBS",
    "APPROVAL_THRESHOLD",
    "p_collision",
    "SSN4_AGREEMENT",
    "FIRST_NAME_AGREEMENT",
    "PHONE_AGREEMENT",
    "GUARD_FIELD_BY_NAME",
    "BAND_U_VALUES",
    "BAND_EDGES",
    "embedding_rules",
    "patient_rules_with_embedding",
    "PATIENT_RULES_WITH_EMBEDDING",
]

EXACT = "exact"
FUZZY = "fuzzy"
#: FHIR4-20: name fields matched by the pinned name-embedding model's
#: calibrated distance bands (see ``matching/name_embedding.py``).
EMBED = "embed"

# Upstream Table 3: field -> (conservative u exact, conservative u fuzzy or
# None when the field has no fuzzy variant). Upstream dismisses Middle Name,
# Suffix, and Year of Birth for data-quality reasons; no Table-2 rule uses
# them, so they are not transcribed here.
FIELD_U_PROBS: dict[str, tuple[float, Optional[float]]] = {
    "first": (0.02, 0.03),
    "last": (0.005, 0.01),
    "dob": (0.0001, None),
    "street_line": (0.00003, 0.00006),
    "phone": (0.000001, None),
    "email": (0.000001, None),
    "ssn4": (0.0001, None),
    "itin4": (0.0001, None),
    "legal_id": (0.000001, None),
    "mbi": (0.000001, None),
    # Upstream: spec says "~=0"; a small nonzero float avoids a literal 0.0
    # masking other fields' probabilities in the product.
    "namespace_id": (1e-15, None),
    "member_id": (0.000001, None),
    "subscriber_id": (0.0001, None),
    # --- AMUX-150 chunk B: identity-resource u-values ---
    # NON-UPSTREAM fhir4ds estimates (upstream Table 3 is patient-specific);
    # conservative collision budgets for identity resources.
    "npi": (1e-9, None),        # 10-digit issued-unique (NPI reality ~1e-10)
    "clia": (1e-7, None),       # CLIA lab identifier
    "tax_id": (1e-7, None),     # TIN/EIN
    "org_name": (0.02, 0.04),   # org names collide at least as much as first names
    "loc_name": (0.01, 0.02),   # "Main Pharmacy" / "Lab Draw Station" ubiquitous
    "addr_key": (0.0001, None),  # street+city+state+zip5 composite
    "geo_key": (0.0001, None),  # rounded lat/long pair
}

# CMS approval threshold (upstream collision.APPROVAL_THRESHOLD).
APPROVAL_THRESHOLD = 2e-12

#: Fields that share information and therefore never corroborate each
#: other under CR-002 threshold enforcement. ``addr_key`` embeds
#: ``street_line`` (line[0]|city|state|postal5), so an agreeing
#: street_line adds no independent evidence to a rule that already
#: matched on addr_key (and vice versa).
FIELD_DEPENDENCY_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"addr_key", "street_line"}),
)


def p_collision(
    fields: tuple[tuple[str, str], ...],
    fuzzy_fields: frozenset[str] = frozenset(),
) -> float:
    """Joint collision probability: product of each field's u-probability.

    `fuzzy_fields` names which fields use their fuzzy u instead of exact
    (only meaningful for fields that have one). Port of upstream
    collision.p_collision.
    """
    result = 1.0
    for name, _mode in fields:
        exact_u, fuzzy_u = FIELD_U_PROBS[name]
        if name in fuzzy_fields and fuzzy_u is not None:
            result *= fuzzy_u
        else:
            result *= exact_u
    return result


# Guard names (fhir4ds deviation, rule 30 only — see module docstring).
SSN4_AGREEMENT = "ssn4_agreement"
FIRST_NAME_AGREEMENT = "first_name_agreement"
# AMUX-150 chunk B: identity-resource guard (practitioner P4) — the same
# post-verification disagreement semantics over the phone field.
PHONE_AGREEMENT = "phone_agreement"

#: Guard name -> guarded field (AMUX-150: the guard whitelist is DATA —
#: each rule set declares its guard-able fields through the guards its
#: rules carry; this map is the closed vocabulary).
GUARD_FIELD_BY_NAME: dict[str, str] = {
    SSN4_AGREEMENT: "ssn4",
    FIRST_NAME_AGREEMENT: "first",
    PHONE_AGREEMENT: "phone",
}


@dataclass(frozen=True)
class MatchRule:
    rule_id: str
    fields: tuple[tuple[str, str], ...]  # (field_name, exact|fuzzy)
    p_collision: float  # exact-field product (upstream p_collision_exact)
    p_collision_fuzzy: float  # product with p_fuzzy_fields fuzzy (== exact when none)
    p_fuzzy_fields: frozenset[str]  # fields taking the fuzzy u in p_collision_fuzzy
    max_fuzzy_fields: int = 0
    p_estimated: bool = False  # retained for API compat; always False since slice 2
    description: str = ""
    # Post-verification disagreement guards (fhir4ds deviation). A candidate
    # that fails any named guard is dropped from THIS rule's survivors;
    # evaluation continues with the next rule (no hard negation of the pair).
    guards: tuple[str, ...] = ()
    # AMUX-150: disabled rules stay listed (documentation + one-flag
    # enablement) but are skipped by the engine.
    enabled: bool = True
    # FHIR4-20: per-band u-values for EMBED-mode name fields, ordered
    # tight -> loose. When present, verification returns the matched band
    # per embed field and the engine computes the effective P(collision)
    # as product(other fields' u) x product(embed fields' band u).
    # ``p_collision`` / ``p_collision_fuzzy`` carry the TIGHTEST- /
    # LOOSEST-band products for table ordering (existing fuzzy rules get
    # first refusal by construction of the sort).
    band_u_values: tuple[tuple[str, float], ...] = ()

    def exact_fields(self) -> tuple[str, ...]:
        return tuple(name for name, mode in self.fields if mode == EXACT)

    def fuzzy_fields(self) -> tuple[str, ...]:
        return tuple(name for name, mode in self.fields if mode == FUZZY)

    def embed_fields(self) -> tuple[str, ...]:
        return tuple(name for name, mode in self.fields if mode == EMBED)

    @property
    def effective_p_min(self) -> float:
        """Ordering key: the smallest effective P(collision) the rule can
        achieve (tightest band for EMBED rules, exact product otherwise)."""
        return self.p_collision

    def effective_p(self, embed_bands: dict[str, str]) -> float:
        """Effective P(collision) for one verified pair.

        For rules without EMBED fields this is the legacy selection
        (``p_collision``); for EMBED rules it is the product of the
        non-embed fields' u-probabilities (fuzzy u for the rule's fuzzy
        fields) times each embed field's matched-band u-value.
        """
        if not self.band_u_values:
            return self.p_collision
        u_by_band = dict(self.band_u_values)
        result = 1.0
        for name, mode in self.fields:
            if mode == EMBED:
                band = embed_bands.get(name)
                if band is None:
                    return float("inf")  # unverified embed field (defensive)
                result *= u_by_band[band]
                continue
            exact_u, fuzzy_u = FIELD_U_PROBS[name]
            if mode == FUZZY and name in self.p_fuzzy_fields and fuzzy_u is not None:
                result *= fuzzy_u
            else:
                result *= exact_u
        return result


def _r(
    rule_id: str,
    fields: list[tuple[str, str]],
    desc: str,
    p_fuzzy_fields: frozenset[str] = frozenset(),
    max_fuzzy_fields: int = 0,
    guards: tuple[str, ...] = (),
) -> MatchRule:
    return MatchRule(
        rule_id=rule_id,
        fields=tuple(fields),
        p_collision=p_collision(tuple(fields)),
        p_collision_fuzzy=p_collision(tuple(fields), fuzzy_fields=p_fuzzy_fields),
        p_fuzzy_fields=p_fuzzy_fields,
        max_fuzzy_fields=max_fuzzy_fields,
        description=desc,
        guards=guards,
    )


_E, _F = EXACT, FUZZY

# --- Category-1 rules (upstream v3.4.0 table2_rules.py, 29 rules) -----------
_RULE_DEFS: list[MatchRule] = [
    _r(
        "01",
        [("first", _F), ("last", _F), ("dob", _F), ("street_line", _F)],
        "First Name* + Last Name* + DOB* + Street Line*",
        p_fuzzy_fields=frozenset({"first", "last"}),
        max_fuzzy_fields=2,
    ),
    _r(
        "02",
        [("first", _E), ("last", _F), ("dob", _F), ("phone", _E)],
        "First Name + Last Name* + DOB* + Phone Number",
        p_fuzzy_fields=frozenset({"last"}),
    ),
    _r(
        "03",
        [("first", _F), ("last", _F), ("dob", _F), ("email", _E)],
        "First Name* + Last Name* + DOB* + Email Address",
        p_fuzzy_fields=frozenset({"first", "last"}),
        max_fuzzy_fields=2,
    ),
    _r(
        "04",
        [("first", _F), ("last", _E), ("dob", _E), ("ssn4", _E)],
        "First Name* + Last Name + DOB + SSN Last 4",
        p_fuzzy_fields=frozenset({"first"}),
    ),
    _r(
        "05",
        [("first", _E), ("last", _F), ("dob", _E), ("ssn4", _E)],
        "First Name + Last Name* + DOB + SSN Last 4",
        p_fuzzy_fields=frozenset({"last"}),
    ),
    _r(
        "06",
        [("first", _F), ("last", _E), ("dob", _E), ("itin4", _E)],
        "First Name* + Last Name + DOB + ITIN Last 4",
        p_fuzzy_fields=frozenset({"first"}),
    ),
    _r(
        "07",
        [("first", _E), ("last", _F), ("dob", _E), ("itin4", _E)],
        "First Name + Last Name* + DOB + ITIN Last 4",
        p_fuzzy_fields=frozenset({"last"}),
    ),
    _r("08", [("first", _E), ("dob", _E), ("mbi", _E)], "First Name + DOB + MBI"),
    _r("09", [("first", _E), ("dob", _E), ("legal_id", _E)], "First Name + DOB + Legal ID"),
    _r(
        "10",
        [("last", _F), ("dob", _F), ("legal_id", _E)],
        "Last Name* + DOB* + Legal ID",
        p_fuzzy_fields=frozenset({"last"}),
    ),
    _r("11", [("first", _E), ("dob", _E), ("phone", _E)], "First Name + DOB + Phone Number"),
    _r("12", [("first", _E), ("dob", _E), ("email", _E)], "First Name + DOB + Email Address"),
    _r("13", [("first", _E), ("phone", _E), ("ssn4", _E)], "First Name + Phone Number + SSN Last 4"),
    _r("14", [("first", _E), ("phone", _E), ("itin4", _E)], "First Name + Phone Number + ITIN Last 4"),
    _r("15", [("first", _E), ("email", _E), ("ssn4", _E)], "First Name + Email Address + SSN Last 4"),
    _r("16", [("first", _E), ("email", _E), ("itin4", _E)], "First Name + Email Address + ITIN Last 4"),
    _r("17", [("phone", _E), ("mbi", _E)], "Phone Number + MBI"),
    _r("18", [("phone", _E), ("legal_id", _E)], "Phone Number + Legal ID (w/issuing-authority namespace)"),
    _r("19", [("email", _E), ("mbi", _E)], "Email Address + MBI"),
    _r("20", [("email", _E), ("legal_id", _E)], "Email Address + Legal ID (w/issuing-authority namespace)"),
    _r("21", [("legal_id", _E), ("mbi", _E)], "Legal ID + MBI"),
    _r("22", [("namespace_id", _E)], "Namespace bound unique identifiers (EMPI, FHIR Patient ID, CSP UUID)"),
    _r("23", [("first", _E), ("dob", _E), ("member_id", _E)], "First Name + DOB + Member ID (payer namespace)"),
    _r(
        "24",
        [("last", _F), ("dob", _F), ("member_id", _E)],
        "Last Name* + DOB* (+/-1 day) + Member ID (payer namespace)",
        p_fuzzy_fields=frozenset({"last"}),
    ),
    _r("25", [("phone", _E), ("member_id", _E)], "Phone Number + Member ID (payer namespace)"),
    _r("26", [("email", _E), ("member_id", _E)], "Email Address + Member ID (payer namespace)"),
    _r(
        "27",
        [("first", _F), ("last", _E), ("dob", _E), ("subscriber_id", _E)],
        "First Name* + Last Name + DOB + Subscriber ID (payer namespace)",
        p_fuzzy_fields=frozenset({"first"}),
    ),
    _r(
        "28",
        [("first", _E), ("last", _F), ("dob", _E), ("subscriber_id", _E)],
        "First Name + Last Name* + DOB + Subscriber ID (payer namespace)",
        p_fuzzy_fields=frozenset({"last"}),
    ),
    _r(
        "30",
        [("last", _F), ("dob", _E), ("phone", _E)],
        "Last Name* + DOB + Phone Number "
        "(legacy exception; fhir4ds sibling guard: ssn4/first-name agreement)",
        p_fuzzy_fields=frozenset({"last"}),
        guards=(SSN4_AGREEMENT, FIRST_NAME_AGREEMENT),
    ),
]

CATEGORY1_RULES: list[MatchRule] = sorted(_RULE_DEFS, key=lambda r: (r.p_collision, r.rule_id))


# ---------------------------------------------------------------------------
# FHIR4-20: embedding match rules (E1-E3) — ADDITIVE, never a rewrite of
# CATEGORY1_RULES. See
# fhir4ds-private/docs/architecture/plans/FEATURE_NAME_EMBEDDING.md §3.3.
# ---------------------------------------------------------------------------

#: Band u-value CONSTANTS (P(collision) of "embedding distance falls in
#: this band or any tighter band" over distinct-name pairs — cumulative
#: from tight outward). CALIBRATED 2026-11-20 by FHIR4-20 P4
#: (``scripts/calibrate_name_embedding.py``, manifest flag
#: ``calibrated=true``): cumulative distinct-pair rates over a seeded
#: 1,000,000-pair sample of the ONC given-name pool (1,489 unique names)
#: plus 2,118 manufactured cross-group DL<=2 hard negatives, at band
#: edges chosen on the held-out (by-group) positive split to capture
#: 0.35 / 0.70 / 0.85 of 3,463 calibration positives; rounded UP to 2
#: significant digits (conservative). The unit test asserts
#: manifest == constants.
BAND_U_VALUES: tuple[tuple[str, float], ...] = (
    ("tight", 0.0025),
    ("mid", 0.034),
    ("loose", 0.12),
)

#: Band upper edges on cosine distance — CALIBRATED with BAND_U_VALUES
#: (same measured histograms; smallest grid edge meeting each cumulative
#: positive-capture target). The runtime comparison carries
#: ±``name_embedding.BAND_HYSTERESIS`` slack toward the tighter band.
BAND_EDGES: dict[str, float] = {"tight": 0.19, "mid": 0.36, "loose": 0.5}

#: Category-1 approval threshold (rules.py slice-2 note): an E-rule's
#: effective P at a band must stay <= this budget for the band to appear
#: in that rule's band list (FDD §3.2 — a band that cannot appear in an
#: approvable rule product ships in NO rule). Measured u-values truncate
#: per rule: E1 keeps tight+mid (loose 6e-12 > budget), E2 keeps all
#: three (phone companion), E3 keeps tight only (double-embed mid
#: 3.5e-12 > budget).
EMBED_APPROVAL_P = 2e-12


def _approvable_rule_bands(
    fields: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, float], ...]:
    """This rule's approvable band list: the tight-anchored prefix of
    ``BAND_U_VALUES`` whose effective P stays within the Category-1
    approval budget (FDD §3.2 — a band that cannot appear in an approvable
    rule product for THIS rule ships in NO rule; approvability is a
    per-rule product, so the truncation is per rule, not global)."""
    embed_count = sum(1 for _f, mode in fields if mode == EMBED)
    companion = 1.0
    for name, mode in fields:
        if mode != EMBED:
            companion *= FIELD_U_PROBS[name][0]
    kept: list[tuple[str, float]] = []
    for band, u in BAND_U_VALUES:
        product = u ** embed_count * companion
        if product > EMBED_APPROVAL_P and not math.isclose(
            product, EMBED_APPROVAL_P, rel_tol=1e-12
        ):
            break
        kept.append((band, u))
    return tuple(kept)


def _embedding_p(fields: tuple[tuple[str, str], ...], band: str) -> float:
    """P(collision) bound for an E-rule at one band: product of the
    non-embed fields' u-probabilities x the band's u-value PER embed
    field (E3 carries two EMBED fields and squares the band u)."""
    result = 1.0
    embed_count = 0
    for name, mode in fields:
        if mode == EMBED:
            embed_count += 1
        else:
            result *= FIELD_U_PROBS[name][0]
    return result * dict(BAND_U_VALUES)[band] ** embed_count


def embedding_rules() -> list[MatchRule]:
    """E1-E3 (embedding twins of the strongest fuzzy shapes), or [] when
    the pinned artifact is missing/corrupt (degradation contract — the
    loader has then already emitted its one WARNING)."""
    if not name_embedding.artifact_available():
        return []
    u = dict(BAND_U_VALUES)
    # E2/E3 carry the rule-30-precedent sibling guard (ssn4 agreement):
    # a pair whose SSN last-4 are non-empty and disjoint is not one
    # person, whatever the names look like. E1 requires exact ssn4
    # in-rule already. Missing ssn4 on either side never fails the guard.
    defs = [
        ("E1",
         [("first", EMBED), ("last", EXACT), ("dob", EXACT), ("ssn4", EXACT)],
         "First Name (embed) + Last Name + DOB + SSN Last 4 "
         "[twin of 04 for DL>=2 name variants]"),
        ("E2",
         [("first", EMBED), ("last", EXACT), ("dob", EXACT), ("phone", EXACT)],
         "First Name (embed) + Last Name + DOB + Phone Number "
         "[twin of 11-class shapes; ssn4-agreement sibling guard]",
         (SSN4_AGREEMENT,)),
        ("E3",
         [("first", EMBED), ("last", EMBED), ("dob", EXACT),
          ("street_line", EXACT)],
         "First Name (embed) + Last Name (embed) + DOB + Street Line "
         "[twin of 01 for full-name variants; ssn4-agreement sibling guard]",
         (SSN4_AGREEMENT,)),
    ]
    rules = []
    for entry in defs:
        rule_id, fields, desc = entry[0], entry[1], entry[2]
        guards = entry[3] if len(entry) > 3 else ()
        fields = tuple(fields)
        bands = _approvable_rule_bands(fields)
        if not bands or bands[0][0] != "tight":
            # Typed check (not ``assert``): the invariant must survive
            # ``python -O`` — a recalibration pushing the tight band out of
            # budget is an authoring error, not a runtime assumption.
            raise ValueError(
                f"{rule_id}: tight band must be approvable (calibrated "
                f"u-values out of budget)")
        rules.append(MatchRule(
            rule_id=rule_id,
            fields=fields,
            p_collision=_embedding_p(fields, bands[0][0]),
            p_collision_fuzzy=_embedding_p(fields, bands[-1][0]),
            p_fuzzy_fields=frozenset(),
            description=desc,
            guards=guards,
            band_u_values=bands,
        ))
    return rules


def patient_rules_with_embedding() -> list[MatchRule]:
    """CATEGORY1_RULES (verbatim order) + E1-E3 sorted by tightest-band P.

    CATEGORY1_RULES is untouched and its entries/relative order are
    preserved exactly, and every E-rule is ordered AFTER the whole
    Category-1 table. FDD §3.3 deviation note: the FDD sketched sorting
    the combined table by tightest-band ``effective_p_min`` expecting that
    to keep cheaper fuzzy rules first, but measured placeholder band
    u-values (tight 0.01) make E1's tightest product (5e-13) SMALLER than
    rule 04's exact product (1e-12) — P-ordering would let E1 preempt
    Category-1 attribution on exactly-equal pairs. Ordering the E-rules
    last implements the FDD's stated intent directly ("the embedding rule
    only ever sees pairs the fuzzy comparators already rejected") and
    keeps every existing match's rule attribution byte-identical."""
    return sorted(
        list(CATEGORY1_RULES) + embedding_rules(),
        key=lambda r: (r.rule_id in ("E1", "E2", "E3"),
                       r.effective_p_min, r.rule_id),
    )


#: Snapshot of the combined table for the artifact shipped in-tree,
#: resolved lazily on first attribute access (keeps ``import`` free of
#: artifact I/O; a missing artifact then warns once at first use, not at
#: import). Call :func:`patient_rules_with_embedding` for the live table
#: (tests / alternate artifact deployments).
def __getattr__(name: str):
    if name == "PATIENT_RULES_WITH_EMBEDDING":
        return patient_rules_with_embedding()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
