"""CQL function overload resolution.

Single authority for choosing among a function's declared overloads.

CQL 1.5 Developer's Guide, "Function Resolution":

    Function resolution proceeds by attempting to match the signature of the
    invocation, i.e. the number and type of each argument, to a defined
    signature for the function. ... In these cases, the least converting
    signature is chosen, meaning the signature with the fewest required
    conversions. If multiple signatures have the same number of required
    conversions, an ambiguous resolution error is thrown.

and "Conversion Precedence", which orders the ways an invocation type can meet
a declared type from least to most converting (exact match, subtype, compatible,
cast, implicit conversion to a simple type, implicit conversion to a class
type, interval promotion, list demotion, interval demotion, list promotion).

The implicit conversions admitted here are exactly the ``Implicit`` cells of
CQL Reference Table 9-E (``Integer -> Long/Decimal/Quantity``,
``Long -> Decimal/Quantity``, ``Decimal -> Quantity``, ``Date -> DateTime``,
``Code -> Concept``). Everything else in that table is an ``Explicit``
``convert``/``To*`` conversion and is therefore NOT usable to resolve an
overload; in particular there is no ``Decimal -> Integer`` conversion at all.

Model knowledge (which names are FHIR types, how they nest) is injected through
:class:`TypeModel`, so the ranking functions are pure and are unit-tested
without a translation context or DuckDB.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from ..errors import TranslationError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..parser.ast_nodes import Expression, TypeSpecifier

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Conversion-precedence ranks (Developer's Guide, "Conversion Precedence")
# ---------------------------------------------------------------------------

EXACT = 0
SUBTYPE = 1
COMPATIBLE = 2
CAST = 3
IMPLICIT_SIMPLE = 4
IMPLICIT_CLASS = 5
INTERVAL_PROMOTION = 6
LIST_DEMOTION = 7
INTERVAL_DEMOTION = 8
LIST_PROMOTION = 9

RANK_NAMES = {
    EXACT: "exact match",
    SUBTYPE: "subtype",
    COMPATIBLE: "compatible",
    CAST: "cast",
    IMPLICIT_SIMPLE: "implicit conversion to a simple type",
    IMPLICIT_CLASS: "implicit conversion to a class type",
    INTERVAL_PROMOTION: "interval promotion",
    LIST_DEMOTION: "list demotion",
    INTERVAL_DEMOTION: "interval demotion",
    LIST_PROMOTION: "list promotion",
}

# Rank meaning "the argument cannot be passed at all".
NO_MATCH: Optional[int] = None

# Outcomes of comparing candidates.
UNIQUE = "unique"
AMBIGUOUS = "ambiguous"
NO_CANDIDATE = "no_candidate"

# Table 9-E ``Implicit`` cells among the System types, keyed by bare names.
_IMPLICIT_CONVERSIONS: Dict[Tuple[str, str], int] = {
    ("Integer", "Long"): IMPLICIT_SIMPLE,
    ("Integer", "Decimal"): IMPLICIT_SIMPLE,
    ("Integer", "Quantity"): IMPLICIT_CLASS,
    ("Long", "Decimal"): IMPLICIT_SIMPLE,
    ("Long", "Quantity"): IMPLICIT_CLASS,
    ("Decimal", "Quantity"): IMPLICIT_CLASS,
    ("Date", "DateTime"): IMPLICIT_SIMPLE,
    ("Code", "Concept"): IMPLICIT_CLASS,
}

# Every type the CQL language itself defines: the simple types of Table 3-G
# plus the structured types of Table 3-H and the CQL 1.5 Vocabulary family.
_SYSTEM_TYPES = frozenset({
    "Any", "Boolean", "Integer", "Long", "Decimal", "String", "Date", "DateTime", "Time",
    "Quantity", "Ratio", "Code", "Concept", "CodeSystem", "ValueSet", "Vocabulary",
})


# ---------------------------------------------------------------------------
# Type representation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NamedType:
    """A named type: ``name`` without its namespace, plus the namespace.

    ``namespace`` is ``"System"``, ``"FHIR"`` (any data-model qualifier), or
    ``None`` for an unqualified name.
    """

    name: str
    namespace: Optional[str] = None


@dataclass(frozen=True)
class ListType:
    element: "CqlType"


@dataclass(frozen=True)
class IntervalType:
    point: "CqlType"


@dataclass(frozen=True)
class ChoiceType:
    choices: Tuple["CqlType", ...]


@dataclass(frozen=True)
class TupleType:
    elements: Tuple[Tuple[str, "CqlType"], ...]


CqlType = Union[NamedType, ListType, IntervalType, ChoiceType, TupleType]

_DELIMITERS = frozenset('<>{}:,."`')


class _TypeSyntaxError(ValueError):
    """Raised when text is not a CQL type specifier."""


class _TypeParser:
    """Recursive-descent parser for CQL type-specifier text."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0

    def parse(self) -> CqlType:
        parsed = self._type()
        self._skip_ws()
        if self.pos != len(self.text):
            raise _TypeSyntaxError(f"unexpected {self.text[self.pos:]!r} in {self.text!r}")
        return parsed

    def _skip_ws(self) -> None:
        while self.pos < len(self.text) and self.text[self.pos].isspace():
            self.pos += 1

    def _at_symbol(self, symbol: str) -> bool:
        self._skip_ws()
        return self.text.startswith(symbol, self.pos)

    def _expect(self, symbol: str) -> None:
        if not self._at_symbol(symbol):
            raise _TypeSyntaxError(f"expected {symbol!r} at {self.pos} in {self.text!r}")
        self.pos += len(symbol)

    def _keyword(self, word: str) -> bool:
        self._skip_ws()
        end = self.pos + len(word)
        if self.text[self.pos:end] != word:
            return False
        if end < len(self.text) and (self.text[end].isalnum() or self.text[end] == "_"):
            return False
        self.pos = end
        return True

    def _type(self) -> CqlType:
        if self._keyword("List"):
            self._expect("<")
            element = self._type()
            self._expect(">")
            return ListType(element=element)
        if self._keyword("Interval"):
            self._expect("<")
            point = self._type()
            self._expect(">")
            return IntervalType(point=point)
        if self._keyword("Choice"):
            self._expect("<")
            choices = [self._type()]
            while not self._at_symbol(">"):
                self._expect(",")
                choices.append(self._type())
            self._expect(">")
            return ChoiceType(choices=tuple(choices))
        if self._keyword("Tuple"):
            self._expect("{")
            elements: List[Tuple[str, CqlType]] = []
            while not self._at_symbol("}"):
                element_name = self._segment()
                self._expect(":")
                elements.append((element_name, self._type()))
                if not self._at_symbol("}"):
                    self._expect(",")
            self._expect("}")
            return TupleType(elements=tuple(elements))
        return self._qualified_name()

    def _segment(self) -> str:
        self._skip_ws()
        if self.pos >= len(self.text):
            raise _TypeSyntaxError(f"unexpected end of {self.text!r}")
        quote = self.text[self.pos]
        if quote in ('"', "`"):
            end = self.text.find(quote, self.pos + 1)
            if end < 0:
                raise _TypeSyntaxError(f"unterminated identifier in {self.text!r}")
            segment = self.text[self.pos + 1:end]
            self.pos = end + 1
        else:
            start = self.pos
            while self.pos < len(self.text) and not self.text[self.pos].isspace() \
                    and self.text[self.pos] not in _DELIMITERS:
                self.pos += 1
            segment = self.text[start:self.pos]
        if not segment:
            raise _TypeSyntaxError(f"empty identifier at {self.pos} in {self.text!r}")
        return segment

    def _qualified_name(self) -> NamedType:
        parts = [self._segment()]
        while self._at_symbol("."):
            self.pos += 1
            parts.append(self._segment())
        if len(parts) == 1:
            return NamedType(name=parts[0])
        if parts[0] == "System":
            return NamedType(name=".".join(parts[1:]), namespace="System")
        # ``FHIR.X`` and every other data-model qualifier (``USCore.X``) name a
        # model type; the type is the last segment.
        return NamedType(name=parts[-1], namespace="FHIR")


