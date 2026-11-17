"""Fuzzy comparators (slice 2, pure Python — no third-party dependencies).

- Damerau-Levenshtein distance <= 1 (`damerau_le1`), restricted (optimal
  string alignment) variant: a substitution or an adjacent transposition,
  plus single insertion/deletion.
- Name fuzzy matching (`name_fuzzy_match`): exact equality, nickname-set
  equivalence (normalizers.nickname_set), or DL <= 1 gated to strings of at
  least `FUZZY_NAME_MIN_LEN` characters per CMS E.3.
- DOB fuzzy matching (`dob_fuzzy_matches`): exact lookup over {d-1, d, d+1}
  via datetime.date arithmetic.
"""

from __future__ import annotations

import datetime as _dt
from typing import Optional

from .normalizers import nickname_set

__all__ = [
    "damerau_le1",
    "name_fuzzy_match",
    "dob_fuzzy_matches",
    "FUZZY_NAME_MIN_LEN",
]

# CMS E.3: edit-distance fuzzy matching only applies to strings >= 5 chars.
FUZZY_NAME_MIN_LEN = 5


def damerau_le1(a: str, b: str) -> bool:
    """True when restricted Damerau-Levenshtein distance(a, b) <= 1.

    Covers equality, one substitution, one adjacent transposition, and one
    insertion/deletion. Pure checks — no full DP table needed at bound 1.
    """
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == 0 or lb == 0:
        return True  # the non-empty side is exactly one insertion away
    if la == lb:
        # equal length: one substitution OR one adjacent transposition
        diffs = [i for i in range(la) if a[i] != b[i]]
        if len(diffs) == 1:
            return True
        if len(diffs) == 2:
            i, j = diffs
            return j == i + 1 and a[i] == b[j] and a[j] == b[i]
        return False
    # lengths differ by exactly 1: single insertion/deletion — one gap walk
    if la > lb:
        a, b = b, a  # b is now the longer string
    i = j = 0
    skipped = False
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            i += 1
            j += 1
        else:
            if skipped:
                return False
            skipped = True
            j += 1
    return True  # any remaining tail of b is at most the single skipped char


def name_fuzzy_match(a: Optional[str], b: Optional[str]) -> bool:
    """Fuzzy name equivalence: exact, nickname-set, or DL<=1 (>= 5 chars).

    Nickname equivalence is exact membership in the same nickname group
    (``b in nickname_set(a)``) with no length gate — "bob"/"robert" match.
    The edit-distance check requires BOTH strings >= FUZZY_NAME_MIN_LEN per
    CMS E.3, so short-name typos ("amy"/"ame") do not fuzzy-match.
    """
    if not a or not b:
        return False
    if a == b:
        return True
    if b in nickname_set(a):
        return True
    if len(a) >= FUZZY_NAME_MIN_LEN and len(b) >= FUZZY_NAME_MIN_LEN:
        return damerau_le1(a, b)
    return False


def dob_fuzzy_matches(a: Optional[str], b: Optional[str]) -> bool:
    """True when two YYYY-MM-DD strings lie within 1 calendar day."""
    if not a or not b:
        return False
    try:
        da = _dt.date.fromisoformat(a)
        db = _dt.date.fromisoformat(b)
    except ValueError:
        return False
    return abs((da - db).days) <= 1
