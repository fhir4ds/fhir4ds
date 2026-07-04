"""Shared code-reference resolution helper for the subsumption closure builder.

The CQL->SQL translator (``fhir4ds.cql.translator.expressions._operators``)
has an instance method ``_resolve_code_ref`` that resolves an AST node to a
``{"code", "codesystem", "display"}`` (or ``{"codes": [...]}`` for Concept)
dict by consulting ``self.context``.

The Phase 3 closure builder (``fhir4ds.cql.terminology.closure``) needs the
same resolution power when it scans a library AST for subsumption seeds
(``Descendents(X)``, ``X ~ Y``, ``X is Y``) — but it cannot pay the cost of
instantiating a full translator just to read ``codesystems`` and ``codes``
tables off a parsed :class:`~fhir4ds.cql.parser.ast_nodes.Library`.

This module exposes :func:`resolve_code_ref_for_library`, a pure helper that
mirrors the translator's resolution logic against a Library's static symbol
tables. It covers the seed-extraction use case (CodeSelector, Identifier
resolving to a CodeDefinition, QualifiedIdentifier/Property for library-qualified
references, Literal ``system|code`` strings). Dynamic / parameterized code
references (those that depend on a runtime parameter binding or a function-inlined
ParameterPlaceholder) are intentionally NOT resolved here — they fall through to
``None`` and the closure builder skips them with a WARNING, matching the FDD's
"per-seed fault tolerance" decision (Decision d).

Design choice (S5 in the design handoff):
    This is an EXTRACT, not a duplication. The translator keeps its instance
    method because it has privileged access to ``self.context.codesystems``,
    ``self.context.codes``, ``self._definition_source_ast`` and
    ``self._static_clinical_value_object`` — all per-translation state that the
    closure builder does not share. The shared contract is the *output shape*:
    both paths return the same dict structure (or ``None``), and both go through
    :class:`SystemResolver.normalize` on the system side before returning.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional

from ..duckdb.udf.system_resolver import SystemResolver

if TYPE_CHECKING:
    from ...parser.ast_nodes import Library

# Lazily imported inside the function to avoid parser-import cycles at module
# load time. The closure builder only calls this on demand for each AST node
# it walks, so the per-call import cost is acceptable.


def _normalized_code_info(
    code: str,
    system: str,
    display: Optional[str] = None,
    version: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the standard code-info dict shape with a normalized system URI.

    The translator's ``_resolve_code_ref`` returns dicts shaped like
    ``{"code", "codesystem", "display", "version"}``; we mirror that shape so
    callers (closure builder, translator equivalence branch) can share code.
    """
    return {
        "code": code,
        "codesystem": SystemResolver.normalize(system) or system,
        "display": display,
        "version": version,
    }


def resolve_code_ref_for_library(
    node: Any,
    library: "Library",
    *,
    codesystems_override: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, Any]]:
    """Resolve an AST node to a code-info dict using a Library's static tables.

    Args:
        node: An AST node from a CQL expression tree (typically the operand of
            ``Descendents(...)``, ``~`` or ``is``).
        library: The owning :class:`Library` AST. Used to look up
            ``codesystems`` and ``codes`` declarations.
        codesystems_override: Optional dict mapping codesystem *name* to URL.
            When provided, takes precedence over ``library.codesystems`` (used
            by callers that resolve codesystem aliases through a wider
            library-resolver scope).

    Returns:
        A dict with shape ``{"code", "codesystem", "display", "version"}``,
        or ``{"codes": [...], "is_concept": True, "display": ...}`` for a
        Concept, or ``None`` when the node does not statically resolve to a
        code reference (e.g., runtime parameter, query alias).

    Notes:
        * The returned ``codesystem`` is always passed through
          :meth:`SystemResolver.normalize` so SNOMED module URLs reduce to
          ``http://snomed.info/sct`` (INV-7).
        * Concept values are returned as a single-element ``codes`` list to
          match the translator's shape; the closure builder fans each entry
          out to a separate seed.
    """
    # Local imports to avoid import cycles at module load.
    from ..parser.ast_nodes import (
        CodeSelector,
        ConceptDefinition,
        Identifier,
        Literal,
        Property,
        QualifiedIdentifier,
    )

    # Build codesystems name -> URL map from the library's declarations.
    cs_map: Dict[str, str] = {}
    for cs_def in getattr(library, "codesystems", []) or []:
        cs_map[cs_def.name] = cs_def.id
    if codesystems_override:
        cs_map.update(codesystems_override)

    # Build codes name -> code info map.
    codes_map: Dict[str, Dict[str, Any]] = {}
    for code_def in getattr(library, "codes", []) or []:
        system_url = cs_map.get(code_def.codesystem, code_def.codesystem)
        codes_map[code_def.name] = _normalized_code_info(
            code=code_def.code,
            system=system_url,
            display=code_def.display,
        )

    # ----- Case 1: inline CodeSelector (Code 'x' from "SYSTEM") -----
    if isinstance(node, CodeSelector):
        system_url = cs_map.get(node.system, node.system)
        return _normalized_code_info(
            code=node.code,
            system=system_url,
            display=node.display,
        )

    # ----- Case 2: bare Identifier referring to a `code "X": ...` def -----
    if isinstance(node, Identifier):
        info = codes_map.get(node.name)
        if info is not None:
            return dict(info)
        # Could be a Concept name from `concept "X": { Code 'a' from S, ... }`.
        for concept_def in getattr(library, "concepts", []) or []:
            if concept_def.name == node.name:
                codes_list = []
                for cd in concept_def.codes:
                    if isinstance(cd, str):
                        # Reference to a named code declared elsewhere.
                        ref_info = codes_map.get(cd)
                        if ref_info is not None:
                            codes_list.append(dict(ref_info))
                    else:
                        system_url = cs_map.get(cd.codesystem, cd.codesystem)
                        codes_list.append(
                            _normalized_code_info(
                                code=cd.code,
                                system=system_url,
                                display=cd.display,
                            )
                        )
                return {
                    "codes": codes_list,
                    "is_concept": True,
                    "display": concept_def.display,
                }
        return None

    # ----- Case 3: QualifiedIdentifier like Lib."code-name" -----
    # We do not resolve cross-library code references in the static path;
    # the translator handles those via its library resolver. Return None so
    # the closure builder skips with a WARNING (per-seed fault tolerance).
    if isinstance(node, (QualifiedIdentifier, Property)):
        return None

    # ----- Case 4: Literal "system|code" string -----
    if isinstance(node, Literal) and isinstance(node.value, str):
        val = node.value
        if "|" in val and not val.strip().startswith("{"):
            system, code = val.rsplit("|", 1)
            return _normalized_code_info(code=code, system=system)
        return None

    # ----- Anything else (FunctionRef, ParameterRef, query alias, etc.) -----
    # is by definition not a statically-known code reference. The closure
    # builder skips it; the translator's instance-method path handles the
    # dynamic cases (ParameterPlaceholder, etc.) at translation time.
    return None
