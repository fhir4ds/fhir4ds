"""Parity regression tests for definition-reference resolution.

The translator has two parallel paths that resolve a CTE reference:

* ``_build_promoted_definition_lookup`` — for **promoted** definitions
  (referenced at least once anywhere in the library). Always emits a
  correlated subquery.
* The inline ``symbol_type == "definition"`` branch of
  ``_translate_identifier`` — for non-promoted definitions. Prefers JOIN
  tracking via the active ``query_builder``.

Both paths answer the same logical question — given a definition's metadata
and the caller's usage context, what shape of SQL reference is safe? The
historical bug pattern is that one path learns a lesson (e.g. "boolean
defines have no value column, use EXISTS") that the other path misses.
These tests pin the parity invariants that both paths must satisfy.
"""

from __future__ import annotations

from ...parser import parse_cql
from ...translator import CQLToSQLTranslator


def _translate(cql: str) -> tuple[str, CQLToSQLTranslator]:
    library = parse_cql(cql)
    translator = CQLToSQLTranslator()
    sql = translator.translate_library_to_population_sql(library)
    return sql, translator


def test_forward_ref_boolean_in_scalar_context_uses_exists():
    """A promoted boolean define referenced in SCALAR context BEFORE its meta
    is populated must still resolve to EXISTS.

    Reproduces the parity gap where ``_build_promoted_definition_lookup``
    lacked the ``_is_forward_ref_boolean`` check that the inline branch had.
    With the gap, the translator emitted
    ``SELECT sub.value FROM "ForwardBool" AS sub ... LIMIT 1`` even though
    the boolean CTE only has ``patient_id`` — same binder error class as
    the CASE-WHEN bug, just from a different reach-in path.

    Setup: ``ScalarUser`` is defined BEFORE ``ForwardBool``, so during
    ``ScalarUser``'s body translation, ``ForwardBool``'s meta is ``None``.
    ``ForwardBool`` is referenced once, so it gets promoted to a global CTE.
    """
    cql = """
    library ForwardRefScalar version '1.0'
    using FHIR version '4.0.1'

    context Patient

    define "ScalarUser":
        "ForwardBool" = true

    define "ForwardBool":
        exists ([Condition])
    """
    sql, translator = _translate(cql)

    # Sanity: ForwardBool really is promoted (otherwise this test isn't
    # exercising the path it claims to).
    assert "ForwardBool" in translator._context.promoted_definitions, (
        "Test setup is wrong: ForwardBool must be promoted to hit Path A. "
        f"Promoted: {translator._context.promoted_definitions}"
    )

    # The buggy emission: SELECT sub.value FROM "ForwardBool" — would binder-fail.
    assert 'sub.value FROM "ForwardBool"' not in sql, (
        "Translator emits `sub.value FROM \"ForwardBool\"` for a forward-ref "
        "boolean define (CTE has no value column). SQL:\n" + sql
    )
    # The safe emission: EXISTS (SELECT 1 FROM "ForwardBool" ...).
    assert 'EXISTS' in sql.upper() and '"ForwardBool"' in sql, (
        "Expected EXISTS subquery referencing \"ForwardBool\"; got:\n" + sql
    )


def test_list_context_over_promoted_boolean_define_does_not_emit_value_or_resource():
    """A LIST-context reference to a promoted boolean define (whose meta IS
    populated) must not emit ``SELECT sub.value`` or ``SELECT sub.resource``.

    The boolean CTE has neither column. This pins the behavior that the
    first CASE-bool fix established for backward references — the parity
    consolidation must not regress it.

    Setup: ``HasHIV`` is promoted (referenced from ``Wrapped``). ``Wrapped``
    is NOT a trivial identity define (it has additional structure) so the
    translator's identity-passthrough optimization doesn't short-circuit
    before reaching Path A.
    """
    cql = """
    library ListRefBool version '1.0'
    using FHIR version '4.0.1'

    context Patient

    define "HasHIV":
        exists ([Condition])

    define "Wrapped":
        "HasHIV" and true
    """
    sql, translator = _translate(cql)

    assert "HasHIV" in translator._context.promoted_definitions, (
        "Test setup is wrong: HasHIV must be promoted. "
        f"Promoted: {translator._context.promoted_definitions}"
    )

    assert 'sub.value FROM "HasHIV"' not in sql, (
        "Translator emits `sub.value FROM \"HasHIV\"` in LIST context "
        "(boolean CTE has no value column). SQL:\n" + sql
    )
    assert 'sub.resource FROM "HasHIV"' not in sql, (
        "Translator emits `sub.resource FROM \"HasHIV\"` in LIST context "
        "(boolean CTE has no resource column). SQL:\n" + sql
    )