def parse_cql_type(text: Optional[str]) -> Optional[CqlType]:
    """Parse CQL type-specifier text; ``None`` when it is not a type specifier."""
    if not isinstance(text, str):
        return None
    try:
        return _TypeParser(text.strip()).parse()
    except _TypeSyntaxError:
        return None


def format_type_specifier(specifier: Any) -> Optional[str]:
    """Render an AST type specifier as CQL type text (lossless for the five kinds)."""
    if specifier is None:
        return None
    if isinstance(specifier, str):
        return specifier.strip() or None
    name = getattr(specifier, "name", None)
    if isinstance(name, str):
        return name
    kind = type(specifier).__name__
    if kind == "ListTypeSpecifier":
        inner = format_type_specifier(specifier.element_type)
        return f"List<{inner}>" if inner else None
    if kind == "IntervalTypeSpecifier":
        point = format_type_specifier(specifier.point_type)
        return f"Interval<{point}>" if point else None
    if kind == "ChoiceTypeSpecifier":
        rendered = [format_type_specifier(choice) for choice in specifier.choices]
        if not rendered or any(item is None for item in rendered):
            return None
        return "Choice<" + ", ".join(rendered) + ">"
    if kind == "TupleTypeSpecifier":
        elements = [(element.name, format_type_specifier(element.type)) for element in specifier.elements]
        if any(item[1] is None for item in elements):
            return None
        return "Tuple{" + ", ".join(f"{n}: {t}" for n, t in elements) + "}"
    return None


