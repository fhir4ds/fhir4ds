#!/usr/bin/env python3
"""FHIR4-20 offline trainer for the name-embedding match model (P1).

DEV-ONLY: ``torch`` is imported lazily inside :func:`train_model` and is
NEVER a runtime dependency of ``fhir4ds`` (inference is pure NumPy in
``fhir4ds/matching/name_embedding.py``).

Training-data construction follows the approved FDD
(``fhir4ds-private/docs/architecture/plans/FEATURE_NAME_EMBEDDING.md``
§3.1) exactly:

- positives (equivalent-name pairs) from (i) intra-group pairs of every
  engine nickname group (<= 20 pairs/group), (ii) intra-group pairs of
  every transliteration group, (iii) DL-1 and DL-2 corruptions of every
  corpus name, (iv) prefix truncations >= 4 chars and single initials of
  nickname-table formal names, (v) stacked transliteration x typo;
- negatives in three strata: easy random pairs, HARD cross-group pairs
  with DL <= 2, and initial-vs-different-name pairs sharing a first
  letter;
- 80/10/10 train/val/calibration split BY GROUP so calibration sees
  held-out names, not held-out spellings.

Anchor-pool diversity comes from the engine's own tables plus the
philipperemy/name-dataset pool (Apache-2.0,
https://github.com/philipperemy/name-dataset) — DEV-ONLY input,
downloaded at train time to a local cache and NEVER shipped: the wheel
carries only the ~400KB NPZ weights.

Determinism: fixed default seed everywhere, one torch thread,
``torch.use_deterministic_algorithms(True)``, fixed hyperparameters, and
a fixed data-generation order. Same arguments -> same artifact bytes on
a platform (verify with ``--verify-determinism``).

Usage:
    python3 scripts/train_name_embedding.py                    # train + export
    python3 scripts/train_name_embedding.py --verify-determinism
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import pickle
import random
import re
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from fhir4ds.matching.normalizers import _NICKNAME_GROUPS  # noqa: E402
from fhir4ds.matching.rules import BAND_EDGES, BAND_U_VALUES  # noqa: E402
from fhir4ds.realism.corrupt import (  # noqa: E402
    TRANSLITERATION_GROUPS,
    _FAMILY_POOL,
    _dl_distance_bounded,
    damerau_le1_typo,
)

# --- pinned external pool (dev-only; never shipped) -------------------------
NAME_DATASET_COMMIT = "a3deb375107bada246ff41bea50408d78a0f9e51"
NAME_DATASET_BASE = (
    "https://raw.githubusercontent.com/philipperemy/name-dataset/"
    f"{NAME_DATASET_COMMIT}/names_dataset/v3"
)
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "fhir4ds" / "name-dataset-v3"

ARTIFACT_PATH = REPO_ROOT / "fhir4ds" / "matching" / "artifacts" / "name_embed_v1.npz"

SEED = 20261120
MAX_NAME_LEN = 24
NAME_RE = re.compile(r"^[a-z]+$")

# Hyperparameters (fixed for determinism; P4 may retrain under new values).
EPOCHS = 6
BATCH_SIZE = 256
LR = 1e-3
MARGIN = 0.3
EMBED_CHARS = 32
CONV_CHANNELS = 160
HIDDEN = 128
OUT_DIM = 16


@dataclass
class TrainingData:
    positives: list[tuple[str, str, str]]  # (a, b, group_key)
    negatives: list[tuple[str, str, str]]  # (a, b, stratum)
    split_of: dict[str, str]  # group_key -> train|val|calibration
    anchors: list[str]

    @property
    def vocab(self) -> list[str]:
        chars: set[str] = set()
        for a, b, _g in self.positives:
            chars.update(a)
            chars.update(b)
        for a, b, _s in self.negatives:
            chars.update(a)
            chars.update(b)
        chars.update(" ")
        vocab = ["<pad>"] + sorted(chars)
        return vocab


def hash_bytes(*blobs: bytes) -> str:
    h = hashlib.sha256()
    for b in blobs:
        h.update(b)
    return h.hexdigest()


def hash_training_data(data: TrainingData) -> str:
    payload = json.dumps(
        {
            "positives": data.positives,
            "negatives": data.negatives,
            "split_of": data.split_of,
            "anchors": data.anchors,
        },
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def corpus_table_hashes() -> dict[str, str]:
    return {
        "nickname_groups": hash_bytes(
            *( "|".join(sorted(g)).encode() for g in _NICKNAME_GROUPS )),
        "transliteration_groups": hash_bytes(
            *( "|".join(sorted(g)).encode() for g in TRANSLITERATION_GROUPS )),
        "family_pool": hash_bytes("|".join(_FAMILY_POOL).encode()),
    }


# ---------------------------------------------------------------------------
# anchor pool
# ---------------------------------------------------------------------------


def ensure_name_dataset(cache_dir: Path = DEFAULT_CACHE_DIR) -> tuple[Path, Path]:
    """Download the pinned philipperemy v3 pickles if not cached."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for name in ("first_names.pkl.gz", "last_names.pkl.gz"):
        dest = cache_dir / name
        if not dest.exists():
            url = f"{NAME_DATASET_BASE}/{name}"
            print(f"downloading {url} ...")
            with urllib.request.urlopen(url) as resp, dest.open("wb") as fh:
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    fh.write(chunk)
        out.append(dest)
    return out[0], out[1]


