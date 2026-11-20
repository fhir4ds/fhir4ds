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

from dataclasses import dataclass
from typing import Optional

__all__ = [
    "MatchRule",
    "CATEGORY1_RULES",
    "EXACT",
    "FUZZY",
    "FIELD_U_PROBS",
    "APPROVAL_THRESHOLD",
    "p_collision",
    "SSN4_AGREEMENT",
    "FIRST_NAME_AGREEMENT",
    "PHONE_AGREEMENT",
    "GUARD_FIELD_BY_NAME",
]

EXACT = "exact"
FUZZY = "fuzzy"

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

    def exact_fields(self) -> tuple[str, ...]:
        return tuple(name for name, mode in self.fields if mode == EXACT)

    def fuzzy_fields(self) -> tuple[str, ...]:
        return tuple(name for name, mode in self.fields if mode == FUZZY)


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