def format_cql_type(cql_type: Optional[CqlType]) -> str:
    """Render a type for diagnostics; an unknown type renders as ``?``."""
    if cql_type is None:
        return "?"
    if isinstance(cql_type, NamedType):
        return f"{cql_type.namespace}.{cql_type.name}" if cql_type.namespace else cql_type.name
    if isinstance(cql_type, ListType):
        return f"List<{format_cql_type(cql_type.element)}>"
    if isinstance(cql_type, IntervalType):
        return f"Interval<{format_cql_type(cql_type.point)}>"
    if isinstance(cql_type, ChoiceType):
        return "Choice<" + ", ".join(format_cql_type(choice) for choice in cql_type.choices) + ">"
    return "Tuple{" + ", ".join(f"{n}: {format_cql_type(t)}" for n, t in cql_type.elements) + "}"


# ---------------------------------------------------------------------------
# Model knowledge
# ---------------------------------------------------------------------------

_FHIR_PARENTS: Optional[Dict[str, Optional[str]]] = None


def _fhir_parents() -> Dict[str, Optional[str]]:
    """FHIR R4 ``type -> parent`` (resources, datatypes, profiles, primitives).

    Loaded from the generated model metadata ``models/r4/type2Parent.json``,
    the canonical hierarchy the FHIRPath engine already uses.
    """
    global _FHIR_PARENTS
    if _FHIR_PARENTS is None:
        try:
            metadata_path = (
                Path(__file__).resolve().parents[2]
                / "fhirpath" / "models" / "r4" / "type2Parent.json"
            )
            with open(metadata_path, encoding="utf-8") as handle:
                _FHIR_PARENTS = json.load(handle)
        except (OSError, ValueError):
            logger.warning("FHIR type hierarchy metadata could not be loaded; FHIR subtyping is unavailable for overload resolution")
            _FHIR_PARENTS = {}
    return _FHIR_PARENTS


def fhir_system_name(fhir_name: str) -> Optional[str]:
    """The System type this translator carries a FHIR type as, when it has one."""
    from .inference import FHIR_TYPE_TO_CQL_TYPE

    return FHIR_TYPE_TO_CQL_TYPE.get(fhir_name)