def load_pool_names(
    pkl_gz: Path, limit: int, seed: int
) -> list[str]:
    """Deterministic alphabetic sample of <= ``limit`` names from a v3
    pickle (dict name -> stats)."""
    with gzip.open(pkl_gz, "rb") as fh:
        raw = pickle.load(fh)
    names = sorted(
        n.lower() for n in raw
        if isinstance(n, str)
        and len(n) <= MAX_NAME_LEN
        and NAME_RE.match(n.lower())
    )
    if len(names) <= limit:
        return names
    rng = random.Random(seed)
    return sorted(rng.sample(names, limit))


def _formal_names() -> list[str]:
    """Longest member of each nickname group is the formal name
    (lexicographic tie-break — set iteration order is not stable across
    processes)."""
    out = []
    for group in _NICKNAME_GROUPS:
        out.append(max(sorted(group), key=len))
    return sorted(set(out))


def generate_training_data(
    seed: int = SEED,
    pool_limit: int = 12000,
    last_pool_limit: int = 4000,
    cache_dir: Path | None = None,
    download: bool = True,
) -> TrainingData:
    """Deterministic training pairs (FDD §3.1). ``pool_limit`` caps the
    external anchor sample; small values keep the generator fast for the
    determinism unit test."""
    rng = random.Random(seed)
    nickname_names = sorted({n for g in _NICKNAME_GROUPS for n in g})
    translit_names = sorted({n for g in TRANSLITERATION_GROUPS for n in g})
    family = sorted({n.lower() for n in _FAMILY_POOL})

    pool_first: list[str] = []
    pool_last: list[str] = []
    if pool_limit > 0:
        if cache_dir is None:
            cache_dir = DEFAULT_CACHE_DIR
        try:
            first_pkl, last_pkl = ensure_name_dataset(cache_dir) \
                if download else _cached_only(cache_dir)
            pool_first = load_pool_names(first_pkl, pool_limit, seed)
            pool_last = load_pool_names(last_pkl, last_pool_limit, seed + 1)
        except Exception as exc:  # offline dev box: proceed engine-only
            print(f"WARNING: external name pool unavailable ({exc}); "
                  "training on the engine corpus only")

    anchors = sorted(set(
        nickname_names + translit_names + family + pool_first + pool_last
    ))

    positives: list[tuple[str, str, str]] = []
    negatives: list[tuple[str, str, str]] = []

    # (i) nickname intra-group pairs, <= 20 per group
    for group in _NICKNAME_GROUPS:
        members = sorted(group)
        pairs = [
            (a, b)
            for i, a in enumerate(members)
            for b in members[i + 1:]
        ]
        if len(pairs) > 20:
            pairs = sorted(rng.sample(pairs, 20))
        for a, b in pairs:
            positives.append((a, b, "nick:" + "|".join(members)))

    # (ii) transliteration intra-group pairs (all)
    for group in TRANSLITERATION_GROUPS:
        members = sorted(group)
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                positives.append((a, b, "translit:" + "|".join(members)))

    # (iii) DL-1 and DL-2 corruptions of every corpus/pool name
    for name in anchors:
        t1 = damerau_le1_typo(name, rng.randrange(2 ** 31))
        t2 = damerau_le1_typo(
            damerau_le1_typo(name, rng.randrange(2 ** 31)),
            rng.randrange(2 ** 31),
        )
        if t1 != name:
            positives.append((name, t1, f"typo1:{name}"))
        if t2 != name and t2 != t1:
            positives.append((name, t2, f"typo2:{name}"))

    # (iv) prefix truncations >= 4 chars + single initials (formal names)
    for formal in _formal_names():
        if len(formal) >= 6:
            for cut in (4, 5):
                if len(formal) > cut:
                    positives.append((formal, formal[:cut], f"prefix:{formal}"))
        positives.append((formal, formal[0], f"initial:{formal}"))

    # (v) stacked transliteration x typo
    for group in TRANSLITERATION_GROUPS:
        members = sorted(group)
        for name in members:
            others = [m for m in members if m != name]
            if not others:
                continue
            other = others[rng.randrange(len(others))]
            stacked = damerau_le1_typo(other, rng.randrange(2 ** 31))
            if stacked != name and stacked != other:
                positives.append(
                    (name, stacked, "stack:" + "|".join(members)))

    # negatives (i): easy random distinct pairs
    for _ in range(min(40000, len(anchors) * 2)):
        a = anchors[rng.randrange(len(anchors))]
        b = anchors[rng.randrange(len(anchors))]
        if a != b:
            negatives.append((a, b, "easy"))

    # negatives (ii): HARD cross-group pairs with DL <= 2
    local = nickname_names + translit_names
    hard: list[tuple[str, str]] = []
    for i, a in enumerate(local):
        for b in local[i + 1:]:
            if _dl_distance_bounded(a, b, 2) <= 2 and \
                    not {a, b} <= _same_group(a, b):
                hard.append((a, b))
    hard = sorted(set(hard))[:5000]
    for a, b in hard:
        negatives.append((a, b, "hard"))

    # negatives (iii): initial-vs-different-name sharing the first letter
    initials = [n for n in set(nickname_names + translit_names) if len(n) == 1]
    by_letter: dict[str, list[str]] = {}
    for n in set(nickname_names + translit_names):
        if len(n) >= 3:
            by_letter.setdefault(n[0], []).append(n)
    trap: list[tuple[str, str]] = []
    for ini in initials:
        for other in sorted(by_letter.get(ini[0], []))[:8]:
            if other[0] == ini[0]:
                trap.append((ini, other))
    trap = sorted(set(trap))[:5000]
    for a, b in trap:
        negatives.append((a, b, "initial_trap"))

    # group-level 80/10/10 split
    groups = sorted({g for _a, _b, g in positives})
    rng.shuffle(groups)
    n = len(groups)
    n_train = n * 8 // 10
    n_val = n * 1 // 10
    split_of: dict[str, str] = {}
    for idx, g in enumerate(groups):
        split_of[g] = (
            "train" if idx < n_train
            else "val" if idx < n_train + n_val
            else "calibration"
        )

    return TrainingData(
        positives=positives,
        negatives=negatives,
        split_of=split_of,
        anchors=anchors,
    )


