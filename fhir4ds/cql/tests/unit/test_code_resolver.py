"""Phase 3 unit tests for the extracted code_resolver helper.

Verifies that the shared ``resolve_code_ref_for_library`` correctly resolves
the static code-reference shapes the closure builder needs to walk:
inline ``CodeSelector``, bare Identifier referencing a ``code`` def,
Concept fan-out, system URL normalization, and graceful None for dynamic
operands.
"""

from __future__ import annotations

from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.translator.code_resolver import resolve_code_ref_for_library


def _library_with(cql_body: str):
    template = (
        "library T version '1.0'\n"
        "using FHIR version '4.0.1'\n"
        f"{cql_body}\n"
        "context Patient\n"
        "define Target: 1\n"
    )
    return parse_cql(template)


def test_resolves_inline_code_selector():
    """Code 'X' from "SYS" resolves via the CodeSelector AST path."""
    lib = _library_with(
        'codesystem "S": \'http://snomed.info/sct\'\n'
        'code "DM": \'73211009\' from "S"\n'
    )
    # Find the CodeDefinition's expression-equivalent: we resolve an
    # Identifier referring to "DM" — the helper should return the code info.
    code_def = lib.codes[0]
    # Synthesize a CodeSelector-like AST.
    from fhir4ds.cql.parser.ast_nodes import CodeSelector

    sel = CodeSelector(code="73211009", system="S", display=None)
    info = resolve_code_ref_for_library(sel, lib)
    assert info is not None
    assert info["code"] == "73211009"
    assert info["codesystem"] == "http://snomed.info/sct"


def test_resolves_identifier_to_code_def():
    """Bare Identifier referring to a `code "X": ...` resolves via codes map."""
    lib = _library_with(
        'codesystem "S": \'http://snomed.info/sct\'\n'
        'code "DM": \'73211009\' from "S"\n'
    )
    from fhir4ds.cql.parser.ast_nodes import Identifier

    info = resolve_code_ref_for_library(Identifier(name="DM"), lib)
    assert info is not None
    assert info["code"] == "73211009"
    assert info["codesystem"] == "http://snomed.info/sct"


def test_normalizes_snomed_module_url():
    """SNOMED module URLs reduce to the base URI on resolution."""
    lib = _library_with(
        'codesystem "SNOMED-US": \'http://snomed.info/sct/731000124108\'\n'
        'code "DM": \'73211009\' from "SNOMED-US"\n'
    )
    from fhir4ds.cql.parser.ast_nodes import Identifier

    info = resolve_code_ref_for_library(Identifier(name="DM"), lib)
    assert info is not None
    assert info["codesystem"] == "http://snomed.info/sct"


def test_returns_none_for_unknown_identifier():
    """Unknown Identifier resolves to None (graceful skip)."""
    lib = _library_with('codesystem "S": \'http://snomed.info/sct\'\n')
    from fhir4ds.cql.parser.ast_nodes import Identifier

    info = resolve_code_ref_for_library(Identifier(name="Unknown"), lib)
    assert info is None


def test_returns_none_for_unsupported_node_types():
    """FunctionRef, etc. resolve to None (dynamic case)."""
    lib = _library_with('codesystem "S": \'http://snomed.info/sct\'\n')
    from fhir4ds.cql.parser.ast_nodes import FunctionRef, Literal

    info = resolve_code_ref_for_library(
        FunctionRef(name="Today", arguments=[]), lib
    )
    assert info is None
    # Numeric literal: not a code reference.
    info2 = resolve_code_ref_for_library(Literal(value=42), lib)
    assert info2 is None


def test_resolves_string_literal_with_pipe():
    """``'system|code'`` literal parses to a code info."""
    lib = _library_with("")
    from fhir4ds.cql.parser.ast_nodes import Literal

    info = resolve_code_ref_for_library(
        Literal(value="http://snomed.info/sct|73211009"), lib
    )
    assert info is not None
    assert info["code"] == "73211009"
    assert info["codesystem"] == "http://snomed.info/sct"
