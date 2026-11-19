"""CMS A-D field normalizers for patient matching (slice 1, pure Python).

Port of the deterministic normalization layer studied from
icanbwell/cms-hte-patient-matching (CMS Patient Matching Proposal v3.4.0,
Apache-2.0). No third-party dependencies: diacritic folding via unicodedata,
phones via digit extraction, dates via strict calendar validation, USPS
address standardization deferred to v2 (v1 = norm_text of the raw line).
"""

from __future__ import annotations

import datetime as _dt
import re
import unicodedata
from typing import Optional

__all__ = [
    "norm_text",
    "norm_text_keep_dots",
    "norm_phone",
    "norm_date",
    "norm_name_parts",
    "parse_suffix",
    "nickname_set",
    "extract_patient_fields",
    "suffix_conflict",
]

_PUNCT_TABLE = str.maketrans("", "", "".join(chr(c) for c in range(0x21, 0x7F) if not chr(c).isalnum()))
_WS_RE = re.compile(r"\s+")

_KEEP_DOT_AT = set(" .@-_")


def norm_text_keep_dots(value: Optional[str]) -> Optional[str]:
    """Email-style normalization: NFKD diacritic fold + lowercase, keep
    email-meaningful punctuation ( . @ - _ ), drop the rest."""
    if value is None:
        return None
    decomposed = unicodedata.normalize("NFKD", value)
    folded = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = folded.lower()
    kept = "".join(ch if (ch.isalnum() or ch in _KEEP_DOT_AT) else " " for ch in lowered)
    collapsed = _WS_RE.sub("", kept).strip()
    return collapsed or None

# ---------------------------------------------------------------------------
# A. Text normalization
# ---------------------------------------------------------------------------


def norm_text(value: Optional[str]) -> Optional[str]:
    """Lowercase, NFKD diacritic fold, strip punctuation, collapse whitespace.

    Returns None for empty/None input.
    """
    if value is None:
        return None
    decomposed = unicodedata.normalize("NFKD", value)
    folded = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = folded.lower()
    stripped = lowered.translate(_PUNCT_TABLE)
    collapsed = _WS_RE.sub(" ", stripped).strip()
    return collapsed or None


# ---------------------------------------------------------------------------
# B. Phone normalization (E.164 digits, placeholder removal)
# ---------------------------------------------------------------------------

_PHONE_PLACEHOLDERS = {"5555555555", "0000000000"}


