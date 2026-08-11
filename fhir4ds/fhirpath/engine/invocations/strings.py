import base64
import functools
import html
import json
import re
from ...engine import util as util
from ...engine.errors import FHIRPathError

# Maximum allowed length for user-supplied regex patterns.
# Prevents excessive compilation time and mitigates ReDoS risk.
_MAX_REGEX_LENGTH = 1000

# Patterns that indicate potential catastrophic backtracking in Python's
# NFA-based re engine.  These detect nested quantifiers and overlapping
# alternations — the two main classes of ReDoS triggers.
_REDOS_PATTERNS = re.compile(
    r"(\((?:[^()]*[+*])[^()]*\)[+*])"   # nested quantifier: (a+)+
    r"|(\([^()]*\|[^()]*\)[+*])"        # quantified alternation: (a|a)+
)


def _validate_regex(pattern: str) -> None:
    """Raise FHIRPathError if a regex pattern exceeds safe limits or
    contains structures known to cause catastrophic backtracking."""
    if len(pattern) > _MAX_REGEX_LENGTH:
        raise FHIRPathError(
            f"Regex pattern too long ({len(pattern)} chars, max {_MAX_REGEX_LENGTH}). "
            "This limit exists to prevent ReDoS attacks."
        )
    if _REDOS_PATTERNS.search(pattern):
        raise FHIRPathError(
            "Regex pattern contains nested quantifiers or quantified alternations "
            "that may cause catastrophic backtracking. Simplify the pattern."
        )


def _regex_flags(flags: str | None = "") -> int:
    """Convert FHIRPath regex flags to Python re flags."""
    if flags is None:
        flags = ""
    if not isinstance(flags, str):
        raise FHIRPathError("Regex flags must be a string")
    invalid = sorted({ch for ch in flags if ch not in {"i", "m"}})
    if invalid:
        raise FHIRPathError(f"Invalid regex flags: {''.join(invalid)}")
    compiled_flags = re.DOTALL
    if "i" in flags:
        compiled_flags |= re.IGNORECASE
    if "m" in flags:
        compiled_flags |= re.MULTILINE
    return compiled_flags


@functools.lru_cache(maxsize=256)
def _compile_regex(pattern: str, flags: int = 0) -> re.Pattern:
    """Cache compiled regex patterns to avoid recompilation."""
    _validate_regex(pattern)
    try:
        return re.compile(pattern, flags)
    except re.error as exc:
        raise FHIRPathError(f"Invalid regular expression: {exc}") from exc


def matchesFull(ctx, coll, regex):
    """
    Full regex matching with capture group support.

    Returns True if the entire string matches the regex pattern.
    Uses re.fullmatch for complete string matching.

    This is similar to matches() but ensures the entire string matches
    the pattern, not just a portion of it.

    Examples:
    - 'hello'.matchesFull('hel.*') -> true
    - 'hello'.matchesFull('hel') -> false (doesn't match entire string)
    - '123-456'.matchesFull('\\d{3}-\\d{3}') -> true
    """
    if not coll:
        return []

    # Empty regex matches empty string
    if regex == "" or regex is None:
        string = ensure_string_singleton(coll)
        return string == ""

    string = ensure_string_singleton(coll)

    try:
        # Use fullmatch to match the entire string
        valid = _compile_regex(regex, re.DOTALL)
        return re.fullmatch(valid, string) is not None
    except re.error:
        raise FHIRPathError(f"Invalid regular expression: {regex}")


def ensure_string_singleton(x):
    if len(x) == 1:
        d = util.get_data(x[0])
        if type(d) == str:
            return d
        raise FHIRPathError("Expected string, but got " + str(d))

    raise FHIRPathError("Expected string, but got " + str(x))


def index_of(ctx, coll, substr):
    if util.is_empty(substr):
        return []
    string = ensure_string_singleton(coll)
    return string.find(substr)


