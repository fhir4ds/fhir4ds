"""Versioned multi-vocabulary concept display index + hybrid retrieval
(AMUX-145 design redirect, 2026-11-20).

The tier-2 cascade coalesces every in-scope resource onto ONE match key:

1. **Canonical tier** — literal ``(system, code)`` set intersection
   (fast path, unchanged). Intersecting code sets never fall through.
2. **Hybrid-search tier** — for resources whose texts might bridge
   vocabularies, resolve the resource's display text against this index
   using hybrid retrieval = **BM25 + character-trigram fuzzy** (both
   deterministic, no model artifact). A confident resolution (top-1 at
   or above ``HYBRID_MIN_SCORE`` AND a clear margin over the runner-up)
   assigns the resolved canonical concept to the resource's key, so a
   LOINC/SNOMED twin pair merges through ordinary partitioning.
   Unconfident resolution falls through.
3. **Text tier (LAST)** — unresolved resources key on the conservative
   normalized text (:mod:`fhir4ds.dedup.lexical`). Resolved concepts
   OUTRANK display equality: equal text with different confident
   canonical keys never merges.

Dense-vector retrieval stays OUT of v1; the ``DedupCodeProposer``
Protocol (default-off) is the upgrade hook.

Index provenance: the DEFAULT index builds deterministically from the
expanded ValueSet fixtures in ``tests/data/valuesets/*.json``
(``expansion.contains`` entries carrying ``system``/``code``/``display``),
restricted to the four dedup-reference vocabularies LOINC, SNOMED,
RxNorm and CVX (CVX does not occur in the current fixture set; the
filter admits it the day it does). The build is versioned
(``INDEX_FORMAT_VERSION`` + content checksum) and every hybrid merge
records index version, score and margin in the audit trail.
"""

from __future__ import annotations

import hashlib
import json
import math
import zlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

from .lexical import normalize_lexical_text

__all__ = [
    "HYBRID_MIN_SCORE",
    "HYBRID_MIN_MARGIN",
    "INDEX_FORMAT_VERSION",
    "INDEX_VOCABULARY_SYSTEMS",
    "ConceptIndex",
    "Resolution",
    "default_concept_index",
]

#: Index format version — bump on any change to build/scoring semantics.
INDEX_FORMAT_VERSION = "1"

#: The dedup-reference vocabularies admitted into the default index.
INDEX_VOCABULARY_SYSTEMS = frozenset({
    "http://loinc.org",
    "http://snomed.info/sct",
    "http://www.nlm.nih.gov/research/umls/rxnorm",
    "http://hl7.org/fhir/sid/cvx",
})

#: Confidence rule: top-1 combined score must reach this AND lead the
#: runner-up by at least ``HYBRID_MIN_MARGIN``. Calibrated (2026-11-20)
#: against the shipped corpora: the observed FALSE resolutions —
#: "Systolic/Diastolic blood pressure" both fuzzy-matching SNOMED
#: "Low blood pressure (disorder)" (score ~0.78, margin ~0.12), and
#: "Application of device" promoting to the more specific compression-
#: device procedure (0.81/0.099) — must fall through, while exact
#: display twins (1.0, margin ~0.2+) resolve. Conservative by design;
#: tuning is a reviewed data change.
HYBRID_MIN_SCORE = 0.85
HYBRID_MIN_MARGIN = 0.15

_BM25_K1 = 1.5
_BM25_B = 0.75
_BM25_WEIGHT = 0.5
_NGRAM_WEIGHT = 0.5

_REPO = Path(__file__).resolve().parents[2]
DEFAULT_INDEX_SOURCE = _REPO / "tests/data/valuesets"


@dataclass(frozen=True)
class Resolution:
    """One confident display-text resolution."""

    system: str
    code: str
    score: float
    margin: float
    index_version: str

    @property
    def concept(self) -> tuple[str, str]:
        return (self.system, self.code)


def _trigrams(text: str) -> frozenset[int]:
    if len(text) < 3:
        return frozenset({zlib.crc32(text.encode("utf-8"))}) if text \
            else frozenset()
    return frozenset(
        zlib.crc32(text[i:i + 3].encode("utf-8"))
        for i in range(len(text) - 2))


