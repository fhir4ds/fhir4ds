"""Category-1 match rule table (port of the CMS deterministic rule set).

Ported from the rule study of icanbwell/cms-hte-patient-matching
(CMS Patient Matching Proposal v3.4.0, Apache-2.0). Rule ids follow the
upstream numbering; field modes are `exact` or `fuzzy` (fuzzy = Damerau-
Levenshtein <= 1 on names, DOB +/- 1 day — slice 2). Slice 1 fires exact
rules only; a rule with any fuzzy field is skipped and audited as
not-implemented.

P(collision) values: anchored numbers come from the upstream study
(rules 01, 04/05, 22, 30). Unrecorded combinations use a conservative
1.0e-12 (or a family-consistent value) and are marked `p_estimated=True`.
Rules are ordered P(collision) ascending, ties by rule id — deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field

__all__ = ["MatchRule", "CATEGORY1_RULES", "EXACT", "FUZZY"]

EXACT = "exact"
FUZZY = "fuzzy"


@dataclass(frozen=True)
class MatchRule:
    rule_id: str
    fields: tuple[tuple[str, str], ...]  # (field_name, exact|fuzzy)
    p_collision: float
    p_estimated: bool = False
    description: str = ""

    def exact_fields(self) -> tuple[str, ...]:
        return tuple(name for name, mode in self.fields if mode == EXACT)

    def fuzzy_fields(self) -> tuple[str, ...]:
        return tuple(name for name, mode in self.fields if mode == FUZZY)


def _r(rule_id: str, fields: list[tuple[str, str]], p: float, desc: str, est: bool = True) -> MatchRule:
    return MatchRule(rule_id=rule_id, fields=tuple(fields), p_collision=p, p_estimated=est, description=desc)


# --- Category-1 exact/fuzzy rule families (29 rules) -----------------------
_RULE_DEFS: list[MatchRule] = [
    # Anchored upstream numbers (est=False)
    _r("01", [("first", FUZZY), ("last", FUZZY), ("dob", FUZZY), ("street_line", EXACT)], 3.0e-13,
       "First* + Last* + DOB* + Street*", est=False),
    _r("04", [("first", EXACT), ("last", EXACT), ("dob", EXACT), ("ssn4", EXACT)], 1.0e-12,
       "First + Last + DOB + SSN4", est=False),
    _r("05", [("first", FUZZY), ("last", FUZZY), ("dob", EXACT), ("ssn4", EXACT)], 1.0e-12,
       "First* + Last* + DOB + SSN4", est=False),
    _r("22", [("namespace_id", EXACT)], 1.0e-15,
       "Namespace-ID alone", est=False),
    _r("30", [("last", FUZZY), ("dob", FUZZY), ("phone", EXACT)], 5.0e-13,
       "Last* + DOB* + Phone", est=False),
    # Ported families (P estimated where the study did not record a value)
    _r("02", [("first", EXACT), ("last", EXACT), ("dob", EXACT), ("street_line", EXACT)], 1.0e-13,
       "First + Last + DOB + Street"),
    _r("03", [("first", FUZZY), ("last", FUZZY), ("dob", FUZZY), ("phone", EXACT)], 8.0e-13,
       "First* + Last* + DOB* + Phone"),
    _r("06", [("first", EXACT), ("last", EXACT), ("dob", EXACT), ("itin4", EXACT)], 1.0e-12,
       "First + Last + DOB + ITIN4"),
    _r("07", [("first", FUZZY), ("last", FUZZY), ("dob", EXACT), ("itin4", EXACT)], 1.0e-12,
       "First* + Last* + DOB + ITIN4"),
    _r("08", [("first", EXACT), ("last", EXACT), ("ssn4", EXACT), ("phone", EXACT)], 1.0e-12,
       "First + Last + SSN4 + Phone"),
    _r("09", [("first", EXACT), ("last", EXACT), ("dob", EXACT), ("mbi", EXACT)], 1.0e-12,
       "First + Last + DOB + MBI"),
    _r("10", [("first", FUZZY), ("last", FUZZY), ("dob", EXACT), ("mbi", EXACT)], 1.0e-12,
       "First* + Last* + DOB + MBI"),
    _r("11", [("first", EXACT), ("last", EXACT), ("dob", EXACT), ("member_id", EXACT)], 1.0e-12,
       "First + Last + DOB + Member ID"),
    _r("12", [("first", EXACT), ("last", EXACT), ("dob", EXACT), ("subscriber_id", EXACT)], 1.0e-12,
       "First + Last + DOB + Subscriber ID"),
    _r("13", [("first", EXACT), ("last", EXACT), ("dob", EXACT), ("legal_id", EXACT)], 1.0e-12,
       "First + Last + DOB + Legal ID"),
    _r("14", [("first", EXACT), ("dob", EXACT), ("phone", EXACT), ("street_line", EXACT)], 1.0e-12,
       "First + DOB + Phone + Street"),
    _r("15", [("last", EXACT), ("dob", EXACT), ("phone", EXACT), ("street_line", EXACT)], 1.0e-12,
       "Last + DOB + Phone + Street"),
    _r("16", [("first", EXACT), ("last", EXACT), ("phone", EXACT), ("email", EXACT)], 1.0e-12,
       "First + Last + Phone + Email"),
    _r("17", [("first", EXACT), ("last", EXACT), ("dob", EXACT), ("email", EXACT)], 1.0e-12,
       "First + Last + DOB + Email"),
    _r("18", [("first", FUZZY), ("last", FUZZY), ("dob", FUZZY), ("email", EXACT)], 8.0e-13,
       "First* + Last* + DOB* + Email"),
    _r("19", [("first", EXACT), ("last", EXACT), ("email", EXACT)], 1.0e-11,
       "First + Last + Email"),
    _r("20", [("first", EXACT), ("dob", EXACT), ("ssn4", EXACT)], 1.0e-11,
       "First + DOB + SSN4"),
    _r("21", [("last", EXACT), ("dob", EXACT), ("ssn4", EXACT)], 1.0e-11,
       "Last + DOB + SSN4"),
    _r("23", [("namespace_id", EXACT), ("dob", EXACT)], 1.0e-15,
       "Namespace-ID + DOB"),
    _r("24", [("member_id", EXACT)], 1.0e-14,
       "Member ID alone"),
    _r("25", [("subscriber_id", EXACT)], 1.0e-14,
       "Subscriber ID alone"),
    _r("26", [("mbi", EXACT)], 1.0e-14,
       "MBI alone"),
    _r("27", [("legal_id", EXACT), ("last", EXACT)], 5.0e-12,
       "Legal ID + Last"),
    _r("28", [("first", EXACT), ("last", EXACT), ("dob", EXACT)], 5.0e-11,
       "First + Last + DOB"),
]

CATEGORY1_RULES: list[MatchRule] = sorted(_RULE_DEFS, key=lambda r: (r.p_collision, r.rule_id))
