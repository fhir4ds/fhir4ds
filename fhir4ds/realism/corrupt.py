"""Duplicate-injection corruption harness (AMUX-150 realism follow-on).

Given any FHIR patient corpus, produce a gold-labeled matching benchmark:

- sample a subset of patients (seeded, deterministic);
- for each sampled patient emit a corrupted DUPLICATE ``Patient`` plus
  correlated duplicates of their clinical resources (patient refs
  rewritten to the duplicate patient);
- every corruption is a NAMED profile — a seeded deterministic
  transform — recorded on the gold pair so per-profile recall can be
  measured downstream;
- untouched patients remain the honest-negative population (two
  different real patients must NOT match).

Profiles
--------
``clean_copy``            exact copy, new id (sanity floor)
``name_typos``            Damerau-Levenshtein distance-1 char op on
                          given/family
``name_nicknames``        swap the given name for another member of the
                          matching engine's own nickname table
``name_transliteration``  swap for another spelling from the built-in
                          transliteration variant table (the documented
                          engine gap this harness exists to expose)
``dob_shift``             birthDate shifted by a day/month-scale amount
``address_move``          street-line / postal-code edit
``phone_digit_flip``      exactly one phone digit changed
``mrn_variant``           same MRN digits, different formatting

Determinism: every transform draws from a caller-supplied
``random.Random`` seeded from ``CorruptionConfig.seed``; patient order is
sorted by id; output sorting is canonical. Same config + same corpus ->
byte-identical result. No wall clock, no global RNG state.
"""

from __future__ import annotations

import copy
import random
import string
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from fhir4ds.matching.normalizers import nickname_set, norm_text

__all__ = [
    "PROFILES",
    "DEFAULT_PROFILE_WEIGHTS",
    "TRANSLITERATION_GROUPS",
    "CorruptionConfig",
    "GoldPair",
    "InjectionResult",
    "apply_profile",
    "damerau_le1_typo",
    "inject_duplicates",
]

#: Registered corruption profiles (``clean_copy`` is a mode, weighted via
#: ``CorruptionConfig.clean_duplicate_ratio`` rather than the weights).
PROFILES: tuple[str, ...] = (
    "clean_copy",
    "name_typos",
    "name_nicknames",
    "name_transliteration",
    "dob_shift",
    "address_move",
    "phone_digit_flip",
    "mrn_variant",
)

#: Default profile weights (name-typos dominant — the common real-world
#: duplicate shape). Any subset of the non-clean profiles may be supplied.
DEFAULT_PROFILE_WEIGHTS: dict[str, float] = {
    "name_typos": 3.0,
    "name_nicknames": 2.0,
    "name_transliteration": 1.0,
    "dob_shift": 2.0,
    "address_move": 1.0,
    "phone_digit_flip": 1.0,
    "mrn_variant": 1.0,
}

#: Built-in transliteration / spelling-variant groups (ComplyAdvantage
#: "ethnic name variations" style examples). Lowercase, disjoint groups.
TRANSLITERATION_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"mohammed", "muhammad", "mohammad", "muhummad", "mohamed",
               "mohamad", "mohmmed"}),
    frozenset({"ahmed", "ahmad", "achmed"}),
    frozenset({"yusuf", "youssef", "yousef", "yousuf", "yussoef"}),
    frozenset({"ali", "aly", "allee"}),
    frozenset({"omar", "omer", "umar", "oumar"}),
    frozenset({"stephen", "steven", "stephan", "stefan", "steffen"}),
    frozenset({"sofia", "sofiya", "sofiia", "sofia", "zofia", "sofie"}),
    frozenset({"nikolai", "nikolay", "mykola", "nicolai"}),
    frozenset({"georgi", "george", "giorgi", "gyorgy", "jurgen"}),
    frozenset({"wei", "wai", "way"}),
    frozenset({"chen", "chin", "chern"}),
    frozenset({"kim", "gim", "ghim"}),
)

