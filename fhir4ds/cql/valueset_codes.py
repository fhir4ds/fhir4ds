"""FHIR R4 ValueSet → enumerable code extraction.

Single source of truth for turning a raw ``ValueSet`` resource into the
``[{system, code, display}, ...]`` list that the ``valueset_codes`` table and
``ResolvedValueSet.codes`` are built from. Previously this logic existed twice
(``fhir4ds.cql.loader.fhir_loader`` and
``fhir4ds.cql.dependency.resolver``) with identical gaps; both now delegate
here.

FHIR R4 semantics implemented (https://hl7.org/fhir/R4/valueset.html):

``ValueSet.expansion.contains`` (0..*)
    When an expansion is present it IS the membership: it is what a terminology
    server computed from the definition, filters, excludes and date-activity
    rules. ``compose`` must not be re-read on top of it. ``contains`` is a
    RECURSIVE backbone (``contains.contains`` 0..*, "Codes contained under this
    entry") — hierarchical expansions (SNOMED / ICD-10 ancestor trees) nest
    descendants under ancestors, so the tree is flattened.
    ``contains.code`` is 0..1 ("Code - if blank, this is not a selectable
    code"): header/grouping nodes carry no code and are not members.

``ValueSet.compose.exclude`` (0..*)
    "Explicitly exclude codes from a code system or other value sets." An
    excluded code is NOT a member. Supported forms: an explicit ``concept``
    list, a ``filter`` with ``op`` ``=`` (names one code), or no ``concept``/
    ``filter`` at all (the whole system is excluded).

    Exclusions that cannot be enumerated without a terminology server
    (``op`` ``is-a``/``descendant-of``/regex, or a nested ``valueSet``
    reference) raise ``ValueSetExpansionError``. Silently keeping a code we
    cannot prove is a member would over-report clinical evidence, which is
    strictly worse than an actionable load-time error — the same doctrine the
    VSAC adapter applies to unenumerable *includes*.

Zero third-party dependencies: this module is imported from translator-side
dependency resolution and must stay cheap.
"""

from __future__ import annotations

from typing import Any, Iterator

__all__ = [
    "ValueSetExpansionError",
    "excluded_members",
    "extract_codes_from_valueset_resource",
    "iter_expansion_codes",
]


class ValueSetExpansionError(ValueError):
    """A ValueSet declaration cannot be enumerated without a terminology server.

    Subclasses ``ValueError`` so callers that already treat malformed ValueSet
    input as a ``ValueError`` keep working.
    """


def _code_row(system: Any, code: Any, display: Any) -> dict[str, Any]:
    return {"system": system, "code": code, "display": display}


def _collect_expansion_codes(
    contains: list[Any],
    out: list[dict[str, Any]],
    seen: set[tuple[Any, Any]],
    *,
    strict: bool,
) -> None:
    """Flatten a (possibly hierarchical) ``expansion.contains`` tree.

    ITERATIVE on purpose: a recursive walk hits CPython's recursion limit
    (~1000 frames) on a corrupt or hostile ValueSet and raises a raw
    ``RecursionError`` out of the public loader API. The explicit stack has no
    depth ceiling and keeps the same depth-first document order.
    """
    stack: list[Any] = list(reversed(contains))
    while stack:
        item = stack.pop()
        if not isinstance(item, dict):
            if strict:
                raise TypeError("ValueSet.expansion.contains entries must be objects")
            continue
        system = item.get("system")
        code = item.get("code")
        # ``code`` 0..1 and blank means "not a selectable code" (grouping node).
        if isinstance(code, str) and code:
            key = (system, code)
            if key not in seen:
                seen.add(key)
                out.append(_code_row(system, code, item.get("display")))
        elif code is not None and strict:
            # A present-but-empty code is a malformed member declaration.
            raise TypeError("ValueSet.expansion.contains.code must be a non-empty string")
        nested = item.get("contains") or []
        if not isinstance(nested, list):
            if strict:
                raise TypeError("ValueSet.expansion.contains.contains must be a list")
            continue
        stack.extend(reversed(nested))


def iter_expansion_codes(
    contains: list[Any], *, strict: bool = False
) -> Iterator[tuple[Any, Any, Any]]:
    """Yield ``(system, code, display)`` from an ``expansion.contains`` tree.

    For callers that convert to their own record type (the terminology
    endpoint adapters). ``expansion.contains`` is a RECURSIVE backbone —
    hierarchical expansions nest descendants under ancestors — so a flat walk
    silently drops every descendant. Blank codes are skipped (0..1, "not a
    selectable code"); repeated ``(system, code)`` pairs (a code reachable
    through two parents) are collapsed.

    ``strict=True`` raises ``TypeError`` on malformed entries (the loader's
    contract); the adapters tolerate and skip half-formed server output.
    """
    out: list[dict[str, Any]] = []
    _collect_expansion_codes(contains, out, set(), strict=strict)
    for row in out:
        yield row["system"], row["code"], row["display"]


