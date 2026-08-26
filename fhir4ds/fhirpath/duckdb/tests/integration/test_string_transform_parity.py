"""Parity tests for FHIRPath string transform functions in DuckDB UDFs."""

from __future__ import annotations

import json

import duckdb
import pytest

from fhir4ds.fhirpath.duckdb import register_fhirpath
from fhir4ds.fhirpath.duckdb.udf import (
    fhirpath_bool_udf,
    fhirpath_json_udf,
    fhirpath_number_udf,
    fhirpath_scalar,
    fhirpath_text_udf,
)


def _connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register_fhirpath(con)
    return con


def _python_fallback_connection(monkeypatch: pytest.MonkeyPatch) -> duckdb.DuckDBPyConnection:
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(con) is False
    return con


def _all_public_outputs(con: duckdb.DuckDBPyConnection, resource: str, expression: str):
    return con.execute(
        "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_number(?::JSON, ?)",
        [resource, expression, resource, expression, resource, expression, resource, expression, resource, expression],
    ).fetchone()


def _all_outputs_with_valid(con: duckdb.DuckDBPyConnection, resource: str, expression: str):
    return con.execute(
        "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_number(?::JSON, ?), fhirpath_is_valid(?)",
        [resource, expression, resource, expression, resource, expression, resource, expression, resource, expression, expression],
    ).fetchone()


def test_string_transform_functions_match_cpp() -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "s": "Abc abc",
            "empty": "",
            "unicode": "café",
            "accent": "é",
            "emoji": "😀",
            "combo": "a😀é",
            "ecirc": "ê",
            "mixed_range": "aêb",
            "upper_accent": "É",
            "sharp": "Straße",
            "sigma": "Σςσ",
            "latin_ext": "ČŽŠ",
            "latin_ext_lower": "čžš",
            "turkish_upper": "İSTANBUL",
            "turkish_lower": "ıstanbul",
            "greek_accent_lower": "άέήίόύώ",
            "greek_accent_upper": "ΆΈΉΊΌΎΏ",
            "eszett_cap": "ẞ",
            "ligature": "ﬃ",
            "deseret_lower": "𐐨",
            "armenian_lower": "ա",
            "georgian_lower": "ა",
            "latin_ext_b_lower": "ƀ",
            "url": "http://fhir.org/guides/cqf/common/Library/FHIR-ModelInfo|4.0.1",
            "code": "N8000123123",
            "multiline": "a\nb",
            "two_lines": "first line\nsecond line",
            "digits": "abc123",
        }
    )
    expressions = [
        "s.upper()",
        "s.lower()",
        "unicode.upper()",
        "unicode.lower()",
        "accent.matches('.')",
        "accent.replaceMatches('.', 'x')",
        "emoji.matches('.')",
        "emoji.replaceMatches('.', 'x')",
        "accent.matches('^[é]$')",
        "emoji.matches('^[😀]$')",
        "accent.replaceMatches('[é]', 'x')",
        "emoji.replaceMatches('[😀]', 'x')",
        "combo.replaceMatches('[😀é]', 'x')",
        "combo.replaceMatches('[^a]', 'x')",
        "ecirc.matches('^[é-ë]$')",
        "ecirc.replaceMatches('[é-ë]', 'x')",
        "mixed_range.replaceMatches('[a-ë]', 'x')",
        "upper_accent.matches('é', 'i')",
        "upper_accent.matches('[é]', 'i')",
        "upper_accent.matches('^[é-ë]$', 'i')",
        "upper_accent.replaceMatches('é', 'x', 'i')",
        "upper_accent.replaceMatches('[é]', 'x', 'i')",
        "upper_accent.replaceMatches('[é-ë]', 'x', 'i')",
        "sharp.upper()",
        "sharp.upper().length()",
        "sigma.upper()",
        "sigma.lower().upper()",
        "latin_ext.lower()",
        "latin_ext_lower.upper()",
        "turkish_upper.lower()",
        "turkish_lower.upper()",
        "greek_accent_lower.upper()",
        "greek_accent_upper.lower()",
        "eszett_cap.lower()",
        "ligature.upper()",
        "deseret_lower.upper()",
        "armenian_lower.upper()",
        "georgian_lower.upper()",
        "latin_ext_b_lower.upper()",
        "s.length()",
        "empty.length()",
        "unicode.length()",
        "s.replace('abc','X')",
        "s.replace('','-')",
        "s.replace('z','X')",
        "empty.replace('z','x')",
        "empty.replace('','x')",
        "url.matches('Library')",
        "code.matches('N[0-9]{8}')",
        "s.matches('^Abc')",
        "s.matches('abc$')",
        "s.matches('A.*c')",
        "url.matches('library', 'i')",
        "two_lines.matches('^second', 'm')",
        "two_lines.matches('^SECOND', 'im')",
        "multiline.matches('a.b')",
        "digits.matches('[a-z]+[0-9]+')",
        "s.replaceMatches('abc','X')",
        "s.replaceMatches('[A-Z]','x')",
        "s.replaceMatches('abc','X', 'i')",
        "two_lines.replaceMatches('^second', 'SECOND', 'm')",
        "s.replaceMatches('','-')",
        "s.toChars()",
        "empty.toChars()",
        "unicode.toChars()",
    ]

    con = _connection()
    try:
        for expression in expressions:
            cpp = con.execute(
                "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?), fhirpath_number(?::JSON, ?)",
                [resource, expression, resource, expression, resource, expression, resource, expression, resource, expression],
            ).fetchone()
            py = (
                fhirpath_scalar(resource, expression),
                fhirpath_text_udf(resource, expression),
                fhirpath_json_udf(resource, expression),
                fhirpath_bool_udf(resource, expression),
                fhirpath_number_udf(resource, expression),
            )
            assert cpp == py
    finally:
        con.close()