_TRANSLIT_LOOKUP: dict[str, frozenset[str]] = {}
for _group in TRANSLITERATION_GROUPS:
    for _name in _group:
        _TRANSLIT_LOOKUP[_name] = _group

_MAX_STACK = 3
_CLINICAL_TYPES = ("Observation", "Condition", "Encounter")


def _usable_patient_id(patient: dict) -> Optional[str]:
    """The patient's id when it is a non-empty string, else ``None``.

    ``load_corpus`` is tolerance-first (QA-D6S-001): structurally-valid
    JSON with a non-string or missing ``id`` loads fine. Duplicate
    injection cannot use such patients — dup ids, gold pairs and the
    matching index all key on the id — so they pass through untouched
    instead of crashing the harness (QA-D6H-001)."""
    pid = patient.get("id")
    if isinstance(pid, str) and pid:
        return pid
    return None

#: Family-name pool for :func:`realisticize_names` (realistic US-style
#: surnames; the given-name pool is derived from the matching engine's
#: own nickname table — formal names and their diminutives).
_FAMILY_POOL: tuple[str, ...] = tuple(sorted({
    "Alvarez", "Brennan", "Carter", "Chen", "Delgado", "Ellison",
    "Fitzgerald", "Griffin", "Huang", "Ibrahim", "Johnson", "Kim",
    "Larsen", "Martinez", "Novak", "Okafor", "Patel", "Quinn",
    "Ramirez", "Sokolov", "Tanaka", "Ustinov", "Vargas", "Whitfield",
    "Xu", "Yamamoto", "Zhao", "Abrams", "Bernstein", "Castellanos",
    "Dvorak", "Eriksen", "Feldman", "Gustafsson", "Hassan", "Ivanov",
    "Jensen", "Kowalski", "Lindqvist", "Mbeki", "Nakamura",
}))

_SYNTHETIC_FAMILY_PREFIX = "patient_"


def _given_name_pool() -> tuple[str, ...]:
    """Deterministic given-name pool from the engine's nickname table."""
    from fhir4ds.matching.normalizers import _NICKNAME_GROUPS
    names = sorted({
        name
        for group in _NICKNAME_GROUPS
        for name in group
        if len(name) >= 3
    })
    return tuple(n.capitalize() for n in names)


def _is_synthetic_name(patient: dict) -> bool:
    """MIMIC demo patients carry ``family: "Patient_<id>"`` with no given
    names — synthetic literals that give name corruption nothing to
    corrupt and the matcher nothing to match on."""
    name = _official_name(patient)
    if name is None:
        return True
    family = name.get("family")
    if not isinstance(family, str) or not family.strip():
        return True
    if norm_text(family).startswith(_SYNTHETIC_FAMILY_PREFIX):
        return True
    return _given(name) is None


def realisticize_names(patients: list[dict],
                       rng: random.Random) -> tuple[list[dict], list[str]]:
    """Replace synthetic patient names with generated realistic ones.

    Returns (new patient list — originals never mutated, ids of patients
    whose names were replaced). Generation draws given names from the
    engine's nickname-table corpus and family names from the built-in
    pool, both deterministically via ``rng``. Patients with real names
    pass through unchanged (deep-copied).
    """
    given_pool = _given_name_pool()
    out: list[dict] = []
    replaced: list[str] = []
    for patient in sorted(patients, key=lambda p: str(p.get("id", ""))):
        if not _is_synthetic_name(patient) or _usable_patient_id(
                patient) is None:
            out.append(patient)
            continue
        clone = copy.deepcopy(patient)
        given = given_pool[rng.randrange(len(given_pool))]
        family = _FAMILY_POOL[rng.randrange(len(_FAMILY_POOL))]
        clone["name"] = [{"use": "official",
                          "family": family, "given": [given]}]
        replaced.append(patient["id"])
        out.append(clone)
    return sorted(out, key=lambda p: str(p.get("id", ""))), replaced


