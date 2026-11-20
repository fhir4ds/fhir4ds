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

Hard scope cuts: name-only NEVER links practitioners (common surnames in
one facility), organizations, or locations (a health system's "Imaging
Center" exists in every city).

NOTE (documented tension, FDD §7): O4 (org_name + addr_key ≈ 2e-6) and
L1/L2 (≈1e-6) nominally exceed the org approval budget — they are kept
per the FDD's own rule tables; the engine applies no threshold cutoff
(the tables list only authored rules), so this is a documentation
caveat, not a behavior difference.
"""

from __future__ import annotations

from .rules import (
    EXACT,
    FUZZY,
    PHONE_AGREEMENT,
    MatchRule,
    p_collision,
)

__all__ = [
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

_E, _F = EXACT, FUZZY


def _rule(rule_id, fields, desc, p_fuzzy_fields=frozenset(),
          guards=(), enabled=True) -> MatchRule:
    return MatchRule(
        rule_id=rule_id,
        fields=tuple(fields),
        p_collision=p_collision(tuple(fields)),
        p_collision_fuzzy=p_collision(tuple(fields),
                                      fuzzy_fields=p_fuzzy_fields),
        p_fuzzy_fields=p_fuzzy_fields,
        description=desc,
        guards=guards,
        enabled=enabled,
    )


# --- Practitioner -----------------------------------------------------------
# Fuzzy names reuse the patient machinery (nickname ∪ DL<=1 @ >=5 chars) —
# suffix-conflict negation transfers unchanged (practitioners carry
# suffixes). P5 (name-only) is a HARD SCOPE CUT, not a rule.
PRACTITIONER_RULES: list[MatchRule] = sorted(
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
)

# --- Organization -----------------------------------------------------------
# O5 ships DISABLED (FDD §10 Q2 default): chain pharmacies share phone
# pools; enable only if measurement on real corpora shows recall loss.
ORGANIZATION_RULES: list[MatchRule] = sorted(
    [
        _rule("O1", [("npi", _E)], "NPI (rare but decisive)"),
        _rule("O2", [("clia", _E)], "CLIA"),
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
)

# --- Location ---------------------------------------------------------------
LOCATION_RULES: list[MatchRule] = sorted(
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
)