class TypeModel:
    """The model knowledge the conversion lattice needs.

    ``context`` is the translation context, or ``None`` for a System-only
    model without data-model profiles.
    """

    def __init__(self, context: Any = None) -> None:
        self._context = context

    def is_fhir_type(self, name: str) -> bool:
        if name in _fhir_parents():
            return True
        return self.profile_base(name) is not None

    def is_known_type(self, named: NamedType) -> bool:
        """False for a model type this translator has no hierarchy for.

        The generated FHIR model metadata carries resources, datatypes,
        primitives and profiles, but not every type a data model may name
        (FHIR enumerations such as ``ObservationStatus`` are one family).
        """
        if named.namespace == "System":
            return named.name in _SYSTEM_TYPES
        if named.namespace == "FHIR":
            return self.is_fhir_type(named.name)
        return named.name in _SYSTEM_TYPES or self.is_fhir_type(named.name)

    def is_string_like(self, named: NamedType) -> bool:
        """True for a type whose values this translator carries as text."""
        return _carried_as(self, named) == "String"

    def parent(self, name: str) -> Optional[str]:
        base = self.profile_base(name)
        return base if base is not None else _fhir_parents().get(name)

    def is_subtype(self, subtype: str, supertype: str) -> bool:
        current = self.parent(subtype)
        for _ in range(16):
            if current is None:
                return False
            if current == supertype:
                return True
            current = self.parent(current)
        return False

    def profile_base(self, name: str) -> Optional[str]:
        """The base FHIR type of a named profile (``None`` for a plain type)."""
        registry = getattr(self._context, "profile_registry", None) if self._context is not None else None
        if registry is None:
            return None
        resolved = registry.resolve_named_profile(name)
        if resolved is None:
            return None
        base = resolved[0]
        return base if base and base != name else None


# ---------------------------------------------------------------------------
# Conversion precedence
# ---------------------------------------------------------------------------


def _is_any(cql_type: Optional[CqlType]) -> bool:
    return isinstance(cql_type, NamedType) and cql_type.name == "Any"


def _same_named(model: TypeModel, left: NamedType, right: NamedType) -> bool:
    if left.name != right.name:
        return False
    namespaces = {left.namespace, right.namespace}
    if len(namespaces) == 1:
        return True
    # An unqualified name is a System name (``System.`` is implicit) and, when
    # the data model defines a type of that name, also that model type.
    if namespaces == {None, "System"}:
        return True
    return None in namespaces and model.is_fhir_type(left.name)


def _carried_as(model: TypeModel, named: NamedType) -> Optional[str]:
    """The System type name a named type is carried as (``None`` for model-only types).

    An unqualified name is a FHIR type when the data model defines one of that
    name (``dateTime``, ``Period``, ``Condition``), and a System type otherwise.
    """
    is_fhir = named.namespace == "FHIR" or (
        named.namespace is None and model.is_fhir_type(named.name)
    )
    return fhir_system_name(named.name) if is_fhir else named.name


def _same_value_type(model: TypeModel, left: NamedType, right: NamedType) -> bool:
    """True when two named types denote the same kind of value to this translator:
    the same type, or a FHIR type and the System type it is carried as."""
    if _same_named(model, left, right):
        return True
    carried = _carried_as(model, left)
    return carried is not None and carried == _carried_as(model, right)