def excluded_members(
    compose: dict[str, Any], *, has_included_codes: bool
) -> tuple[set[tuple[Any, Any]], set[Any]]:
    """Resolve ``compose.exclude`` into excluded ``(system, code)`` pairs and
    fully-excluded systems (``system`` with neither ``concept`` nor ``filter``).

    An exclusion that cannot be enumerated without a terminology server
    (``is-a``/``descendent-of``/regex filters, or a nested ``valueSet``
    reference) raises ``ValueSetExpansionError`` — but only when there are
    actually included codes to remove. A compose block whose includes cannot be
    enumerated either (system-only includes, as VSAC emits for
    fully-intensional sets) has nothing to exclude, so the exclusions are moot
    and the zero-code warning downstream is the honest signal.
    """
    pairs: set[tuple[Any, Any]] = set()
    systems: set[Any] = set()
    excludes = compose.get("exclude") or []
    if not isinstance(excludes, list):
        raise TypeError("ValueSet.compose.exclude must be a list")
    for exclude in excludes:
        if not isinstance(exclude, dict):
            raise TypeError("ValueSet.compose.exclude entries must be objects")
        system = exclude.get("system")
        concepts = exclude.get("concept") or []
        filters = exclude.get("filter") or []
        if not isinstance(concepts, list):
            raise TypeError("ValueSet.compose.exclude.concept must be a list")
        if not isinstance(filters, list):
            raise TypeError("ValueSet.compose.exclude.filter must be a list")
        if exclude.get("valueSet"):
            if not has_included_codes:
                continue
            raise ValueSetExpansionError(
                "ValueSet.compose.exclude references nested value sets, which "
                "cannot be enumerated locally; supply the expanded ValueSet "
                "(expansion.contains) instead of an intensional definition"
            )
        if concepts:
            for concept in concepts:
                if not isinstance(concept, dict):
                    raise TypeError(
                        "ValueSet.compose.exclude.concept entries must be objects"
                    )
                code = concept.get("code")
                if isinstance(code, str) and code:
                    pairs.add((system, code))
            continue
        if filters:
            for flt in filters:
                if not isinstance(flt, dict):
                    raise TypeError(
                        "ValueSet.compose.exclude.filter entries must be objects"
                    )
                prop = flt.get("property")
                op = flt.get("op")
                value = flt.get("value")
                if op == "=" and prop in (None, "concept") and isinstance(value, str):
                    pairs.add((system, value))
                    continue
                if not has_included_codes:
                    continue
                raise ValueSetExpansionError(
                    "ValueSet.compose.exclude uses a filter that cannot be "
                    f"enumerated locally (property={prop!r}, op={op!r}); supply "
                    "the expanded ValueSet (expansion.contains) instead of an "
                    "intensional definition"
                )
            continue
        # No concept list and no filter: the whole code system is excluded.
        systems.add(system)
    return pairs, systems


def extract_codes_from_valueset_resource(valueset: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract the enumerable members of a raw FHIR R4 ``ValueSet`` resource.

    Returns ``[{"system", "code", "display"}, ...]`` preserving authored order
    and de-duplicating by ``(system, code)`` — membership is a set, and
    hierarchical expansions can legitimately reach the same code through more
    than one parent.
    """
    if not isinstance(valueset, dict):
        raise TypeError(
            f"ValueSet resource must be an object, got {type(valueset).__name__}"
        )

    codes: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any]] = set()

    # FHIR JSON parsing treats null members as absent (FHIR R4 json.html);
    # "expansion": null must not crash extraction.
    expansion_contains = (valueset.get("expansion") or {}).get("contains") or []
    if not isinstance(expansion_contains, list):
        raise TypeError("ValueSet.expansion.contains must be a list")
    if expansion_contains:
        _collect_expansion_codes(expansion_contains, codes, seen, strict=True)
        return codes

    compose = valueset.get("compose") or {}
    if not isinstance(compose, dict):
        raise TypeError("ValueSet.compose must be an object")

    includes = compose.get("include") or []
    if not isinstance(includes, list):
        raise TypeError("ValueSet.compose.include must be a list")
    for include in includes:
        if not isinstance(include, dict):
            raise TypeError("ValueSet.compose.include entries must be objects")
        system = include.get("system")
        concepts = include.get("concept", [])
        if concepts is None:
            concepts = []
        if not isinstance(concepts, list):
            raise TypeError("ValueSet.compose.include.concept must be a list")
        for concept in concepts:
            if not isinstance(concept, dict):
                raise TypeError("ValueSet.compose.include.concept entries must be objects")
            code = concept.get("code")
            key = (system, code)
            if key not in seen:
                seen.add(key)
                codes.append(_code_row(system, code, concept.get("display")))

    excluded_pairs, excluded_systems = excluded_members(
        compose, has_included_codes=bool(codes)
    )
    if excluded_pairs or excluded_systems:
        codes = [
            row
            for row in codes
            if (row["system"], row["code"]) not in excluded_pairs
            and row["system"] not in excluded_systems
        ]

    return codes
