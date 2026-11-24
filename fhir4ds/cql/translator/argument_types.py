"""Static types of function-call arguments, for overload resolution.

An argument's type is needed to choose among a function's overloads
(:mod:`overload`). This module answers "what is the CQL type of this argument
expression?" from the CQL AST, or ``None`` when it cannot be determined.

Three sources, most precise first:

* a substituted function parameter (:class:`ParameterPlaceholder`) carries the
  type its parameter was declared with;
* navigation from a FHIR-typed root (``E.period.start``, ``Patient.gender``,
  ``Observation.value``) is typed from the FHIR model, so the declared type
  keeps its model identity (``FHIR.dateTime``, not ``DateTime``);
* everything else uses the lowering-authority inference
  (:func:`type_map.infer_cql_type_compat`).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple, Union

from ..parser.ast_nodes import BinaryExpression, Identifier, Property
from .overload import (
    ChoiceType,
    CqlType,
    ListType,
    NamedType,
    TypeModel,
    _same_named,
    fhir_system_name,
    parse_cql_type,
)
from .type_map import infer_cql_type_compat, is_fhir_resource_type, property_chain_parts

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..parser.ast_nodes import Expression

logger = logging.getLogger(__name__)

# One navigation step: the element's type name, the names of a choice
# element's alternatives, or ``None`` when the model does not know it; and
# whether the element is multi-valued.
_Step = Tuple[Union[str, List[str], None], bool]

# Anonymous inline types: the next path segment is looked up on the parent path.
_INLINE_TYPES = frozenset({"BackboneElement", "Element"})

_PATH2TYPE: Optional[Dict[str, str]] = None


def _path2type() -> Dict[str, str]:
    """Generated FHIR R4 metadata ``<type>.<path> -> element type``.

    The schema registry types resource-relative paths; this table also covers
    paths that continue into a datatype (``Period.start``, ``Coding.code``).
    """
    global _PATH2TYPE
    if _PATH2TYPE is None:
        try:
            metadata_path = (
                Path(__file__).resolve().parents[2]
                / "fhirpath" / "models" / "r4" / "path2Type.json"
            )
            with open(metadata_path, encoding="utf-8") as handle:
                _PATH2TYPE = json.load(handle)
        except (OSError, ValueError):
            logger.warning(
                "FHIR path-to-type metadata could not be loaded; FHIR navigation "
                "is untyped for overload resolution"
            )
            _PATH2TYPE = {}
    return _PATH2TYPE


def argument_type(context: Any, node: Any) -> Optional[CqlType]:
    """The static CQL type of a call argument, or ``None`` when unknown."""
    if node is None:
        return None
    if type(node).__name__ == "ParameterPlaceholder":
        return parse_cql_type(getattr(node, "cql_type", None))
    if isinstance(node, Property):
        navigated = _navigation_type(context, node)
        if navigated is not None:
            return navigated
    elif isinstance(node, Identifier):
        bound = _bound_type(context, node.name)
        if bound is not None:
            return bound
        combined = _definition_set_type(context, node.name)
        if combined is not None:
            return combined
    elif isinstance(node, BinaryExpression) and str(node.operator).lower() in _SET_OPERATORS:
        return _set_type(context, node)
    return _inferred(context, node)


def argument_types(context: Any, nodes: Sequence[Any]) -> List[Optional[CqlType]]:
    return [argument_type(context, node) for node in nodes]


# ---------------------------------------------------------------------------
# Set operations
# ---------------------------------------------------------------------------

_SET_OPERATORS = frozenset({"union", "intersect", "except"})


def _definition_ast(context: Any, name: str) -> Optional[Any]:
    ast = (getattr(context, "_definition_cql_asts", None) or {}).get(name)
    if ast is not None:
        return ast
    definition = (getattr(context, "expression_definitions", None) or {}).get(name)
    return getattr(definition, "expression", definition) if definition is not None else None


def _definition_set_type(context: Any, name: str) -> Optional[CqlType]:
    """Type of a definition that is a set operation (``[A] union [B]``).

    The lowering-authority inference reports a set operation's LEFT operand
    type; for overload resolution that is too specific (the value may be of
    either operand's type), so such a definition is typed as the choice.
    """
    source = _definition_ast(context, name)
    if isinstance(source, BinaryExpression) and str(source.operator).lower() in _SET_OPERATORS:
        return _set_type(context, source)
    return None


def _set_type(context: Any, node: BinaryExpression) -> Optional[CqlType]:
    """``A union B`` has a choice of the operands' element types."""
    left = argument_type(context, node.left)
    right = argument_type(context, node.right)
    if left is None or right is None or left == right:
        return left if left == right else None
    left_is_list, right_is_list = isinstance(left, ListType), isinstance(right, ListType)
    if left_is_list != right_is_list:
        return None
    members: List[CqlType] = []
    for side in (left.element if left_is_list else left, right.element if right_is_list else right):
        members.extend(side.choices if isinstance(side, ChoiceType) else [side])
    if any(not isinstance(member, NamedType) for member in members):
        return None
    model = TypeModel(context)
    distinct = [
        member for member in members
        if not any(
            other is not member
            and (_same_named(model, member, other) or model.is_subtype(member.name, other.name))
            for other in members
        )
    ]
    combined: CqlType = distinct[0] if len(distinct) == 1 else ChoiceType(tuple(distinct))
    return ListType(combined) if left_is_list else combined


# ---------------------------------------------------------------------------
# Names bound in scope
# ---------------------------------------------------------------------------


def _inferred(context: Any, node: Any) -> Optional[CqlType]:
    inferred = infer_cql_type_compat(context, node)
    if not inferred or inferred == "Any":
        return None
    return parse_cql_type(inferred)


def _definition_type(context: Any, name: str) -> Optional[CqlType]:
    """Type of a named definition, from its metadata or its expression."""
    meta = (getattr(context, "definition_meta", None) or {}).get(name)
    declared = parse_cql_type(getattr(meta, "cql_type", None))
    if declared is not None and not (isinstance(declared, NamedType) and declared.name == "Any"):
        return declared
    combined = _definition_set_type(context, name)
    if combined is not None:
        return combined
    source = _definition_ast(context, name)
    return _inferred(context, source) if source is not None else None


def _alias_type(context: Any, name: str) -> Optional[CqlType]:
    """Type of a query-alias element: what the alias's source yields.

    Read from the alias's own symbol (the definition or expression it ranges
    over) and from the query translator's alias resource-type map. If the two
    disagree the type is unknown: neither is trusted enough to reject a call.
    """
    element_types: List[Optional[CqlType]] = []
    symbol = context.lookup_symbol(name) if hasattr(context, "lookup_symbol") else None
    if symbol is not None and getattr(symbol, "symbol_type", None) == "alias":
        source = getattr(symbol, "ast_expr", None)
        if source is not None:
            element_types.append(_element_of(_inferred(context, source)))
        if getattr(symbol, "cte_name", None):
            element_types.append(_element_of(_definition_type(context, symbol.cte_name)))
    resource = (getattr(context, "_alias_resource_types", None) or {}).get(name)
    if resource:
        element_types.append(NamedType(resource))
    known = [element for element in element_types if element is not None]
    if not known:
        return None
    first = known[0]
    if any(not _same_type(other, first) for other in known[1:]):
        return None
    return first


def _element_of(cql_type: Optional[CqlType]) -> Optional[CqlType]:
    return cql_type.element if isinstance(cql_type, ListType) else cql_type


def _same_type(left: CqlType, right: CqlType) -> bool:
    return left == right


def _bound_type(context: Any, name: str) -> Optional[CqlType]:
    """Type of a name bound by a query alias, a ``let`` clause or a promotion alias."""
    promoted = (getattr(context, "_promotion_parameter_types", None) or {}).get(name)
    if promoted:
        return parse_cql_type(promoted)
    if hasattr(context, "lookup_symbol"):
        symbol = context.lookup_symbol(name)
        if symbol is not None and getattr(symbol, "symbol_type", None) == "alias":
            return _alias_type(context, name)
    alias_resource = (getattr(context, "_alias_resource_types", None) or {}).get(name)
    if alias_resource:
        return NamedType(alias_resource)
    source = (getattr(context, "_alias_source_asts", None) or {}).get(name)
    if source is not None:
        source_type = _inferred(context, source)
        if isinstance(source_type, ListType):
            # A query alias ranges over the elements of its source.
            return source_type.element
        return source_type
    let_expression = (getattr(context, "_let_clause_asts", None) or {}).get(name)
    if let_expression is not None:
        return _inferred(context, let_expression)
    return None


def _root_type(context: Any, name: str) -> Optional[NamedType]:
    """The FHIR type a navigation starts from, when ``name`` denotes one."""
    candidates: List[Optional[CqlType]] = [
        _bound_type(context, name),
        NamedType(name) if is_fhir_resource_type(context, name) else None,
    ]
    meta = (getattr(context, "definition_meta", None) or {}).get(name)
    declared = parse_cql_type(getattr(meta, "cql_type", None))
    if declared is not None and not (isinstance(declared, NamedType) and declared.name == "Any"):
        candidates.append(declared)
    candidates.append(_inferred(context, Identifier(name=name)))
    for candidate in candidates:
        if isinstance(candidate, ListType):
            candidate = candidate.element
        if isinstance(candidate, NamedType) and TypeModel(context).is_fhir_type(candidate.name):
            return candidate
    return None


# ---------------------------------------------------------------------------
# FHIR navigation
# ---------------------------------------------------------------------------


def _base_type(context: Any, name: str) -> str:
    """A profile's base FHIR type (the name itself for a plain type)."""
    resolved = TypeModel(context).profile_base(name)
    return resolved or name


def _lookup(context: Any, root: str, path: str, current_type: Optional[str]) -> _Step:
    """Type of the element at ``path`` below a value of type ``root``.

    The schema registry and the path table key resource-relative paths
    (``Encounter.location.period``); the path table also keys paths relative
    to a datatype (``Period.start``, ``Quantity.value``), which is what
    ``current_type`` is for.
    """
    schema = getattr(context, "fhir_schema", None)
    if schema is not None and root in getattr(schema, "resources", {}):
        if "." not in path and schema.is_choice_element(root, path):
            choices = schema.get_choice_types(root, path)
            if choices:
                return choices, schema.is_multi_valued_element(root, path)
        element_type = schema.get_element_type(root, path)
        if element_type is not None:
            return element_type, schema.is_multi_valued_element(root, path)
    element_type = _path2type().get(f"{root}.{path}")
    if element_type is None and current_type is not None:
        element_type = _path2type().get(f"{current_type}.{path.rsplit('.', 1)[-1]}")
    return (element_type, False) if element_type is not None else (None, False)


def _navigation_type(context: Any, node: Property) -> Optional[CqlType]:
    """Type of a property chain rooted at a FHIR-typed name (``E.period.start``)."""
    root, parts = property_chain_parts(node)
    if not root or not parts:
        return None
    root_type = _root_type(context, root)
    if root_type is None:
        return None
    root_name = _base_type(context, root_type.name)
    current: Optional[NamedType] = root_type
    is_list = False
    for index, part in enumerate(parts):
        stepped, multi_valued = _lookup(
            context, root_name, ".".join(parts[: index + 1]),
            None if current is None or current.name in _INLINE_TYPES else current.name,
        )
        is_primitive_value = False
        if stepped is None and part == "value" and current is not None \
                and fhir_system_name(current.name) is not None:
            # ``.value`` on a FHIR primitive yields the System value.
            stepped, is_primitive_value = fhir_system_name(current.name), True
        if stepped is None:
            return None
        is_list = is_list or multi_valued
        if isinstance(stepped, list):
            # A choice element: navigation beyond it is not typed.
            if index != len(parts) - 1:
                return None
            choice = ChoiceType(tuple(NamedType(name, "FHIR") for name in stepped))
            return ListType(choice) if is_list else choice
        if stepped.startswith("System."):
            current = NamedType(stepped[len("System."):], "System")
        elif is_primitive_value:
            current = NamedType(stepped, "System")
        else:
            current = NamedType(stepped, "FHIR")
    if current is None or current.name in _INLINE_TYPES:
        return None
    return ListType(current) if is_list else current