def _same_group(a: str, b: str) -> frozenset[str]:
    """Members of any nickname/transliteration group containing BOTH names
    (empty when the pair is genuinely cross-group)."""
    shared: set[str] = set()
    for group in (*_NICKNAME_GROUPS, *TRANSLITERATION_GROUPS):
        if a in group and b in group:
            shared |= group
    return frozenset(shared)


def _cached_only(cache_dir: Path) -> tuple[Path, Path]:
    first = cache_dir / "first_names.pkl.gz"
    last = cache_dir / "last_names.pkl.gz"
    if not (first.exists() and last.exists()):
        raise FileNotFoundError(f"cached pool incomplete under {cache_dir}")
    return first, last


# ---------------------------------------------------------------------------
# model + training (torch, dev-only)
# ---------------------------------------------------------------------------


def build_model_torch(vocab_size: int):
    import torch
    import torch.nn as nn

    class Net(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.embed = nn.Embedding(vocab_size, EMBED_CHARS)
            self.conv3 = nn.Conv1d(EMBED_CHARS, CONV_CHANNELS, 3)
            self.conv5 = nn.Conv1d(EMBED_CHARS, CONV_CHANNELS, 5)
            self.fc1 = nn.Linear(2 * CONV_CHANNELS, HIDDEN)
            self.fc2 = nn.Linear(HIDDEN, OUT_DIM)

        def forward(self, x):  # x: (B, L) int64
            e = self.embed(x).transpose(1, 2)  # (B, E, L)
            c3 = torch.relu(self.conv3(e)).max(dim=2).values
            c5 = torch.relu(self.conv5(e)).max(dim=2).values
            h = torch.relu(self.fc1(torch.cat([c3, c5], dim=1)))
            z = self.fc2(h)
            return z / z.norm(dim=1, keepdim=True).clamp_min(1e-12)

    return Net()


def _encode(name: str, vocab: dict[str, int]) -> list[int]:
    ids = [vocab.get(ch, 0) for ch in name[:MAX_NAME_LEN]]
    while len(ids) < 5:
        ids.append(0)
    return ids


def train_model(data: TrainingData, seed: int = SEED, epochs: int = EPOCHS):
    """Train the triplet model on CPU deterministically. Returns
    (model, vocab_list, logs)."""
    import torch
    import torch.nn.functional as F

    torch.set_num_threads(1)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)

    vocab = data.vocab
    vmap = {c: i for i, c in enumerate(vocab)}
    train_pos = [
        (a, b) for a, b, g in data.positives if data.split_of[g] == "train"
    ]
    val_pos = [
        (a, b) for a, b, g in data.positives if data.split_of[g] == "val"
    ]
    negatives = data.negatives
    rng = random.Random(seed)

    triplets = []
    for a, b in train_pos:
        neg = negatives[rng.randrange(len(negatives))][0:2]
        triplets.append((a, b, neg[0], neg[1]))
    print(f"train triplets: {len(triplets)}  val positives: {len(val_pos)}")

    model = build_model_torch(len(vocab))
    params = sum(p.numel() for p in model.parameters())
    print(f"parameters: {params}")
    opt = torch.optim.Adam(model.parameters(), lr=LR)

    def batch_tensors(items):
        enc = [[_encode(x, vmap) for x in (a, p, n)]
               for a, p, n, _m in items]
        width = max(len(e) for row in enc for e in row)
        rows = [[e + [0] * (width - len(e)) for e in row] for row in enc]
        anc = torch.tensor([r[0] for r in rows])
        pos = torch.tensor([r[1] for r in rows])
        neg = torch.tensor([r[2] for r in rows])
        return anc, pos, neg

    logs = []
    order = list(range(len(triplets)))
    for epoch in range(epochs):
        rng.shuffle(order)
        model.train()
        total = 0.0
        for start in range(0, len(order), BATCH_SIZE):
            idx = order[start:start + BATCH_SIZE]
            items = [triplets[i] for i in idx]
            anc, pos, neg = batch_tensors(items)
            za, zp, zn = model(anc), model(pos), model(neg)
            loss = F.triplet_margin_loss(
                za, zp, zn, margin=MARGIN, swap=True)
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += float(loss) * len(idx)
        # quick val metrics
        model.eval()
        with torch.no_grad():
            pos_d, neg_d, correct = 0.0, 0.0, 0
            for start in range(0, max(len(val_pos), 1), BATCH_SIZE):
                chunk = val_pos[start:start + BATCH_SIZE]
                if not chunk:
                    break
                negs = [negatives[rng.randrange(len(negatives))][0]
                        for _ in chunk]
                enc = [
                    [_encode(x, vmap) for x in (a, b, n)]
                    for (a, b), n in zip(chunk, negs)
                ]
                width = max(len(e) for row in enc for e in row)
                rows = [[e + [0] * (width - len(e)) for e in row]
                        for row in enc]
                va = torch.tensor([r[0] for r in rows])
                vp = torch.tensor([r[1] for r in rows])
                vn = torch.tensor([r[2] for r in rows])
                da = (1 - (model(va) * model(vp)).sum(1))
                dn = (1 - (model(va) * model(vn)).sum(1))
                pos_d += float(da.sum())
                neg_d += float(dn.sum())
                correct += int((da < dn).sum())
            n_val = max(len(val_pos), 1)
            logs.append({
                "epoch": epoch + 1,
                "train_loss": total / len(order),
                "val_pos_dist": pos_d / n_val,
                "val_neg_dist": neg_d / n_val,
                "val_triplet_acc": correct / n_val,
            })
            print(json.dumps(logs[-1]))
    return model, vocab, logs


