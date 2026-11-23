"""FHIR4-20 name-embedding inference runtime (pure NumPy, deterministic).

Loads the pinned char-level triplet-loss name-embedding artifact
(``artifacts/name_embed_v1.npz``, trained offline by
``scripts/train_name_embedding.py`` — torch is a DEV-ONLY dependency of
that script, never imported here) and provides:

- :func:`embed` — name -> 16-dim unit ``float64`` vector;
- :func:`distance` — cosine distance between two names;
- :func:`name_distance_band` — ``tight`` / ``mid`` / ``loose`` band (or
  ``None`` when the pair is not close enough), with ±``BAND_HYSTERESIS``
  edge hysteresis so cross-platform float drift near a band edge resolves
  deterministically to the TIGHTER band;
- :func:`band_u_values` / :func:`band_edges` — the manifest tables the
  matching rule module pins its constants against.

Degradation contract (FHIR4-20 FDD §3.4): a missing or corrupt artifact
(hash mismatch) makes :func:`artifact_available` false,
:func:`band_u_values` empty, and — on the matching side —
``rules.embedding_rules()`` an empty list, after exactly ONE WARNING per
process. No torch, no network, no eager I/O at import beyond a lazy NPZ
open.

Determinism: fixed float32 weights from the hash-checked artifact, a pure
float64 NumPy forward pass, per-process LRU caches on normalized names.
Same inputs -> bit-identical outputs on a platform.
"""

from __future__ import annotations

import hashlib
import logging
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np

__all__ = [
    "MODEL_VERSION",
    "ARTIFACT_FILENAME",
    "BAND_HYSTERESIS",
    "EMBED_DIM",
    "MAX_NAME_LEN",
    "artifact_available",
    "artifact_path",
    "band_edges",
    "band_u_values",
    "distance",
    "embed",
    "embedding_model_id",
    "manifest",
    "name_distance_band",
    "reload",
    "_band_for_distance",
]

logger = logging.getLogger("fhir4ds.matching.name_embedding")

MODEL_VERSION = "name-embed-v1"
ARTIFACT_FILENAME = "name_embed_v1.npz"

#: Band-edge hysteresis (FDD §3.4): a distance within this margin ABOVE a
#: band's upper edge is assigned to the tighter band, so ±1e-3-class
#: cross-platform float drift cannot flip a band assignment.
BAND_HYSTERESIS = 1e-3

EMBED_DIM = 16
MAX_NAME_LEN = 24
_MIN_LEN = 5  # shortest sequence producing one conv window of width 5

_DEFAULT_ARTIFACT = Path(__file__).resolve().parent / "artifacts" / ARTIFACT_FILENAME

# Module state (reload-able for tests / alternate deployments).
_path: Optional[Path] = None
_manifest: Optional[dict] = None
_weights: Optional[dict] = None
_vocab: Optional[dict] = None
_model_id: Optional[str] = None
_degradation_warned = False


def artifact_path() -> Path:
    return _path if _path is not None else _DEFAULT_ARTIFACT


def reload(path: Optional[Path] = None) -> None:
    """Point the loader at ``path`` (None -> the shipped artifact) and
    drop all caches. Intended for tests and deployments that carry the
    artifact elsewhere."""
    global _path, _manifest, _weights, _vocab, _model_id, _degradation_warned
    _path = Path(path) if path is not None else None
    _manifest = _weights = _vocab = None
    _model_id = None
    _degradation_warned = False
    _embed_cached.cache_clear()
    _band_pair.cache_clear()


def _warn_degraded(reason: str) -> None:
    global _degradation_warned
    if not _degradation_warned:
        _degradation_warned = True
        logger.warning(
            "name-embedding artifact %s unavailable (%s); "
            "embedding match rules are disabled for this process",
            ARTIFACT_FILENAME,
            reason,
        )


def _weights_digest(payload: dict) -> str:
    h = hashlib.sha256()
    for key in (
        "embed_weight", "conv3_weight", "conv3_bias",
        "conv5_weight", "conv5_bias", "fc1_weight", "fc1_bias",
        "fc2_weight", "fc2_bias",
    ):
        h.update(key.encode("utf-8"))
        h.update(np.ascontiguousarray(payload[key]).tobytes())
    return h.hexdigest()


def _load() -> bool:
    """Load + verify the artifact once. Returns availability."""
    global _manifest, _weights, _vocab, _model_id
    if _manifest is not None:
        return _weights is not None
    path = artifact_path()
    try:
        with np.load(path, allow_pickle=False) as npz:
            payload = {k: npz[k] for k in npz.files}
    except FileNotFoundError:
        _manifest = {}
        _warn_degraded("file not found")
        return False
    except Exception as exc:  # corrupt zip / npz
        _manifest = {}
        _warn_degraded(f"unreadable artifact: {type(exc).__name__}")
        return False
    import json

    try:
        raw = payload["metadata_json"]
        meta = json.loads(raw.item() if hasattr(raw, "item") else raw)
    except Exception as exc:
        _manifest = {}
        _warn_degraded(f"bad metadata: {type(exc).__name__}")
        return False
    if meta.get("version") != MODEL_VERSION:
        _manifest = {}
        _warn_degraded(f"unsupported version {meta.get('version')!r}")
        return False
    if str(payload["weights_sha256"]) != _weights_digest(payload):
        _manifest = {}
        _warn_degraded("weights hash mismatch")
        return False
    vocab = [str(c) for c in payload["vocab"].tolist()]
    if payload["fc2_weight"].shape[0] != EMBED_DIM:
        _manifest = {}
        _warn_degraded("unexpected embedding dimension")
        return False
    _manifest = meta
    _weights = {k: payload[k] for k in payload if k != "metadata_json"}
    _vocab = {ch: i for i, ch in enumerate(vocab)}
    _model_id = f"{MODEL_VERSION}@{hashlib.sha256(path.read_bytes()).hexdigest()[:8]}"
    return True


