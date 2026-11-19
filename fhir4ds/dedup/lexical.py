"""Tier-2 lexical code normalization for the dedup fallback cascade
(AMUX-145).

When a resource's code/text cannot be resolved through canonical
``(system, code)`` intersection, tier 2 compares a CONSERVATIVE normalized
form of the display texts (``code.text`` plus every ``coding.display`` of
the primary code field). Two resources are lexically compatible when their
text SETS share at least one normalized string — mirroring the code-set
any-intersection doctrine.

Normalization pipeline (FDD §3, all pure/deterministic, in order):

1. ``str.casefold()`` (Unicode-aware, not lower()).
2. Unicode NFKC normalization (compatibility forms: ﬁ → fi, ² → 2).
3. Punctuation → single space (every codepoint not ``\\w`` or whitespace).
4. UCUM unit alias normalization (token-level, vendored table below).
5. Whitespace collapse + strip.
6. Empty results are discarded from the set.

Explicitly OUT (each pinned by an acceptance test): word-order
normalization, stemming/lemmatization, synonym expansion, stop-word
removal, numeric-token tolerance.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

from .codes import _code_field

__all__ = [
    "UCUM_ALIAS_TABLE_VERSION",
    "UCUM_DISPLAY_ALIASES",
    "normalize_lexical_text",
    "raw_code_texts",
    "tier2_text_set",
]

#: Version of the vendored UCUM display-alias table. Additions are a
#: REVIEWED DATA CHANGE — bump this version when the table changes.
UCUM_ALIAS_TABLE_VERSION = "1.0.0-amux145"

#: Token-level alias map applied AFTER casefold/NFKC/punctuation→space,
#: so both keys and values are lowercase, punctuation-free token runs.
#: Sourced from LOINC display conventions and common clinical feed
#: spellings. Keys are single tokens; values may expand to multiple
#: canonical tokens (whitespace-separated).
UCUM_DISPLAY_ALIASES: dict[str, str] = {
    # heart rate / frequency
    "bpm": "min",           # 'beats/min' vs '/min'
    "mmhg": "mm hg",        # 'mmHg' (bracket/squash spellings)
    "kpa": "kpa",
    "kilopascals": "kpa",
    # mass
    "grams": "g",
    "gram": "g",
    "milligrams": "mg",
    "micrograms": "ug",
    "mcg": "ug",            # medical abbreviation for microgram
    "kilograms": "kg",
    "pounds": "lb",
    # volume
    "milliliters": "ml",
    "deciliters": "dl",
    "liters": "l",
    # length
    "millimeters": "mm",
    "centimeters": "cm",
    "meters": "m",
    "kilometers": "km",
    "inches": "in",
    # substance
    "millimoles": "mmol",
    "moles": "mol",
    # temperature
    "celsius": "cel",
    "fahrenheit": "degf",
    # misc clinical
    "units": "u",
}

_PUNCT_RE = re.compile(r"[^\w\s]")


def normalize_lexical_text(text: object) -> str:
    """Conservative normalized form of one display text (FDD §3).

    Non-string input yields "" (discarded from the text set).
    """
    if not isinstance(text, str):
        return ""
    folded = text.casefold()
    compatible = unicodedata.normalize("NFKC", folded)
    spaced = _PUNCT_RE.sub(" ", compatible)
    tokens = [_alias_token(tok) for tok in spaced.split()]
    return " ".join(tok for tok in tokens if tok)


def _alias_token(token: str) -> str:
    aliased = UCUM_DISPLAY_ALIASES.get(token)
    if aliased is None:
        return token
    # Alias values are pre-normalized token runs; the first token stands
    # in for the run positionally (multi-token values re-join below and
    # both spellings collapse because the alias is applied uniformly).
    return aliased


def _code_texts(resource: dict) -> list[str]:
    """Authored-order raw texts of the primary code field:
    ``code.text`` first (the human assertion), then every
    ``coding.display`` (the code-system renderings)."""
    code_field = _code_field(resource)
    if code_field is None:
        return []
    texts: list[str] = []
    text = code_field.get("text")
    if isinstance(text, str) and text:
        texts.append(text)
    codings = code_field.get("coding")
    if isinstance(codings, list):
        for coding in codings:
            if not isinstance(coding, dict):
                continue
            display = coding.get("display")
            if isinstance(display, str) and display:
                texts.append(display)
    return texts


def raw_code_texts(resource: dict) -> list[str]:
    """Authored-order raw display texts (public for audit evidence)."""
    if not isinstance(resource, dict):
        return []
    return _code_texts(resource)


def tier2_text_set(resource: dict) -> frozenset[str]:
    """SET of normalized display texts; empty set = not tier-2-eligible."""
    if not isinstance(resource, dict):
        return frozenset()
    normalized = {normalize_lexical_text(t) for t in _code_texts(resource)}
    return frozenset(t for t in normalized if t)


def tier2_provenance(resource: dict,
                     code_keys: Optional[frozenset] = None) -> str:
    """Record-level code provenance (FDD §5.1): ``canonical`` when the
    canonical code key is non-empty; ``lexical`` when the key is empty but
    a tier-2 text set exists; ``none`` otherwise."""
    if code_keys is None:
        from .codes import normalize_codes
        code_keys = normalize_codes(resource)
    if code_keys:
        return "canonical"
    if tier2_text_set(resource):
        return "lexical"
    return "none"