def rebase_future_birthdates(patients: list[dict]) -> tuple[list[dict], int]:
    """Shift future birthDates back by whole centuries (2083 -> 1983).

    MIMIC de-identification shifts dates far out (often next century),
    which the matcher's strict date normalization rejects as future —
    making every DOB field vacuous. Subtracting 100-year steps is
    deterministic, preserves the age structure, and keeps every date in
    the past. Originals are never mutated. Returns (patients, n shifted).
    """
    out: list[dict] = []
    shifted = 0
    for patient in sorted(patients, key=lambda p: str(p.get("id", ""))):
        dob = patient.get("birthDate")
        if isinstance(dob, str) and len(dob) >= 4:
            try:
                year = int(dob[:4])
            except ValueError:
                year = 0
            if year > 2000:
                clone = copy.deepcopy(patient)
                new_year = year
                while new_year > 2000:
                    new_year -= 100
                clone["birthDate"] = f"{new_year:04d}" + dob[4:]
                out.append(clone)
                shifted += 1
                continue
        out.append(patient)
    return sorted(out, key=lambda p: str(p.get("id", ""))), shifted


# ---------------------------------------------------------------------------
# config + result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CorruptionConfig:
    """Seeded, deterministic injection configuration."""

    seed: int = 20261120
    #: How many patients get duplicates (``None`` = every patient).
    num_patients: Optional[int] = None
    #: Duplicates emitted per selected patient.
    dups_per_patient: int = 1
    #: Fraction of duplicates that are exact copies (sanity floor).
    clean_duplicate_ratio: float = 0.0
    #: Probability a duplicate receives a SECOND (third…) profile.
    stack_probability: float = 0.0
    #: Profile weights (subset of the non-clean profiles). ``None`` ->
    #: :data:`DEFAULT_PROFILE_WEIGHTS`.
    profile_weights: Optional[dict[str, float]] = None
    #: Replace synthetic patient names (MIMIC demo ``Patient_<id>``
    #: literals with no given names) with generated realistic names
    #: BEFORE duplicate selection, so name corruption has something to
    #: corrupt. Ids of rewritten patients are reported.
    realistic_names: bool = False
    #: Shift future (de-identification-shifted) birthDates back by whole
    #: centuries so the matcher's strict date normalization sees them.
    rebase_future_birthdates: bool = False

    def __post_init__(self) -> None:
        if self.num_patients is not None and self.num_patients < 0:
            raise ValueError("num_patients must be >= 0")
        if self.dups_per_patient < 1:
            raise ValueError("dups_per_patient must be >= 1")
        if not 0.0 <= self.clean_duplicate_ratio <= 1.0:
            raise ValueError("clean_duplicate_ratio must be in [0, 1]")
        if not 0.0 <= self.stack_probability <= 1.0:
            raise ValueError("stack_probability must be in [0, 1]")
        weights = self.effective_weights()
        unknown = set(weights) - set(PROFILES)
        if unknown:
            raise ValueError(f"unknown profile(s) in weights: {sorted(unknown)}")
        if any(w < 0 for w in weights.values()):
            raise ValueError("profile weights must be non-negative")
        if sum(weights.values()) <= 0:
            raise ValueError("profile weights must sum > 0")

    def effective_weights(self) -> dict[str, float]:
        if self.profile_weights is None:
            return dict(DEFAULT_PROFILE_WEIGHTS)
        return dict(self.profile_weights)


@dataclass(frozen=True)
class GoldPair:
    """One injected duplicate: original id, dup id, profiles applied."""

    original_id: str
    dup_id: str
    profiles_applied: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "original_id": self.original_id,
            "dup_id": self.dup_id,
            "profiles_applied": list(self.profiles_applied),
        }


@dataclass
class InjectionResult:
    """Full output of :func:`inject_duplicates`."""

    patients: list[dict]
    clinical: list[dict]
    gold_pairs: list[GoldPair]
    seed: int
    config: CorruptionConfig
    honest_negative_ids: list[str] = field(default_factory=list)
    names_replaced: list[str] = field(default_factory=list)
    birthdates_rebased: int = 0