def test_string_transform_invalid_types_match_python_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "s": "Abc abc",
            "num": 123,
            "flag": True,
            "arr": ["abc", "def"],
        }
    )
    expressions = [
        "num.matches('123')",
        "flag.matches('true')",
        "s.matches(123)",
        "s.replace(123,'x')",
        "s.replace('b',123)",
        "num.replaceMatches('2','x')",
        "flag.replaceMatches('true','x')",
        "s.replaceMatches(123,'x')",
        "s.replaceMatches('b',123)",
        "arr.length()",
        "123.upper()",
        "123.replace('2','x')",
        "num.toChars()",
        "flag.toChars()",
        "s.matches('(a+)+')",
        "s.matches('[invalid')",
        "s.replaceMatches('(a|aa)+','x')",
        "s.replaceMatches('[invalid','x')",
        "'abc'.matches('(a+)+')",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            assert _all_public_outputs(native, resource, expression) == _all_public_outputs(
                fallback, resource, expression
            )
    finally:
        native.close()
        fallback.close()


def test_string_transform_dynamic_arguments_match_python_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "s": "Abc abc",
            "pattern": "abc",
            "sub": "X",
            "regex": "[a-z]+",
        }
    )
    expressions = [
        ("s.replace(pattern, sub)", (["Abc X"], "Abc X", '["Abc X"]', None, None)),
        ("s.matches(regex)", (["true"], "true", "[true]", True, None)),
        ("s.replaceMatches(regex, sub)", (["AX X"], "AX X", '["AX X"]', None, None)),
        ("s.matches(regex, 'i')", (["true"], "true", "[true]", True, None)),
        ("s.replaceMatches(regex, sub, 'i')", (["X X"], "X X", '["X X"]', None, None)),
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in expressions:
            assert _all_public_outputs(native, resource, expression) == expected
            assert _all_public_outputs(fallback, resource, expression) == expected
    finally:
        native.close()
        fallback.close()


def test_string_transform_invalid_signatures_and_regex_validation_match_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource = json.dumps({"resourceType": "Patient", "s": "Abc abc"})
    overlong_pattern = "a" * 1001
    expressions = [
        "s.upper(1)",
        "s.lower(1)",
        "s.trim(1)",
        "s.trim({})",
        "s.replace('a')",
        "s.replace('a', 'b', 'c')",
        "s.matches()",
        "s.matches('a', 'b')",
        "s.matches('a', 'x')",
        "s.replaceMatches('a')",
        "s.replaceMatches('a', 'b', 'c')",
        "s.replaceMatches('a', 'b', 'x')",
        "s.length(1)",
        "s.toChars(1)",
        "s.replace(123, 'x')",
        "s.replace('a', 123)",
        "s.matches('(a+)+')",
        "s.replaceMatches('(a|aa)+', 'x')",
        "s.matches('[invalid')",
        "s.replaceMatches('[invalid', 'x')",
        f"s.matches('{overlong_pattern}')",
        f"s.replaceMatches('{overlong_pattern}', 'x')",
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression in expressions:
            expected = ([], None, None, None, None, False)
            assert _all_outputs_with_valid(native, resource, expression) == expected
            assert _all_outputs_with_valid(fallback, resource, expression) == expected
    finally:
        native.close()
        fallback.close()


def test_string_transform_replace_matches_substitution_edge_cases_fp10_skeptic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FP-10 SKEPTIC iter 1: replaceMatches substitution edge cases.

    Per FHIRPath §5.6.10, the native C++ extension treats unknown group
    references gracefully (returns empty for out-of-range $N; literal
    passthrough for ${name} with no named group). The Python fallback
    previously raised uncaught re.error exceptions on these inputs,
    producing a native↔fallback parity defect surfaced through DuckDB
    as InvalidInputException. This test confirms both paths now agree.
    """
    resource = json.dumps({"resourceType": "Patient", "s": "abc"})
    expressions = [
        # Out-of-range $N — native returns empty substitution; fallback
        # previously raised re.error.
        ("s.replaceMatches('(b)', '$5')", (["ac"], "ac", '["ac"]', None, None)),
        ("s.replaceMatches('(b)', '$10')", (["ac"], "ac", '["ac"]', None, None)),
        # $0 full match
        ("s.replaceMatches('(b)', '[$0]')", (["a[b]c"], "a[b]c", '["a[b]c"]', None, None)),
        # $1 valid
        ("s.replaceMatches('(b)', '[$1]')", (["a[b]c"], "a[b]c", '["a[b]c"]', None, None)),
        # ${name} with no matching named group — literal passthrough
        ("s.replaceMatches('(b)', '[${name}]')", (["a[${name}]c"], "a[${name}]c", '["a[${name}]c"]', None, None)),
        # ${N} numeric in braces — native treats as literal ${N}
        ("s.replaceMatches('(b)', '[${1}]')", (["a[${1}]c"], "a[${1}]c", '["a[${1}]c"]', None, None)),
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in expressions:
            assert _all_public_outputs(native, resource, expression) == expected
            assert _all_public_outputs(fallback, resource, expression) == expected
    finally:
        native.close()
        fallback.close()


def test_string_transform_replace_matches_named_group_spec_example_fp10_skeptic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    r"""FP-10: §5.6.10 canonical spec example with named groups.

    The FHIRPath §5.6.10 spec example uses PCRE-style named groups
    (?<name>...) and named substitution references ${name}:
       '11/30/1972'.replaceMatches('(?<month>\d{1,2})/(?<day>\d{1,2})/(?<year>\d{2,4})',
              '${day}-${month}-${year}')
    Expected per spec: '30-11-1972'.

    FP-10 HISTORIAN QA-001: the native C++ path previously failed the
    spec's own canonical example (std::regex has no named-group syntax and
    the substitution went raw to std::regex_replace). normalizeFHIRPathRegex
    now translates (?<name>...) to a plain capturing group (numbering
    preserved) and replaceMatches rewrites ${name} for existing named
    groups to the numbered $N form. Both engines must now run the
    canonical example identically.
    """
    resource = json.dumps({"resourceType": "Patient"})
    expressions = [
        # Spec example w/o word boundaries
        ("'11/30/1972'.replaceMatches('(?<month>[0-9]{1,2})/(?<day>[0-9]{1,2})/(?<year>[0-9]{2,4})', '${day}-${month}-${year}')",
         (["30-11-1972"], "30-11-1972", '["30-11-1972"]', None, None)),
        # Numeric group reference works in both backends
        ("'11/30/1972'.replaceMatches('([0-9]{1,2})/([0-9]{1,2})/([0-9]{2,4})', '$2-$1-$3')",
         (["30-11-1972"], "30-11-1972", '["30-11-1972"]', None, None)),
        # Spec example WITH word boundaries (verbatim §5.6.10 pattern)
        (r"'11/30/1972'.replaceMatches('\\b(?<month>\\d{1,2})/(?<day>\\d{1,2})/(?<year>\\d{2,4})\\b', '${day}-${month}-${year}')",
         (["30-11-1972"], "30-11-1972", '["30-11-1972"]', None, None)),
        # Named group + mixed numbered references
        ("'ab'.replaceMatches('(?<n>a)(b)', '$2${n}')",
         (["ba"], "ba", '["ba"]', None, None)),
        # ${unknown} stays literal; bare $name stays literal
        ("'abc'.replaceMatches('(?<n>a)', '${missing}')",
         (["${missing}bc"], "${missing}bc", '["${missing}bc"]', None, None)),
        ("'abc'.replaceMatches('(?<n>a)', '$n')",
         (["$nbc"], "$nbc", '["$nbc"]', None, None)),
        # Named groups inside matches() (no substitution)
        ("'11/30/1972'.matches('(?<month>[0-9]{1,2})/(?<day>[0-9]{1,2})')",
         (["true"], "true", "[true]", True, None)),
        # Named group combined with a leading inline flag group (the captured
        # text keeps its original case — 'A' — in both engines)
        ("'AB'.replaceMatches('(?i)(?<n>a)', '${n}${n}')",
         (["AAB"], "AAB", '["AAB"]', None, None)),
        # Multiline flag path with named groups and ${name} substitution
        ("'a\\nb'.replaceMatches('(?m)^(?<n>a)', '${n}X')",
         (["aX\nb"], "aX\nb", '["aX\\nb"]', None, None)),
    ]
    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in expressions:
            assert _all_public_outputs(native, resource, expression) == expected, expression
            assert _all_public_outputs(fallback, resource, expression) == expected, expression
    finally:
        native.close()
        fallback.close()


def test_string_transform_regex_anchor_flags_and_classes_parity_fp10_skeptic2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    r"""FP-10 SKEPTIC iter 1 (fresh rerun): regex dialect parity fixes.

    Three parity doctrines pinned after dual-path probing:
    - QA-001: default-mode `$` follows PCRE semantics — matches at end of
      subject OR immediately before a single trailing newline (native
      previously end-only like raw std::regex ECMAScript).
    - QA-002: PCRE inline flag groups (?i)/(?m)/(?im)/(?s) at the pattern
      start are honored (native previously failed compilation).
    - QA-003: `\w`/`\d`/`\s`/`\b` are ASCII classes per the PCRE-recommended
      dialect (§5.6.9 note: FHIRPath does not prescribe a dialect, PCRE
      recommended; PCRE defaults are ASCII). The Python fallback previously
      compiled with Unicode-aware classes; it now passes re.ASCII.
    - QA-005: `$$` inside a replaceMatches substitution string literal is
      valid syntax (escaped literal dollar); the fallback's syntax precheck
      previously rejected the whole expression.
    """
    resource = json.dumps({"resourceType": "Patient", "s": "Abc abc"})
    expressions = [
        # QA-001: PCRE $ before a single trailing newline (LF only; the
        # preceding \r in CRLF is an ordinary character, so 'ab$' on
        # "ab\r\n" is false — matching PCRE and Python re)
        ("'abc\\n'.matches('abc$')", (["true"], "true", "[true]", True, None)),
        ("'ab\\r\\n'.matches('ab$')", (["false"], "false", "[false]", False, None)),
        ("'ab\\n\\n'.matches('ab$')", (["false"], "false", "[false]", False, None)),
        ("'abc'.matches('abc$')", (["true"], "true", "[true]", True, None)),
        ("'abc'.matches('ab$')", (["false"], "false", "[false]", False, None)),
        # QA-002: inline flags
        ("s.matches('(?i)abc')", (["true"], "true", "[true]", True, None)),
        ("s.matches('(?i)zzz')", (["false"], "false", "[false]", False, None)),
        ("s.matches('(?m)^abc')", (["false"], "false", "[false]", False, None)),
        ("s.matches('(?im)^abc')", (["true"], "true", "[true]", True, None)),
        ("s.matches('(?s)A.c')", (["true"], "true", "[true]", True, None)),
        ("s.replaceMatches('(?i)a', 'X')", (["Xbc Xbc"], "Xbc Xbc", '["Xbc Xbc"]', None, None)),
        # QA-003: ASCII \w \d \s \b (PCRE default dialect)
        ("'日本語'.matches('\\\\w+')", (["false"], "false", "[false]", False, None)),
        ("'abc'.matches('\\\\w+')", (["true"], "true", "[true]", True, None)),
        ("'١٢٣'.matches('\\\\d+')", (["false"], "false", "[false]", False, None)),
        ("'123'.matches('\\\\d+')", (["true"], "true", "[true]", True, None)),
        ("'a\\u00A0b'.matches('\\\\s')", (["false"], "false", "[false]", False, None)),
        ("'a b'.matches('\\\\s')", (["true"], "true", "[true]", True, None)),
        ("'straße'.matches('stra\\\\b')", (["true"], "true", "[true]", True, None)),
        ("'日本語'.matches('.+')", (["true"], "true", "[true]", True, None)),
        # QA-005: $$ substitution literal
        ("s.replaceMatches('A','$$')", (["$bc abc"], "$bc abc", '["$bc abc"]', None, None)),
        # $1 out-of-range group -> empty substitution; trailing $ stays literal
        ("s.replaceMatches('A','$1$')", (["$bc abc"], "$bc abc", '["$bc abc"]', None, None)),
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in expressions:
            assert _all_public_outputs(native, resource, expression) == expected, expression
            assert _all_public_outputs(fallback, resource, expression) == expected, expression
    finally:
        native.close()
        fallback.close()


def test_string_transform_regex_dialect_documented_divergences_fp10_skeptic2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    r"""FP-10 SKEPTIC iter 1 (fresh rerun): spec-sanctioned dialect divergences.

    §5.6.9 note: "FHIRPath does not prescribe a particular dialect". Native
    std::regex ECMAScript has no lookbehind assertions, no mid-pattern or
    scoped inline flags, and no regex-level \uXXXX escapes (Python re
    supports all three; default PCRE also lacks \u). Named groups ARE
    supported natively since FP-10 HISTORIAN (translated to numbered
    groups). These assertions pin each engine's actual behavior so future
    dialect work is deliberate.
    """
    resource = json.dumps({"resourceType": "Patient"})
    native_expectations = [
        ("'abc'.matches('(?<=a)b')", ([], None, None, None, None)),  # unsupported -> invalid
        # FP-10 HISTORIAN QA-003: mid-pattern inline flags unsupported natively
        ("'ab'.matches('a(?i)B')", ([], None, None, None, None)),
        # scoped flag group (?i:...) unsupported natively
        ("'AB'.matches('(?i:a)b')", ([], None, None, None, None)),
        # regex-level \uXXXX escape (NOT a FHIRPath literal escape): the
        # pattern text contains a literal backslash-u sequence, which
        # Python re interprets but std::regex and default PCRE do not
        (r"'café'.matches('caf\\u00E9')", (["false"], "false", "[false]", False, None)),
    ]
    fallback_expectations = [
        ("'abc'.matches('(?<=a)b')", (["true"], "true", "[true]", True, None)),
        ("'ab'.matches('a(?i)B')", (["true"], "true", "[true]", True, None)),
        ("'AB'.matches('(?i:a)b')", (["false"], "false", "[false]", False, None)),
        (r"'café'.matches('caf\\u00E9')", (["true"], "true", "[true]", True, None)),
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in native_expectations:
            assert _all_public_outputs(native, resource, expression) == expected, expression
        for expression, expected in fallback_expectations:
            assert _all_public_outputs(fallback, resource, expression) == expected, expression
    finally:
        native.close()
        fallback.close()


def test_string_transform_regex_quantifier_on_unicode_scalar_fp10_explorer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FP-10 EXPLORER iter 1: regex quantifier on multi-byte Unicode scalar.

    Per FHIRPath §5.6.9 ("matches operates on Unicode scalar values") and
    §5.6.10 (replaceMatches shares the regex normalization path), a regex
    quantifier (* + ? {n} {n,} {n,m}) following a non-ASCII literal must
    apply to the whole Unicode scalar, not to the last byte of the UTF-8
    sequence. The native C++ normalizeFHIRPathRegex previously appended
    non-ASCII bytes one at a time in the non-ignore_case path, so std::regex
    saw the quantifier binding only to the trailing continuation byte.
    Reproducer: 'éé'.matches('^é*$') returned false natively while the
    Python fallback correctly returned true.

    This test confirms the fix: non-ASCII literals followed by quantifiers
    are now wrapped in a non-capturing group so the quantifier binds to
    the whole codepoint. Both backends now agree across 2/3/4-byte UTF-8
    scalars and across all quantifier forms.
    """
    resource = json.dumps({"resourceType": "Patient"})
    expressions = [
        # 2-byte UTF-8 (U+00E9 é)
        ("'éé'.matches('^é*$')",
         (["true"], "true", "[true]", True, None)),
        ("'éé'.matches('^é+$')",
         (["true"], "true", "[true]", True, None)),
        ("'ééé'.matches('^é{3}$')",
         (["true"], "true", "[true]", True, None)),
        ("'éééé'.matches('^é{2,}$')",
         (["true"], "true", "[true]", True, None)),
        ("'ééé'.matches('^é{1,5}$')",
         (["true"], "true", "[true]", True, None)),
        ("'é'.matches('^é?$')",
         (["true"], "true", "[true]", True, None)),
        ("'éé'.matches('^é?$')",
         (["false"], "false", "[false]", False, None)),
        # 3-byte UTF-8 (U+3042 あ)
        ("'ああ'.matches('^あ*$')",
         (["true"], "true", "[true]", True, None)),
        ("'あああ'.matches('^あ{3}$')",
         (["true"], "true", "[true]", True, None)),
        # 4-byte UTF-8 (U+1F600 😀)
        ("'😀😀'.matches('^😀*$')",
         (["true"], "true", "[true]", True, None)),
        ("'😀😀😀'.matches('^😀{3}$')",
         (["true"], "true", "[true]", True, None)),
        ("'😀😀😀😀😀'.matches('^😀{2,10}$')",
         (["true"], "true", "[true]", True, None)),
        # Quantifier on replaceMatches — generalizes the bug to replacement
        ("'ééé'.replaceMatches('é', 'X')",
         (["XXX"], "XXX", '["XXX"]', None, None)),
        ("'ééé'.replaceMatches('é+', 'X')",
         (["X"], "X", '["X"]', None, None)),
        ("'aééb'.replaceMatches('é+', 'X')",
         (["aXb"], "aXb", '["aXb"]', None, None)),
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in expressions:
            assert _all_public_outputs(native, resource, expression) == expected
            assert _all_public_outputs(fallback, resource, expression) == expected
    finally:
        native.close()
        fallback.close()



def test_escaped_backslash_argument_literals_lex_correctly_fp10_explorer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FHIRPath lexical grammar: STRING must close at its own closing quote.

    A greedy antlr loop let ESC's `\\'` alternative match across a raw
    backslash, swallowing the closing quote and the following comma, so any
    expression with a string literal ending in an escaped backslash followed
    by a comma (e.g. replace('\\\\', '/')) mis-lexed as one token in the
    Python fallback while the native engine evaluated it correctly. The
    non-greedy STRING loop fixes this; tolerant raw-backslash corners
    ('abc\\', 'short \\u005') must keep their prior behavior.
    """
    resource = json.dumps({"resourceType": "Patient", "p": "C:\\x\\y"})
    cases = [
        ("p.replace('\\\\', '/')", ["C:/x/y"]),
        ("'a'.iif(true, '\\\\', 'x')", ["\\"]),
        ("('\\\\') | 'x'", ["\\", "x"]),
        ("p.replaceMatches('\\\\d', '#')", ["C:\\x\\y"]),
        # Tolerated raw-backslash corners must be unchanged
        (r"'abc\'", ["abc"]),
        (r"'short \u005'", ["short u005"]),
        ("'a\\nb'.length()", ["3"]),
    ]

    native = _connection()
    fallback = _python_fallback_connection(monkeypatch)
    try:
        for expression, expected in cases:
            assert _all_public_outputs(native, resource, expression)[0] == expected
            assert _all_public_outputs(fallback, resource, expression)[0] == expected
        # is_valid parity for the previously mis-lexed form
        assert (
            native.execute("SELECT fhirpath_is_valid(?)", ["p.replace('\\\\', '/')"]).fetchone()[0]
            is True
        )
        assert (
            fallback.execute("SELECT fhirpath_is_valid(?)", ["p.replace('\\\\', '/')"]).fetchone()[0]
            is True
        )
    finally:
        native.close()
        fallback.close()
