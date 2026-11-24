"""Choosing an overload for a call whose argument types are statically known.

CQL 1.5 Developer's Guide, "Function Resolution": the least-converting
declared signature is chosen, and equally-converting signatures are an
ambiguous resolution error. :mod:`overload` is the authority for that
comparison; this module is the *call-site policy* on top of it (AMUX-167
Stage 1) and is deliberately conservative:

* the choice is used only when **every** argument's static type is known and
  exactly one candidate is the unique least-converting one — a unique exact
  match (rank 0) or a unique best rank above it;
* in every other case — an argument of unknown type, a tie, no callable
  candidate, a candidate whose parameters cannot be read — the answer is
  ``None``, which leaves the existing by-name resolution exactly as it was.

A conservative no-op is a correct outcome here: a changed answer on an
ambiguous call is not. Calls inside inlined library bodies typically have
arguments of unknown type (a parameter placeholder, a nested navigation the
model cannot type), and those keep today's declaration-order answer.

Only non-fluent calls are resolved here. A fluent call (``X.f(y)``) has a
receiver, which the fluent translator resolves from the receiver's resource
type (:meth:`SQLTranslationContext.get_function`); it is untouched.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, NamedTuple, Optional, Sequence

from .argument_types import argument_types
from .overload import (
    UNIQUE,
    CqlType,
    TypeModel,
    conversion_rank,
    format_type_specifier,
    parse_cql_type,
    resolve_least_converting,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .context import FunctionInfo, SQLTranslationContext


class ResolvedOverload(NamedTuple):
    """A call's chosen overload and the library it was declared in."""

    function: "FunctionInfo"
    library_name: Optional[str]


def declared_parameter_types(function: "FunctionInfo") -> List[Optional[CqlType]]:
    """A function's declared parameter types, ``None`` where unreadable."""
    return [
        parse_cql_type(format_type_specifier(getattr(parameter, "type", None)))
        for parameter in (getattr(function, "parameters", None) or [])
    ]


def _declared_overloads(
    context: "SQLTranslationContext", name: str
) -> tuple:
    """The overloads a call may resolve to, and the library they come from.

    ``Lib.f(...)`` names a function of an included library; an unqualified
    name is the library being translated.
    """
    library_name, _, bare_name = name.rpartition(".")
    if library_name:
        library = (getattr(context, "includes", None) or {}).get(library_name)
        if library is None:
            return [], library_name
        return list(getattr(library, "function_overloads", {}).get(bare_name, [])), library_name
    return list((getattr(context, "_function_overloads", None) or {}).get(name, [])), None


def choose_call_overload(
    context: "SQLTranslationContext", name: str, arguments: Sequence[Any]
) -> Optional[ResolvedOverload]:
    """The one overload this call resolves to, or ``None`` to keep today's answer.

    ``arguments`` are the call's argument expressions, whose static types are
    read with :func:`argument_types.argument_types`.
    """
    overloads, library_name = _declared_overloads(context, name)
    if len(overloads) < 2:
        # Nothing to choose: the by-name lookup already is the only candidate.
        return None
    candidates = [
        function
        for function in overloads
        if not getattr(function, "is_fluent", False)
        and getattr(function, "expression", None) is not None
        and len(getattr(function, "parameters", None) or []) == len(arguments)
    ]
    if len(candidates) < 2:
        # Either one candidate is left (nothing to choose) or the call's arity
        # rules them all out (not ours to decide).
        return None

    types = argument_types(context, arguments)
    if any(cql_type is None for cql_type in types):
        # An unknown argument type never excludes a candidate and never
        # favours one (:func:`overload.conversion_rank`), so a tie here is an
        # artefact of what this translator knows, not a property of the call.
        return None

    declared = [declared_parameter_types(function) for function in candidates]
    if any(
        declared_type is None
        for parameter_types in declared
        for declared_type in parameter_types
    ):
        return None

    model = TypeModel(context)
    ranks = [
        [conversion_rank(model, argument, parameter) for argument, parameter in zip(types, parameter_types)]
        for parameter_types in declared
    ]
    selection = resolve_least_converting(ranks)
    if selection.outcome != UNIQUE:
        return None
    return ResolvedOverload(candidates[selection.index], library_name)