# ---------------------------------------------------------------------------
# primitive transforms
# ---------------------------------------------------------------------------


def damerau_le1_typo(word: str, seed: int) -> str:
    """One deterministic Damerau-Levenshtein distance-1 edit on ``word``.

    Ops: substitute / delete / insert / transpose — chosen from a
    ``random.Random(seed)``; guaranteed to change the word.
    """
    if not word:
        raise ValueError("cannot typo an empty word")
    rng = random.Random(seed)
    letters = string.ascii_lowercase
    for _ in range(50):
        op = rng.choice(("sub", "del", "ins", "swap"))
        pos = rng.randrange(len(word))
        if op == "sub":
            repl = rng.choice(letters)
            out = word[:pos] + repl + word[pos + 1:]
        elif op == "del" and len(word) > 1:
            out = word[:pos] + word[pos + 1:]
        elif op == "ins":
            out = word[:pos] + rng.choice(letters) + word[pos:]
        elif op == "swap" and len(word) > 1 and pos + 1 < len(word):
            out = (word[:pos] + word[pos + 1] + word[pos]
                   + word[pos + 2:])
        else:
            continue
        if out != word:
            return out
    # Degenerate inputs (e.g. single repeated letter): force a substitute.
    return word + "x"


def _official_name(patient: dict) -> Optional[dict]:
    names = patient.get("name") or []
    official = [n for n in names
                if isinstance(n, dict) and n.get("use") == "official"]
    name = (official or [n for n in names if isinstance(n, dict)])[0] \
        if names else None
    return name if isinstance(name, dict) else None


def _given(name: dict) -> Optional[str]:
    given = name.get("given") or []
    if isinstance(given, str):
        given = [given]
    given = [g for g in given if isinstance(g, str)]
    return given[0] if given else None


def _set_given(name: dict, value: str) -> None:
    given = name.get("given")
    if isinstance(given, list) and given:
        name["given"] = [value] + [
            g for g in given[1:] if isinstance(g, str)]
    else:
        name["given"] = [value]


def _phone_telecom(patient: dict) -> Optional[dict]:
    for telecom in patient.get("telecom") or []:
        if (isinstance(telecom, dict)
                and telecom.get("system") == "phone"
                and isinstance(telecom.get("value"), str)
                and any(c.isdigit() for c in telecom["value"])):
            return telecom
    return None


def _mrn_identifier(patient: dict) -> Optional[dict]:
    """Pick the identifier to corrupt: MR-typed first, else any numeric
    system-scoped identifier (the MIMIC demo has no MR type — its
    patient identifiers are system-scoped numerics)."""
    fallback: Optional[dict] = None
    for ident in patient.get("identifier") or []:
        if not isinstance(ident, dict):
            continue
        value = ident.get("value")
        if not isinstance(value, str) or not value.isdigit() or len(value) < 5:
            continue
        coding = ((ident.get("type") or {}).get("coding") or [{}])[0]
        system = (ident.get("system") or "").lower()
        if coding.get("code") == "MR" or "mrn" in system or "medical" in system:
            return ident
        if system and fallback is None:
            fallback = ident
    return fallback


def _profile_name_typos(patient: dict, rng: random.Random) -> bool:
    name = _official_name(patient)
    if name is None:
        return False
    targets = []
    given = _given(name)
    if given and len(given) >= 3:
        targets.append(("given", given))
    family = name.get("family")
    if isinstance(family, str) and len(family) >= 3:
        targets.append(("family", family))
    if not targets:
        return False
    kind, word = rng.choice(sorted(targets))
    typo = damerau_le1_typo(word, rng.randrange(2 ** 31))
    if kind == "given":
        _set_given(name, typo)
    else:
        name["family"] = typo
    return True


