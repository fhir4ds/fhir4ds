"""CQL 2.0 ``#`` directive interpretation (chunk CQL20-D, FHIR-41326).

Pure functions interpreting the directive list attached to a parsed
:class:`~fhir4ds.cql.parser.ast_nodes.Library`:

* ``parse_comparison_precision_directive`` — extract the
  ``#DefaultComparisonPrecision`` declaration (precision + inclusion
  behavior) and validate it.
* ``resolve_effective_comparison_precision`` — compute the effective
  default comparison precision for a library from its OWN directive and
  what it INHERITED from an including library, per the inclusion
  behaviors:

  - (no clause): the directive is local to the declaring library;
    included libraries are unaffected.
  - ``default included libraries``: the directive applies to included
    libraries that do not declare their own.
  - ``override included libraries``: the directive applies to included
    libraries regardless of their own declaration.
  - ``check included libraries``: like ``default``, but a conflicting
    declaration in an included library is an error.

Ground truth: CQL 2.0 Developer's Guide, "Directives" /
"DefaultComparisonPrecision",
https://cql.hl7.org/03-developersguide.html#defaultcomparisonprecision.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from ..errors import TranslationError
from ..parser.ast_nodes import Directive

# Comparison precisions supported by #DefaultComparisonPrecision. 'week' is
# deliberately excluded: CQL §8 timing comparisons "involving weeks are not
# supported" (pinned doctrine, CQL-13/14 chunks).
COMPARISON_PRECISIONS = (
    "year", "month", "day", "hour", "minute", "second", "millisecond",
)

INCLUSION_BEHAVIORS = (
    "default included libraries",
    "override included libraries",
    "check included libraries",
)

# (precision, inclusion-behavior) — behavior None means "local to the
# declaring library".
_ComparisonDirective = Tuple[Optional[str], Optional[str]]

_DIRECTIVE_NAME = "DefaultComparisonPrecision"


def parse_comparison_precision_directive(
    directives: Sequence[Directive],
) -> Optional[_ComparisonDirective]:
    """Extract and validate the ``#DefaultComparisonPrecision`` directive.

    Args:
        directives: The library's parsed directive list.

    Returns:
        ``(precision, inclusion_behavior)`` — behavior is None for a
        local-only declaration — or None when the library does not
        declare the directive.

    Raises:
        TranslationError: On an invalid precision value (including
            ``week``, which CQL comparisons do not support), a duplicate
            declaration, a missing value, or an inclusion behavior on
            another directive (the parser rejects that case at parse
            time already; this is defense in depth for programmatic ASTs).
    """
    found: Optional[_ComparisonDirective] = None
    for directive in directives or []:
        if directive.name != _DIRECTIVE_NAME:
            continue
        if found is not None:
            raise TranslationError(
                "Duplicate #DefaultComparisonPrecision directive — a "
                "library may declare it at most once [CQL 2.0, FHIR-41326]"
            )
        if directive.value is None:
            raise TranslationError(
                "#DefaultComparisonPrecision requires a precision value "
                "(one of: " + ", ".join(COMPARISON_PRECISIONS) + ") "
                "[CQL 2.0, FHIR-41326]"
            )
        precision = directive.value.strip().lower()
        if precision not in COMPARISON_PRECISIONS:
            extra = (
                " (comparisons involving weeks are not supported per CQL §8)"
                if precision == "week"
                else ""
            )
            raise TranslationError(
                f"Invalid #DefaultComparisonPrecision value {directive.value!r}; "
                f"expected one of: " + ", ".join(COMPARISON_PRECISIONS) + extra
            )
        behavior = directive.inclusion_behavior
        if behavior is not None and behavior not in INCLUSION_BEHAVIORS:
            raise TranslationError(
                f"Invalid inclusion behavior {behavior!r} on "
                f"#DefaultComparisonPrecision; expected one of: "
                + ", ".join(INCLUSION_BEHAVIORS)
            )
        found = (precision, behavior)
    return found


def resolve_effective_comparison_precision(
    own: Optional[_ComparisonDirective],
    inherited: Optional[_ComparisonDirective],
) -> _ComparisonDirective:
    """Compute the effective precision for ONE library.

    Args:
        own: This library's own ``#DefaultComparisonPrecision`` declaration
            (``None`` precision means no declaration), as returned by
            :func:`parse_comparison_precision_directive`.
        inherited: What the INCLUDING library passes down:
            ``(effective_precision_of_parent, parents_own_clause)`` where
            the clause is ``None`` when the parent's directive is
            local-only or the parent declared no directive at all.

    Returns:
        ``(effective_precision, clause_for_THIS_library's_includes)``.
        The clause that governs this library's own includes is its OWN
        clause when it declares one (one-level semantics: a clause on a
        directive governs the includes of the library that declared it);
        otherwise ``None`` — an inherited precision does not automatically
        continue past the level the parent's clause explicitly reached.

    Raises:
        TranslationError: When the parent declared ``check included
            libraries`` and this library declares a different precision.
    """
    inherited_prec = inherited[0] if inherited is not None else None
    inherited_clause = inherited[1] if inherited is not None else None
    own_prec = own[0] if own is not None else None
    own_clause = own[1] if own is not None else None

    if own_prec is not None:
        if (
            inherited_prec is not None
            and inherited_clause == "override included libraries"
        ):
            effective = inherited_prec
        elif (
            inherited_prec is not None
            and inherited_clause == "check included libraries"
            and own_prec != inherited_prec
        ):
            raise TranslationError(
                f"#DefaultComparisonPrecision conflict: this library "
                f"declares {own_prec!r} but the including library declared "
                f"{inherited_prec!r} with 'check included libraries' "
                f"[CQL 2.0, FHIR-41326]"
            )
        else:
            effective = own_prec
        return (effective, own_clause)

    # No own declaration: the parent's clause decides whether it reaches us.
    if inherited_prec is not None and inherited_clause is not None:
        return (inherited_prec, None)
    return (None, None)