def substring(ctx, coll, start, length=None):
    string = ensure_string_singleton(coll)

    if isinstance(start, list) or start is None:
        return []

    start = int(start)
    if start < 0:
        # FHIRPath §5.6.2: "If start lies outside the length of the string,
        # the function returns an empty collection."
        return []
    if start >= len(string):
        return []

    if length is None or length == []:
        return string[start:]

    length = int(length)
    if length <= 0:
        return ""

    return string[start : start + length]


def starts_with(ctx, coll, prefix):
    if util.is_empty(prefix):
        return []
    string = ensure_string_singleton(coll)
    if not isinstance(prefix, str):
        return False
    return string.startswith(prefix)


def ends_with(ctx, coll, postfix):
    if util.is_empty(postfix):
        return []
    string = ensure_string_singleton(coll)
    if not isinstance(postfix, str):
        return False
    return string.endswith(postfix)


def contains_fn(ctx, coll, substr):
    if util.is_empty(substr):
        return []
    string = ensure_string_singleton(coll)
    return substr in string


def upper(ctx, coll):
    string = ensure_string_singleton(coll)
    return string.upper()


def lower(ctx, coll):
    string = ensure_string_singleton(coll)
    return string.lower()


def split(ctx, coll, delimiter):
    if util.is_empty(delimiter):
        return []
    string = ensure_string_singleton(coll)
    if delimiter == '':
        return list(string)
    return string.split(delimiter)


def trim(ctx, coll):
    string = ensure_string_singleton(coll)
    return string.strip()


def encode(ctx, coll, format):
    if not coll:
        return []

    str_to_encode = util.get_data(coll[0]) if isinstance(coll, list) else coll
    if not str_to_encode or not isinstance(str_to_encode, str):
        return []

    if format in ["urlbase64", "base64url"]:
        encoded = base64.b64encode(str_to_encode.encode()).decode()
        return encoded.replace("+", "-").replace("/", "_")

    if format == "base64":
        return base64.b64encode(str_to_encode.encode()).decode()

    if format == "hex":
        return "".join([hex(ord(c))[2:].zfill(2) for c in str_to_encode])

    return []


def decode(ctx, coll, format):
    if not coll:
        return []

    str_to_decode = util.get_data(coll[0]) if isinstance(coll, list) else coll
    if not str_to_decode or not isinstance(str_to_decode, str):
        return []

    try:
        if format in ["urlbase64", "base64url"]:
            decoded = str_to_decode.replace("-", "+").replace("_", "/")
            return base64.b64decode(decoded, validate=True).decode()

        if format == "base64":
            return base64.b64decode(str_to_decode, validate=True).decode()
    except (ValueError, UnicodeDecodeError):
        return []

    if format == "hex":
        if len(str_to_decode) % 2 != 0:
            raise ValueError("Decode 'hex' requires an even number of characters.")
        return "".join(
            [chr(int(str_to_decode[i : i + 2], 16)) for i in range(0, len(str_to_decode), 2)]
        )

    return []


def join(ctx, coll, separator=""):
    stringValues = []
    for n in coll:
        d = util.get_data(n)
        if isinstance(d, str):
            stringValues.append(d)
        else:
            raise TypeError("Join requires a collection of strings.")

    return separator.join(stringValues)


def matches(ctx, coll, regex, flags=""):
    """FHIRPath matches() uses regex search semantics."""
    if not coll or util.is_empty(regex) or regex is None:
        return []

    string = ensure_string_singleton(coll)
    valid = _compile_regex(regex, _regex_flags(flags))
    return valid.search(string) is not None


def replace(ctx, coll, regex, repl):
    string = ensure_string_singleton(coll)
    # Handle empty collection as regex argument
    if util.is_empty(regex):
        return []
    # Handle empty collection as replacement argument
    if util.is_empty(repl):
        return []
    if regex == "" and isinstance(repl, str):
        if string == "":
            return repl
        return repl + repl.join(character for character in string) + repl
    return string.replace(regex, repl)


