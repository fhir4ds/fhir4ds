"""AMUX-150 chunk B — identity-resource rule tables.

Practitioner / Organization / Location rule sets on the shared
:class:`~fhir4ds.matching.rules.MatchRule` machinery, with extended
u-probability entries (NON-UPSTREAM fhir4ds estimates — upstream
CMS Table 3 is patient-specific; see ``rules.FIELD_U_PROBS``).

Per-rule-set approval thresholds (FDD §3.3 / §10 Q1 default, Joel
approved 2026-11-20): identity resources tolerate a higher collision
budget than patient EMPI merges —

- practitioners 1e-8 (NPI-alone P ≈ 1e-9 fires as rule P1)
- organizations 1e-8
- locations 1e-6

CR-002 (Joel decision 2026-11-20): the thresholds are now ENFORCED for
non-Patient entities — the rule sets ship as :class:`RuleSet` lists
carrying their ``approval_threshold``, and the engine refuses to link a
candidate on a rule whose effective P(collision) exceeds the budget
unless corroborating exactly-agreeing fields bring the COMBINED
evidence (rule P x field u-probabilities, the engine's product
semantics) back under budget. See ``engine.match_fields``. Patient
matching (plain rule list, no threshold attribute) is byte-identical
and never enforced.

Hard scope cuts: name-only NEVER links practitioners (common surnames in
one facility), organizations, or locations (a health system's "Imaging
Center" exists in every city).
"""

from __future__ import annotations

from typing import Optional

from .rules import (
    EXACT,
    FUZZY,
    PHONE_AGREEMENT,
    MatchRule,
    p_collision,
)

__all__ = [
    "RuleSet",
    "PRACTITIONER_APPROVAL_THRESHOLD",
    "ORGANIZATION_APPROVAL_THRESHOLD",
    "LOCATION_APPROVAL_THRESHOLD",
    "PRACTITIONER_RULES",
    "ORGANIZATION_RULES",
    "LOCATION_RULES",
]

PRACTITIONER_APPROVAL_THRESHOLD = 1e-8
ORGANIZATION_APPROVAL_THRESHOLD = 1e-8
LOCATION_APPROVAL_THRESHOLD = 1e-6


class RuleSet(list):
    """A rule table carrying its rule-set approval threshold (CR-002).

    A plain ``list`` subclass so it flows through every existing
    ``rules=`` parameter unchanged; ``approval_threshold`` is read by
    :func:`fhir4ds.matching.engine.match_fields` (an explicit
    ``approval_threshold`` argument overrides it; ``None``/absent — e.g.
    the Patient Category-1 table — disables enforcement entirely).
    """

    approval_threshold: Optional[float] = None


def _ruleset(rules: list[MatchRule],
             approval_threshold: float) -> RuleSet:
    rule_set = RuleSet(rules)
    rule_set.approval_threshold = approval_threshold
    return rule_set

_E, _F = EXACT, FUZZY


def _rule(rule_id, fields, desc, p_fuzzy_fields=frozenset(),
          guards=(), enabled=True, p_override=None) -> MatchRule:
    return MatchRule(
        rule_id=rule_id,
        fields=tuple(fields),
        p_collision=(p_override if p_override is not None
                     else p_collision(tuple(fields))),
        p_collision_fuzzy=(p_override if p_override is not None
                           else p_collision(tuple(fields),
                                            fuzzy_fields=p_fuzzy_fields)),
        p_fuzzy_fields=p_fuzzy_fields,
        description=desc,
        guards=guards,
        enabled=enabled,
    )


# --- Practitioner -----------------------------------------------------------
# Fuzzy names reuse the patient machinery (nickname ∪ DL<=1 @ >=5 chars) —
# suffix-conflict negation transfers unchanged (practitioners carry
# suffixes). P5 (name-only) is a HARD SCOPE CUT, not a rule.
PRACTITIONER_RULES: RuleSet = _ruleset(sorted(
    [
        _rule(
            "P1",
            [("npi", _E)],
            "NPI (hard anchor; NPI-alone, issued-unique)",
        ),
        _rule(
            "P2",
            [("last", _F), ("first", _F), ("phone", _E)],
            "Last Name* + First Name* + Phone (workhorse when NPI absent)",
            p_fuzzy_fields=frozenset({"last", "first"}),
        ),
        _rule(
            "P3",
            [("last", _F), ("first", _F), ("street_line", _E),
             ("email", _E)],
            "Last Name* + First Name* + Street Line + Email (clinic twins)",
            p_fuzzy_fields=frozenset({"last", "first"}),
        ),
        _rule(
            "P4",
            [("last", _F), ("first", _F), ("street_line", _E)],
            "Last Name* + First Name* + Street Line (solo practice; "
            "phone-agreement guard)",
            p_fuzzy_fields=frozenset({"last", "first"}),
            guards=(PHONE_AGREEMENT,),
        ),
    ],
    key=lambda r: (r.p_collision, r.rule_id),
), PRACTITIONER_APPROVAL_THRESHOLD)

# --- Organization -----------------------------------------------------------
# O5 ships DISABLED (FDD §10 Q2 default): chain pharmacies share phone
# pools; enable only if measurement on real corpora shows recall loss.
ORGANIZATION_RULES: RuleSet = _ruleset(sorted(
    [
        _rule("O1", [("npi", _E)], "NPI (rare but decisive)"),
        # O2 retune (Joel decision 2026-11-20, FHIR4-18): CLIA links ALONE.
        # The generic table entry (FIELD_U_PROBS["clia"] = 1e-7) exceeds the
        # 1e-8 org budget, which made CR-002 demand an org_name corroborator
        # for a facility-unique identifier. CLIA numbers are CMS-issued and
        # unique per laboratory/facility (10-digit, category + state + serial),
        # so modeling the collision P at 1e-8 — at budget, like practitioner
        # NPI's 1e-9 sit under theirs — is defensible and is the authored
        # intent of the rule. Authored-P override, NOT an engine change.
        _rule("O2", [("clia", _E)], "CLIA (facility-unique; links alone)",
              p_override=1e-8),
        _rule(
            "O3",
            [("tax_id", _E), ("org_name", _F)],
            "TAX ID + Organization Name*",
            p_fuzzy_fields=frozenset({"org_name"}),
        ),
        _rule(
            "O4",
            [("org_name", _F), ("addr_key", _E)],
            "Organization Name* + Address Key",
            p_fuzzy_fields=frozenset({"org_name"}),
        ),
        _rule(
            "O5",
            [("phone", _E), ("org_name", _F)],
            "Phone + Organization Name* (DISABLED: shared pharmacy phone "
            "pools)",
            p_fuzzy_fields=frozenset({"org_name"}),
            enabled=False,
        ),
    ],
    key=lambda r: (r.p_collision, r.rule_id),
), ORGANIZATION_APPROVAL_THRESHOLD)

# --- Location ---------------------------------------------------------------
LOCATION_RULES: RuleSet = _ruleset(sorted(
    [
        _rule(
            "L1",
            [("addr_key", _E), ("loc_name", _F)],
            "Address Key + Location Name*",
            p_fuzzy_fields=frozenset({"loc_name"}),
        ),
        _rule(
            "L2",
            [("geo_key", _E), ("loc_name", _F)],
            "Geo Key + Location Name* (position-bearing campus buildings)",
            p_fuzzy_fields=frozenset({"loc_name"}),
        ),
    ],
    key=lambda r: (r.p_collision, r.rule_id),
), LOCATION_APPROVAL_THRESHOLD)