def _named_rank(model: TypeModel, argument: NamedType, parameter: NamedType) -> Optional[int]:
    if _is_any(argument):
        return COMPATIBLE
    if _is_any(parameter):
        return SUBTYPE
    if _same_named(model, argument, parameter):
        return EXACT
    if model.is_subtype(argument.name, parameter.name):
        return SUBTYPE
    if not model.is_known_type(argument) or not model.is_known_type(parameter):
        # A model type without a hierarchy (a FHIR enumeration): this
        # translator cannot say how it relates, so it excludes only what it
        # cannot hold. Such values are codes, i.e. text.
        known = parameter if model.is_known_type(parameter) else argument
        return COMPATIBLE if model.is_string_like(known) else NO_MATCH
    if model.profile_base(argument.name) is not None and model.profile_base(parameter.name) is not None:
        # Two profiles of the same base type. This translator knows profiles
        # only down to their base resource, not whether one derives from the
        # other (in US Core 7 the laboratory-result observation profile derives
        # from the clinical-result one), so it cannot rule the call out.
        return COMPATIBLE
    argument_system = _carried_as(model, argument)
    parameter_system = _carried_as(model, parameter)
    if argument_system is None or parameter_system is None:
        return NO_MATCH
    if argument_system == parameter_system:
        # A FHIR type and the System type this translator carries it as
        # (``dateTime``/``instant`` ~ ``DateTime``, ``CodeableConcept`` ~ ``Concept``).
        return IMPLICIT_SIMPLE
    return _IMPLICIT_CONVERSIONS.get((argument_system, parameter_system), NO_MATCH)


def _relates_without_conversion(model: TypeModel, left: NamedType, right: NamedType) -> bool:
    """True when values of the two types relate as given, with no conversion.

    Either direction counts: a profile is a base type, and a base type is
    compatible with a choice of its profiles. A FHIR type and the System type
    it is carried as are the same values.
    """
    if _same_value_type(model, left, right):
        return True
    for one, other in ((left, right), (right, left)):
        rank = _named_rank(model, one, other)
        if rank is not NO_MATCH and rank <= CAST:
            return True
    return False


def _choice_to_named_rank(model: TypeModel, argument: ChoiceType, parameter: NamedType) -> Optional[int]:
    if all(
        isinstance(choice, NamedType) and _relates_without_conversion(model, choice, parameter)
        for choice in argument.choices
    ):
        # Every alternative already is a value of the declared type.
        return COMPATIBLE
    # Cast: the choice includes the declared type (or a subtype of it).
    if any(
        isinstance(choice, NamedType)
        and (
            _same_value_type(model, choice, parameter)
            or model.is_subtype(choice.name, parameter.name)
        )
        for choice in argument.choices
    ):
        return CAST
    return NO_MATCH


def _reshaped(
    model: TypeModel, value: CqlType, target: CqlType, rank: int
) -> Optional[int]:
    """Promote or demote ``value`` to ``target`` when no conversion of the value is needed."""
    inner = conversion_rank(model, value, target)
    return rank if inner is not NO_MATCH and inner <= CAST else NO_MATCH