def _profile_name_nicknames(patient: dict, rng: random.Random) -> bool:
    name = _official_name(patient)
    if name is None:
        return False
    given = _given(name)
    if given is None:
        return False
    group = nickname_set(norm_text(given))
    candidates = sorted(n for n in group if n != norm_text(given))
    if not candidates:
        return False
    pick = candidates[rng.randrange(len(candidates))]
    _set_given(name, pick.capitalize())
    return True


def _dl_distance_bounded(a: str, b: str, cap: int = 2) -> int:
    """Damerau-Levenshtein distance, early-exiting above ``cap``."""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if abs(la - lb) > cap:
        return cap + 1
    prev2 = None
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            val = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if (i > 1 and j > 1 and a[i - 1] == b[j - 2]
                    and a[i - 2] == b[j - 1]):
                val = min(val, prev2[j - 2] + 1)  # transposition
            cur[j] = val
        if min(cur) > cap:
            return cap + 1
        prev2, prev = prev, cur
    return prev[lb]


def _profile_name_transliteration(patient: dict, rng: random.Random) -> bool:
    name = _official_name(patient)
    if name is None:
        return False
    given = _given(name)
    if given is None:
        return False
    group = _TRANSLIT_LOOKUP.get(given.lower())
    if group is None:
        return False
    candidates = sorted(n for n in group if n != given.lower())
    if not candidates:
        return False
    # Prefer distance-2+ variants: single-edit spellings are caught by
    # the engine's DL<=1 fuzzy names, so the *corruption* class this
    # profile represents is the genuinely-different transliteration.
    far = [n for n in candidates
           if _dl_distance_bounded(given.lower(), n, 2) > 1]
    pool = far or candidates
    pick = pool[rng.randrange(len(pool))]
    _set_given(name, pick.capitalize())
    return True


def _profile_dob_shift(patient: dict, rng: random.Random) -> bool:
    dob = patient.get("birthDate")
    if not isinstance(dob, str):
        return False
    try:
        d = date.fromisoformat(dob)
    except ValueError:
        return False
    mode = rng.choice(("days", "month"))
    if mode == "days":
        d = d + timedelta(days=rng.choice((-1, 1)) *
                          rng.randint(1, 30))
    else:
        month = d.month + rng.choice((-1, 1))
        year = d.year + (0 if 1 <= month <= 12 else (-1 if month < 1 else 1))
        month = (month - 1) % 12 + 1
        # clamp day to the target month length
        for day in range(d.day, 0, -1):
            try:
                d = date(year, month, day)
                break
            except ValueError:
                continue
    patient["birthDate"] = d.isoformat()
    return True


def _profile_address_move(patient: dict, rng: random.Random) -> bool:
    addresses = [a for a in patient.get("address") or []
                 if isinstance(a, dict)]
    if not addresses:
        return False
    addr = addresses[0]
    target = rng.choice(("street", "zip"))
    if target == "street":
        lines = addr.get("line")
        if isinstance(lines, list) and lines and isinstance(lines[0], str):
            line = lines[0]
            for i, ch in enumerate(line):
                if ch.isdigit():
                    new_digit = str((int(ch) + rng.randint(1, 9)) % 10)
                    lines[0] = line[:i] + new_digit + line[i + 1:]
                    return True
            lines[0] = line + " B"
            return True
        addr["line"] = ["1 Moved Street"]
        return True
    zip_code = addr.get("postalCode")
    if isinstance(zip_code, str) and len(zip_code) >= 3:
        i = rng.randrange(len(zip_code))
        ch = zip_code[i]
        if ch.isdigit():
            addr["postalCode"] = (
                zip_code[:i] + str((int(ch) + rng.randint(1, 9)) % 10)
                + zip_code[i + 1:])
        else:
            addr["postalCode"] = zip_code + "9"
        return True
    addr["postalCode"] = "99999"
    return True