def artifact_available() -> bool:
    return _load()


def embedding_model_id() -> Optional[str]:
    """``name-embed-v1@<sha8-of-artifact>`` or None when degraded."""
    return _model_id if _load() else None


def manifest() -> dict:
    """The artifact manifest (version, training-data hash, band tables).
    Empty dict when degraded."""
    return dict(_manifest) if _load() else {}


def band_edges() -> dict[str, float]:
    """Band upper-edge table (cosine distance): tight <= mid <= loose."""
    if not _load():
        return {}
    return dict(_manifest.get("band_edges", {}))


def band_u_values() -> tuple[tuple[str, float], ...]:
    """Per-band u-values (P(collision) placeholders until P4 calibration),
    ordered tight -> loose."""
    if not _load():
        return ()
    u = _manifest.get("band_u_values", {})
    return tuple((b, float(u[b])) for b in ("tight", "mid", "loose") if b in u)


def _normalize(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name)
    folded = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return "".join(ch for ch in folded.lower() if "a" <= ch <= "z" or ch == " ")[:MAX_NAME_LEN]


@lru_cache(maxsize=8192)
def _embed_cached(name: str) -> tuple[float, ...]:
    vec = _forward(_normalize(name))
    return tuple(float(x) for x in vec)


def embed(name: str) -> np.ndarray:
    """Embed one name as a deterministic 16-dim unit float64 vector."""
    if not _load():
        raise RuntimeError(
            "name-embedding artifact unavailable; call artifact_available() first"
        )
    return np.asarray(_embed_cached(name), dtype=np.float64)


def _forward(s: str) -> np.ndarray:
    w = _weights
    vocab = _vocab
    pad = vocab.get("<pad>", 0)
    ids = [vocab.get(ch, pad) for ch in s]
    if len(ids) < _MIN_LEN:
        ids = ids + [pad] * (_MIN_LEN - len(ids))
    emb_w = w["embed_weight"].astype(np.float64)  # (V, E)
    seq = emb_w[np.asarray(ids, dtype=np.int64)]  # (L, E)
    out = []
    for key in ("conv3", "conv5"):
        weight = w[f"{key}_weight"].astype(np.float64)  # (C, E, K)
        bias = w[f"{key}_bias"].astype(np.float64)  # (C,)
        k = weight.shape[2]
        windows = np.stack(
            [seq[i:i + k] for i in range(len(seq) - k + 1)]
        )  # (L-K+1, K, E)
        feats = windows.reshape(windows.shape[0], -1) @ weight.reshape(weight.shape[0], -1).T + bias
        out.append(np.maximum(feats, 0.0).max(axis=0))
    h = np.concatenate(out)
    h = np.maximum(h @ w["fc1_weight"].astype(np.float64).T
                   + w["fc1_bias"].astype(np.float64), 0.0)
    z = h @ w["fc2_weight"].astype(np.float64).T + w["fc2_bias"].astype(np.float64)
    norm = np.linalg.norm(z)
    return z / norm if norm > 0 else z


def distance(a: str, b: str) -> float:
    """Cosine distance between two names (unit vectors -> 1 - dot)."""
    va = embed(a)
    vb = embed(b)
    dot = float(va @ vb)
    if dot > 1.0:
        dot = 1.0
    elif dot < -1.0:
        dot = -1.0
    d = 1.0 - dot
    return 0.0 if abs(d) < 1e-12 else d


def _band_for_distance(d: float) -> Optional[str]:
    """Band for a cosine distance, tight side first, with hysteresis:
    ``d <= edge + BAND_HYSTERESIS`` counts as inside the tighter band."""
    edges = band_edges()
    if not edges:
        return None
    for band in ("tight", "mid", "loose"):
        if d <= edges[band] + BAND_HYSTERESIS:
            return band
    return None


@lru_cache(maxsize=8192)
def _band_pair(a: str, b: str) -> Optional[str]:
    return _band_for_distance(distance(a, b))


def name_distance_band(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """Embedding band for a name pair, or None when the artifact is
    degraded, the pair is not close enough for any band, or either name
    carries no Latin-letter signal (non-Latin scripts normalize to the
    empty string — a vacuous comparison that must never yield a band, lest
    two distinct non-Latin given names embed identically and land in the
    ``tight`` band; QA-D14S-002)."""
    if not a or not b:
        return None
    if not _load():
        return None
    if not _normalize(a).strip() or not _normalize(b).strip():
        return None
    return _band_pair(a, b)
