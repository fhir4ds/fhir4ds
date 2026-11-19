"""Expanded nickname table tests (AMUX-134).

Covers the ~220-set English nickname table added in normalizers.py and the
guarded prefix/initial abbreviation rule in fuzzy.name_fuzzy_match:
representative pairs from every major family, symmetric equivalence for
shared diminutives, no accidental cross-family equivalence, and structural
invariants over the whole table.
"""

from __future__ import annotations

from fhir4ds.matching.fuzzy import name_fuzzy_match
from fhir4ds.matching.normalizers import _NICKNAME_GROUPS, nickname_set

# ---------------------------------------------------------------------------
# Representative pairs (each side must match the other)
# ---------------------------------------------------------------------------

_REPRESENTATIVE_PAIRS = [
    # male classics
    ("katherine", "kathy"), ("katherine", "kitty"), ("katherine", "kat"),
    ("elizabeth", "betty"), ("elizabeth", "lisa"), ("elizabeth", "libby"),
    ("margaret", "peg"), ("margaret", "peggy"), ("margaret", "madge"),
    ("william", "bill"), ("william", "liam"), ("william", "willie"),
    ("robert", "bobby"), ("robert", "bobbie"),
    ("richard", "dick"), ("richard", "richie"), ("richard", "ricky"),
    ("james", "jimmie"), ("john", "jonny"), ("joseph", "joey"),
    ("charles", "chuck"), ("thomas", "tommy"), ("michael", "mickey"),
    ("daniel", "danny"), ("edward", "ned"), ("theodore", "theo"),
    ("frederick", "freddy"), ("ronald", "ronnie"), ("donald", "donnie"),
    ("jonathan", "jono"), ("ezekiel", "zeke"), ("rudolph", "rudy"),
    ("zachary", "zack"), ("gabriel", "gabe"), ("stephen", "steve"),
    ("stuart", "stu"), ("victor", "vic"), ("wallace", "wally"),
    # female classics
    ("patricia", "patsy"), ("patricia", "tricia"),
    ("jennifer", "jenny"), ("deborah", "debby"), ("barbara", "babs"),
    ("susan", "suzie"), ("suzanne", "suzy"), ("nancy", "nan"),
    ("linda", "lindy"), ("dorothy", "dottie"), ("virginia", "ginny"),
    ("frances", "frannie"), ("rebecca", "becks"), ("sandra", "sandy"),
    ("stephanie", "steph"), ("michelle", "shelly"), ("kimberly", "kimmy"),
    ("angela", "angie"), ("melissa", "missy"), ("laura", "laurie"),
    ("sarah", "sally"), ("sarah", "sadie"), ("mary", "mamie"),
    ("mary", "polly"), ("mary", "molly"), ("martha", "mattie"),
    ("catherine", "cathy"), ("kathleen", "kathy"), ("kathryn", "kat"),
    ("beatrice", "trixie"), ("jacqueline", "jackie"), ("penelope", "penny"),
    ("theresa", "tessa"), ("tamara", "tammy"), ("veronica", "ronnie"),
    ("victoria", "vicki"), ("winifred", "winnie"), ("eleanor", "nell"),
    ("isabella", "belle"), ("roberta", "bobbie"), ("geraldine", "geri"),
    ("regina", "gina"), ("cynthia", "cindy"), ("constance", "connie"),
    ("abigail", "gail"), ("madeline", "maddy"), ("louise", "lou"),
    ("robert", "bob"), ("lillian", "lily"), ("emily", "emmy"),
]

# Pairs that must NOT match: distinct names sharing a diminutive root, or
# deliberately excluded look-alikes. (Note: truncation-shaped distinct
# names like nathan/nathaniel or jose/joseph DO match under the guarded
# prefix rule by design — that is truncation semantics, not the table.)
_MUST_NOT_MATCH = [
    ("christopher", "christine"),  # share "chris" but are distinct names
    ("theodore", "edward"),  # share "ted"
    ("micah", "michael"),  # Micah is a separate biblical name
    ("megan", "margaret"),  # share "meg" but are distinct formal names
    ("suzanne", "susan"),  # share sue/suzy but distinct names
    ("pepe", "jose"),  # explicitly excluded non-English convention
    ("leo", "leonard"),  # Leo deliberately excluded (3-char prefix, standalone)
    ("wendy", "gwendolyn"),  # wendy deliberately excluded
    ("sasha", "alexandra"),  # sasha deliberately excluded
    ("maya", "mary"),  # not a standard diminutive
    ("marcus", "martin"),  # no cross-family leak through marc/marty
    ("bob", "roberto"),  # legacy pin from slice 2 (robert/roberto is DL<=1)
]


class TestRepresentativePairs:
    def test_representative_pairs_match_both_directions(self):
        for a, b in _REPRESENTATIVE_PAIRS:
            assert name_fuzzy_match(a, b), f"{a} should match {b}"
            assert name_fuzzy_match(b, a), f"{b} should match {a} (symmetry)"

    def test_must_not_match_pairs(self):
        for a, b in _MUST_NOT_MATCH:
            assert not name_fuzzy_match(a, b), f"{a} must NOT match {b}"


class TestSharedDiminutiveSemantics:
    """Cross-family sharing is allowed by design: a diminutive belongs to
    every family that owns it, but two formal names sharing a diminutive
    never become equivalent to each other."""

    def test_chris_is_symmetric_into_each_family(self):
        assert name_fuzzy_match("chris", "christopher")
        assert name_fuzzy_match("chris", "christine")
        assert name_fuzzy_match("chris", "christina")
        assert name_fuzzy_match("christine", "chris")  # reverse direction
        assert name_fuzzy_match("tina", "christine")

    def test_shared_diminutive_never_equates_formal_names(self):
        # ted: edward + theodore; meg: margaret + megan; jo: josephine + joan
        assert not name_fuzzy_match("edward", "theodore")
        assert not name_fuzzy_match("margaret", "megan")
        assert not name_fuzzy_match("josephine", "joan")
        # sue: susan + suzanne
        assert not name_fuzzy_match("susan", "suzanne")

    def test_nickname_set_union_for_shared_diminutives(self):
        s = nickname_set("chris")
        assert {"christopher", "christine", "christina", "tina"} <= s
        # single-family names keep exactly their family
        assert nickname_set("robert") == frozenset(
            {"robert", "rob", "bob", "bobby", "bobbie", "robby"}
        )

    def test_identity_preserved_within_single_family(self):
        # implementation detail pinned by slice-1 tests: names living in one
        # group share the same frozenset object
        assert nickname_set("Robert") is nickname_set("Bob")


class TestTableStructure:
    def test_table_size(self):
        # AMUX-134 target: 150-250 sets
        assert 150 <= len(_NICKNAME_GROUPS) <= 250

    def test_every_group_has_formal_name_and_diminutive(self):
        for group in _NICKNAME_GROUPS:
            assert len(group) >= 2, f"group too small: {group}"
            for name in group:
                assert name == name.lower() and name.isalpha(), (
                    f"non-normalized entry {name!r} in {group}"
                )

    def test_full_table_symmetry(self):
        # every within-group pair matches in BOTH directions via nickname_set
        for group in _NICKNAME_GROUPS:
            for a in group:
                for b in group:
                    assert b in nickname_set(a), (
                        f"asymmetric: {b} not in nickname_set({a}) ({group})"
                    )

    def test_every_member_is_indexed(self):
        for group in _NICKNAME_GROUPS:
            for name in group:
                assert name in nickname_set(name)