def _savez_deterministic(out_path: Path, payload: dict) -> None:
    """Byte-reproducible NPZ: entries in sorted key order, fixed zip
    timestamps (``np.savez`` stamps the wall clock, which would make the
    artifact hash differ across identical runs)."""
    import io
    import zipfile

    import numpy as np

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED,
                         allowZip64=True) as zf:
        for key in sorted(payload):
            info = zipfile.ZipInfo(f"{key}.npy", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            arr = np.asarray(payload[key])
            with zf.open(info, "w", force_zip64=True) as fh:
                np.lib.format.write_array(fh, arr, allow_pickle=False)
    tmp = out_path.with_suffix(".tmp")
    tmp.write_bytes(buf.getvalue())
    tmp.replace(out_path)


def export_artifact(model, vocab: list[str], out_path: Path,
                    data_hash: str, logs: list[dict],
                    pool_info: dict) -> dict:
    import numpy as np  # noqa: F401 (torch pulls the weights to host)

    from fhir4ds.matching.name_embedding import _weights_digest

    payload = {
        "embed_weight": model.embed.weight.detach().numpy().astype(np.float32),
        "conv3_weight": model.conv3.weight.detach().numpy().astype(np.float32),
        "conv3_bias": model.conv3.bias.detach().numpy().astype(np.float32),
        "conv5_weight": model.conv5.weight.detach().numpy().astype(np.float32),
        "conv5_bias": model.conv5.bias.detach().numpy().astype(np.float32),
        "fc1_weight": model.fc1.weight.detach().numpy().astype(np.float32),
        "fc1_bias": model.fc1.bias.detach().numpy().astype(np.float32),
        "fc2_weight": model.fc2.weight.detach().numpy().astype(np.float32),
        "fc2_bias": model.fc2.bias.detach().numpy().astype(np.float32),
        "vocab": np.asarray(vocab, dtype="U6"),
    }
    params = sum(int(p.numel()) for p in model.parameters())
    meta = {
        "version": "name-embed-v1",
        "trained_by": "scripts/train_name_embedding.py",
        "seed": SEED,
        "epochs": EPOCHS,
        "margin": MARGIN,
        "params": params,
        "training_data_sha256": data_hash,
        "corpus_table_hashes": corpus_table_hashes(),
        "name_dataset_commit": NAME_DATASET_COMMIT,
        "pool": pool_info,
        "logs": logs,
        "band_edges": dict(BAND_EDGES),
        "band_u_values": dict(BAND_U_VALUES),
        "calibrated": False,
        "note": "band edges/u-values are FDD illustrative UNCALIBRATED "
                "placeholders; FHIR4-20 P4 calibrates them",
    }
    payload["metadata_json"] = np.asarray(json.dumps(meta, sort_keys=True))
    payload["weights_sha256"] = np.asarray(_weights_digest(payload))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _savez_deterministic(out_path, payload)
    digest = hashlib.sha256(out_path.read_bytes()).hexdigest()
    info = {
        "path": str(out_path),
        "bytes": out_path.stat().st_size,
        "sha256": digest,
        "params": params,
    }
    print(json.dumps(info, indent=2))
    return info


def run_training(out_path: Path = ARTIFACT_PATH, seed: int = SEED) -> dict:
    data = generate_training_data(seed=seed)
    data_hash = hash_training_data(data)
    print(f"training-data sha256: {data_hash}")
    print(f"positives: {len(data.positives)}  negatives: {len(data.negatives)}")
    model, vocab, logs = train_model(data, seed=seed)
    pool_info = {
        "anchors": len(data.anchors),
        "positives": len(data.positives),
        "negatives": len(data.negatives),
        "groups_train": sum(1 for s in data.split_of.values() if s == "train"),
        "groups_val": sum(1 for s in data.split_of.values() if s == "val"),
        "groups_calibration": sum(
            1 for s in data.split_of.values() if s == "calibration"),
    }
    return export_artifact(model, vocab, out_path, data_hash, logs, pool_info)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ARTIFACT_PATH)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument(
        "--verify-determinism", action="store_true",
        help="run the FULL pipeline twice (to temp files) and assert "
             "identical artifact sha256 (slow)",
    )
    args = parser.parse_args(argv)

    if args.verify_determinism:
        with tempfile.TemporaryDirectory() as td:
            a = run_training(Path(td) / "a.npz", seed=args.seed)
            b = run_training(Path(td) / "b.npz", seed=args.seed)
        assert a["sha256"] == b["sha256"], (
            f"training is not deterministic: {a['sha256']} != {b['sha256']}")
        print(f"DETERMINISM OK: {a['sha256']}")
        return 0

    run_training(args.output, seed=args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
