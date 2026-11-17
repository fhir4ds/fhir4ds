#!/usr/bin/env python3
"""Generate the AMUX-134 patient-matching golden corpus (v1).

Deterministic (fixed seed) synthetic labeled corpus of Patient PAIRS:

- ~60 duplicate pairs spanning the variation axes the engine is designed to
  absorb: diacritics, nickname swaps, phone formatting + placeholder noise,
  email casing, SSN digit formats, street-line formatting, +/-1-day DOB on
  true duplicates, and transposition typos in names.
- ~60 negative pairs, half of them HARD family negatives: siblings sharing
  address + last name + DOB(+/-0) with different first names / SSN4, and
  twins sharing DOB + address + last name with different first names/SSN4.

Generator discipline (per the AMUX-134 gates brief): every labeled duplicate
is verified at generation time to be catchable by at least one Category-1
rule in isolation, and no labeled negative pair may be caught by any rule.
If the engine legitimately cannot distinguish a scenario (rule 30's
documented "no twin disambiguation" legacy exception matches same-phone
siblings), the GENERATOR is adjusted (hard family members get distinct
contact points) rather than the engine.

Usage:
    PYTHONPATH=. python3 scripts/gen_matching_golden.py \
        [--out fhir4ds/matching/tests/fixtures/golden_corpus.json] [--seed 1340]

Self-checks run by default; ``--no-selfcheck`` skips them (not recommended).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fhir4ds.matching.fuzzy import name_fuzzy_match  # noqa: E402
from fhir4ds.matching.evaluation import (  # noqa: E402
    catching_rules,
    evaluate_golden,
    load_golden_corpus,
)

DEFAULT_OUT = REPO_ROOT / "fhir4ds/matching/tests/fixtures/golden_corpus.json"
DEFAULT_SEED = 1340

SSN_SYSTEM = "http://hl7.org/fhir/sid/us-ssn"

# Nickname pairs drawn from the engine's equivalence index (base, nickname).
NICKNAME_PAIRS = [
    ("Robert", "Bob"),
    ("William", "Bill"),
    ("Elizabeth", "Liz"),
    ("James", "Jim"),
    ("Margaret", "Maggie"),
    ("Katherine", "Kate"),
    ("Richard", "Rick"),
    ("Thomas", "Tom"),
    ("Daniel", "Dan"),
    ("Jennifer", "Jen"),
]

# Given names for generic people (>= 5 chars where typos are applied).
FIRST_NAMES = [
    "Marcus", "Adriana", "Sofia", "Lucas", "Elena", "Mateo", "Nadia",
    "Victor", "Camila", "Andre", "Bianca", "Stefan", "Monica", "Felipe",
    "Ingrid", "Darius", "Rosalba", "Emilio", "Clara", "Hugo", "Patricia",
    "Gabriel", "Valentina", "Sebastian", "Daniela", "Fernando", "Carolina",
    "Theodore", "Josephine", "Maximilian", "Charlotte", "Nathaniel",
    "Evangelina", "Bartholomew", "Perpetua", "Anastasia", "Konstantin",
    "Rafaela", "Montgomery", "Seraphina",
]

# Diacritic-bearing display variants (display -> ASCII-folded).
DIACRITIC_NAMES = {
    "Jose": "José",
    "Elena": "Elena",
    "Mateo": "Matéo",
    "Andre": "André",
    "Stefan": "Stefan",
    "Monica": "Mónica",
    "Felipe": "Felipe",
    "Ingrid": "Ingrid",
    "Emilio": "Emílio",
    "Clara": "Clára",
    "Rafaela": "Rafaela",
    "Seraphina": "Seraphina",
}

LAST_NAMES = [
    "Thompson", "Vasquez", "Okafor", "Kowalski", "Nakamura", "Fitzgerald",
    "Delacroix", "Brennan", "Charleston", "Wolfeschlegel", "Ivanovich",
    "Montenegro", "Silverstein", " Harrington", "Castellanos", "Rasmussen",
    "Ferreira", "Lindqvist", "Abioye", "Petrovitch", "Vandermeer",
    "Zielinski", "Cardoza", "Menendez", "Ostrander", "Bienvenue",
    "Kalogeropoulos", "Wetherbee", "Salazar", "Thorvaldsen",
]
LAST_NAMES = [n.strip() for n in LAST_NAMES]

STREETS = [
    "Maple Street", "Birchwood Avenue", "Harborview Lane", "Cedar Court",
    "Lakeshore Drive", "Quarry Road", "Sycamore Bend", "Windmere Way",
    "Foxglove Terrace", "Bellweather Circle", "Juniper Crossing",
    "Aldergate Row", "Pembrook Place", "Stonehedge Path", "Copperline Alley",
]

CITIES = ["Springfield", "Riverton", "Fairview", "Lakewood", " Georgetown"]
STATES = ["IL", "OH", "TX", "WA", "GA"]

# Twin/sibling first-name pairs verified safe (no nickname equivalence, no
# DL<=1) by the self-check below; the generator retries until safe.
FAMILY_FIRST_POOL = [
    "Jasmine", "Alexander", "Miriam", "Theodore", "Leandra", "Caspian",
    "Rosalind", "Percival", "Anwen", "Barnaby", "Seraphina", "Dmitri",
    "Isolde", "Lucian", "Marisol", "Gregor", "Yolanda", "Fitzgerald",
    "Antonia", "Humberto", "Winston", "Esperanza", "Maximilian", "Iolanda",
]

PHONE_FORMATS = [
    lambda d: f"({d[0:3]}) {d[3:6]}-{d[6:]}",
    lambda d: f"{d[0:3]}-{d[3:6]}-{d[6:]}",
    lambda d: f"{d[0:3]}.{d[3:6]}.{d[6:]}",
    lambda d: f"+1{d}",
    lambda d: d,
]


def _fmt_ssn(digits9: str) -> str:
    return f"{digits9[0:3]}-{digits9[3:5]}-{digits9[5:]}"


def _transposition(name: str, rng: random.Random) -> str:
    """Swap two adjacent distinct letters of a >=5-char name (DL == 1)."""
    idxs = [i for i in range(len(name) - 1) if name[i] != name[i + 1]]
    i = rng.choice(idxs)
    return name[:i] + name[i + 1] + name[i] + name[i + 2 :]


class CorpusBuilder:
    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)
        self.patients: list[dict] = []
        self.pairs: list[dict] = []
        self._used_ids: set[str] = set()
        self._used_ssns: set[str] = set()
        self._used_phones: set[str] = set()
        self._used_emails: set[str] = set()

    # -- primitive pools ----------------------------------------------------
    def _id(self, base: str) -> str:
        n = 1
        while f"{base}-{n:03d}" in self._used_ids:
            n += 1
        pid = f"{base}-{n:03d}"
        self._used_ids.add(pid)
        return pid

    def _ssn9(self) -> str:
        while True:
            d = "".join(str(self.rng.randrange(10)) for _ in range(9))
            if d not in self._used_ssns and not d.startswith("000") and d[3:5] != "00" and d[5:] != "0000":
                self._used_ssns.add(d)
                return d

    def _phone10(self) -> str:
        while True:
            d = "".join(str(self.rng.randrange(10)) for _ in range(10))
            if (
                d not in self._used_phones
                and len(set(d)) > 1
                and d not in ("5555555555", "0000000000")
                and d[3:6] != "555"  # keep clear of the placeholder family
            ):
                self._used_phones.add(d)
                return d

    def _email(self, first_ascii: str, last_ascii: str) -> str:
        base = f"{first_ascii.lower()}.{last_ascii.lower()}"
        email = f"{base}@example.org"
        n = 2
        while email in self._used_emails:
            email = f"{base}{n}@example.org"
            n += 1
        self._used_emails.add(email)
        return email

    # -- resource assembly ---------------------------------------------------
    def _patient(
        self,
        pid: str,
        *,
        first_display: str,
        last_display: str,
        dob: str,
        phone: str | None,
        email: str | None,
        street: str | None,
        ssn9: str | None,
        phone_placeholder: bool = False,
        extra_ssn_format: bool = False,
    ) -> dict:
        telecom = []
        if phone_placeholder:
            telecom.append({"system": "phone", "value": "555-555-5555"})
        if phone is not None:
            fmt = PHONE_FORMATS[self.rng.randrange(len(PHONE_FORMATS))]
            telecom.append({"system": "phone", "value": fmt(phone)})
        if email is not None:
            casing = self.rng.choice([str.lower, str.upper, str.title])
            telecom.append({"system": "email", "value": casing(email)})
        resource: dict = {
            "resourceType": "Patient",
            "id": pid,
            "name": [{"use": "official", "family": last_display, "given": [first_display]}],
            "birthDate": dob,
            "gender": self.rng.choice(["male", "female"]),
        }
        if telecom:
            resource["telecom"] = telecom
        if street is not None:
            street_fmt = self.rng.choice(
                [lambda s: s, str.upper, lambda s: "  ".join(s.split())]
            )
            resource["address"] = [
                {
                    "line": [street_fmt(street)],
                    "city": self.rng.choice(CITIES),
                    "state": self.rng.choice(STATES),
                    "postalCode": f"{self.rng.randrange(10000, 99999)}",
                }
            ]
        if ssn9 is not None:
            value = ssn9 if extra_ssn_format else _fmt_ssn(ssn9)
            resource["identifier"] = [{"system": SSN_SYSTEM, "value": value}]
        self.patients.append(resource)
        return resource

    def _label(self, a: str, b: str, label: str, kind: str) -> None:
        self.pairs.append({"a": a, "b": b, "label": label, "kind": kind})

    # -- duplicate subtypes ---------------------------------------------------
    def duplicate_pairs(self) -> None:
        rng = self.rng
        # 10x id_format: formatting-only variation (diacritics, SSN digits,
        # phone formats, street casing) around an identical identity.
        for i in range(10):
            first = FIRST_NAMES[i]
            first_b = DIACRITIC_NAMES.get(first, first)
            last = LAST_NAMES[i]
            dob = _dt.date(1960 + i, (i % 12) + 1, (i % 27) + 1).isoformat()
            phone = self._phone10()
            ssn = self._ssn9()
            street = f"{100 + i} {STREETS[i % len(STREETS)]}"
            email = self._email(first.lower(), last.lower())
            pa = self._patient(
                self._id("dup"), first_display=first, last_display=last,
                dob=dob, phone=phone, email=email, street=street, ssn9=ssn,
            )
            pb = self._patient(
                self._id("dup"), first_display=first_b, last_display=last,
                dob=dob, phone=phone, email=email, street=street, ssn9=ssn,
                extra_ssn_format=True,
            )
            self._label(pa["id"], pb["id"], "duplicate", "id_format")

        # 10x nickname swap (rule 04/05 fuzzy first).
        for i, (base, nick) in enumerate(NICKNAME_PAIRS):
            last = LAST_NAMES[10 + i]
            dob = _dt.date(1955 + i, (i % 12) + 1, (i % 27) + 1).isoformat()
            phone = self._phone10()
            ssn = self._ssn9()
            pa = self._patient(
                self._id("dup"), first_display=base, last_display=last,
                dob=dob, phone=phone, email=None, street=None, ssn9=ssn,
            )
            pb = self._patient(
                self._id("dup"), first_display=nick, last_display=last,
                dob=dob, phone=phone, email=None, street=None, ssn9=ssn,
            )
            self._label(pa["id"], pb["id"], "duplicate", "nickname_swap")

        # 10x last-name transposition typo (rule 05 fuzzy last).
        for i in range(10):
            first = FIRST_NAMES[10 + i]
            last = LAST_NAMES[20 + i] if 20 + i < len(LAST_NAMES) else LAST_NAMES[i]
            last_typo = _transposition(last, rng)
            dob = _dt.date(1970 + i, (i % 12) + 1, (i % 27) + 1).isoformat()
            phone = self._phone10()
            ssn = self._ssn9()
            pa = self._patient(
                self._id("dup"), first_display=first, last_display=last,
                dob=dob, phone=phone, email=None, street=None, ssn9=ssn,
            )
            pb = self._patient(
                self._id("dup"), first_display=first, last_display=last_typo,
                dob=dob, phone=phone, email=None, street=None, ssn9=ssn,
            )
            self._label(pa["id"], pb["id"], "duplicate", "name_transposition")

        # 10x +/-1-day DOB with shared address, no SSN (rule 01/02).
        for i in range(10):
            first = FIRST_NAMES[20 + i] if 20 + i < len(FIRST_NAMES) else FIRST_NAMES[i]
            last = LAST_NAMES[i]
            dob = _dt.date(1980 + i, (i % 12) + 1, (i % 27) + 1)
            dob_b = dob + _dt.timedelta(days=rng.choice([-1, 1]))
            phone = self._phone10()
            street = f"{200 + i} {STREETS[(i + 3) % len(STREETS)]}"
            pa = self._patient(
                self._id("dup"), first_display=first, last_display=last,
                dob=dob.isoformat(), phone=phone, email=None, street=street, ssn9=None,
            )
            pb = self._patient(
                self._id("dup"), first_display=first, last_display=last,
                dob=dob_b.isoformat(), phone=phone, email=None, street=street, ssn9=None,
            )
            self._label(pa["id"], pb["id"], "duplicate", "dob_off_by_one")

        # 10x email casing/diacritics as the strong shared field (rule 03).
        for i in range(10):
            first = FIRST_NAMES[i]
            first_b = DIACRITIC_NAMES.get(first, first)
            last = LAST_NAMES[5 + i]
            dob = _dt.date(1975 + i, (i % 12) + 1, (i % 27) + 1)
            dob_b = dob + _dt.timedelta(days=rng.choice([0, 1, -1]))
            email = self._email(first.lower(), last.lower())
            email_b = None
            # variant spelling of the same mailbox
            email_b = email.replace(first.lower(), first.lower().replace("e", "é", 1) if "e" in first.lower() else first.lower(), 1)
            pa = self._patient(
                self._id("dup"), first_display=first, last_display=last,
                dob=dob.isoformat(), phone=None, email=email, street=None, ssn9=None,
            )
            pb = self._patient(
                self._id("dup"), first_display=first_b, last_display=last,
                dob=dob_b.isoformat(), phone=None, email=email_b, street=None, ssn9=None,
            )
            self._label(pa["id"], pb["id"], "duplicate", "email_case")

        # 10x phone formatting + placeholder noise (rule 11/12).
        for i in range(10):
            first = FIRST_NAMES[15 + i] if 15 + i < len(FIRST_NAMES) else FIRST_NAMES[i]
            last = LAST_NAMES[10 + i]
            dob = _dt.date(1965 + i, (i % 12) + 1, (i % 27) + 1).isoformat()
            phone = self._phone10()
            email = self._email(first.lower(), last.lower())
            pa = self._patient(
                self._id("dup"), first_display=first, last_display=last,
                dob=dob, phone=phone, email=email, street=None, ssn9=None,
            )
            pb = self._patient(
                self._id("dup"), first_display=first, last_display=last,
                dob=dob, phone=phone, email=email, street=None, ssn9=None,
                phone_placeholder=True,
            )
            self._label(pa["id"], pb["id"], "duplicate", "phone_placeholder")

    # -- negative subtypes ------------------------------------------------------
    def negative_pairs(self) -> None:
        rng = self.rng
        # 20x sibling hard negatives: same address + last name + DOB,
        # different SSN4 / first names / phones / emails.
        for i in range(20):
            last = LAST_NAMES[i]
            dob = _dt.date(1990 + (i % 10), (i % 12) + 1, (i % 27) + 1)
            street = f"{300 + i} {STREETS[i % len(STREETS)]}"
            f1, f2 = self._safe_family_first_pair()
            ssn_a, ssn_b = self._ssn9(), self._ssn9()
            phone_a, phone_b = self._phone10(), self._phone10()
            pa = self._patient(
                self._id("sib"), first_display=f1, last_display=last,
                dob=dob.isoformat(), phone=phone_a,
                email=self._email(f1.lower(), last.lower()), street=street, ssn9=ssn_a,
            )
            pb = self._patient(
                self._id("sib"), first_display=f2, last_display=last,
                dob=dob.isoformat(), phone=phone_b,
                email=self._email(f2.lower(), last.lower()), street=street, ssn9=ssn_b,
            )
            self._label(pa["id"], pb["id"], "non_duplicate", "sibling_hard")

        # 10x twin hard negatives: DOB+address+last name shared, distinct
        # first names / SSN4 / contact points.
        for i in range(10):
            last = LAST_NAMES[10 + i]
            dob = _dt.date(2000 + (i % 5), (i % 12) + 1, (i % 27) + 1)
            street = f"{400 + i} {STREETS[(i + 5) % len(STREETS)]}"
            f1, f2 = self._safe_family_first_pair()
            ssn_a, ssn_b = self._ssn9(), self._ssn9()
            pa = self._patient(
                self._id("twin"), first_display=f1, last_display=last,
                dob=dob.isoformat(), phone=self._phone10(),
                email=self._email(f1.lower(), last.lower()), street=street, ssn9=ssn_a,
            )
            pb = self._patient(
                self._id("twin"), first_display=f2, last_display=last,
                dob=dob.isoformat(), phone=self._phone10(),
                email=self._email(f2.lower(), last.lower()), street=street, ssn9=ssn_b,
            )
            self._label(pa["id"], pb["id"], "non_duplicate", "twin_hard")

        # 30x easy negatives: unrelated people, some sharing an address
        # (roommates / apartment building) with different last names.
        for i in range(30):
            first = FIRST_NAMES[(i * 3) % len(FIRST_NAMES)]
            other_first = FIRST_NAMES[(i * 7 + 5) % len(FIRST_NAMES)]
            while other_first == first:
                other_first = FIRST_NAMES[(i * 7 + 13) % len(FIRST_NAMES)]
            last = LAST_NAMES[(i * 2) % len(LAST_NAMES)]
            other_last = LAST_NAMES[(i * 3 + 7) % len(LAST_NAMES)]
            while other_last == last:
                other_last = LAST_NAMES[(i * 3 + 11) % len(LAST_NAMES)]
            dob_a = _dt.date(1950 + (i * 3) % 60, (i % 12) + 1, (i % 27) + 1)
            dob_b = _dt.date(1950 + ((i + 9) * 5) % 60, ((i + 3) % 12) + 1, ((i + 11) % 27) + 1)
            shared_street = None
            if i % 2 == 0:
                shared_street = f"{500 + i} {STREETS[(i + 7) % len(STREETS)]}"
            pa = self._patient(
                self._id("neg"), first_display=first, last_display=last,
                dob=dob_a.isoformat(), phone=self._phone10(),
                email=self._email(first.lower(), last.lower()),
                street=shared_street or f"{600 + i} {STREETS[i % len(STREETS)]}",
                ssn9=self._ssn9(),
            )
            pb = self._patient(
                self._id("neg"), first_display=other_first, last_display=other_last,
                dob=dob_b.isoformat(), phone=self._phone10(),
                email=self._email(other_first.lower(), other_last.lower()),
                street=shared_street or f"{700 + i} {STREETS[(i + 2) % len(STREETS)]}",
                ssn9=self._ssn9(),
            )
            self._label(pa["id"], pb["id"], "non_duplicate", "unrelated")

    def _safe_family_first_pair(self) -> tuple[str, str]:
        """Two first names the engine cannot fuzzy-equate (no nickname set
        overlap, DL > 1). Retries until safe; the corpus self-check re-verifies."""
        while True:
            a = self.rng.choice(FAMILY_FIRST_POOL)
            b = self.rng.choice(FAMILY_FIRST_POOL)
            if a == b:
                continue
            if not name_fuzzy_match(a.lower(), b.lower()):
                return a, b

    def build(self) -> dict:
        self.duplicate_pairs()
        self.negative_pairs()
        return {
            "description": (
                "AMUX-134 patient-matching golden corpus v1 — synthetic "
                "labeled pairs (duplicate / non-duplicate) with realistic "
                "variation. Regenerate with scripts/gen_matching_golden.py."
            ),
            "patients": self.patients,
            "pairs": self.pairs,
        }


def selfcheck(corpus: dict, out_path: Path) -> None:
    import duckdb

    from fhir4ds.matching.store import create_matching_tables, index_patient

    conn = duckdb.connect()
    create_matching_tables(conn)
    for resource in corpus["patients"]:
        index_patient(conn, resource)

    problems: list[str] = []
    for pair in corpus["pairs"]:
        a, b, label, kind = pair["a"], pair["b"], pair["label"], pair["kind"]
        rules_ab = catching_rules(conn, a, b) + catching_rules(conn, b, a)
        if label == "duplicate" and not rules_ab:
            problems.append(f"duplicate pair not catchable by any rule: {a} {b} ({kind})")
        if label == "non_duplicate" and rules_ab:
            problems.append(
                f"negative pair caught by rules {sorted(set(rules_ab))}: {a} {b} ({kind})"
            )
    if problems:
        raise SystemExit("SELF-CHECK FAILED:\n  " + "\n  ".join(problems))

    metrics = evaluate_golden(conn, corpus)
    bad_fp = [m["pair"] for m in metrics.false_positives]
    bad_fn = [m["pair"] for m in metrics.misses]
    if bad_fp:
        raise SystemExit(f"SELF-CHECK FAILED: false positives {bad_fp}")
    if bad_fn:
        raise SystemExit(f"SELF-CHECK FAILED: false negatives {bad_fn}")
    print(
        f"self-check OK: precision={metrics.precision:.4f} recall={metrics.recall:.4f} "
        f"(tp={metrics.true_positives} fp={metrics.false_positive_count} "
        f"fn={metrics.false_negative_count} ambiguous={metrics.ambiguous_pair_count})"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--no-selfcheck", action="store_true")
    args = parser.parse_args()

    builder = CorpusBuilder(args.seed)
    corpus = builder.build()
    corpus["seed"] = args.seed
    corpus["generator"] = f"scripts/gen_matching_golden.py --seed {args.seed}"

    if not args.no_selfcheck:
        selfcheck(corpus, args.out)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(corpus, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    n_dup = sum(1 for p in corpus["pairs"] if p["label"] == "duplicate")
    n_neg = len(corpus["pairs"]) - n_dup
    print(f"wrote {args.out}: {len(corpus['patients'])} patients, {n_dup} duplicate / {n_neg} negative pairs")


if __name__ == "__main__":
    main()