def _profile_phone_digit_flip(patient: dict, rng: random.Random) -> bool:
    telecom = _phone_telecom(patient)
    if telecom is None:
        return False
    digits = [(i, ch) for i, ch in enumerate(telecom["value"])
              if ch.isdigit()]
    if not digits:
        return False
    i, ch = digits[rng.randrange(len(digits))]
    new_digit = str((int(ch) + rng.randint(1, 9)) % 10)
    value = telecom["value"]
    telecom["value"] = value[:i] + new_digit + value[i + 1:]
    return True


def _profile_mrn_variant(patient: dict, rng: random.Random) -> bool:
    ident = _mrn_identifier(patient)
    if ident is None:
        return False
    digits = ident["value"]
    variants = []
    stripped = digits.lstrip("0")
    if stripped and stripped != digits:
        variants.append(stripped)
    if len(digits) >= 6:
        variants.append(f"{digits[:3]}-{digits[3:]}")
    padded = digits.zfill(len(digits) + 2)
    variants.append(padded)
    pick = sorted(set(v for v in variants if v != digits))
    ident["value"] = pick[rng.randrange(len(pick))]
    return True


_PROFILE_FUNCS = {
    "name_typos": _profile_name_typos,
    "name_nicknames": _profile_name_nicknames,
    "name_transliteration": _profile_name_transliteration,
    "dob_shift": _profile_dob_shift,
    "address_move": _profile_address_move,
    "phone_digit_flip": _profile_phone_digit_flip,
    "mrn_variant": _profile_mrn_variant,
}


def apply_profile(profile: str, patient: dict,
                  rng: random.Random) -> bool:
    """Apply one named profile to ``patient`` IN PLACE.

    Returns ``True`` when the profile changed the patient, ``False``
    when it was inapplicable (e.g. nickname swap on a name absent from
    the nickname table). ``clean_copy`` is always applicable and changes
    nothing (returns ``True`` with identity semantics — the duplicate
    id assignment happens in :func:`inject_duplicates`).
    """
    if profile == "clean_copy":
        return True
    func = _PROFILE_FUNCS.get(profile)
    if func is None:
        raise ValueError(
            f"unknown corruption profile {profile!r}; "
            f"known: {sorted(PROFILES)}")
    return func(patient, rng)


# ---------------------------------------------------------------------------
# injection
# ---------------------------------------------------------------------------


def _dup_id(base_id: object, k: int) -> str:
    suffix = f"-d{k}"
    stem = str(base_id)[: 64 - len(suffix)]
    return f"{stem}{suffix}"


def _rewrite_patient_ref(resource: dict, new_ref: str) -> bool:
    """Rewrite subject/patient reference -> ``Patient/<new_ref>``."""
    changed = False
    for field_name in ("subject", "patient"):
        ref = resource.get(field_name)
        if isinstance(ref, dict) and isinstance(ref.get("reference"), str):
            ref["reference"] = f"Patient/{new_ref}"
            changed = True
    return changed


def _pick_weighted(weights: dict[str, float],
                   rng: random.Random) -> str:
    names = sorted(weights)
    total = sum(weights[n] for n in names)
    roll = rng.random() * total
    acc = 0.0
    for name in names:
        acc += weights[name]
        if roll < acc:
            return name
    return names[-1]


def _corrupt_duplicate(dup: dict, config: CorruptionConfig,
                       rng: random.Random) -> tuple[str, ...]:
    """Choose + apply profiles to one duplicate. Returns applied names."""
    applied: list[str] = []
    if rng.random() < config.clean_duplicate_ratio:
        return ("clean_copy",)
    weights = config.effective_weights()
    while len(applied) < _MAX_STACK:
        pick = _pick_weighted(weights, rng)
        if pick in applied:
            break  # never apply the same transform twice to one dup
        if apply_profile(pick, dup, rng):
            applied.append(pick)
            break
        # Inapplicable (e.g. no address): retry once via name_typos, which
        # every patient in a matching corpus must have.
        if apply_profile("name_typos", dup, rng):
            applied.append("name_typos")
            break
        applied.append("clean_copy")  # nameless patient: identity copy
        break
    # Optional stacking of a second/third distinct profile.
    attempts = 0
    while (rng.random() < config.stack_probability
           and len(applied) < _MAX_STACK
           and attempts < 4 * len(weights)):
        attempts += 1
        pick = _pick_weighted(weights, rng)
        if pick in applied:
            continue
        if apply_profile(pick, dup, rng):
            applied.append(pick)
        else:
            break  # inapplicable for this patient; stop stacking
    return tuple(applied)


