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


@functools.lru_cache(maxsize=256)
def _compile_regex(pattern: str, flags: int = 0) -> re.Pattern:
    """Cache compiled regex patterns to avoid recompilation."""
    _validate_regex(pattern)
    return re.compile(pattern, flags)


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
        # FHIRPath §5.6.3: "If start lies outside the length of the string,
        # the function returns an empty collection."
        return []
    if start > len(string):
        return []

    if length is None or length == []:
        return string[start:]

    return string[start : start + int(length)]


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


def matches(ctx, coll, regex):
    """FHIRPath matches() — full-string regex match (FHIRPath §5.7.2).

    Returns true only when the *entire* string matches the given regex.
    """
    if not coll or util.is_empty(regex) or regex is None:
        return []

    string = ensure_string_singleton(coll)
    valid = _compile_regex(regex, re.DOTALL)
    return re.fullmatch(valid, string) is not None


def replace(ctx, coll, regex, repl):
    string = ensure_string_singleton(coll)
    # Handle empty collection as regex argument
    if util.is_empty(regex):
        return []
    # Handle empty collection as replacement argument
    if util.is_empty(repl):
        return []
    if regex == "" and isinstance(repl, str):
        return repl + repl.join(character for character in string) + repl
    if not string or not regex:
        return []
    return string.replace(regex, repl)


def replace_matches(ctx, coll, regex, repl):
    string = ensure_string_singleton(coll)
    if isinstance(regex, list) or isinstance(repl, list):
        return []

    # Empty regex should return the original string unchanged
    if regex == "":
        return string

    # Convert FHIRPath $N capture group references to Python \g<N> syntax.
    # Using \g<N> avoids ambiguity: $0 → \g<0> (full match), $1 → \g<1>, etc.
    repl = re.sub(r"\$(\d+)", r"\\g<\1>", repl)

    valid = _compile_regex(regex)
    return re.sub(valid, repl, string)


def length(ctx, coll):
    if not coll:
        return []
    data = util.get_data(coll[0])
    if not isinstance(data, str):
        return []
    return len(data)


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
