"""Post-translation CQL type map builder.

Computes a structural :class:`CQLTypeRef` for every library definition
AFTER translation completes and attaches it to the definition's
:class:`~fhir4ds.cql.translator.context.DefinitionMeta` via the additive
``cql_type_ref`` field.

Design invariants (FEATURE_CQL_TYPE_SYSTEM.md):

- **Read-only + one additive field.** The builder never mutates
  ``DefinitionMeta.cql_type`` or any lowering state, so generated SQL is
  byte-identical with or without this module (guarded by the DQM corpus
  baseline gate).
- **Declaration-order safe.** ``definition_meta`` is populated in
  declaration order (the translator's phase-1 loop), so the builder runs
  its own memoized dependency walk with a cycle cutoff rather than
  assuming any particular population order.
- **Never guesses.** Uncertainty-returning surfaces (``AgeIn*``,
  ``duration/difference in <prec> between``) and uncast choice-type
  disjunctions are typed ``Any`` so the facade defers to runtime
  inference instead of emitting misleading ``cqf-cqlType`` extensions.
- **``sql_result_type`` is an input, not an oracle.** When AST-derived
  typing yields ``Any`` and the lowering recorded a physical result hint
  (e.g. ``Quantity``), the hint seeds the type ref — the facade never
  trusts a physical hint blind.

The expression typing mirrors ``InferenceMixin._infer_cql_type`` for the
node families covered by this unit (literals, selectors, casts, operators,
unwrappers, retrieves). Query/property/function typing lands in later
units; unknown nodes silently resolve to ``Any``.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Set

from ..types.typeref import ANY_TYPE, CQLTypeRef

# Builtin functions whose results are runtime-uncertainty surfaces: the
# physical result is a VARCHAR holding either an integer or a closed
# interval JSON (CQL-21 doctrine). Typing them Integer would force the
# facade into rescue-WARNING on every uncertain patient, so they defer
# to runtime inference.
_UNCERTAIN_RESULT_FUNCTIONS = frozenset({
    "ageinyears", "ageinmonths", "ageinweeks", "ageindays",
    "ageinhours", "ageinminutes", "ageinseconds",
    "ageinyearsat", "ageinmonthsat", "ageinweeksat", "ageindaysat",
    "ageinhoursat", "ageinminutesat", "ageinsecondsat",
    "calculateageinyears", "calculateageinmonths", "calculateageinweeks",
    "calculateageindays", "calculateageinhours", "calculateageinminutes",
    "calculateageinseconds", "calculateageinyearsat",
    "calculateageinmonthsat", "calculateageinweeksat",
    "calculateageindaysat", "calculateageinhoursat",
    "calculateageinminutesat", "calculateageinsecondsat",
})

_TO_FUNCTION_TYPES = {
    "toboolean": "Boolean",
    "tointeger": "Integer",
    "tolong": "Long",
    "todecimal": "Decimal",
    "tostring": "String",
    "todate": "Date",
    "todatetime": "DateTime",
    "totime": "Time",
    "toquantity": "Quantity",
    "toratio": "Ratio",
    "toconcept": "Concept",
}

_COMPARISON_OPERATORS = frozenset({
    '=', '!=', '<>', '<', '>', '<=', '>=',
    'and', 'or', 'xor', 'implies',
    'on or before', 'on or after', 'before', 'after',
    'starts', 'ends', 'during', 'overlaps', 'in',
    '~', '!~', 'equivalent', 'not equivalent',
    'same or before', 'same or after',
    'includes', 'included in',
    'properly includes', 'properly included in',
    'meets', 'meets before', 'meets after',
    'contains', 'is',
})

_TEMPORAL_TYPES = ("Date", "DateTime", "Time")


def _simple(name: str) -> CQLTypeRef:
    return CQLTypeRef(name)


_TYPE_CACHE: Dict[str, CQLTypeRef] = {}


def _shared_simple(name: str) -> CQLTypeRef:
    """Intern simple type refs (immutable dataclasses; cuts allocation)."""
    ref = _TYPE_CACHE.get(name)
    if ref is None:
        ref = CQLTypeRef(name)
        _TYPE_CACHE[name] = ref
    return ref


class TypeMapBuilder:
    """Builds and attaches ``cql_type_ref`` metadata for library defines."""

    def __init__(self, context: Any) -> None:
        self._context = context
        self._memo: Dict[str, CQLTypeRef] = {}
        self._visiting: Set[str] = set()
        self._visiting_functions: Set[str] = set()

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def attach(self) -> Dict[str, CQLTypeRef]:
        """Type every known definition and attach refs to ``DefinitionMeta``.

        Returns the memo map (definition name -> type ref) for tests and
        gap reporting.
        """
        expression_definitions = getattr(self._context, "expression_definitions", {}) or {}
        for name in expression_definitions:
            ref = self._definition_type(name)
            if ref.bare_name == "Any":
                meta = self._context.definition_meta.get(name)
                hint = getattr(meta, "sql_result_type", None) if meta else None
                if hint:
                    ref = CQLTypeRef.parse(str(hint))
            meta = self._context.definition_meta.get(name)
            if meta is not None:
                meta.cql_type_ref = ref
        return dict(self._memo)

    # ------------------------------------------------------------------
    # Definition-level resolution
    # ------------------------------------------------------------------

    def _definition_type(self, name: str) -> CQLTypeRef:
        if name in self._memo:
            return self._memo[name]
        if name in self._visiting:
            # Cycle: the translator's own inference cuts off here too.
            return ANY_TYPE
        self._visiting.add(name)
        try:
            expression_definitions = getattr(self._context, "expression_definitions", {}) or {}
            ast = expression_definitions.get(name)
            if ast is None:
                # Prefer already-recorded metadata for the pre-registered
                # name (e.g. promoted defines) before giving up.
                meta = self._context.definition_meta.get(name)
                if meta is not None and meta.cql_type != "Any":
                    ref = CQLTypeRef.parse(meta.cql_type)
                else:
                    ref = ANY_TYPE
            else:
                ref = self.type_of(ast)
        finally:
            self._visiting.discard(name)
        self._memo[name] = ref
        return ref

    # ------------------------------------------------------------------
    # Expression typing
    # ------------------------------------------------------------------

    def type_of(self, node: Any) -> CQLTypeRef:
        """Compute the structural CQL type of an expression AST node."""
        if node is None:
            return ANY_TYPE

        from ..parser import ast_nodes as N

        # ---- literals (source 1) ------------------------------------
        if isinstance(node, N.Literal):
            explicit_type = getattr(node, "type", None)
            if explicit_type:
                bare = str(explicit_type).split(".")[-1]
                if bare in {"Boolean", "Integer", "Long", "Decimal", "String"}:
                    return _shared_simple(bare)
            value = node.value
            if isinstance(value, bool):
                return _shared_simple("Boolean")
            if isinstance(value, int):
                return _shared_simple("Integer")
            if isinstance(value, float):
                return _shared_simple("Decimal")
            if isinstance(value, str):
                return _shared_simple("String")
            return ANY_TYPE

        # ---- selectors (source 2) -----------------------------------
        if isinstance(node, N.CodeSelector):
            return _shared_simple("Code")

        if isinstance(node, N.Quantity):
            return _shared_simple("Quantity")

        if isinstance(node, N.DateTimeLiteral):
            value = str(getattr(node, "value", "") or "")
            if value.startswith("T"):
                return _shared_simple("Time")
            return _shared_simple("DateTime" if "T" in value else "Date")

        if isinstance(node, N.TimeLiteral):
            return _shared_simple("Time")

        if isinstance(node, N.ListExpression):
            element_types = [
                t for t in (self.type_of(el) for el in node.elements)
                if t.bare_name != "Any"
            ]
            if not element_types:
                return CQLTypeRef("List", args=(ANY_TYPE,))
            first = element_types[0]
            if all(t == first for t in element_types):
                return CQLTypeRef("List", args=(first,))
            return CQLTypeRef("List", args=(ANY_TYPE,))

        if isinstance(node, N.TupleExpression):
            # TupleElement.type holds the VALUE expression in tuple
            # selectors (verified against the parser).
            fields = tuple(
                (el.name, self.type_of(el.type)) for el in node.elements
            )
            return CQLTypeRef("Tuple", fields=fields)

        if isinstance(node, N.Interval):
            point = ANY_TYPE
            if node.low is not None:
                point = self.type_of(node.low)
            elif node.high is not None:
                point = self.type_of(node.high)
            return CQLTypeRef("Interval", args=(point,))

        if isinstance(node, N.InstanceExpression):
            type_name = str(getattr(node, "type", "") or "")
            bare = type_name.split(".")[-1] if "." in type_name else type_name
            if bare in {
                "Code", "Concept", "ValueSet", "CodeSystem",
                "Vocabulary", "Quantity", "Ratio",
            }:
                return _shared_simple(bare)
            return ANY_TYPE

        # ---- retrieves (source 5) -----------------------------------
        if isinstance(node, N.Retrieve):
            resource_type = getattr(node, "type", "Resource") or "Resource"
            return CQLTypeRef("List", args=(_simple(str(resource_type)),))

        # ---- unwrappers (source 13) ---------------------------------
        if isinstance(node, N.ExistsExpression):
            return _shared_simple("Boolean")

        if isinstance(node, N.DistinctExpression):
            return self.type_of(node.source)

        if isinstance(node, (N.FirstExpression, N.LastExpression)):
            return self._unwrap_list(self.type_of(node.source))

        # ---- operators (sources 4) ----------------------------------
        if isinstance(node, N.BinaryExpression):
            return self._binary_type(node)

        if isinstance(node, N.UnaryExpression):
            return self._unary_type(node)

        if isinstance(node, N.ConditionalExpression):
            then_type = self.type_of(node.then_expr)
            else_type = self.type_of(node.else_expr)
            if then_type == else_type:
                return then_type
            return ANY_TYPE

        # ---- identifiers: symbol table + define chains ---------------
        if isinstance(node, N.Identifier):
            return self._identifier_type(node)

        if isinstance(node, N.QualifiedIdentifier):
            return self._qualified_identifier_type(node)

        if isinstance(node, N.AliasRef):
            # Alias refs are typed by the scoped-symbol walker; outside a
            # query scope they carry no static type.
            return ANY_TYPE

        # ---- properties (source 8) ----------------------------------
        if isinstance(node, N.Property):
            return self._property_type(node)

        # ---- queries (source 9) --------------------------------------
        if isinstance(node, N.Query):
            return self._query_type(node)

        # ---- function calls: builtin table only in this unit ---------
        if isinstance(node, N.FunctionRef):
            return self._function_type(node)

        # Method invocations and everything else land in later units;
        # unknown never blocks SQL generation.
        return ANY_TYPE

    # ------------------------------------------------------------------
    # Operator typing
    # ------------------------------------------------------------------

    def _binary_type(self, node: Any) -> CQLTypeRef:
        from ..parser import ast_nodes as N

        op = str(getattr(node, "operator", "") or "").lower()

        # "duration in X between" parses as BinaryExpression(op='in',
        # left=Identifier('duration'), right=DurationBetween(...)). It is
        # an uncertainty surface at runtime -> Any (never Integer).
        if (
            op == "in"
            and isinstance(node.left, N.Identifier)
            and node.left.name.lower() == "duration"
            and isinstance(node.right, (N.DurationBetween, N.DifferenceBetween))
        ):
            return ANY_TYPE

        if isinstance(node, (N.DurationBetween, N.DifferenceBetween)):
            return ANY_TYPE

        if op in _COMPARISON_OPERATORS:
            return _shared_simple("Boolean")
        if op.startswith("same "):
            return _shared_simple("Boolean")

        if op in ("intersect", "union", "except"):
            left_type = self.type_of(node.left)
            if left_type.bare_name != "Any":
                return left_type
            return self.type_of(node.right)

        if op in ("+", "-"):
            left_type = self.type_of(node.left)
            right_type = self.type_of(node.right)
            if left_type.bare_name in _TEMPORAL_TYPES:
                return left_type
            if right_type.bare_name in _TEMPORAL_TYPES:
                return right_type
            if "Quantity" in (left_type.bare_name, right_type.bare_name):
                return _shared_simple("Quantity")
            if "Decimal" in (left_type.bare_name, right_type.bare_name):
                return _shared_simple("Decimal")
            if "Long" in (left_type.bare_name, right_type.bare_name):
                return _shared_simple("Long")
            if "Integer" in (left_type.bare_name, right_type.bare_name):
                return _shared_simple("Integer")
            return ANY_TYPE

        if op in ("*", "/", "div", "mod", "^"):
            left_type = self.type_of(node.left)
            right_type = self.type_of(node.right)
            if "Quantity" in (left_type.bare_name, right_type.bare_name):
                return _shared_simple("Quantity")
            if "Decimal" in (left_type.bare_name, right_type.bare_name) or op == "/":
                return _shared_simple("Decimal")
            if "Long" in (left_type.bare_name, right_type.bare_name):
                return _shared_simple("Long")
            if "Integer" in (left_type.bare_name, right_type.bare_name):
                return _shared_simple("Integer")
            return ANY_TYPE

        if op in ("as", "convert"):
            return self._cast_type(node)

        return ANY_TYPE

    def _cast_type(self, node: Any) -> CQLTypeRef:
        from ..parser import ast_nodes as N

        target = node.right
        if isinstance(target, N.NamedTypeSpecifier):
            name = getattr(target, "name", None)
        elif isinstance(target, N.Identifier):
            name = target.name
        else:
            return ANY_TYPE
        if not name:
            return ANY_TYPE
        bare = str(name).split(".")[-1]
        source_type = self.type_of(node.left)
        if bare == "Any":
            return source_type
        if bare == "Vocabulary" and source_type.bare_name in {"ValueSet", "CodeSystem"}:
            return source_type
        return _simple(str(name)) if "." not in str(name) else _simple(bare)

    def _unary_type(self, node: Any) -> CQLTypeRef:
        op = str(getattr(node, "operator", "") or "").lower()
        if op in ("not", "is null", "is not null", "is true", "is false",
                  "is not true", "is not false"):
            return _shared_simple("Boolean")
        if op == "singleton from":
            return self._unwrap_list(self.type_of(node.operand))
        if op in ("+", "-", "predecessor of", "successor of"):
            return self.type_of(node.operand)
        return ANY_TYPE

    # ------------------------------------------------------------------
    # Identifier / function typing
    # ------------------------------------------------------------------

    def _identifier_type(self, node: Any) -> CQLTypeRef:
        name = node.name

        if name in (getattr(self._context, "valuesets", {}) or {}):
            return _shared_simple("ValueSet")
        if name in (getattr(self._context, "codesystems", {}) or {}):
            return _shared_simple("CodeSystem")
        code_info = (getattr(self._context, "codes", {}) or {}).get(name)
        if code_info:
            return _shared_simple("Concept" if code_info.get("is_concept") else "Code")

        param_info = (getattr(self._context, "parameters", {}) or {}).get(name)
        if param_info is not None and getattr(param_info, "cql_type", None):
            return CQLTypeRef.parse(str(param_info.cql_type))

        meta = self._context.definition_meta.get(name)
        if meta is not None and getattr(meta, "cql_type", "Any") != "Any":
            return CQLTypeRef.parse(meta.cql_type)

        # Define-of-define chains: memoized recursion with cycle cutoff.
        return self._definition_type(name)

    def _qualified_identifier_type(self, node: Any) -> CQLTypeRef:
        """Library-qualified references (``Alias.Def`` from includes)."""
        parts = list(getattr(node, "parts", []) or [])
        if len(parts) != 2:
            return ANY_TYPE
        prefixed = f"{parts[0]}.{parts[1]}"
        meta = self._context.definition_meta.get(prefixed)
        if meta is not None:
            if getattr(meta, "cql_type_ref", None) is not None:
                return meta.cql_type_ref
            if getattr(meta, "cql_type", "Any") != "Any":
                return CQLTypeRef.parse(meta.cql_type)
            hint = getattr(meta, "sql_result_type", None)
            if hint:
                return CQLTypeRef.parse(str(hint))
        return ANY_TYPE

    def _function_type(self, node: Any) -> CQLTypeRef:
        from ..parser import ast_nodes as N

        func_name = str(getattr(node, "name", "") or "").lower()

        if func_name in _UNCERTAIN_RESULT_FUNCTIONS:
            # Runtime integer-or-interval JSON VARCHAR -> defer.
            return ANY_TYPE

        if func_name in ("count", "indexof"):
            return _shared_simple("Integer")

        if func_name in _TO_FUNCTION_TYPES:
            return _shared_simple(_TO_FUNCTION_TYPES[func_name])

        if func_name == "date":
            return _shared_simple("Date")
        if func_name in ("datetime", "now", "today"):
            return _shared_simple("DateTime")
        if func_name in ("time", "timeofday"):
            return _shared_simple("Time")

        if func_name in ("first", "last"):
            if node.arguments:
                return self._unwrap_list(self.type_of(node.arguments[0]))
            return ANY_TYPE

        if func_name == "distinct":
            if node.arguments:
                return self.type_of(node.arguments[0])
            return CQLTypeRef("List", args=(ANY_TYPE,))

        if func_name == "flatten":
            if node.arguments:
                source = self.type_of(node.arguments[0])
                if source.bare_name == "List" and source.args:
                    inner = source.args[0]
                    if inner.bare_name == "List" and inner.args:
                        return CQLTypeRef("List", args=(inner.args[0],))
                if source.bare_name == "List":
                    return CQLTypeRef("List", args=(ANY_TYPE,))
            return CQLTypeRef("List", args=(ANY_TYPE,))

        if func_name in ("minimum", "maximum"):
            if node.arguments and isinstance(node.arguments[0], N.Identifier):
                type_name = node.arguments[0].name.split(".")[-1]
                if type_name in {"Integer", "Long", "Decimal", "Date", "DateTime", "Time"}:
                    return _shared_simple(type_name)
            return ANY_TYPE

        if func_name == "message":
            # Message returns its SOURCE unchanged (CQL §13.1).
            if node.arguments:
                return self.type_of(node.arguments[0])
            return ANY_TYPE

        if func_name in ("children", "descendants"):
            return CQLTypeRef("List", args=(ANY_TYPE,))

        # Numeric aggregates (mirrors InferenceMixin._infer_cql_type).
        if func_name in ("sum", "product", "min", "max"):
            if node.arguments:
                source = self.type_of(node.arguments[0])
                if source.canonical() == "List<Long>":
                    return _shared_simple("Long")
                if source.canonical() == "List<Quantity>" and func_name in ("sum", "product"):
                    return _shared_simple("Quantity")
            if func_name in ("min", "max"):
                return ANY_TYPE
            return _shared_simple("Decimal")

        if func_name == "avg":
            return _shared_simple("Decimal")

        if func_name == "abs":
            if node.arguments:
                arg_type = self.type_of(node.arguments[0])
                if arg_type.bare_name in ("Integer", "Long", "Decimal", "Quantity"):
                    return arg_type
            return ANY_TYPE

        if func_name == "power":
            arg_types = [self.type_of(arg) for arg in node.arguments]
            if arg_types and all(t.bare_name in ("Integer", "Long") for t in arg_types):
                exponent = node.arguments[1] if len(node.arguments) > 1 else None
                if self._static_numeric_value(exponent) is not None and self._static_numeric_value(exponent) < 0:
                    return _shared_simple("Decimal")
                if any(t.bare_name == "Long" for t in arg_types):
                    return _shared_simple("Long")
                return _shared_simple("Integer")
            return _shared_simple("Decimal")

        if func_name == "coalesce":
            # CQL §Coalesce: common type of the arguments — first
            # statically-known non-Any argument's type.
            for arg in node.arguments:
                arg_type = self.type_of(arg)
                if arg_type.bare_name != "Any":
                    return arg_type
            return ANY_TYPE

        # User-defined functions: recurse into the function body with the
        # function's parameters bound to their declared types.
        raw_name = str(getattr(node, "name", "") or "")
        if raw_name and raw_name not in self._visiting_functions:
            func_info = self._context_get_function(raw_name)
            if func_info is not None and getattr(func_info, "expression", None) is not None:
                param_scope: Dict[str, Any] = {}
                for pdef in getattr(func_info, "parameters", []) or []:
                    pname = getattr(pdef, "name", None)
                    ptype = getattr(pdef, "type", None)
                    if pname and ptype is not None:
                        param_scope[pname] = self._specifier_ref(ptype)
                self._visiting_functions.add(raw_name)
                try:
                    return self.type_of_scoped(func_info.expression, param_scope)
                finally:
                    self._visiting_functions.discard(raw_name)

        return ANY_TYPE

    def _specifier_ref(self, spec: Any) -> CQLTypeRef:
        """Convert a TypeSpecifier AST node (or name string) to a ref."""
        name = getattr(spec, "name", None) or str(spec)
        if not name:
            return ANY_TYPE
        text = str(name).replace("System.", "")
        try:
            ref = CQLTypeRef.parse(text)
        except Exception:
            return ANY_TYPE
        if not ref.args and not ref.fields and "." not in ref.bare_name:
            return _shared_simple(ref.bare_name)
        return ref

    def _context_get_function(self, name: Any):
        if name is None:
            return None
        getter = getattr(self._context, "get_function", None)
        if getter is None:
            return None
        try:
            return getter(name)
        except Exception:
            return None

    @staticmethod
    def _static_numeric_value(node: Any) -> Optional[float]:
        """Statically evaluate a literal-ish numeric (Literal + unary +/-)."""
        from ..parser import ast_nodes as N

        if isinstance(node, N.Literal):
            try:
                if isinstance(node.value, bool):
                    return None
                return float(node.value)
            except (TypeError, ValueError):
                return None
        if isinstance(node, N.UnaryExpression) and node.operator in ("+", "-"):
            inner = TypeMapBuilder._static_numeric_value(node.operand)
            if inner is None:
                return None
            return -inner if node.operator == "-" else inner
        return None

    # ------------------------------------------------------------------
    # Property typing (source 8)
    # ------------------------------------------------------------------

    def _property_type(self, node: Any) -> CQLTypeRef:
        from ..parser import ast_nodes as N

        source = node.source
        path = str(getattr(node, "path", "") or "")

        # Patient.birthDate special (context resource property).
        if isinstance(source, N.Identifier) and source.name == "Patient":
            fhir_type = self._fhir_property_cql_type("Patient", path)
            if fhir_type:
                return fhir_type

        if isinstance(source, N.Identifier):
            # Include-prefixed define reference: Common.Foo parses as
            # Property(source=Identifier('Common'), path='Foo').
            prefixed = f"{source.name}.{path}"
            meta = self._context.definition_meta.get(prefixed)
            if meta is not None:
                if getattr(meta, "cql_type_ref", None) is not None:
                    return meta.cql_type_ref
                if meta.cql_type and meta.cql_type != "Any":
                    return CQLTypeRef.parse(meta.cql_type)
                if meta.sql_result_type:
                    return CQLTypeRef.parse(meta.sql_result_type)
            # Alias-of-tuple field: X.field where X resolves to a Tuple.
            tuple_ref = self._tuple_field_ref(source.name, path)
            if tuple_ref is not None:
                return tuple_ref
            source_ref = self._identifier_type(source)
            return self._navigate(source_ref, path)

        if isinstance(source, N.Property):
            base = self._property_type(source)
            return self._navigate(base, path)

        if isinstance(source, (N.Query, N.FunctionRef, N.MethodInvocation)):
            base = self.type_of(source)
            return self._navigate(base, path)

        # Generic typed-source fallback (e.g. Property over an `as`-cast
        # BinaryExpression such as (X as FHIR.Quantity).unit).
        base = self.type_of(source)
        if base.bare_name != "Any":
            return self._navigate(base, path)
        return ANY_TYPE

    def _navigate(self, source_ref: CQLTypeRef, path: str) -> CQLTypeRef:
        """Navigate a property path through a typed source ref."""
        if source_ref.bare_name == "List" and source_ref.args:
            inner = self._navigate(source_ref.args[0], path)
            return CQLTypeRef("List", args=(inner,))
        bare = source_ref.bare_name
        # Tuple field navigation.
        if bare == "Tuple":
            fields = dict(source_ref.fields) if source_ref.fields else {}
            field = fields.get(path)
            return field if field is not None else ANY_TYPE
        if not self._is_fhir_resource_type(bare):
            # Quantity subfield navigation (value/unit/system/code).
            sub = self._quantity_subfield_type(bare, path)
            return sub if sub is not None else ANY_TYPE
        fhir_type = self._fhir_property_cql_type(bare, path)
        if fhir_type is not None:
            return fhir_type
        sub = self._quantity_subfield_type(bare, path)
        return sub if sub is not None else ANY_TYPE

    def _quantity_subfield_type(self, bare: str, path: str) -> Optional[CQLTypeRef]:
        if bare != "Quantity" or "." in path:
            return None
        sub = {
            "value": "Decimal",
            "unit": "String",
            "system": "String",
            "code": "String",
            "comparator": "String",
        }.get(path)
        return _shared_simple(sub) if sub else None

    def _fhir_property_cql_type(self, resource_type: str, path: str) -> Optional[CQLTypeRef]:
        """Schema-driven FHIR property typing (mirrors InferenceMixin)."""
        schema = getattr(self._context, "fhir_schema", None)
        if schema is None:
            return None
        from .inference import FHIR_TYPE_TO_CQL_TYPE

        fhir_type = schema.get_element_type(resource_type, path)
        cql_name = FHIR_TYPE_TO_CQL_TYPE.get(fhir_type) if fhir_type else None
        if cql_name:
            return _shared_simple(cql_name) if "." not in cql_name else _simple(cql_name)

        if "." not in path:
            return None
        head, tail = path.split(".", 1)
        if schema.get_element_type(resource_type, head) == "Quantity":
            sub = {
                "value": "Decimal",
                "unit": "String",
                "system": "String",
                "code": "String",
                "comparator": "String",
            }.get(tail)
            if sub:
                return _shared_simple(sub)
        return None

    def _is_fhir_resource_type(self, type_name: str) -> bool:
        if not type_name:
            return False
        bare = type_name.split(".")[-1]
        if bare == "Resource":
            return True
        registry = getattr(self._context, "profile_registry", None)
        if registry is not None and registry.resolve_named_profile(bare) is not None:
            return True
        schema = getattr(self._context, "fhir_schema", None)
        return bool(schema is not None and bare in getattr(schema, "resources", {}))

    def _tuple_field_ref(self, definition_name: str, field_name: str) -> Optional[CQLTypeRef]:
        """Type of ``<define>.<field>`` when the define returns a Tuple."""
        ast_node = self._raw_definition_ast(definition_name)
        if ast_node is None:
            return None
        from ..parser import ast_nodes as N

        if isinstance(ast_node, N.Identifier):
            return self._tuple_field_ref(ast_node.name, field_name)
        if isinstance(ast_node, N.FunctionRef) and ast_node.name.lower() in ("first", "last"):
            args = getattr(ast_node, "arguments", []) or []
            if args:
                ast_node = args[0]
        if isinstance(ast_node, N.TupleExpression):
            for element in ast_node.elements:
                if getattr(element, "name", None) == field_name:
                    return self.type_of(element.type)
            return None
        if not isinstance(ast_node, N.Query) or ast_node.return_clause is None:
            return None
        ret_expr = ast_node.return_clause.expression
        if not isinstance(ret_expr, N.TupleExpression):
            return None
        for element in ret_expr.elements:
            if getattr(element, "name", None) == field_name:
                return self.type_of(element.type)
        return None

    def _raw_definition_ast(self, name: str) -> Optional[Any]:
        expr_defs = getattr(self._context, "expression_definitions", {}) or {}
        ast_def = expr_defs.get(name)
        if ast_def is None:
            return None
        return ast_def.expression if hasattr(ast_def, "expression") else ast_def

    # ------------------------------------------------------------------
    # Query typing (source 9): scoped-symbol walker
    # ------------------------------------------------------------------

    def _query_type(self, query: Any) -> CQLTypeRef:
        from ..parser import ast_nodes as N

        alias_sources: Dict[str, Any] = {}
        for source in self._query_sources(query):
            if isinstance(source, N.QuerySource) and source.alias:
                alias_sources[source.alias] = source.expression

        let_aliases: Dict[str, Any] = {
            getattr(let, "alias", None): getattr(let, "expression", None)
            for let in (getattr(query, "let_clauses", []) or [])
            if getattr(let, "alias", None)
        }
        with_aliases: Dict[str, Any] = {
            getattr(w, "alias", None): None  # with rows: resource-typed via source
            for w in (getattr(query, "with_clauses", []) or [])
            if getattr(w, "alias", None)
        }

        # Aggregate clause: single scalar per patient.
        aggregate = getattr(query, "aggregate", None)
        if aggregate is not None:
            # Accumulator type = the body's type under (acc, element) scope.
            scope = dict(alias_sources)
            scope[getattr(aggregate, "identifier", "_acc")] = None
            return self.type_of_scoped(aggregate.expression, scope)

        return_clause = getattr(query, "return_clause", None)
        if return_clause is not None:
            rc_expr = return_clause.expression if hasattr(return_clause, "expression") else return_clause
            if isinstance(rc_expr, N.Identifier) and rc_expr.name in alias_sources:
                source_type = self.type_of(alias_sources[rc_expr.name])
                return source_type  # already List<T> for retrieves
            scope = dict(alias_sources)
            scope.update(let_aliases)
            element_type = self.type_of_scoped(rc_expr, scope)
            if element_type.bare_name != "Any":
                return CQLTypeRef("List", args=(element_type,))
            return CQLTypeRef("List", args=(ANY_TYPE,))

        # No return clause: type mirrors the (single) source.
        sources = self._query_sources(query)
        if len(sources) == 1 and isinstance(sources[0], N.QuerySource):
            return self.type_of(sources[0].expression)
        return ANY_TYPE

    @staticmethod
    def _query_sources(query: Any) -> list:
        source = getattr(query, "source", None)
        if isinstance(source, list):
            return source
        return [source] if source is not None else []

    def type_of_scoped(self, node: Any, scope: Dict[str, Any]) -> CQLTypeRef:
        """Type an expression with query aliases/lets in scope."""
        from ..parser import ast_nodes as N

        if isinstance(node, N.Identifier) and node.name in scope:
            source_expr = scope[node.name]
            if isinstance(source_expr, CQLTypeRef):
                return source_expr
            if isinstance(source_expr, N.Retrieve):
                return self.type_of(source_expr)
            if source_expr is not None:
                # Scope-aware typing so let values referencing query
                # aliases (let L: O.status) resolve through the scope.
                return self.type_of_scoped(source_expr, scope)
            return ANY_TYPE
        if isinstance(node, N.AliasRef):
            return ANY_TYPE
        if isinstance(node, N.Property) and isinstance(node.source, N.Identifier) and node.source.name in scope:
            source_expr = scope[node.source.name]
            if isinstance(source_expr, N.Retrieve):
                resource_type = str(getattr(source_expr, "type", "Resource") or "Resource")
                fhir_type = self._fhir_property_cql_type(resource_type, str(node.path or ""))
                if fhir_type:
                    return fhir_type
                return ANY_TYPE
            if source_expr is not None:
                source_ref = self.type_of(source_expr)
                ref = self._navigate(self._unwrap_list(source_ref), str(node.path or ""))
                if ref.bare_name != "Any":
                    return ref
                return self._property_type(node)
            return ANY_TYPE
        if isinstance(node, N.Property) and isinstance(node.source, N.AliasRef):
            return self._scoped_property_from_alias(node, scope)
        # Compound expressions: thread the scope into the primary
        # recursive node families so function bodies (x + x) and query
        # return expressions see let/param bindings.
        if isinstance(node, N.BinaryExpression):
            left = self.type_of_scoped(node.left, scope)
            right = self.type_of_scoped(node.right, scope)
            return self._binary_type_from_refs(node, left, right)
        if isinstance(node, N.UnaryExpression):
            return self.type_of_scoped(node.operand, scope)
        if isinstance(node, N.FunctionRef):
            scoped_fn = N.FunctionRef(
                name=node.name,
                arguments=[self._rescope_if_needed(a, scope) for a in node.arguments],
            )
            return self._function_type(scoped_fn)
        if isinstance(node, N.Query):
            return self._query_type_scoped(node, scope)
        if isinstance(node, N.ConditionalExpression):
            then_t = self.type_of_scoped(node.then_expr, scope)
            else_t = self.type_of_scoped(node.else_expr, scope)
            if then_t == else_t:
                return then_t
            return ANY_TYPE
        return self.type_of(node)

    def _rescope_if_needed(self, node: Any, scope: Dict[str, Any]) -> Any:
        """Substitute scope-resolved identifiers inside function arguments.

        Only Identifiers bound in scope are replaced by a marker the
        function-argument typing understands (literal-like refs); for
        anything else the node passes through unchanged.
        """
        from ..parser import ast_nodes as N

        if isinstance(node, N.Identifier) and node.name in scope:
            return node  # _function_type re-types via type_of; keep node
        return node

    def _binary_type_from_refs(self, node: Any, left: CQLTypeRef, right: CQLTypeRef) -> CQLTypeRef:
        """Binary typing from pre-computed operand refs (scope-threaded)."""
        op = str(getattr(node, "operator", "") or "").lower()

        if op in _COMPARISON_OPERATORS or op.startswith("same "):
            return _shared_simple("Boolean")
        if op in ("intersect", "union", "except"):
            return left if left.bare_name != "Any" else right
        if op in ("+", "-"):
            for ref in (left, right):
                if ref.bare_name in _TEMPORAL_TYPES:
                    return ref
            for name in ("Quantity", "Decimal", "Long", "Integer"):
                if left.bare_name == name:
                    return left
                if right.bare_name == name:
                    return right
            return ANY_TYPE
        if op in ("*", "/", "div", "mod", "^"):
            if left.bare_name == "Quantity" or right.bare_name == "Quantity":
                return _shared_simple("Quantity")
            if op == "/":
                return _shared_simple("Decimal")
            for name in ("Decimal", "Long", "Integer"):
                if left.bare_name == name:
                    return left
                if right.bare_name == name:
                    return right
            return ANY_TYPE
        if op in ("as", "convert"):
            return self._cast_type(node)
        return ANY_TYPE

    def _query_type_scoped(self, query: Any, outer_scope: Dict[str, Any]) -> CQLTypeRef:
        """Query typing with an outer (function-param/let) scope visible."""
        rc = getattr(query, "return_clause", None)
        if rc is not None:
            rc_expr = rc.expression if hasattr(rc, "expression") else rc
            merged = dict(outer_scope)
            for source in self._query_sources(query):
                if type(source).__name__ == "QuerySource" and getattr(source, "alias", None):
                    merged[source.alias] = source.expression
            for let in getattr(query, "let_clauses", []) or []:
                if getattr(let, "alias", None):
                    merged[let.alias] = getattr(let, "expression", None)
            return self.type_of_scoped(rc_expr, merged)
        return self._query_type(query)

    def _scoped_property_from_alias(self, node: Any, scope: Dict[str, Any]) -> Optional[CQLTypeRef]:
        alias_name = getattr(node.source, "name", None)
        source_expr = scope.get(alias_name) if alias_name else None
        if isinstance(source_expr, N.Retrieve):
            resource_type = str(getattr(source_expr, "type", "Resource") or "Resource")
            fhir_type = self._fhir_property_cql_type(resource_type, str(node.path or ""))
            return fhir_type if fhir_type else ANY_TYPE
        if source_expr is not None:
            source_ref = self.type_of(source_expr)
            ref = self._navigate(self._unwrap_list(source_ref), str(node.path or ""))
            if ref.bare_name != "Any":
                return ref
        return ANY_TYPE

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _unwrap_list(ref: CQLTypeRef) -> CQLTypeRef:
        if ref.bare_name == "List" and ref.args:
            return ref.args[0]
        return ANY_TYPE


# ----------------------------------------------------------------------
# Shared static type helpers (single source of truth).
#
# These module-level functions are the shared "tables, not logic" surface
# required by the FDD consolidation guardrails: the frozen lowering
# classifiers, InferenceMixin, and TypeMapBuilder all import them instead
# of keeping private copies. Any behavior change here is a lowering-facing
# change and must clear the byte-identical SQL gate.
# ----------------------------------------------------------------------

logger = logging.getLogger(__name__)


def static_numeric_literal_value(ast_node: Any) -> "int | float | None":
    """Statically evaluate a numeric literal (Literal + unary +/-)."""
    from ..parser.ast_nodes import Literal, UnaryExpression

    if isinstance(ast_node, Literal) and isinstance(ast_node.value, (int, float)) and not isinstance(ast_node.value, bool):
        return ast_node.value
    if isinstance(ast_node, UnaryExpression) and ast_node.operator in {"+", "-"}:
        inner = static_numeric_literal_value(ast_node.operand)
        if inner is None:
            return None
        return -inner if ast_node.operator == "-" else inner
    return None


def property_chain_parts(ast_node: Any) -> tuple[Optional[str], list]:
    """Return the root identifier and property path parts for a chain."""
    from ..parser.ast_nodes import Identifier, Property

    parts: list = []
    current = ast_node
    while isinstance(current, Property):
        parts.append(current.path)
        current = current.source
    if isinstance(current, Identifier):
        parts.reverse()
        return current.name, parts
    return None, []


def infer_fhir_property_type_str(context: Any, resource_type: str, path: str) -> Optional[str]:
    """Infer the CQL type STRING for a FHIR property path from schema metadata.

    Shared by InferenceMixin, the compat inference function below, and the
    frozen logical-operand classifier (replaces the former duplicated
    ``_logical_operand_property_cql_type`` in the expression layer).
    """
    from .inference import FHIR_TYPE_TO_CQL_TYPE

    schema = getattr(context, "fhir_schema", None)
    if schema is None:
        return None
    cql_type = FHIR_TYPE_TO_CQL_TYPE.get(schema.get_element_type(resource_type, path))
    if cql_type is not None:
        return cql_type

    if "." not in path:
        return None
    head, tail = path.split(".", 1)
    if schema.get_element_type(resource_type, head) == "Quantity":
        return {
            "value": "Decimal",
            "unit": "String",
            "system": "String",
            "code": "String",
            "comparator": "String",
        }.get(tail)
    return None


def is_fhir_resource_type(context: Any, cql_type: Optional[str]) -> bool:
    """Return True when a CQL type name denotes a FHIR resource/profile."""
    if not cql_type:
        return False
    type_name = str(cql_type).strip()
    if type_name.startswith("List<") and type_name.endswith(">"):
        type_name = type_name[len("List<"):-1].strip()
    bare = type_name.split(".")[-1] if "." in type_name else type_name
    if bare == "Resource":
        return True

    registry = getattr(context, "profile_registry", None)
    if registry is not None and registry.resolve_named_profile(bare) is not None:
        return True
    schema = getattr(context, "fhir_schema", None)
    return bool(schema is not None and bare in getattr(schema, "resources", {}))


def infer_query_return_property_type_str(context: Any, query: Any, return_expr: Any) -> Optional[str]:
    """Infer the property return type STRING for aliased retrieve queries."""
    from ..parser.ast_nodes import QuerySource, Retrieve

    sources = query.source
    if not isinstance(sources, list):
        sources = [sources]
    alias_resource_types: dict = {}
    for source in sources:
        if (
            isinstance(source, QuerySource)
            and source.alias
            and isinstance(source.expression, Retrieve)
        ):
            alias_resource_types[source.alias] = source.expression.type

    root_name, path_parts = property_chain_parts(return_expr)
    if not root_name or not path_parts:
        return None
    resource_type = alias_resource_types.get(root_name)
    if not resource_type:
        return None
    return infer_fhir_property_type_str(context, resource_type, ".".join(path_parts))


def static_source_cql_type(source: Any) -> str:
    """Standalone static CQL type for temporal/complex literal sources.

    Narrow literal/FunctionRef subset used by temporal-component routing
    and Ratio accessor detection (formerly the expression-layer
    ``_static_source_cql_type`` classifiers, deleted in the type-map
    consolidation).
    """
    from ..parser.ast_nodes import FunctionRef as _FunctionRef
    from ..parser.ast_nodes import DateTimeLiteral, TimeLiteral

    if isinstance(source, DateTimeLiteral):
        value = str(getattr(source, "value", "") or "")
        if value.startswith("T"):
            return "Time"
        return "DateTime" if "T" in value else "Date"
    if isinstance(source, TimeLiteral):
        return "Time"
    if isinstance(source, _FunctionRef):
        name = (getattr(source, "name", "") or "").lower()
        if name == "totime":
            return "Time"
        if name == "todate":
            return "Date"
        if name == "todatetime":
            return "DateTime"
        if name == "toratio":
            return "Ratio"
    return "Any"


# ----------------------------------------------------------------------
# Compat (legacy) inference — the LOWERING-authority type function.
#
# Verbatim port of the former InferenceMixin._infer_cql_type body
# (pre-consolidation). This function feeds ~40 SQL-generation sites via
# translator.py DefinitionMeta population and MUST preserve the legacy
# semantics byte-for-byte: Integer DurationBetween, Decimal-only power,
# no Quantity Sum branch, full dotted as/convert names, the
# valuesets→codesystems→codes→definition_meta→parameters→forward-ref
# identifier order, and the Any fallthrough for Property shapes outside
# the Identifier-source branch. It intentionally DIVERGES from
# TypeMapBuilder.type_of (the facade authority) on documented doctrine
# points — the drift tripwire test enumerates them.
# ----------------------------------------------------------------------

def infer_cql_type_compat(context: Any, ast_node: Any) -> str:
    from ..parser.ast_nodes import (
        Retrieve, ExistsExpression, FunctionRef, Literal,
        BinaryExpression, Property, UnaryExpression, Identifier,
        FirstExpression, LastExpression, ConditionalExpression,
        DurationBetween, DifferenceBetween, Interval, CodeSelector,
        InstanceExpression, ListExpression, Quantity, DateTimeLiteral,
        TimeLiteral, DistinctExpression, TupleExpression,
    )

    if ast_node is None:
        return "Any"

    if isinstance(ast_node, CodeSelector):
        return "Code"

    if isinstance(ast_node, InstanceExpression):
        type_name = getattr(ast_node, "type", "")
        bare = type_name.split(".")[-1] if "." in type_name else type_name
        if bare in {
            "Code",
            "Concept",
            "ValueSet",
            "CodeSystem",
            "Vocabulary",
            "Quantity",
            "Ratio",
        }:
            return bare

    if isinstance(ast_node, Quantity):
        return "Quantity"

    if isinstance(ast_node, DateTimeLiteral):
        value = str(getattr(ast_node, "value", "") or "")
        if value.startswith("T"):
            return "Time"
        return "DateTime" if "T" in value else "Date"

    if isinstance(ast_node, TimeLiteral):
        return "Time"

    # DurationBetween / DifferenceBetween return Integer (years/months/days/etc. between)
    if isinstance(ast_node, (DurationBetween, DifferenceBetween)):
        return "Integer"

    # Retrieve returns List<ResourceType>
    if isinstance(ast_node, Retrieve):
        resource_type = getattr(ast_node, 'type', 'Resource')
        return f"List<{resource_type}>"

    # Exists returns Boolean
    if isinstance(ast_node, ExistsExpression):
        return "Boolean"

    if isinstance(ast_node, DistinctExpression):
        return infer_cql_type_compat(context, ast_node.source)

    # Literals
    if isinstance(ast_node, Literal):
        explicit_type = getattr(ast_node, "type", None)
        if explicit_type:
            bare_type = str(explicit_type).split(".")[-1]
            if bare_type in {"Boolean", "Integer", "Long", "Decimal", "String"}:
                return bare_type
        value = ast_node.value
        if isinstance(value, bool):
            return "Boolean"
        elif isinstance(value, int):
            return "Integer"
        elif isinstance(value, float):
            return "Decimal"
        elif isinstance(value, str):
            return "String"
        return "Any"

    if isinstance(ast_node, ListExpression):
        element_types = [
            element_type
            for element_type in (infer_cql_type_compat(context, element) for element in ast_node.elements)
            if element_type != "Any"
        ]
        if not element_types:
            return "List<Any>"
        first_type = element_types[0]
        if all(element_type == first_type for element_type in element_types):
            return f"List<{first_type}>"
        return "List<Any>"

    if isinstance(ast_node, TupleExpression):
        fields = []
        for element in ast_node.elements:
            field_type = infer_cql_type_compat(context, element.type)
            fields.append(f"{element.name}: {field_type}")
        return "Tuple{" + ", ".join(fields) + "}"

    # Interval expressions
    if isinstance(ast_node, Interval):
        point_type = "Any"
        if ast_node.low is not None:
            point_type = infer_cql_type_compat(context, ast_node.low)
        elif ast_node.high is not None:
            point_type = infer_cql_type_compat(context, ast_node.high)
        if point_type == "Any":
            logger.warning(
                "Could not infer point type for Interval expression — "
                "defaulting to Interval<Any>. This may affect SQL generation."
            )
        return f"Interval<{point_type}>"

    # First/Last returns element type of source
    if isinstance(ast_node, (FirstExpression, LastExpression)):
        source_type = infer_cql_type_compat(context, ast_node.source)
        if source_type.startswith("List<"):
            return source_type[5:-1]  # Extract inner type
        return "Any"

    # Function calls
    if isinstance(ast_node, FunctionRef):
        func_name = ast_node.name.lower() if hasattr(ast_node, 'name') else ''
        if func_name == 'count':
            return "Integer"
        elif func_name == 'indexof':
            return "Integer"
        elif func_name in ('sum', 'product', 'min', 'max'):
            if ast_node.arguments:
                source_type = infer_cql_type_compat(context, ast_node.arguments[0])
                if source_type == "List<Long>":
                    return "Long"
            if func_name in ('min', 'max'):
                return "Any"
            return "Decimal"
        elif func_name == 'avg':
            return "Decimal"
        elif func_name in ('abs',):
            if ast_node.arguments:
                arg_type = infer_cql_type_compat(context, ast_node.arguments[0])
                if arg_type in {"Integer", "Long", "Decimal", "Quantity"}:
                    return arg_type
            return "Any"
        elif func_name in ('power',):
            arg_types = [infer_cql_type_compat(context, arg) for arg in ast_node.arguments]
            if arg_types and all(arg_type in {"Integer", "Long"} for arg_type in arg_types):
                exponent = ast_node.arguments[1] if len(ast_node.arguments) > 1 else None
                if static_numeric_literal_value(exponent) is not None and static_numeric_literal_value(exponent) < 0:
                    return "Decimal"
                if "Long" in arg_types:
                    return "Long"
            return "Decimal"
        elif func_name in ('minimum', 'maximum'):
            if ast_node.arguments and isinstance(ast_node.arguments[0], Identifier):
                type_name = ast_node.arguments[0].name.split(".")[-1]
                if type_name in {"Integer", "Long", "Decimal", "Date", "DateTime", "Time"}:
                    return type_name
            return "Any"
        elif func_name in ('first', 'last'):
            # Returns element type of source
            if ast_node.arguments:
                source_type = infer_cql_type_compat(context, ast_node.arguments[0])
                if source_type.startswith("List<"):
                    return source_type[5:-1]  # Extract inner type
            return "Any"
        elif func_name == 'date':
            return "Date"
        elif func_name in ('datetime', 'now', 'today'):
            return "DateTime"
        elif func_name == 'time':
            return "Time"
        elif func_name == 'distinct':
            if ast_node.arguments:
                return infer_cql_type_compat(context, ast_node.arguments[0])
            return "List<Any>"
        elif func_name == 'flatten':
            if ast_node.arguments:
                source_type = infer_cql_type_compat(context, ast_node.arguments[0])
                if source_type.startswith("List<List<") and source_type.endswith(">>"):
                    return f"List<{source_type[10:-2]}>"
                if source_type.startswith("List<"):
                    return "List<Any>"
            return "List<Any>"
        elif func_name in {
            "toboolean",
            "tointeger",
            "tolong",
            "todecimal",
            "tostring",
            "todate",
            "todatetime",
            "totime",
            "toquantity",
            "toratio",
            "toconcept",
        }:
            return {
                "toboolean": "Boolean",
                "tointeger": "Integer",
                "tolong": "Long",
                "todecimal": "Decimal",
                "tostring": "String",
                "todate": "Date",
                "todatetime": "DateTime",
                "totime": "Time",
                "toquantity": "Quantity",
                "toratio": "Ratio",
                "toconcept": "Concept",
            }[func_name]
        else:
            func_info = context.get_function(ast_node.name)
            if func_info and func_info.expression is not None:
                return infer_cql_type_compat(context, func_info.expression)

    # Binary comparisons and temporal operators return Boolean
    if isinstance(ast_node, BinaryExpression):
        op = getattr(ast_node, 'operator', '').lower()
        # "duration in X between" is parsed as BinaryExpression(op='in',
        # left=Identifier('duration'), right=DurationBetween(...)).
        # This is a duration computation, not a membership test — return Integer.
        if (op == 'in'
                and isinstance(ast_node.left, Identifier)
                and ast_node.left.name.lower() == 'duration'
                and isinstance(ast_node.right, DurationBetween)):
            return "Integer"
        if op in ('=', '!=', '<>', '<', '>', '<=', '>=',
                  'and', 'or', 'xor', 'implies',
                  'on or before', 'on or after', 'before', 'after',
                  'starts', 'ends', 'during', 'overlaps', 'in',
                  '~', '!~', 'equivalent', 'not equivalent',
                  'same or before', 'same or after',
                  'includes', 'included in',
                  'properly includes', 'properly included in',
                  'meets', 'meets before', 'meets after',
                  'contains', 'is'):
            return "Boolean"
        # Precision-qualified same operators: "same or before month of", etc.
        if op.startswith('same '):
            return "Boolean"
        # intersect/union/except preserve the element type
        if op in ('intersect', 'union', 'except'):
            left_type = infer_cql_type_compat(context, ast_node.left)
            if left_type != "Any":
                return left_type
            return infer_cql_type_compat(context, ast_node.right)
        if op in ('+', '-'):
            left_type = infer_cql_type_compat(context, ast_node.left)
            right_type = infer_cql_type_compat(context, ast_node.right)
            if left_type in ("Date", "DateTime", "Time"):
                return left_type
            if right_type in ("Date", "DateTime", "Time"):
                return right_type
            if left_type == "Quantity" or right_type == "Quantity":
                return "Quantity"
            if "Decimal" in (left_type, right_type):
                return "Decimal"
            if "Long" in (left_type, right_type):
                return "Long"
            if "Integer" in (left_type, right_type):
                return "Integer"
            return "Any"
        if op in ('*', '/', 'div', 'mod', '^'):
            left_type = infer_cql_type_compat(context, ast_node.left)
            right_type = infer_cql_type_compat(context, ast_node.right)
            if left_type == "Quantity" or right_type == "Quantity":
                return "Quantity"
            if "Decimal" in (left_type, right_type) or op == '/':
                return "Decimal"
            if "Long" in (left_type, right_type):
                return "Long"
            if "Integer" in (left_type, right_type):
                return "Integer"
            return "Any"
        # "as" cast: type is the target type specifier
        if op == 'as':
            from ..parser.ast_nodes import NamedTypeSpecifier
            ts = ast_node.right
            if isinstance(ts, NamedTypeSpecifier):
                type_name = getattr(ts, 'name', None)
                if type_name:
                    bare_type = type_name.split(".")[-1]
                    source_type = infer_cql_type_compat(context, ast_node.left)
                    if bare_type == "Any":
                        return source_type
                    if bare_type == "Vocabulary" and source_type in {"ValueSet", "CodeSystem"}:
                        return source_type
                    return type_name
            elif isinstance(ts, Identifier):
                bare_type = ts.name.split(".")[-1]
                source_type = infer_cql_type_compat(context, ast_node.left)
                if bare_type == "Any":
                    return source_type
                if bare_type == "Vocabulary" and source_type in {"ValueSet", "CodeSystem"}:
                    return source_type
                return ts.name
        if op == 'convert':
            from ..parser.ast_nodes import NamedTypeSpecifier
            ts = ast_node.right
            source_type = infer_cql_type_compat(context, ast_node.left)
            if isinstance(ts, NamedTypeSpecifier):
                type_name = getattr(ts, 'name', None)
                if type_name:
                    bare_type = type_name.split(".")[-1]
                    if bare_type == "Any":
                        return source_type
                    return type_name
            elif isinstance(ts, Identifier):
                bare_type = ts.name.split(".")[-1]
                if bare_type == "Any":
                    return source_type
                return ts.name

    # Unary NOT returns Boolean; "singleton from" extracts element type
    if isinstance(ast_node, UnaryExpression):
        op = getattr(ast_node, 'operator', '').lower()
        if op in ('not', 'is null', 'is not null'):
            return "Boolean"
        if op in ('+', '-', 'predecessor of', 'successor of'):
            return infer_cql_type_compat(context, ast_node.operand)
        if op == 'singleton from':
            operand_type = infer_cql_type_compat(context, ast_node.operand)
            if operand_type.startswith("List<"):
                return operand_type[5:-1]
            return operand_type

    # Conditional propagates branch types (if consistent)
    if isinstance(ast_node, ConditionalExpression):
        then_type = infer_cql_type_compat(context, ast_node.then_expr)
        else_type = infer_cql_type_compat(context, ast_node.else_expr)
        if then_type == else_type:
            return then_type
        return "Any"

    # Property access — resolve library-qualified definition references
    if isinstance(ast_node, Property):
        if (
            isinstance(ast_node.source, Identifier)
            and ast_node.source.name == "Patient"
            and ast_node.path == "birthDate"
        ):
            return "Date"
        if isinstance(ast_node.source, Identifier) and ast_node.path:
            prefixed = f"{ast_node.source.name}.{ast_node.path}"
            meta = context.definition_meta.get(prefixed)
            if meta:
                return meta.cql_type
            if hasattr(context, 'expression_definitions'):
                ast_def = context.expression_definitions.get(prefixed)
                if ast_def is not None:
                    return infer_cql_type_compat(context, ast_def)
            # CQL-04 EXPLORER QA-003 (restored): element access on a FHIR
            # resource-typed source (the context resource `Patient.active`,
            # retrieve aliases, profile names) infers its CQL type from
            # schema metadata so value-bearing Boolean/Date/String
            # defines feed logical/string operators by VALUE instead of
            # failing operand validation with List<Any>.
            source_name = ast_node.source.name
            context_resource = str(getattr(context, "current_context", "") or "")
            if is_fhir_resource_type(context, source_name) or (
                context_resource and source_name == context_resource
            ):
                fhir_type = infer_fhir_property_type_str(context, source_name, ast_node.path)
                if fhir_type:
                    return fhir_type
        return "Any"

    # Check if it's an identifier referencing a known definition
    if isinstance(ast_node, Identifier):
        if ast_node.name in context.valuesets:
            return "ValueSet"
        if ast_node.name in context.codesystems:
            return "CodeSystem"
        code_info = context.codes.get(ast_node.name)
        if code_info:
            return "Concept" if code_info.get("is_concept") else "Code"
        meta = context.definition_meta.get(ast_node.name)
        if meta:
            return meta.cql_type
        param_info = context.parameters.get(ast_node.name)
        if param_info and getattr(param_info, "cql_type", None):
            return str(param_info.cql_type)
        # Forward ref: check CQL AST for type hints.
        # The cql_ast represents the EXPRESSION of the definition, so infer
        # its type directly (it already represents the full definition type,
        # e.g., a BinaryExpression(intersect) of queries returns List<Date>).
        if hasattr(context, '_definition_cql_asts'):
            cql_ast = context._definition_cql_asts.get(ast_node.name)
            if cql_ast is not None:
                inferred = infer_cql_type_compat(context, cql_ast)
                if inferred != "Any":
                    return inferred

    # Query node: infer type from return clause or source
    from ..parser.ast_nodes import Query, QuerySource, ReturnClause
    if isinstance(ast_node, Query):
        if ast_node.return_clause is not None:
            rc_expr = ast_node.return_clause.expression if isinstance(ast_node.return_clause, ReturnClause) else ast_node.return_clause
            if isinstance(rc_expr, Identifier):
                sources = ast_node.source if isinstance(ast_node.source, list) else [ast_node.source]
                for source in sources:
                    if isinstance(source, QuerySource) and source.alias == rc_expr.name:
                        source_type = infer_cql_type_compat(context, source.expression)
                        if source_type.startswith("List<"):
                            return source_type
                        if source_type != "Any":
                            return f"List<{source_type}>"
            property_return_type = infer_query_return_property_type_str(context, ast_node, rc_expr)
            if property_return_type is not None:
                return f"List<{property_return_type}>"
            return_type = infer_cql_type_compat(context, rc_expr)
            if return_type != "Any":
                return f"List<{return_type}>"
        # No return clause: type is same as source
        src = ast_node.source
        if isinstance(src, list) and len(src) == 1:
            src = src[0]
        from ..parser.ast_nodes import QuerySource
        if isinstance(src, QuerySource) and src.expression:
            return infer_cql_type_compat(context, src.expression)

    return "Any"