def inject_duplicates(
    patients: list[dict],
    clinical: list[dict],
    config: CorruptionConfig,
) -> InjectionResult:
    """Emit corrupted duplicates + gold pairs for a patient corpus.

    ``patients``: FHIR Patient resources (never mutated — deep-copied).
    ``clinical``: the non-Patient resources (Observation / Condition /
    Encounter / …), also never mutated; duplicates of the selected
    patients' clinical records are emitted with rewritten patient refs.
    """
    rng = random.Random(config.seed)
    ordered = sorted(patients, key=lambda p: str(p.get("id", "")))
    names_replaced: list[str] = []
    dobs_rebased = 0
    if config.realistic_names:
        ordered, names_replaced = realisticize_names(ordered, rng)
    if config.rebase_future_birthdates:
        ordered, dobs_rebased = rebase_future_birthdates(ordered)

    # QA-D6H-001: only patients with a usable string id can participate
    # in injection; loader-tolerated unusable shapes pass through.
    eligible = [p for p in ordered if _usable_patient_id(p) is not None]

    if config.num_patients == 0:
        return InjectionResult(
            patients=ordered,
            clinical=sorted(clinical,
                            key=lambda r: str(r.get("id", ""))),
            gold_pairs=[], seed=config.seed, config=config,
            honest_negative_ids=sorted(p["id"] for p in eligible),
            names_replaced=names_replaced,
            birthdates_rebased=dobs_rebased,
        )

    if config.num_patients is None:
        selected = eligible
    else:
        selected = sorted(
            rng.sample(eligible, min(config.num_patients,
                                     len(eligible))),
            key=lambda p: p["id"])
    selected_ids = {p["id"] for p in selected}

    clinical_by_patient: dict[str, list[dict]] = {}
    for resource in sorted(clinical, key=lambda r: str(r.get("id", ""))):
        ref = None
        for field_name in ("subject", "patient"):
            holder = resource.get(field_name)
            if isinstance(holder, dict) and isinstance(
                    holder.get("reference"), str):
                ref = holder["reference"]
                break
        if ref and ref.startswith("Patient/"):
            clinical_by_patient.setdefault(
                ref[len("Patient/"):], []).append(resource)

    dup_patients: list[dict] = []
    dup_clinical: list[dict] = []
    gold: list[GoldPair] = []
    for original in selected:
        for k in range(1, config.dups_per_patient + 1):
            dup = copy.deepcopy(original)
            dup_id = _dup_id(original["id"], k)
            dup["id"] = dup_id
            profiles = _corrupt_duplicate(dup, config, rng)
            dup_patients.append(dup)
            gold.append(GoldPair(original["id"], dup_id, profiles))
            for resource in clinical_by_patient.get(original["id"], []):
                dup_res = copy.deepcopy(resource)
                dup_res["id"] = _dup_id(resource.get("id") or "res", k)
                _rewrite_patient_ref(dup_res, dup_id)
                dup_clinical.append(dup_res)

    all_patients = sorted(ordered + dup_patients,
                          key=lambda p: str(p.get("id", "")))
    all_clinical = sorted(
        list(clinical) + dup_clinical, key=lambda r: str(r.get("id", "")))
    honest = sorted(p["id"] for p in eligible
                    if p["id"] not in selected_ids)
    return InjectionResult(
        patients=all_patients,
        clinical=all_clinical,
        gold_pairs=gold,
        seed=config.seed,
        config=config,
        honest_negative_ids=honest,
        names_replaced=names_replaced,
        birthdates_rebased=dobs_rebased,
    )