def conversion_rank(
    model: TypeModel, argument: Optional[CqlType], parameter: Optional[CqlType]
) -> Optional[int]:
    """Rank how ``argument`` meets a parameter declared as ``parameter``.

    ``argument is None`` means the argument's static type is unknown. It is
    treated like ``Any`` (rank ``COMPATIBLE``): it never excludes a candidate
    and never favours one. ``parameter is None`` (declared type unreadable) is
    likewise compatible with anything. Returns ``NO_MATCH`` (``None``) when the
    argument cannot be passed at all.
    """
    if argument is None or parameter is None:
        return COMPATIBLE
    if _is_any(parameter):
        return SUBTYPE
    if _is_any(argument):
        return COMPATIBLE

    if isinstance(parameter, NamedType):
        if isinstance(argument, NamedType):
            return _named_rank(model, argument, parameter)
        if isinstance(argument, ChoiceType):
            return _choice_to_named_rank(model, argument, parameter)
        if isinstance(argument, ListType):
            return _reshaped(model, argument.element, parameter, LIST_DEMOTION)
        if isinstance(argument, IntervalType):
            return _reshaped(model, argument.point, parameter, INTERVAL_DEMOTION)
        return NO_MATCH

    if isinstance(argument, NamedType):
        if isinstance(parameter, ListType):
            return _reshaped(model, argument, parameter.element, LIST_PROMOTION)
        if isinstance(parameter, IntervalType):
            return _reshaped(model, argument, parameter.point, INTERVAL_PROMOTION)
        if isinstance(parameter, ChoiceType):
            # A plain value is a choice of one type: compatible when it
            # relates to a declared alternative without a conversion.
            return COMPATIBLE if any(
                isinstance(choice, NamedType) and _relates_without_conversion(model, argument, choice)
                for choice in parameter.choices
            ) else NO_MATCH
        return NO_MATCH

    if isinstance(argument, ListType) and isinstance(parameter, ListType):
        return conversion_rank(model, argument.element, parameter.element)
    if isinstance(argument, IntervalType) and isinstance(parameter, IntervalType):
        return conversion_rank(model, argument.point, parameter.point)

    if isinstance(argument, ChoiceType) and isinstance(parameter, ChoiceType):
        # A choice can be passed where another choice is declared when the
        # two overlap: a value of the argument's type is then cast to the
        # declared alternatives (e.g. a FHIR ``effective`` choice into
        # QICoreCommon.toInterval's choice). Unrelated choices cannot.
        overlaps = any(
            isinstance(mine, NamedType) and isinstance(declared, NamedType)
            and _relates_without_conversion(model, mine, declared)
            for mine in argument.choices
            for declared in parameter.choices
        )
        return COMPATIBLE if overlaps else NO_MATCH

    if isinstance(argument, TupleType) and isinstance(parameter, TupleType):
        # Class and tuple types are compatible when the elements of one are a subset of the other's, by name.
        mine = dict(argument.elements)
        theirs = dict(parameter.elements)
        if all(name in mine for name, _ in parameter.elements):
            return COMPATIBLE if all(
                conversion_rank(model, mine[name], declared) is not NO_MATCH
                for name, declared in parameter.elements
            ) else NO_MATCH
        if all(name in theirs for name, _ in argument.elements):
            return COMPATIBLE
        return NO_MATCH

    return NO_MATCH


@dataclass(frozen=True)
class Selection:
    """Outcome of comparing candidates by their conversion paths."""

    outcome: str
    index: Optional[int] = None
    tied: Tuple[int, ...] = ()


def _dominates(left: Sequence[Optional[int]], right: Sequence[Optional[int]]) -> bool:
    """``left`` converts no more than ``right`` at every argument and less at one."""
    return all(a <= b for a, b in zip(left, right)) and list(left) != list(right)


def resolve_least_converting(ranks: Sequence[Sequence[Optional[int]]]) -> Selection:
    """Pick the least-converting candidate from per-argument rank rows.

    A candidate with any ``NO_MATCH`` argument is not callable. Among the
    callable candidates, one is dropped when another is at least as good at
    every argument and strictly better at one. One survivor wins
    (``UNIQUE``); several survivors are ``AMBIGUOUS``; none means ``NO_CANDIDATE``.
    """
    callable_candidates = [index for index, row in enumerate(ranks) if all(rank is not NO_MATCH for rank in row)]
    if not callable_candidates:
        return Selection(NO_CANDIDATE)
    best = tuple(
        index
        for index in callable_candidates
        if not any(_dominates(ranks[other], ranks[index]) for other in callable_candidates if other != index)
    )
    if len(best) == 1:
        return Selection(UNIQUE, index=best[0])
    return Selection(AMBIGUOUS, tied=best)


def _visible(cql_type: Optional[CqlType]) -> Optional[str]:
    """A type as this translator's value model sees it (FHIR types via their System name)."""
    if cql_type is None:
        return None
    if isinstance(cql_type, NamedType):
        carried = _carried_as(TypeModel(), cql_type)
        return f"System.{carried}" if carried else f"FHIR.{cql_type.name}"
    if isinstance(cql_type, ListType):
        return f"List<{_visible(cql_type.element)}>"
    if isinstance(cql_type, IntervalType):
        return f"Interval<{_visible(cql_type.point)}>"
    if isinstance(cql_type, ChoiceType):
        return "Choice<" + ",".join(sorted(_visible(choice) or "?" for choice in cql_type.choices)) + ">"
    return "Tuple{" + ",".join(f"{name}:{_visible(kind)}" for name, kind in cql_type.elements) + "}"