class ConceptIndex:
    """Deterministic, version-pinned concept display index with
    BM25 + character-trigram hybrid retrieval."""

    def __init__(self, entries: Iterable[dict]):
        # Dedup by (system, code) — first (sorted) display wins.
        seen: dict[tuple[str, str], str] = {}
        for entry in sorted(
                ({k: e[k] for k in ("system", "code", "display")}
                 for e in entries
                 if isinstance(e, dict)
                 and isinstance(e.get("system"), str) and e["system"]
                 and isinstance(e.get("code"), str) and e["code"]
                 and isinstance(e.get("display"), str) and e["display"]),
                key=lambda e: (e["system"], e["code"], e["display"])):
            key = (entry["system"], entry["code"])
            if key not in seen:
                seen[key] = entry["display"]
        self.entries: list[dict] = [
            {"system": s, "code": c, "display": d}
            for (s, c), d in sorted(seen.items())]
        self.index_version = self._compute_version()
        self._build()

    # -- build -----------------------------------------------------------

    def _compute_version(self) -> str:
        payload = json.dumps(
            {"format": INDEX_FORMAT_VERSION, "entries": self.entries},
            sort_keys=True).encode("utf-8")
        checksum = hashlib.sha256(payload).hexdigest()
        self.checksum = checksum
        return f"format{INDEX_FORMAT_VERSION}+sha256:{checksum[:12]}"

    def _build(self) -> None:
        self._displays = [normalize_lexical_text(e["display"])
                          for e in self.entries]
        self._tokens = [tuple(d.split()) for d in self._displays]
        self._trigrams = [_trigrams(d) for d in self._displays]
        self._doc_len = [len(t) for t in self._tokens]
        avgdl = (sum(self._doc_len) / len(self._doc_len)
                 if self._doc_len else 0.0)
        self._avgdl = avgdl or 1.0
        postings: dict[str, dict[int, int]] = {}
        for doc_id, tokens in enumerate(self._tokens):
            counts: dict[str, int] = {}
            for token in tokens:
                counts[token] = counts.get(token, 0) + 1
            for token, tf in counts.items():
                postings.setdefault(token, {})[doc_id] = tf
        n_docs = len(self.entries) or 1
        self._idf = {
            token: math.log(1.0 + (n_docs - len(post) + 0.5)
                            / (len(post) + 0.5))
            for token, post in postings.items()}
        self._postings = postings

    # -- retrieval -------------------------------------------------------

    def _candidates(self, query_tokens: tuple[str, ...]) -> set[int]:
        out: set[int] = set()
        for token in query_tokens:
            out.update(self._postings.get(token, {}))
        return out

    def _bm25(self, doc_id: int, query_tokens: tuple[str, ...]) -> float:
        score = 0.0
        dl = self._doc_len[doc_id]
        for token in dict.fromkeys(query_tokens):
            tf = self._postings.get(token, {}).get(doc_id)
            if tf is None:
                continue
            idf = self._idf.get(token, 0.0)
            score += idf * tf * (_BM25_K1 + 1.0) / (
                tf + _BM25_K1 * (1.0 - _BM25_B
                                 + _BM25_B * dl / self._avgdl))
        return score

    def resolve(self, text: object) -> Optional[Resolution]:
        """Resolve one display text; None when unconfident (fall through
        to the text tier). Deterministic: ties break on
        ``(-score, system, code)`` and an exactly-tied top-2 has zero
        margin, i.e. it falls through."""
        query = normalize_lexical_text(text)
        if not query or not self.entries:
            return None
        query_tokens = tuple(query.split())
        query_grams = _trigrams(query)
        scored: list[tuple[float, int]] = []
        for doc_id in sorted(self._candidates(query_tokens)):
            bm25 = self._bm25(doc_id, query_tokens)
            doc_grams = self._trigrams[doc_id]
            if query_grams and doc_grams:
                dice = (2.0 * len(query_grams & doc_grams)
                        / (len(query_grams) + len(doc_grams)))
            else:
                dice = 0.0
            scored.append((bm25, dice, doc_id))
        if not scored:
            return None
        bm25_max = max(s[0] for s in scored) or 1.0
        combined: list[tuple[float, tuple[str, str], int]] = []
        for bm25, dice, doc_id in scored:
            norm_bm25 = bm25 / bm25_max if bm25_max else 0.0
            value = _BM25_WEIGHT * norm_bm25 + _NGRAM_WEIGHT * dice
            if query == self._displays[doc_id]:
                value = 1.0  # exact normalized display match
            entry = self.entries[doc_id]
            combined.append(
                (value, (entry["system"], entry["code"]), doc_id))
        combined.sort(key=lambda item: (-item[0], item[1]))
        best_score, best_concept, _ = combined[0]
        second = combined[1][0] if len(combined) > 1 else 0.0
        margin = best_score - second
        if best_score >= HYBRID_MIN_SCORE and margin >= HYBRID_MIN_MARGIN:
            return Resolution(
                system=best_concept[0], code=best_concept[1],
                score=round(best_score, 6), margin=round(margin, 6),
                index_version=self.index_version)
        return None

    def __len__(self) -> int:
        return len(self.entries)


@lru_cache(maxsize=4)
def _build_default_index(source_str: str) -> ConceptIndex:
    source = Path(source_str)
    entries: list[dict] = []
    if source.is_dir():
        for path in sorted(source.glob("*.json")):
            try:
                doc = json.loads(path.read_text(encoding="utf-8-sig"))
            except (ValueError, OSError):
                continue
            if not isinstance(doc, dict):
                continue
            for contain in doc.get("expansion", {}).get("contains", []):
                if not isinstance(contain, dict):
                    continue
                if contain.get("system") in INDEX_VOCABULARY_SYSTEMS:
                    entries.append({"system": contain.get("system"),
                                    "code": contain.get("code"),
                                    "display": contain.get("display")})
    return ConceptIndex(entries)


def default_concept_index() -> ConceptIndex:
    """The default index over the in-repo expanded ValueSet fixtures
    (``tests/data/valuesets``), filtered to the dedup-reference
    vocabularies. Empty (but valid) when the fixture directory is
    absent, so environments without the corpus still run the cascade."""
    return _build_default_index(str(DEFAULT_INDEX_SOURCE))