def replace_matches(ctx, coll, regex, repl, flags=""):
    string = ensure_string_singleton(coll)
    if isinstance(regex, list) or isinstance(repl, list) or isinstance(flags, list):
        return []
    _regex_flags(flags)

    # Empty regex should return the original string unchanged
    if regex == "":
        return string

    # Translate (?<name>...) → (?P<name>...) so Python can parse the spec's
    # canonical named-group syntax (FHIRPath §5.6.10 example). Only translates
    # when the char after (?< is an identifier start (skips (?<= and (?<!
    # lookbehind syntax). Falls through to compile error if syntax is invalid.
    regex_translated = re.sub(
        r"\(\?<([A-Za-z_][A-Za-z0-9_]*)>",
        r"(?P<\1>",
        regex,
    )

    try:
        valid = _compile_regex(regex_translated, _regex_flags(flags))
    except (re.error, FHIRPathError):
        # Return empty collection on regex compile errors to match the
        # native C++ extension's graceful-degradation behavior.
        return []

    # Translate FHIRPath/PCRE substitution syntax to Python re.sub syntax,
    # but ONLY for group references that actually exist in the compiled
    # pattern. This matches the native C++ behavior:
    #   - ${name} for existing named group → substitution
    #   - ${name} for unknown name → literal ${name}
    #   - $N for existing numbered group → substitution
    #   - $N for nonexistent number → empty substitution (group missing)
    #   - $$ → literal $
    #   - $<other> → literal $<other>
    # See FHIRPath §5.6.10. Per spec note, PCRE is the recommended dialect.
    group_index = valid.groupindex  # mapping of name → group number
    num_groups = valid.groups  # count of numbered groups

    def translate_repl(match):
        # match.group(1) is the digits for $N, group(2) is the {name} or {N}
        # for ${...}, group(3) is the literal $$.
        if match.group(3) is not None:  # $$
            return "$"
        if match.group(2) is not None:  # ${...}
            ref = match.group(2)
            # ${N} (numeric in braces) → native treats as literal ${N}, so we
            # do NOT translate it. Only ${name} for an existing named group
            # is translated to \g<name>.
            if not ref.isdigit() and ref in group_index:
                return f"\\g<{ref}>"
            # Unknown name or numeric in braces: literal passthrough
            return match.group(0)
        if match.group(1) is not None:  # $N (no braces)
            n = int(match.group(1))
            if 0 <= n <= num_groups:
                return f"\\g<{n}>"
            # Out of range: native substitutes empty for missing group
            return ""
        return match.group(0)

    repl_translated = re.sub(
        r"\$(\d+)|\$\{(\w+)\}|(\$\$)",
        translate_repl,
        repl,
    )

    try:
        return re.sub(valid, repl_translated, string)
    except (re.error, FHIRPathError):
        # Defensive: any residual re.error (e.g. malformed escape) returns
        # empty {} to match native C++ behavior.
        return []


def length(ctx, coll):
    if not coll:
        return []
    string = ensure_string_singleton(coll)
    return len(string)


def toChars(ctx, coll):
    if not coll:
        return []
    string = ensure_string_singleton(coll)
    return list(string)


def escape(ctx, coll, format):
    """
    Escapes a string according to the specified format.
    Supported formats: 'html', 'json'
    """
    if util.is_empty(coll):
        return []

    string = ensure_string_singleton(coll)

    if format == "html":
        # HTML escape: escape &, <, >, ", '
        return html.escape(string, quote=True)
    elif format == "json":
        # JSON escape: use json.dumps and strip the surrounding quotes
        return json.dumps(string)[1:-1]
    else:
        return []


def unescape(ctx, coll, format):
    """
    Unescapes a string according to the specified format.
    Supported formats: 'html', 'json'
    """
    if util.is_empty(coll):
        return []

    string = ensure_string_singleton(coll)

    if format == "html":
        # HTML unescape
        return html.unescape(string)
    elif format == "json":
        # JSON unescape: wrap in quotes and parse
        try:
            return json.loads('"' + string + '"')
        except json.JSONDecodeError:
            return string
    else:
        return []