def _is_provable_ambiguity(
    declared: Sequence[Sequence[Optional[CqlType]]],
    argument_types: Sequence[Optional[CqlType]],
    tied: Tuple[int, ...],
) -> bool:
    """True when a tie is a real spec-level ambiguity this translator can adjudicate.

    It is provable only if some argument position has a known type AND the
    tied overloads declare types the translator's value model can tell apart
    there. A tie caused by an unknown or ``Any`` argument, or by overloads that
    are indistinguishable in the value model (FHIR ``dateTime`` and ``instant``
    are both carried as ``DateTime``), is not something it can decide.
    """
    for position, argument in enumerate(argument_types):
        if argument is None or _is_any(argument):
            continue
        first = _visible(declared[tied[0]][position])
        if any(_visible(declared[candidate][position]) != first for candidate in tied[1:]):
            return True
    return False


def _signature(parameter_types: Sequence[Optional[CqlType]]) -> str:
    return "(" + ", ".join(format_cql_type(kind) for kind in parameter_types) + ")"


_WARNED: Set[Tuple[str, ...]] = set()
_WARNED_LIMIT = 5000


def warn_once(key: Tuple[str, ...], message: str) -> None:
    """Log ``message`` at WARNING once per ``key`` (bounded, per process)."""
    if key in _WARNED:
        return
    if len(_WARNED) < _WARNED_LIMIT:
        _WARNED.add(key)
    logger.warning(message)


def choose_overload(
    function_label: str,
    declared: Sequence[Sequence[Optional[CqlType]]],
    argument_types: Sequence[Optional[CqlType]],
    legacy_index: int,
    model: Optional[TypeModel] = None,
) -> Tuple[int, bool]:
    """Choose one overload for a call; return ``(candidate index, used_legacy_fallback)``.

    ``declared[i]`` are candidate ``i``'s parameter types (``None`` where the
    type could not be read); every candidate must already match the call's
    arity. ``argument_types`` holds each argument's static type or ``None``
    when unknown. ``legacy_index`` is the candidate the by-name lookup would
    have returned.

    Raises:
        TranslationError: when no candidate is callable, or when candidates
            convert equally and the ambiguity is provable ("an ambiguous
            resolution error is thrown").
    """
    model = model or TypeModel()
    ranks = [
        [conversion_rank(model, argument, parameter) for argument, parameter in zip(argument_types, declared[candidate])]
        for candidate in range(len(declared))
    ]
    selection = resolve_least_converting(ranks)
    if selection.outcome == UNIQUE:
        return selection.index, False

    arguments_text = "(" + ", ".join(format_cql_type(kind) for kind in argument_types) + ")"
    if selection.outcome == NO_CANDIDATE:
        overloads = ", ".join(f"'{function_label}{_signature(types)}'" for types in declared)
        raise TranslationError(
            f"Cannot resolve call to function '{function_label}'{arguments_text}: no overload is "
            "callable with these argument types (CQL 1.5 Table 9-E defines no implicit conversion "
            f"for at least one argument). Declared overloads: {overloads}"
        )

    tied_signatures = ", ".join(
        f"'{function_label}{_signature(declared[candidate])}'" for candidate in selection.tied
    )
    if _is_provable_ambiguity(declared, argument_types, selection.tied):
        raise TranslationError(
            f"Ambiguous call to function '{function_label}'{arguments_text}: the overloads "
            f"{tied_signatures} all apply with the same number of required conversions. "
            "Add an explicit cast or conversion to choose one (CQL 1.5 Developer's Guide, Function Resolution)."
        )

    # Not provable: the tie comes from types this translator cannot determine
    # or distinguish. Keep the declaration-order pick rather than fail a
    # library that resolved before, but say so.
    warn_once(
        (function_label, arguments_text, tied_signatures),
        f"Overloads of function '{function_label}' ({tied_signatures}) are equally applicable to "
        f"arguments {arguments_text} and cannot be told apart statically; using the last-declared "
        "overload. Add an explicit cast to the argument if a different overload is intended.",
    )
    return legacy_index, True