def norm_phone(value: Optional[str]) -> Optional[str]:
    """Normalize to 10 dialable digits ( NANP centric).

    - strips all non-digits
    - strips a leading country code 1 from 11-digit numbers
    - rejects (returns None) anything that is not exactly 10 digits afterwards
    - rejects placeholders: all-same-digit, 555-555-5555, 0000000000
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return None  # pathological-resource guard: non-string values reject
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return None
    if len(set(digits)) == 1:
        return None
    if digits in _PHONE_PLACEHOLDERS:
        return None
    return digits


# ---------------------------------------------------------------------------
# C. Date normalization (strict YYYY-MM-DD, v1 = full DOB only)
# ---------------------------------------------------------------------------

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_AGE_DAYS = 120 * 366


def norm_date(value: Optional[str], as_of: Optional[_dt.date] = None) -> Optional[str]:
    """Strict YYYY-MM-DD only. Rejects future dates and ages > 120 years.

    ``as_of`` overrides the wall-clock reference date (default
    ``date.today()``). DETERMINISM CARVE-OUT: indexed content depends on the
    evaluation date ONLY through the future-date and >120-year rejections —
    a fixed ``as_of`` makes the normalization fully deterministic; absent
    it, a date near "today" can flip as the calendar advances.
    """
    if value is None or not isinstance(value, str) or not _DATE_RE.match(value):
        return None
    try:
        d = _dt.date.fromisoformat(value)
    except ValueError:
        return None
    today = as_of if as_of is not None else _dt.date.today()
    if d > today:
        return None
    if (today - d).days > _MAX_AGE_DAYS:
        return None
    return value


# ---------------------------------------------------------------------------
# D. Name parts / suffixes / placeholders
# ---------------------------------------------------------------------------

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}

_PLACEHOLDER_NAMES = {
    "test patient",
    "testpatient",
    "baby boy",
    "babyboy",
    "baby girl",
    "babygirl",
    "john doe",
    "johndoe",
    "jane doe",
    "janedoe",
}


def parse_suffix(token: str) -> Optional[str]:
    """Return the canonical suffix for a token (jr/sr/ii/iii/iv/v) else None."""
    t = norm_text(token)
    if t is None:
        return None
    t = t.replace(".", "")
    if t in _SUFFIXES:
        return t
    return None


def norm_name_parts(value: Optional[str]) -> Optional[tuple[list[str], list[str]]]:
    """Split a display-name string into (given/family parts, suffixes).

    Placeholder names (test patient, baby boy/girl, john/jane doe) return None.
    Parts are norm_text-normalized; suffix tokens are stripped from the parts.
    """
    normalized = norm_text(value)
    if normalized is None:
        return None
    if normalized in _PLACEHOLDER_NAMES:
        return None
    tokens = normalized.split()
    parts: list[str] = []
    suffixes: list[str] = []
    for tok in tokens:
        tok_clean = tok.replace(".", "")
        suffix = parse_suffix(tok_clean)
        if suffix is not None:
            suffixes.append(suffix)
        else:
            parts.append(tok_clean)
    if not parts and not suffixes:
        return None
    return parts, suffixes


# ---------------------------------------------------------------------------
# Nickname equivalence expansion (~210 standard English nickname families)
#
# Built from the canonical healthcare name-matching diminutive lists (the
# ICU-style nickname dictionaries used by patient-matching tooling: SSA
# top given names cross-referenced with standard diminutive conventions).
# Selection rule: a set is included ONLY when every member is a
# well-established bidirectional diminutive/variant of the formal name —
# when unsure, EXCLUDE (precision over recall). Sets deliberately OVERLAP
# on shared diminutives ("chris" ∈ {christopher} and {christine,
# christina}; "ted" ∈ {edward} and {theodore}); the index below unions all
# groups containing a name, so equivalence is symmetric (chris↔christine
# matches from either side) while unrelated formal names in different
# groups never become equivalent through a shared diminutive
# (christopher↔christine does NOT match).
# Non-English nickname conventions (Jose→Pepe etc.) are deliberately
# absent — only universally standard English families are safe.
# ---------------------------------------------------------------------------

_NICKNAME_GROUPS: list[frozenset[str]] = [
    frozenset(g)
    for g in [
        # ---- male -------------------------------------------------------
        {"alan", "al"},
        {"albert", "al", "bert", "albie", "bertie"},
        {"alfred", "al", "alfie"},
        {"allan", "allen", "al"},
        {"andrew", "andy", "drew"},
        {"anthony", "tony"},
        {"arthur", "art", "artie"},
        {"bartholomew", "bart"},
        {"benedict", "ben", "benny"},
        {"benjamin", "ben", "benny", "benji"},
        {"bernard", "bern", "bernie"},
        {"bradley", "brad"},
        {"calvin", "cal"},
        {"cameron", "cam"},
        {"charles", "charlie", "chuck", "chas", "chip"},
        {"chester", "chet"},
        {"christopher", "chris", "kit"},
        {"clifford", "cliff"},
        {"daniel", "dan", "danny"},
        {"david", "dave", "davey"},
        {"dennis", "denny", "den"},
        {"dominic", "dom"},
        {"donald", "don", "donnie"},
        {"douglas", "doug"},
        {"edgar", "ed", "eddie"},
        {"edmund", "ed", "eddie"},
        {"edward", "ed", "eddie", "ted", "teddy", "ned"},
        {"edwin", "ed", "eddie"},
        {"ernest", "ernie"},
        {"eugene", "gene"},
        {"ezekiel", "zeke"},
        {"frederick", "fred", "freddy", "freddie"},
        {"francis", "frank", "frankie"},
        {"gabriel", "gabe", "gabby"},
        {"geoffrey", "geoff"},
        {"george", "georgie"},
        {"gerald", "jerry"},
        {"gilbert", "gil", "bert"},
        {"gordon", "gordy"},
        {"gregory", "greg", "gregg"},
        {"harold", "hal"},
        {"henry", "hank", "harry", "hal"},
        {"herbert", "herb", "bert", "bertie"},
        {"howard", "howie"},
        {"jacob", "jake"},
        {"james", "jim", "jimmy", "jimmie", "jamie"},
        {"jeffrey", "jeff"},
        {"jeremiah", "jerry"},
        {"jeremy", "jerry"},
        {"john", "jack", "johnny", "jon", "jonny"},
        {"jonathan", "jon", "jonny", "jono"},
        {"joseph", "joe", "joey"},
        {"joshua", "josh"},
        {"julian", "jules"},
        {"kenneth", "ken", "kenny"},
        {"lawrence", "larry"},
        {"leonard", "len", "lenny"},
        {"louis", "lou", "louie"},
        {"lucas", "luke", "luca"},
        {"marcus", "mark", "marc"},
        {"mark", "marc"},
        {"martin", "marty"},
        {"matthew", "matt", "matty"},
        {"maxwell", "max"},
        {"michael", "mike", "mikey", "mick", "mickey"},
        {"mitchell", "mitch"},
        {"nathaniel", "nate", "nat"},
        {"nathan", "nate", "nat"},
        {"nicholas", "nick", "nicky"},
        {"norman", "norm"},
        {"oliver", "ollie"},
        {"patrick", "pat", "paddy"},
        {"peter", "pete", "petey"},
        {"philip", "phillip", "phil"},
        {"randall", "randy"},
        {"raymond", "ray"},
        {"reginald", "reggie", "reg"},
        {"richard", "rick", "ricky", "dick", "richie", "rich"},
        {"robert", "rob", "bob", "bobby", "bobbie", "robby"},
        {"rodney", "rod"},
        {"ronald", "ron", "ronnie"},
        {"rudolph", "rudy"},
        {"russell", "russ", "rusty"},
        {"samuel", "sam", "sammy"},
        {"scott", "scot", "scotty"},
        {"stanley", "stan"},
        {"stephen", "steve", "stevie"},
        {"steven", "steve", "stevie"},
        {"stuart", "stu"},
        {"terrence", "terry"},
        {"theodore", "theo", "ted", "teddy"},
        {"thomas", "tom", "tommy"},
        {"timothy", "tim", "timmy"},
        {"tobias", "toby"},
        {"tyler", "ty"},
        {"vernon", "vern"},
        {"victor", "vic"},
        {"vincent", "vince", "vinny", "vin"},
        {"wallace", "wally"},
        {"walter", "walt"},
        {"wesley", "wes"},
        {"william", "bill", "will", "billy", "willie", "billie", "liam"},
        {"zachary", "zach", "zack", "zac"},
        # ---- female -----------------------------------------------------
        {"abigail", "abby", "abbey", "gail"},
        {"agnes", "aggie"},
        {"alexandra", "alex", "allie", "lexie"},
        {"allison", "alison", "allie", "ally"},
        {"amanda", "mandy"},
        {"amelia", "millie", "milly"},
        {"andrea", "andie"},
        {"angela", "angie"},
        {"anna", "ann", "anne", "annie", "nancy"},
        {"antoinette", "toni"},
        {"ashley", "ash"},
        {"barbara", "barb", "babs", "barbie"},
        {"beatrice", "bea", "trixie"},
        {"beverly", "bev"},
        {"brittany", "britt", "brit"},
        {"candace", "candy", "candi"},
        {"carolyn", "carol", "carrie"},
        {"caroline", "carol", "carrie", "callie"},
        {"catherine", "cathy", "cat", "kate", "katie"},
        {"katherine", "kathy", "kate", "katie", "kat", "kitty"},
        {"kathleen", "kathy", "kate", "katie"},
        {"kathryn", "kate", "katie", "kathy", "kat"},
        {"cecilia", "cece"},
        {"charlotte", "lottie", "charlie"},
        {"cheryl", "sherry"},
        {"christina", "chris", "chrissy", "tina", "christy"},
        {"christine", "chris", "chrissy", "tina"},
        {"constance", "connie"},
        {"cynthia", "cindy", "cyn"},
        {"danielle", "dani"},
        {"deborah", "deb", "debbie", "debby"},
        {"diana", "diane"},
        {"dorothy", "dot", "dottie", "dotty"},
        {"edith", "edie"},
        {"eleanor", "ellie", "nora", "nell"},
        {"elizabeth", "liz", "lizzie", "beth", "betsy", "betty", "eliza", "lisa", "libby"},
        {"ellen", "nell"},
        {"emily", "em", "emmy"},
        {"esther", "essie"},
        {"evelyn", "evie", "ev"},
        {"florence", "flo", "flossie"},
        {"frances", "fran", "frannie"},
        {"geraldine", "geri", "gerry"},
        {"grace", "gracie"},
        {"gwendolyn", "gwen"},
        {"harriet", "hattie"},
        {"helen", "nell"},
        {"henrietta", "etta", "hettie"},
        {"isabella", "bella", "isa", "belle"},
        {"jacqueline", "jackie", "jacqui"},
        {"jane", "janie"},
        {"janet", "jan", "janie"},
        {"janice", "jan"},
        {"jennifer", "jen", "jenny"},
        {"jessica", "jess", "jessie"},
        {"joan", "jo", "joanie"},
        {"joanna", "jo", "joanie"},
        {"joanne", "jo", "joanie"},
        {"josephine", "jo", "josie"},
        {"judith", "judy", "judie", "jude"},
        {"julia", "julie"},
        {"kimberly", "kim", "kimmy"},
        {"kristen", "kris", "kristy"},
        {"laura", "laurie"},
        {"lillian", "lily", "lillie", "lil"},
        {"linda", "lin", "lindy"},
        {"louise", "lou"},
        {"lucille", "lucy"},
        {"mackenzie", "kenzie"},
        {"madeline", "maddie", "maddy"},
        {"madison", "maddie"},
        {"margaret", "maggie", "meg", "peg", "peggy", "marge", "margie", "madge"},
        {"marguerite", "maggie", "peggy", "margie"},
        {"marjorie", "marge", "margie"},
        {"martha", "marty", "mattie", "patsy"},
        {"mary", "marie", "molly", "mamie", "polly"},
        {"megan", "meg"},
        {"melissa", "missy", "mel", "lissa"},
        {"michelle", "shelly"},
        {"mildred", "millie"},
        {"millicent", "millie"},
        {"miriam", "mimi"},
        {"natalie", "nat"},
        {"natasha", "nat", "tasha"},
        {"nancy", "nan"},
        {"olivia", "liv", "livvy"},
        {"pamela", "pam"},
        {"patricia", "pat", "patty", "patsy", "trish", "tricia"},
        {"pauline", "polly"},
        {"penelope", "penny"},
        {"philippa", "pippa"},
        {"regina", "gina"},
        {"rebecca", "becky", "becks"},
        {"roberta", "bobbie"},
        {"rosemary", "rose", "rosie"},
        {"rose", "rosie"},
        {"roxanne", "roxy", "roxie"},
        {"ruth", "ruthie"},
        {"samantha", "sam", "sammy"},
        {"sandra", "sandy"},
        {"sarah", "sally", "sadie"},
        {"sharon", "shari"},
        {"stephanie", "steph"},
        {"susan", "sue", "susie", "suzie", "suzy"},
        {"suzanne", "sue", "suzy", "suzie"},
        {"sydney", "syd"},
        {"sylvia", "sylvie"},
        {"tamara", "tammy"},
        {"teresa", "terry", "terri", "teri", "tess", "tessa"},
        {"theresa", "terry", "terri", "teri", "tess", "tessa"},
        {"tiffany", "tiff"},
        {"valerie", "val"},
        {"veronica", "ronnie", "roni"},
        {"victoria", "vicky", "vicki", "tori"},
        {"virginia", "ginny"},
        {"vivian", "viv"},
        {"winifred", "winnie"},
    ]
]

# Index: name -> UNION of every group containing it. Names living in a
# single group keep that exact frozenset object (identity-stable for the
# common case); shared diminutives get the merged union so equivalence is
# symmetric without making sibling formal names equivalent.
_groups_by_name: dict[str, list[frozenset[str]]] = {}
for _group in _NICKNAME_GROUPS:
    for _name in _group:
        _groups_by_name.setdefault(_name, []).append(_group)

_NICKNAME_INDEX: dict[str, frozenset[str]] = {}
for _name, _groups in _groups_by_name.items():
    if len(_groups) == 1:
        _NICKNAME_INDEX[_name] = _groups[0]
    else:
        _merged: set[str] = set()
        for _g in _groups:
            _merged |= _g
        _NICKNAME_INDEX[_name] = frozenset(_merged)


def nickname_set(name: Optional[str]) -> frozenset[str]:
    """Equivalence-expanded set for a normalized given name (contains the
    name itself when known; a singleton of the name otherwise).

    For a shared diminutive living in several families ("chris" is a
    diminutive of both Christopher and Christine/Christina) the union of
    all families is returned, so equivalence is symmetric while the
    distinct formal names (Christopher vs Christine) remain inequivalent.
    """
    n = norm_text(name)
    if n is None:
        return frozenset()
    return _NICKNAME_INDEX.get(n, frozenset({n}))


# ---------------------------------------------------------------------------
# Field extraction from a FHIR R4 Patient resource
# ---------------------------------------------------------------------------

_SSN_SYSTEMS = ("us-ssn", "2.16.840.1.113883.4.1")
_ITIN_SYSTEMS = ("itin", "2.16.840.1.113883.4.23")


def _dedup(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if v is not None and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _norm_ident(value: str) -> Optional[str]:
    """Identifier value normalization: norm_text without whitespace."""
    n = norm_text(value)
    if n is None:
        return None
    return n.replace(" ", "") or None


def extract_patient_fields(patient_resource: dict) -> dict[str, list[str]]:
    """Extract the CMS match-field vocabulary from a Patient resource.

    Returns a dict of field_name -> list of normalized values (deduped,
    order-preserving). Fields with no data are absent from the dict.

    Field list: first, last, dob, street_line, phone, email, ssn4, itin4,
    mbi, legal_id, member_id, subscriber_id, namespace_id, suffix (internal,
    consumed by the suffix-conflict negation, never referenced by a rule).
    """
    if not isinstance(patient_resource, dict):
        raise TypeError(
            f"patient_resource must be a dict (a FHIR Patient resource), "
            f"got {type(patient_resource).__name__}"
        )
    out: dict[str, list[str]] = {}

    def add(field: str, value: Optional[str]) -> None:
        if value is None:
            return
        out.setdefault(field, []).append(value)

    # Names: prefer use=official, fall back to all names. Multiple values per
    # field are legal (multiple given tokens, multiple historical names).
    names = patient_resource.get("name") or []
    official = [n for n in names if isinstance(n, dict) and n.get("use") == "official"] or [
        n for n in names if isinstance(n, dict)
    ]
    for name in official:
        family = name.get("family")
        given = name.get("given") or []
        if isinstance(given, str):
            given = [given]
        # Pathological-resource guard: non-string given entries (e.g. a bare
        # number) are skipped, not crashed on.
        given = [g for g in given if isinstance(g, str)]
        # Name-level placeholder detection (john doe / test patient etc.)
        full_name = " ".join([given[0] if given else "", family if isinstance(family, str) else ""])
        if norm_text(full_name) in _PLACEHOLDER_NAMES:
            continue
        if isinstance(family, str):
            parsed = norm_name_parts(family)
            if parsed is not None:
                if parsed[0]:
                    add("last", " ".join(parsed[0]))
                for suf in parsed[1]:
                    add("suffix", suf)
        for g in given:
            parsed = norm_name_parts(g)
            if parsed is not None:
                if parsed[0]:
                    add("first", " ".join(parsed[0]))
                for suf in parsed[1]:
                    add("suffix", suf)

    add("dob", norm_date(patient_resource.get("birthDate")))

    for address in patient_resource.get("address") or []:
        if not isinstance(address, dict):
            continue  # pathological-resource guard: non-dict entries skipped
        lines = address.get("line") or []
        if isinstance(lines, str):
            lines = [lines]
        # Pathological-resource guard: non-string line entries are skipped.
        lines = [ln for ln in lines if isinstance(ln, str)]
        if lines:
            # v1: norm_text of the raw first line (USPS standardization v2).
            add("street_line", norm_text(lines[0]))

    for telecom in patient_resource.get("telecom") or []:
        if not isinstance(telecom, dict):
            continue  # pathological-resource guard: non-dict entries skipped
        system = telecom.get("system")
        value = telecom.get("value")
        if system == "phone":
            add("phone", norm_phone(value))
        elif system == "email":
            # emails keep their @ and . — diacritic-fold + lowercase only
            if isinstance(value, str) and value.strip():
                add("email", norm_text_keep_dots(value))

    for ident in patient_resource.get("identifier") or []:
        if not isinstance(ident, dict):
            continue  # pathological-resource guard: non-dict entries skipped
        system = ident.get("system") or ""
        if not isinstance(system, str):
            system = ""  # non-string system: no namespace heuristic applies
        system_l = system.lower()
        value = ident.get("value")
        if not isinstance(value, str) or not value.strip():
            continue
        if any(k in system_l for k in _SSN_SYSTEMS):
            digits = re.sub(r"\D", "", value)
            if len(digits) >= 4:
                add("ssn4", digits[-4:])
            continue
        if any(k in system_l for k in _ITIN_SYSTEMS):
            digits = re.sub(r"\D", "", value)
            if len(digits) >= 4:
                add("itin4", digits[-4:])
            continue
        if "mbi" in system_l:
            add("mbi", _norm_ident(value))
            continue
        if "member" in system_l:
            add("member_id", _norm_ident(value))
            continue
        if "subscriber" in system_l:
            add("subscriber_id", _norm_ident(value))
            continue
        if "legal" in system_l:
            add("legal_id", _norm_ident(value))
            continue
        # Unclassified but system-scoped identifiers become namespace-id
        # pairs (system + value) — the rule-22 "Namespace-ID alone" surface.
        if system:
            ns_value = _norm_ident(value)
            if ns_value is not None:
                add("namespace_id", f"{system_l}::{ns_value}")

    return {k: _dedup(v) for k, v in out.items() if _dedup(v)}


def suffix_conflict(a_suffixes: list[str], b_suffixes: list[str]) -> bool:
    """True when both suffix sets are non-empty AND disjoint (e.g. Jr vs Sr)."""
    if not a_suffixes or not b_suffixes:
        return False
    return not (set(a_suffixes) & set(b_suffixes))
