"""Core expression translation: literals, identifiers, and type conversions."""
from __future__ import annotations

import json
import logging
import re as _re
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

from ...parser.ast_nodes import (
    AggregateExpression,
    AliasRef,
    AllExpression,
    AnyExpression,
    BinaryExpression,
    CaseExpression,
    CaseItem,
    CodeSelector,
    ConditionalExpression,
    DateComponent,
    DateTimeLiteral,
    DifferenceBetween,
    DurationBetween,
    ExistsExpression,
    FirstExpression,
    FunctionRef,
    Identifier,
    IndexerExpression,
    InstanceExpression,
    Interval,
    LastExpression,
    ListExpression,
    Literal,
    MethodInvocation,
    NamedTypeSpecifier,
    Property,
    QualifiedIdentifier,
    Quantity,
    Query,
    QuerySource,
    SingletonExpression,
    SkipExpression,
    TakeExpression,
    TimeLiteral,
    TupleElement,
    TupleExpression,
    UnaryExpression,
)
from ...translator.context import ExprUsage, RowShape, DefinitionMeta
from ...translator.function_inliner import ParameterPlaceholder
from ...translator.placeholder import RetrievePlaceholder
from ...translator.expressions._refstrategy import _RefKind, _RefStrategy
from ...translator.types import (
    PRECEDENCE,
    SQLAlias,
    SQLArray,
    SQLBinaryOp,
    SQLCase,
    SQLCast,
    SQLExists,
    SQLExpression,
    SQLExtract,
    SQLFunctionCall,
    SQLIdentifier,
    SQLInterval,
    SQLIntervalLiteral,
    SQLJoin,
    SQLLambda,
    SQLLiteral,
    SQLNamedArg,
    SQLNull,
    SQLParameterRef,
    SQLQualifiedIdentifier,
    SQLRaw,
    SQLSelect,
    SQLSubquery,
    SQLUnaryOp,
    SQLUnion,
    SQLIntersect,
    SQLExcept,
)
from ...translator.expressions._utils import (
    BINARY_OPERATOR_MAP,
    UNARY_OPERATOR_MAP,
    _is_list_returning_sql,
    _contains_sql_subquery,
    _ensure_scalar_body,
    _get_qicore_extension_fhirpath,
    _resolve_library_code_constant,
)

if TYPE_CHECKING:
    from ...translator.context import SQLTranslationContext

logger = logging.getLogger(__name__)

def _camel_to_snake_cached(name: str) -> str:
    """Convert CamelCase to snake_case."""
    result = []
    for i, char in enumerate(name):
        if char.isupper() and i > 0:
            result.append("_")
        result.append(char.lower())
    return "".join(result)


class CoreMixin:
    """Mixin providing literal, identifier, and basic conversion translations."""
    @staticmethod
    def _bare_parameter_type_name(cql_type: Optional[str]) -> Optional[str]:
        """Return the bare CQL type name for parameter metadata."""
        if cql_type is None:
            return None
        text = str(cql_type)
        if "name='" in text:
            text = text.split("name='", 1)[1].split("'", 1)[0]
        elif 'name="' in text:
            text = text.split('name="', 1)[1].split('"', 1)[0]
        if "." in text:
            text = text.rsplit(".", 1)[-1]
        return text

    def _parameter_binding_expression(
        self,
        binding: Any,
        cql_type: Optional[str],
    ) -> SQLExpression:
        """Lower a scalar parameter binding/default with declared CQL type."""
        if isinstance(
            binding,
            (
                BinaryExpression,
                DateTimeLiteral,
                FunctionRef,
                Identifier,
                ListExpression,
                Literal,
                Quantity,
                TimeLiteral,
                TupleExpression,
                UnaryExpression,
            ),
        ):
            return self.translate(binding, usage=ExprUsage.SCALAR)

        if binding is None:
            return SQLNull()

        bare_type = (self._bare_parameter_type_name(cql_type) or "Any").lower()
        literal = SQLLiteral(value=binding)
        target_sql_type = {
            "boolean": "BOOLEAN",
            "integer": "INTEGER",
            "long": "BIGINT",
            "decimal": "DECIMAL(38, 8)",
        }.get(bare_type)
        if target_sql_type is not None:
            return SQLCast(expression=literal, target_type=target_sql_type, try_cast=True)
        if bare_type == "string":
            return SQLLiteral(value=str(binding))
        return literal

    @staticmethod
    def _interval_parameter_binding_parts(
        binding: Any,
    ) -> tuple[Any, Any, bool, bool] | None:
        """Return low/high/closure metadata for an interval parameter binding.

        Runtime two-tuples keep their historical closed-bound behavior. CQL
        authored defaults are stored as dictionaries so their interval syntax
        (`[`, `]`, `(`, `)`) survives into population SQL.
        """
        if isinstance(binding, dict) and ("low" in binding or "high" in binding):
            return (
                binding.get("low"),
                binding.get("high"),
                bool(binding.get("lowClosed", True)),
                bool(binding.get("highClosed", False)),
            )
        if isinstance(binding, tuple):
            if len(binding) == 2:
                return (binding[0], binding[1], True, True)
            if len(binding) == 4:
                return (binding[0], binding[1], bool(binding[2]), bool(binding[3]))
        return None

    @staticmethod
    def _interval_parameter_bound_sql(
        value: Any,
        *,
        is_datetime: bool,
        is_high: bool,
    ) -> SQLExpression:
        if value is None:
            return SQLLiteral(value="{mp_end}" if is_high else "{mp_start}")
        text = str(value)
        if is_datetime and _re.match(r"^\d{4}-\d{2}-\d{2}$", text):
            text = text + ("T23:59:59.999" if is_high else "T00:00:00.000")
        return SQLLiteral(value=text)

    def _parameter_reference_expression(self, name: str, cql_type: Optional[str]) -> SQLExpression:
        """Return a runtime parameter reference preserving declared primitive type."""
        ref = SQLParameterRef(name=name)
        bare_type = (self._bare_parameter_type_name(cql_type) or "Any").lower()
        target_sql_type = {
            "boolean": "BOOLEAN",
            "integer": "INTEGER",
            "long": "BIGINT",
            "decimal": "DECIMAL(38, 8)",
        }.get(bare_type)
        if target_sql_type is not None:
            return SQLCast(expression=ref, target_type=target_sql_type, try_cast=True)
        return ref

    def _camel_to_snake(self, name: str) -> str:
        """Convert CamelCase to snake_case."""
        return _camel_to_snake_cached(name)

    def _clinical_code_literal(
        self,
        code: str,
        system: Optional[str] = None,
        display: Optional[str] = None,
        version: Optional[str] = None,
    ) -> SQLLiteral:
        """Build a JSON-shaped CQL Code literal."""
        code_obj: Dict[str, Any] = {"code": code}
        if system:
            code_obj["system"] = self.context.codesystems.get(system, system)
            if version is None:
                version = self.context.codesystem_versions.get(system)
                if version is None:
                    for cs_name, cs_url in self.context.codesystems.items():
                        if cs_url == system:
                            version = self.context.codesystem_versions.get(cs_name)
                            break
        if version:
            code_obj["version"] = version
        if display:
            code_obj["display"] = display
        return SQLLiteral(value=json.dumps(code_obj, separators=(",", ":")))

    @staticmethod
    def _split_terminology_ref(ref: str) -> tuple[str, Optional[str]]:
        """Split the context's compact ``id|version`` terminology reference."""
        if "|" not in ref:
            return ref, None
        identifier, version = ref.rsplit("|", 1)
        return identifier, version or None

    def _clinical_valueset_literal(self, name: str, ref: str) -> SQLLiteral:
        """Build a JSON-shaped CQL ValueSet reference."""
        identifier, version = self._split_terminology_ref(ref)
        valueset_obj: Dict[str, Any] = {"id": identifier, "name": name}
        if version:
            valueset_obj["version"] = version
        codesystems = []
        for cs_name in self.context.valueset_codesystems.get(name, []):
            lookup_name = cs_name.split(".")[-1]
            cs_id = self.context.codesystems.get(cs_name)
            if cs_id is None:
                cs_id = self.context.codesystems.get(lookup_name, cs_name)
            cs_obj: Dict[str, Any] = {"id": cs_id, "name": lookup_name}
            cs_version = self.context.codesystem_versions.get(cs_name)
            if cs_version is None:
                cs_version = self.context.codesystem_versions.get(lookup_name)
            if cs_version:
                cs_obj["version"] = cs_version
            codesystems.append(cs_obj)
        if codesystems:
            valueset_obj["codesystems"] = codesystems
        return SQLLiteral(value=json.dumps(valueset_obj, separators=(",", ":")))

    def _clinical_codesystem_literal(self, name: str, ref: str) -> SQLLiteral:
        """Build a JSON-shaped CQL CodeSystem reference."""
        codesystem_obj: Dict[str, Any] = {"id": ref, "name": name}
        version = self.context.codesystem_versions.get(name)
        if version:
            codesystem_obj["version"] = version
        return SQLLiteral(value=json.dumps(codesystem_obj, separators=(",", ":")))

    def _clinical_concept_literal(self, concept_info: Dict[str, Any]) -> SQLLiteral:
        """Build a JSON-shaped CQL Concept literal from context metadata."""
        codes = []
        for code_info in concept_info.get("codes", []) or []:
            if not isinstance(code_info, dict):
                continue
            code_value = code_info.get("code")
            if not code_value:
                continue
            code_obj: Dict[str, Any] = {"code": code_value}
            system = code_info.get("codesystem", code_info.get("system"))
            if system:
                code_obj["system"] = self.context.codesystems.get(system, system)
            version = code_info.get("version")
            if version:
                code_obj["version"] = version
            display = code_info.get("display")
            if display:
                code_obj["display"] = display
            codes.append(code_obj)

        concept_obj: Dict[str, Any] = {"codes": codes}
        display = concept_info.get("display")
        if display:
            concept_obj["display"] = display
        return SQLLiteral(value=json.dumps(concept_obj, separators=(",", ":")))

    def _translate_literal(self, lit: Literal, boolean_context: bool = False) -> SQLExpression:
        """Translate a CQL literal to SQL."""
        value = lit.value

        if value is None:
            return SQLNull()

        if isinstance(value, bool):
            return SQLLiteral(value=value)

        if isinstance(value, str):
            return SQLLiteral(value=value)

        if isinstance(value, (int, float)):
            if getattr(lit, 'type', None) == "Decimal" and getattr(lit, 'raw_str', None):
                # NOTE: no extent rejection here on purpose. The official CQL
                # conformance fixtures (ValueLiteralsAndSelectors.xml) pin
                # 28-int-digit literals such as 10000000000000000000000000000.00000000
                # as VALID Decimal selectors; official fixtures outrank the
                # (10^28-1)/10^8 "maximum Decimal" prose, so out-of-extent
                # Decimal literals must translate (Integer/Long keep their
                # range checks because fixtures pin those rejections).
                return SQLLiteral(value=value, raw_sql=lit.raw_str)
                return SQLLiteral(value=value, raw_sql=lit.raw_str)
            # CQL §2.2: Integer is 32-bit signed [-2^31, 2^31-1]
            if isinstance(value, int) and not isinstance(value, bool):
                if getattr(lit, 'type', None) == "Integer" and (value > 2147483647 or value < -2147483648):
                    raise ValueError(
                        f"Integer literal {value} out of range for CQL Integer type "
                        f"[-2147483648, 2147483647]"
                    )
                if getattr(lit, 'type', None) == "Long" and (value > 9223372036854775807 or value < -9223372036854775808):
                    raise ValueError(
                        f"Long literal {value} out of range for CQL Long type "
                        f"[-9223372036854775808, 9223372036854775807]"
                    )
            # Handle special numeric values
            if isinstance(value, float):
                if value == float("inf"):
                    return SQLLiteral(value=float("inf"))
                elif value == float("-inf"):
                    return SQLLiteral(value=float("-inf"))
                elif value != value:  # NaN
                    return SQLLiteral(value=float("nan"))
            return SQLLiteral(value=value)

        # Fallback
        return SQLLiteral(value=str(value))

    def _translate_date_time_literal(self, dt: DateTimeLiteral, boolean_context: bool = False) -> SQLExpression:
        """Translate a CQL DateTime literal to SQL VARCHAR preserving precision.

        CQL §18.2: DateTime precision is determined by the number of specified
        components.  We emit the original ISO 8601 string so downstream
        precision-aware UDFs (cqlSameOrBefore, cqlDateTimeAdd, etc.) can infer
        precision from the string format.  E.g. '@2014' → '2014' (year precision),
        '@2014-01' → '2014-01' (month precision).
        """
        value = dt.value
        # CQL format: @2024-01-15T12:30:00 or @2024-01-15 or @2024

        # Remove @ prefix if present
        if value.startswith("@"):
            value = value[1:]

        # Time-only literal (T-prefixed) — validate components
        if value.startswith("T") or value.startswith("t"):
            time_str = value[1:]
            if time_str.endswith("Z") or any(ch in time_str[1:] for ch in ("+", "-")):
                raise ValueError("Invalid time literal: timezone suffix is not supported")
            parts = time_str.split(':')
            if len(parts) >= 1:
                h = int(parts[0])
                if h > 23:
                    raise ValueError(f"Invalid time literal: hour {h} exceeds 23")
            if len(parts) >= 2:
                m = int(parts[1])
                if m > 59:
                    raise ValueError(f"Invalid time literal: minute {m} exceeds 59")
            if len(parts) >= 3:
                sec_parts = parts[2].split('.')
                s = int(sec_parts[0])
                if s > 59:
                    raise ValueError(f"Invalid time literal: second {s} exceeds 59")
                if len(sec_parts) > 1 and len(sec_parts[1]) > 3:
                    raise ValueError(
                        f"Invalid time literal: millisecond value {sec_parts[1]} "
                        f"exceeds maximum precision"
                    )

        # Preserve ISO 8601 format with 'T' separator (not space).
        # This keeps precision information intact for downstream UDFs.
        value = value.strip()

        # Return as VARCHAR literal preserving original precision
        return SQLLiteral(value=value)

    def _translate_time_literal(self, t: TimeLiteral, boolean_context: bool = False) -> SQLExpression:
        """Translate a CQL Time literal to SQL TIME."""
        value = t.value
        # CQL format: @T12:30:00 or @T14:00

        # Remove @T prefix if present
        if value.startswith("@T"):
            value = value[2:]
        elif value.startswith("T"):
            value = value[1:]

        # Validate time components per ISO 8601
        parts = value.split(':')
        if len(parts) >= 1:
            h = int(parts[0])
            if h > 23:
                raise ValueError(f"Invalid time literal: hour {h} exceeds 23")
        if len(parts) >= 2:
            m = int(parts[1])
            if m > 59:
                raise ValueError(f"Invalid time literal: minute {m} exceeds 59")
        if len(parts) >= 3:
            sec_parts = parts[2].split('.')
            s = int(sec_parts[0])
            if s > 59:
                raise ValueError(f"Invalid time literal: second {s} exceeds 59")
            if len(sec_parts) > 1:
                ms_str = sec_parts[1]
                if len(ms_str) > 3:
                    ms_val = int(ms_str)
                    if ms_val > 999:
                        raise ValueError(
                            f"Invalid time literal: millisecond value {ms_val} exceeds 999"
                        )

        return SQLFunctionCall(
            name="CAST",
            args=[
                SQLLiteral(value=value),
            ],
        )

    def _translate_quantity(self, qty: Quantity, boolean_context: bool = False) -> SQLExpression:
        """Translate a CQL Quantity to SQL (as JSON or UDF call)."""
        value = qty.value
        unit = qty.unit

        # Create a JSON representation of the quantity
        quantity_dict = {
            "value": value,
            "unit": unit,
            "system": "http://unitsofmeasure.org",
        }

        # Return as JSON string that can be used with quantity UDFs
        result = SQLFunctionCall(
            name="parse_quantity",
            args=[SQLLiteral(value=json.dumps(quantity_dict))],
        )
        result.result_type = "Quantity"
        return result

    def _translate_code_selector(self, cs: CodeSelector, boolean_context: bool = False) -> SQLExpression:
        """Translate a CQL Code selector to SQL.

        Code selectors (e.g., Code '73211009' from "SNOMED-CT") resolve
        the system name through codesystem definitions and produce a
        JSON-shaped CQL Code value.
        """
        return self._clinical_code_literal(cs.code, cs.system, cs.display)

    def _build_promoted_definition_lookup(self, name: str, usage: ExprUsage) -> SQLExpression:
        """Build a correlated subquery lookup for a promoted global definition.

        Ensures that definitions are translated once as CTEs and referenced via
        lightweight lookups rather than inline expansion. Classification of the
        reference shape (EXISTS vs correlated subquery, which column) is
        delegated to ``_classify_definition_ref`` so it stays in sync with the
        inline definition-reference branch of ``_translate_identifier``.
        """
        meta = self.context.definition_meta.get(name)
        strategy = self._classify_definition_ref(name, usage, meta)

        if strategy.kind == _RefKind.EXISTS:
            return self._build_correlated_exists(name)

        _outer_pid_alias = self.context.resource_alias or self.context.patient_alias or "_pt"
        select = SQLSelect(
            columns=[SQLQualifiedIdentifier(parts=["sub", strategy.column])],
            from_clause=SQLAlias(
                expr=SQLIdentifier(name=name, quoted=True),
                alias="sub",
            ),
            where=SQLBinaryOp(
                operator="=",
                left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                right=SQLQualifiedIdentifier(parts=[_outer_pid_alias, "patient_id"]),
            )
        )

        # LIMIT 1 whenever the caller wants a scalar OR the underlying define is
        # patient-scalar shape (one row per patient by construction). The
        # classifier already route Booleans to EXISTS, so reaching here means
        # the define genuinely has a value/resource column.
        is_patient_scalar = meta is not None and meta.shape == RowShape.PATIENT_SCALAR
        if strategy.kind == _RefKind.CORRELATED_SCALAR or is_patient_scalar:
            select.limit = 1

        res = SQLSubquery(query=select)
        if meta and meta.sql_result_type:
            res.result_type = meta.sql_result_type
        if usage == ExprUsage.BOOLEAN and strategy.kind == _RefKind.CORRELATED_SCALAR:
            # Value-bearing Boolean define consumed by a logical operator:
            # force an explicit Boolean cast so CQL 3VL applies to the VALUE
            # instead of inheriting DuckDB string truthiness.
            return SQLCast(expression=res, target_type="BOOLEAN")
        return res

    def _translate_identifier(self, ident: Identifier, usage: ExprUsage = ExprUsage.LIST) -> SQLExpression:
        """Translate a CQL identifier to SQL.

        Args:
            ident: The CQL identifier to translate.
            usage: How the expression result will be used (LIST, SCALAR, BOOLEAN, EXISTS).

        Returns:
            SQL expression appropriate for the given usage context.
        """
        # For backward compatibility with old handlers that still pass boolean_context
        # This will be removed after full migration
        if isinstance(usage, bool):
            usage = ExprUsage.BOOLEAN if usage else ExprUsage.LIST

        name = ident.name

        # CQL-02 QA-004: statically-known clinical literal definitions (Code
        # selectors, Concept instances, ValueSet/CodeSystem references) are
        # library constants with no retrieve/query dependency. Inline them at
        # reference sites instead of emitting patient-correlated CTE lookups
        # against literal CTEs that have no patient_id column (Binder error
        # end-to-end). Must run before alias/promotion/CTE resolution so all
        # reference paths agree.
        if not self.context.is_alias(name):
            clinical_source = self._definition_source_ast(name)
            if clinical_source is not None and self._is_static_clinical_definition(clinical_source):
                return self.translate(clinical_source, usage=usage)

        # CQL-03 QA-002: temporal literal defines are library constants too;
        # inline them for the same patient-correlated-CTE reason.
        if not self.context.is_alias(name):
            temporal_source = self._definition_source_ast(name)
            if temporal_source is not None and self._is_static_temporal_definition(temporal_source):
                return self.translate(temporal_source, usage=usage)

        # Check if this definition is promoted to a global CTE for deduplication.
        # If so, we MUST return a subquery lookup instead of the full AST
        # to prevent combinatorial explosion.
        if name in self.context.promoted_definitions:
            return self._build_promoted_definition_lookup(name, usage)

        # Check if this is a known alias with a stored SQL expression
        if self.context.is_alias(name):
            symbol = self.context.lookup_symbol(name)
            table_alias = getattr(symbol, "table_alias", None) if symbol else None
            if table_alias and usage == ExprUsage.SCALAR:
                source_ast = getattr(self.context, "_alias_source_asts", {}).get(name)
                if isinstance(source_ast, ListExpression):
                    return SQLIdentifier(name=table_alias)
                if isinstance(source_ast, Query):
                    # Nested query source (``[X] x return e a``): the alias
                    # iterates element VALUES of the inner query's projection,
                    # not resource rows (CQL 1.5 §Query).
                    return SQLIdentifier(name=table_alias)
                cte_name = getattr(symbol, "cte_name", None)
                col = "resource"
                if cte_name:
                    meta = self.context.definition_meta.get(cte_name)
                    if meta and not meta.has_resource:
                        col = meta.value_column or "value"
                    elif meta is None:
                        col = self._get_definition_value_column(cte_name)
                return SQLQualifiedIdentifier(parts=[table_alias, col])

            # Check for union_expr marker (stored for SQLUnion or SQLCase with SQLUnion)
            union_expr = getattr(symbol, 'union_expr', None) if symbol else None
            if union_expr is not None:
                # This alias was stored with a union_expr - return it directly
                # The caller (e.g., _translate_property) will handle it
                return union_expr

            # Check for AST expression first (fixes B4-B6 violations)
            ast_expr = getattr(symbol, 'ast_expr', None) if symbol else None
            if ast_expr is not None:
                # When ast_expr is an SQLSubquery but the symbol also has a
                # cte_name, skip the ast_expr and fall through to the cte_name
                # path below.  The cte_name path produces the correct
                # SQLQualifiedIdentifier(parts=[alias, "resource"]) which is
                # the proper row-level reference.  Returning the SQLSubquery
                # here would produce an uncorrelated scalar subquery that
                # scans the entire CTE instead of referencing the current row.
                _skip_ast = (
                    isinstance(ast_expr, SQLSubquery)
                    and symbol is not None
                    and getattr(symbol, 'cte_name', None)
                )
                if not _skip_ast:
                    # Use AST introspection instead of string inspection
                    from ...translator.ast_utils import (
                        ast_is_case_with_union,
                        ast_is_list_operation,
                        ast_is_boolean_result,
                    )

                    # Check for invalid pattern: CASE with SQLUnion in branches (B4)
                    if ast_is_case_with_union(ast_expr):
                        # This is problematic - the CASE has UNION in branches
                        # Log a warning as it indicates a structural issue
                        pass

                    # Check if expression is a list operation (B5)
                    is_list_expr = ast_is_list_operation(ast_expr)

                    # Check if expression is already boolean-valued (B6)
                    is_boolean_result = ast_is_boolean_result(ast_expr)

                    if is_list_expr and not is_boolean_result:
                        # Wrap in list_extract to get first element for scalar use
                        return SQLFunctionCall(
                            name="list_extract",
                            args=[ast_expr, SQLLiteral(value=1)]
                        )

                    # Alias-bound resource-row subqueries project
                    # (patient_id, resource); in scalar usage the whole
                    # subquery would be inlined where a single value is
                    # expected (DuckDB: "Subquery returns 2 columns").
                    # Narrow to the resource column; computed-value
                    # projections (query return clauses) are unaffected.
                    if usage == ExprUsage.SCALAR:
                        ast_expr = self._narrow_to_resource_column(ast_expr)

                    # Return the AST expression directly
                    return ast_expr

            sql_expr_val = getattr(symbol, 'sql_expr', None) if symbol else None
            if not sql_expr_val:
                sql_expr_val = getattr(symbol, 'sql_ref', None) if symbol else None
            if sql_expr_val:
                # Try to construct a proper AST node from the string
                if sql_expr_val.startswith('"') and sql_expr_val.endswith('"') and '.' not in sql_expr_val:
                    # Quoted identifier like '"MyCTE"'
                    return SQLIdentifier(name=sql_expr_val.strip('"'))
                if '.' in sql_expr_val and not any(c in sql_expr_val for c in '()+*/ '):
                    # Qualified identifier like 'alias.column'
                    parts = [p.strip('"') for p in sql_expr_val.split('.')]
                    return SQLQualifiedIdentifier(parts=parts)
                logger.warning("AliasRef '%s' using SQLRaw fallback (no ast_expr on symbol)", name)
                return SQLRaw(raw_sql=sql_expr_val)
            # When both ast_expr and sql_expr are absent but cte_name is set,
            # qualify with the appropriate CTE column to avoid returning the
            # full DuckDB row STRUCT.
            if symbol and symbol.cte_name:
                # Use the SQL-level table alias when available (e.g., from
                # _translate_query_on_alias), falling back to the CQL name.
                _sql_alias = symbol.table_alias or name
                meta = self.context.definition_meta.get(symbol.cte_name)
                if meta:
                    col = "resource" if meta.has_resource else (meta.value_column or "value")
                    return SQLQualifiedIdentifier(parts=[_sql_alias, col])
                else:
                    col = self._get_definition_value_column(symbol.cte_name)
                    return SQLQualifiedIdentifier(parts=[_sql_alias, col])
            return SQLIdentifier(name=name)

        # Look up in symbol table
        symbol = self.context.lookup_symbol(name)
        if symbol:
            if symbol.symbol_type == "parameter":
                # Generic interval parameter binding lookup
                parameter_bindings = getattr(self.context, "_parameter_bindings", {})
                has_binding = name in parameter_bindings
                binding = parameter_bindings[name] if has_binding else None
                interval_parts = self._interval_parameter_binding_parts(binding)
                if interval_parts is not None:
                    b_start, b_end, low_closed, high_closed = interval_parts
                    # For Interval<DateTime> parameters, use TIMESTAMP precision
                    # so that datetime comparisons are exact (e.g.,
                    # 2026-01-01T08:00 is NOT within [2025-07-01, 2026-01-01]
                    # because at datetime precision 08:00 > 00:00).
                    # Date-only end bounds get end-of-day (T23:59:59.999)
                    # to match CQL date→datetime promotion semantics.
                    is_dt = symbol.cql_type and "DateTime" in str(symbol.cql_type)
                    cast_type = "TIMESTAMP" if is_dt else "DATE"
                    start_literal = self._interval_parameter_bound_sql(
                        b_start,
                        is_datetime=bool(is_dt),
                        is_high=False,
                    )
                    end_literal = self._interval_parameter_bound_sql(
                        b_end,
                        is_datetime=bool(is_dt),
                        is_high=True,
                    )
                    return SQLFunctionCall(
                        name="intervalFromBounds",
                        args=[
                            SQLCast(expression=start_literal, target_type=cast_type),
                            SQLCast(expression=end_literal, target_type=cast_type),
                            SQLLiteral(value=low_closed),
                            SQLLiteral(value=high_closed),
                        ],
                    )
                if has_binding:
                    return self._parameter_binding_expression(binding, symbol.cql_type)
                return self._parameter_reference_expression(name, symbol.cql_type)
            elif symbol.symbol_type == "definition":
                # Reference to a named expression - generate subquery reference to CTE
                # The definition will be available as a CTE in the final SQL.
                # Classification (EXISTS vs correlated subquery, which column) is
                # delegated to _classify_definition_ref so this path stays in sync
                # with _build_promoted_definition_lookup.
                meta = self.context.definition_meta.get(name)
                strategy = self._classify_definition_ref(name, usage, meta)

                if strategy.kind == _RefKind.EXISTS:
                    # EXISTS strategy covers both BOOLEAN/EXISTS usage and any
                    # reference (LIST/SCALAR) to a boolean-like define. When a
                    # query_builder is active AND the meta says PATIENT_SCALAR
                    # Boolean, prefer a JOIN with `alias.patient_id IS NOT NULL`
                    # over a correlated EXISTS subquery — same semantics, lets
                    # the planner reuse the JOIN for any other reference site.
                    if (self.context.query_builder
                            and meta is not None
                            and meta.shape == RowShape.PATIENT_SCALAR
                            and meta.cql_type == "Boolean"):
                        alias = self.context.query_builder.track_cte_reference(
                            name, usage=ExprUsage.BOOLEAN, shape=meta.shape
                        )
                        return SQLBinaryOp(
                            operator="IS NOT",
                            left=SQLQualifiedIdentifier(parts=[alias, "patient_id"]),
                            right=SQLNull(),
                        )
                    return self._build_correlated_exists(name)

                if usage == ExprUsage.SCALAR or (
                    usage == ExprUsage.BOOLEAN
                    and strategy.kind == _RefKind.CORRELATED_SCALAR
                ):
                    # Diagnostic: RESOURCE_ROWS defines referenced as scalars
                    # are almost always a user mistake (no ORDER BY → row choice
                    # is unspecified). Only emitted from this path because
                    # promoted RESOURCE_ROWS defines are an established pattern.
                    if meta and meta.shape == RowShape.RESOURCE_ROWS:
                        self.context.warnings.add_semantics(
                            message="RESOURCE_ROWS used in SCALAR context - using LIMIT 1 or correlated subquery",
                            definition=name,
                            suggestion="Use First() or Last() for explicit single-value selection"
                        )
                    # SCALAR always wants a single value: emit a LIMIT-1 subquery.
                    _outer_pid_alias = self.context.resource_alias or self.context.patient_alias or "_pt"
                    subq = SQLSubquery(query=SQLSelect(
                        columns=[SQLQualifiedIdentifier(parts=["sub", strategy.column])],
                        from_clause=SQLAlias(
                            expr=SQLIdentifier(name=name, quoted=True),
                            alias="sub",
                        ),
                        where=SQLBinaryOp(
                            operator="=",
                            left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                            right=SQLQualifiedIdentifier(parts=[_outer_pid_alias, "patient_id"]),
                        ),
                        limit=1
                    ))
                    if meta and meta.sql_result_type:
                        subq.result_type = meta.sql_result_type
                    if usage == ExprUsage.BOOLEAN:
                        # Value-bearing Boolean define consumed by a logical
                        # operator: force an explicit Boolean cast so CQL 3VL
                        # applies to the VALUE (null/false included) instead
                        # of inheriting DuckDB string truthiness.
                        return SQLCast(expression=subq, target_type="BOOLEAN")
                    return subq

                # LIST context on a non-boolean define. Prefer JOIN tracking
                # when a query_builder is active and the CTE has a resource
                # column; fall through to a correlated subquery otherwise.
                if self.context.query_builder:
                    self.context.query_builder.track_cte_reference(name)
                    ref = self.context.query_builder.get_cte_reference(name)
                    if ref and meta and meta.has_resource:
                        return SQLQualifiedIdentifier(parts=[ref.alias, "resource"])

                subquery = SQLSubquery(query=SQLSelect(
                    columns=[SQLIdentifier(name=strategy.column)],
                    from_clause=SQLIdentifier(name=name, quoted=True)
                ))
                return subquery
            elif symbol.symbol_type == "alias":
                # When the alias has a known CTE backing, qualify with the
                # appropriate column so DuckDB doesn't return the full row STRUCT.
                if symbol.cte_name:
                    meta = self.context.definition_meta.get(symbol.cte_name)
                    if meta:
                        col = "resource" if meta.has_resource else (meta.value_column or "value")
                        return SQLQualifiedIdentifier(parts=[name, col])
                    else:
                        # Forward reference — meta not yet available.
                        # Infer column from the CQL AST definition.
                        col = self._get_definition_value_column(symbol.cte_name)
                        return SQLQualifiedIdentifier(parts=[name, col])
                return SQLIdentifier(name=name)
            elif symbol.sql_expr:
                # A-1: Handle both string and AST node during migration
                if isinstance(symbol.sql_expr, str):
                    return SQLIdentifier(name=symbol.sql_expr)
                else:
                    # It's an AST node, return it directly
                    return symbol.sql_expr

        # Check if this is a let variable
        if name in self.context.let_variables:
            return self.context.let_variables[name]

        # Check if this is Patient context reference
        if name == "Patient":
            # Flag that the _patients CTE needs current-patient resource columns.
            self.context._needs_demographics = True
            # Determine the outer patient_id reference for correlation.
            outer_alias = self.context.resource_alias
            if outer_alias:
                outer_pid = SQLQualifiedIdentifier(parts=[outer_alias, "patient_id"])
            else:
                outer_alias = "_pt"
                outer_pid = SQLQualifiedIdentifier(parts=[outer_alias, "patient_id"])
            if outer_alias == "_pt":
                return SQLQualifiedIdentifier(parts=["_pt", "patient_resource"])
            return SQLSubquery(query=SQLSelect(
                columns=[SQLQualifiedIdentifier(parts=["_pd", "patient_resource"])],
                from_clause=SQLAlias(
                    expr=SQLIdentifier(name="_patients", quoted=False),
                    alias="_pd"
                ),
                where=SQLBinaryOp(
                    left=SQLQualifiedIdentifier(parts=["_pd", "patient_id"]),
                    operator="=",
                    right=outer_pid,
                ),
                limit=1,
            ))

        # Check if this is a code reference
        if hasattr(self.context, 'codes') and name in self.context.codes:
            code_info = self.context.codes[name]
            if code_info.get("is_concept"):
                return self._clinical_concept_literal(code_info)

            system = code_info.get("codesystem", code_info.get("system", ""))
            code = code_info.get("code", "")
            display = code_info.get("display")
            version = code_info.get("version")
            return self._clinical_code_literal(code, system, display, version)

        # CQL ValueSet and CodeSystem references are structured clinical values,
        # not SQL identifiers and not FHIR resources.
        if name in self.context.valuesets:
            return self._clinical_valueset_literal(name, self.context.valuesets[name])
        if name in self.context.codesystems:
            return self._clinical_codesystem_literal(name, self.context.codesystems[name])

        # Check if this is a definition reference (not in symbol table but defined in context)
        definition = self.context.get_definition(name)
        if definition:
            # CQL-02 QA-004: statically-known clinical literal definitions
            # (Code selectors, Concept instances, ValueSet/CodeSystem refs)
            # are library constants. Inline them at reference sites instead
            # of emitting a patient-correlated CTE lookup against a literal
            # CTE with no patient_id column (Binder error end-to-end).
            # Fetch meta here so it's available for LIST context too.
            meta = self.context.definition_meta.get(name)
            # For SCALAR/BOOLEAN/EXISTS context, register JOIN with query builder
            if usage in (ExprUsage.SCALAR, ExprUsage.BOOLEAN, ExprUsage.EXISTS):

                if usage in (ExprUsage.BOOLEAN, ExprUsage.EXISTS):
                    # FIX: Always use EXISTS subquery for BOOLEAN/EXISTS context CTE references.
                    # JOIN aliases (j1.resource IS NOT NULL) are only valid in the same SELECT scope
                    # where the JOIN is added, but this reference may appear inside nested subqueries
                    # where the alias is not visible. Using EXISTS is safer and works in all contexts.
                    return self._build_correlated_exists(name)

                elif usage == ExprUsage.SCALAR:
                    # FIX: Always use correlated subquery for SCALAR context CTE references.
                    # JOIN aliases (j1.resource) are only valid in the same SELECT scope where
                    # the JOIN is added, but this reference may appear inside nested subqueries
                    # (e.g., WHERE clause of a First/Last query) where the alias is not visible.
                    # Using a subquery is safer and works in all contexts.
                    # For boolean definitions (PATIENT_SCALAR, no resource, Boolean type), use EXISTS check
                    if meta and meta.shape == RowShape.PATIENT_SCALAR and not meta.has_resource and meta.cql_type == "Boolean":
                        return self._build_correlated_exists(name)
                    # For CTEs with value column (scalars), select value
                    if meta and not meta.has_resource:
                        return SQLSubquery(query=SQLSelect(
                            columns=[SQLQualifiedIdentifier(parts=["sub", "value"])],
                            from_clause=SQLAlias(
                                expr=SQLIdentifier(name=name, quoted=True),
                                alias="sub",
                            ),
                            where=SQLBinaryOp(
                                operator="=",
                                left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                                right=SQLQualifiedIdentifier(parts=["_pt", "patient_id"]),
                            ),
                            limit=1
                        ))
                    # For other types, use meta-aware or forward-reference-aware column
                    col = self._get_definition_value_column(name)
                    return SQLSubquery(query=SQLSelect(
                        columns=[SQLQualifiedIdentifier(parts=["sub", col])],
                        from_clause=SQLAlias(
                            expr=SQLIdentifier(name=name, quoted=True),
                            alias="sub",
                        ),
                        where=SQLBinaryOp(
                            operator="=",
                            left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                            right=SQLQualifiedIdentifier(parts=["_pt", "patient_id"]),
                        ),
                        limit=1
                    ))

            # Check if the referenced definition IS boolean, regardless of how WE're using it.
            # This handles: define Denominator: "Initial Population"
            # where Initial Population is Boolean but Denominator uses it as a value reference.
            if meta and meta.shape == RowShape.PATIENT_SCALAR and meta.cql_type == "Boolean":
                # This definition evaluates to true/false per patient.
                # Even in LIST/SCALAR context, the right pattern is EXISTS/JOIN.
                if self.context.query_builder:
                    alias = self.context.query_builder.track_cte_reference(
                        name, usage=ExprUsage.BOOLEAN, shape=meta.shape
                    )
                    return SQLBinaryOp(
                        operator="IS NOT",
                        left=SQLQualifiedIdentifier(parts=[alias, "patient_id"]),
                        right=SQLNull(),
                    )
                else:
                    return self._build_correlated_exists(name)

            # LIST context - track CTE reference for JOIN optimization.
            # Only use the JOIN-alias shortcut when the definition shape is
            # known.  UNKNOWN-shape definitions might be RESOURCE_ROWS with a
            # ``resource`` column, so defaulting to ``value`` would break.
            from ...translator.context import RowShape as _RS
            if self.context.query_builder and meta is not None and meta.shape != _RS.UNKNOWN:
                self.context.query_builder.track_cte_reference(name)
                ref = self.context.query_builder.get_cte_reference(name)
                if ref:
                    if meta.has_resource:
                        return SQLQualifiedIdentifier(parts=[ref.alias, "resource"])
                    elif not meta.has_resource and meta.cql_type != "Boolean":
                        return SQLQualifiedIdentifier(parts=[ref.alias, meta.value_column])
            if meta and not meta.has_resource and meta.cql_type != "Boolean" and meta.shape != _RS.UNKNOWN:
                return SQLSubquery(query=SQLSelect(
                    columns=[SQLQualifiedIdentifier(parts=["sub", meta.value_column or "value"])],
                    from_clause=SQLAlias(
                        expr=SQLIdentifier(name=name, quoted=True),
                        alias="sub",
                    ),
                    where=SQLBinaryOp(
                        operator="=",
                        left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                        right=SQLQualifiedIdentifier(parts=["_pt", "patient_id"]),
                    ),
                    limit=1
                ))
            # For boolean CTEs (patient_id only), SELECT * is fine
            if meta and not meta.has_resource and meta.shape != _RS.UNKNOWN:
                return SQLSubquery(query=SQLSelect(
                    columns=[SQLIdentifier(name="*")],
                    from_clause=SQLIdentifier(name=name, quoted=True)
                ))
            # When meta is None (forward reference not yet translated),
            # use _get_definition_value_column to infer the correct column
            if meta is None:
                col = self._get_definition_value_column(name)
                return SQLSubquery(query=SQLSelect(
                    columns=[SQLQualifiedIdentifier(parts=["sub", col])],
                    from_clause=SQLAlias(
                        expr=SQLIdentifier(name=name, quoted=True),
                        alias="sub",
                    ),
                    where=SQLBinaryOp(
                        operator="=",
                        left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                        right=SQLQualifiedIdentifier(parts=["_pt", "patient_id"]),
                    ),
                    limit=1
                ))
            # For RESOURCE_ROWS or fully unknown, select resource column
            return SQLSubquery(query=SQLSelect(
                columns=[SQLIdentifier(name="resource")],
                from_clause=SQLIdentifier(name=name, quoted=True)
            ))

        # Check if this is a forward reference to a definition (not yet translated but will be)
        if hasattr(self.context, '_definition_names') and name in self.context._definition_names:
            # Emit warning for forward reference
            self.context.warnings.add_performance(
                message="Forward reference caused fallback to correlated subquery",
                definition=name,
                suggestion="Ensure definitions are ordered by dependency (check topological sort)"
            )

            # Fetch meta here so it's available for LIST context too.
            meta = self.context.definition_meta.get(name)
            # For SCALAR/BOOLEAN/EXISTS context, register JOIN with query builder
            if usage in (ExprUsage.SCALAR, ExprUsage.BOOLEAN, ExprUsage.EXISTS):

                if usage in (ExprUsage.BOOLEAN, ExprUsage.EXISTS):
                    # FIX: Always use EXISTS subquery for BOOLEAN/EXISTS context CTE references.
                    # JOIN aliases (j1.resource IS NOT NULL) are only valid in the same SELECT scope
                    # where the JOIN is added, but this reference may appear inside nested subqueries
                    # where the alias is not visible. Using EXISTS is safer and works in all contexts.
                    return self._build_correlated_exists(name)

                elif usage == ExprUsage.SCALAR:
                    # Check if RESOURCE_ROWS is used in SCALAR context - emit warning
                    if meta and meta.shape == RowShape.RESOURCE_ROWS:
                        self.context.warnings.add_semantics(
                            message="RESOURCE_ROWS used in SCALAR context - using LIMIT 1 or correlated subquery",
                            definition=name,
                            suggestion="Use First() or Last() for explicit single-value selection"
                        )
                    # FIX: Always use correlated subquery for SCALAR context CTE references.
                    # JOIN aliases (j1.resource) are only valid in the same SELECT scope where
                    # the JOIN is added, but this reference may appear inside nested subqueries
                    # (e.g., WHERE clause of a First/Last query) where the alias is not visible.
                    # Using a subquery is safer and works in all contexts.
                    # For boolean definitions (PATIENT_SCALAR, no resource, Boolean type), use EXISTS check
                    if meta and meta.shape == RowShape.PATIENT_SCALAR and not meta.has_resource and meta.cql_type == "Boolean":
                        return self._build_correlated_exists(name)
                    # For CTEs with value column (scalars), select value
                    if meta and not meta.has_resource:
                        return SQLSubquery(query=SQLSelect(
                            columns=[SQLQualifiedIdentifier(parts=["sub", meta.value_column or "value"])],
                            from_clause=SQLAlias(
                                expr=SQLIdentifier(name=name, quoted=True),
                                alias="sub",
                            ),
                            where=SQLBinaryOp(
                                operator="=",
                                left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                                right=SQLQualifiedIdentifier(parts=["_pt", "patient_id"]),
                            ),
                            limit=1
                        ))
                    # For other types, use meta-aware or forward-reference-aware column
                    col = self._get_definition_value_column(name)
                    return SQLSubquery(query=SQLSelect(
                        columns=[SQLQualifiedIdentifier(parts=["sub", col])],
                        from_clause=SQLAlias(
                            expr=SQLIdentifier(name=name, quoted=True),
                            alias="sub",
                        ),
                        where=SQLBinaryOp(
                            operator="=",
                            left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                            right=SQLQualifiedIdentifier(parts=["_pt", "patient_id"]),
                        ),
                        limit=1
                    ))

            # LIST context - track CTE reference for JOIN optimization
            from ...translator.context import RowShape as _RS2
            if self.context.query_builder and meta is not None and meta.shape != _RS2.UNKNOWN:
                self.context.query_builder.track_cte_reference(name)
                ref = self.context.query_builder.get_cte_reference(name)
                if ref:
                    if meta.has_resource:
                        return SQLQualifiedIdentifier(parts=[ref.alias, "resource"])
                    elif not meta.has_resource and meta.cql_type != "Boolean":
                        return SQLQualifiedIdentifier(parts=[ref.alias, meta.value_column])

            # For non-resource CTEs with a value column, select only value column
            if meta and not meta.has_resource and meta.cql_type != "Boolean" and meta.shape != _RS2.UNKNOWN:
                return SQLSubquery(query=SQLSelect(
                    columns=[SQLQualifiedIdentifier(parts=["sub", meta.value_column or "value"])],
                    from_clause=SQLAlias(
                        expr=SQLIdentifier(name=name, quoted=True),
                        alias="sub",
                    ),
                    where=SQLBinaryOp(
                        operator="=",
                        left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                        right=SQLQualifiedIdentifier(parts=["_pt", "patient_id"]),
                    ),
                    limit=1
                ))
            # Boolean CTE - select all
            if meta and not meta.has_resource and meta.shape != _RS2.UNKNOWN:
                return SQLSubquery(query=SQLSelect(
                    columns=[SQLIdentifier(name="*")],
                    from_clause=SQLIdentifier(name=name, quoted=True)
                ))
            # When meta is None, infer column from CQL AST
            if meta is None:
                col = self._get_definition_value_column(name)
                return SQLSubquery(query=SQLSelect(
                    columns=[SQLQualifiedIdentifier(parts=["sub", col])],
                    from_clause=SQLAlias(
                        expr=SQLIdentifier(name=name, quoted=True),
                        alias="sub",
                    ),
                    where=SQLBinaryOp(
                        operator="=",
                        left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                        right=SQLQualifiedIdentifier(parts=["_pt", "patient_id"]),
                    ),
                    limit=1
                ))
            # When meta has UNKNOWN shape but column info, use correlated subquery
            if meta is not None and meta.shape == _RS2.UNKNOWN:
                col = "resource" if meta.has_resource else meta.value_column
                return SQLSubquery(query=SQLSelect(
                    columns=[SQLQualifiedIdentifier(parts=["sub", col])],
                    from_clause=SQLAlias(
                        expr=SQLIdentifier(name=name, quoted=True),
                        alias="sub",
                    ),
                    where=SQLBinaryOp(
                        operator="=",
                        left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                        right=SQLQualifiedIdentifier(parts=["_pt", "patient_id"]),
                    ),
                    limit=1
                ))
            # For RESOURCE_ROWS, select resource column
            return SQLSubquery(query=SQLSelect(
                columns=[SQLIdentifier(name="resource")],
                from_clause=SQLIdentifier(name=name, quoted=True)
            ))

        # Default: treat as identifier
        _inlining_lib = getattr(self.context, '_current_inlining_library', None)
        if _inlining_lib is None:
            msg = (
                f"Undefined CQL definition '{name}' passed through as SQL identifier. "
                "This will likely cause a DuckDB error at execution time. "
                "Check that the definition is spelled correctly and that all "
                "required library includes are present."
            )
            logger.debug(msg)
        else:
            logger.debug("Definition '%s' from inlined library '%s' passed through as SQL identifier", name, _inlining_lib)
        return SQLIdentifier(name=name)

    def _translate_qualified_identifier(self, qi: QualifiedIdentifier, usage: ExprUsage = ExprUsage.LIST) -> SQLExpression:
        """Translate a CQL qualified identifier (e.g., Library.Function) to SQL."""
        boolean_context = usage in (ExprUsage.BOOLEAN, ExprUsage.EXISTS)
        parts = qi.parts

        if not parts:
            return SQLNull()

        first = parts[0]

        # Check if first part is an include reference
        if first in self.context.includes:
            # Raise early for references to unresolved includes (QA8-001)
            if self.context.is_include_unresolved(first):
                from ...errors import TranslationError
                raise TranslationError(
                    message=(
                        f"Reference to included library '{first}' cannot be "
                        f"resolved: no library_loader was configured. Provide a "
                        f"library_loader to CQLToSQLTranslator to resolve "
                        f"include references."
                    ),
                )
            # Reference to included library
            # e.g., FHIRHelpers.ToDateTime or AIFrailLTCF."Some Definition"
            if len(parts) >= 2:
                full_name = ".".join(parts)
                # Check if this definition was successfully loaded
                if hasattr(self.context, 'has_included_definition') and not self.context.has_included_definition(full_name):
                    # Definition wasn't loaded (library failed to parse)
                    # Add a warning to make the issue visible
                    self.context.warnings.add_semantics(
                        message=f"Included library definition '{full_name}' was not loaded, generating EXISTS subquery",
                        definition=full_name,
                        suggestion="Ensure the included library parses correctly for optimal results"
                    )
                    # Generate an EXISTS subquery referencing the expected CTE name
                    # The CTE will be generated by the query builder even if the definition wasn't parsed
                    # This ensures the SQL is syntactically correct and references the CTE properly
                    if boolean_context:
                        return self._build_correlated_exists(full_name)
                    # For list context, return a subquery selecting from the expected CTE
                    return SQLSubquery(
                        query=SQLSelect(
                            columns=[SQLIdentifier(name="resource")],
                            from_clause=SQLIdentifier(name=full_name, quoted=True),
                        )
                    )
                # This is a reference to a definition in an included library.
                # Same usage-aware pattern as the cross-library branch in
                # _translate_property: BOOLEAN/EXISTS -> EXISTS, SCALAR ->
                # correlated scalar subquery + LIMIT 1, LIST -> SELECT *.
                # Note: must catch BOTH BOOLEAN and EXISTS (the old code used
                # `boolean_context` which derived True for both).
                if self.context.query_builder:
                    self.context.query_builder.track_cte_reference(full_name)
                meta = self.context.get_definition_meta(full_name)
                if usage in (ExprUsage.BOOLEAN, ExprUsage.EXISTS):
                    return self._build_correlated_exists(full_name)
                if usage == ExprUsage.SCALAR:
                    if self.context.query_builder:
                        ref = self.context.query_builder.get_cte_reference(full_name)
                        if ref:
                            if meta and meta.has_resource:
                                return SQLQualifiedIdentifier(parts=[ref.alias, "resource"])
                            elif meta and (meta.is_scalar or (not meta.has_resource and meta.cql_type != "Boolean")):
                                return SQLQualifiedIdentifier(parts=[ref.alias, meta.value_column])
                    strategy = self._classify_definition_ref(full_name, usage, meta)
                    if strategy.kind == _RefKind.EXISTS:
                        return self._build_correlated_exists(full_name)
                    _outer_pid_alias = (
                        self.context.resource_alias
                        or self.context.patient_alias
                        or "_pt"
                    )
                    subquery = SQLSubquery(query=SQLSelect(
                        columns=[SQLQualifiedIdentifier(parts=["sub", strategy.column])],
                        from_clause=SQLAlias(
                            expr=SQLIdentifier(name=full_name, quoted=True),
                            alias="sub",
                        ),
                        where=SQLBinaryOp(
                            operator="=",
                            left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                            right=SQLQualifiedIdentifier(parts=[_outer_pid_alias, "patient_id"]),
                        ),
                        limit=1,
                    ))
                    if meta and meta.sql_result_type:
                        subquery.result_type = meta.sql_result_type
                    return subquery
                # usage == LIST (default): SELECT * identity passthrough.
                subquery = SQLSubquery(query=SQLSelect(
                    columns=[SQLIdentifier(name="*")],
                    from_clause=SQLIdentifier(name=full_name, quoted=True)
                ))
                return subquery
            return SQLIdentifier(name=first)

        # Check if this is a valueset reference
        if first in self.context.valuesets and len(parts) == 1:
            return self._clinical_valueset_literal(first, self.context.valuesets[first])

        # Check if this is a codesystem reference
        if first in self.context.codesystems:
            cs_url = self.context.codesystems[first]
            if len(parts) > 1:
                # Code from codesystem: JSON-shaped CQL Code value
                return self._clinical_code_literal(parts[1], cs_url)
            return self._clinical_codesystem_literal(first, cs_url)

        # Default: qualified identifier
        return SQLQualifiedIdentifier(parts=parts)

    def _translate_promoted_function_ref(self, expr, boolean_context: bool = False) -> SQLExpression:
        """Translate a PromotedFunctionRef to a CTE lookup.

        The inliner has decided this function call should use a pre-computed
        CTE instead of inline expansion. Generate a correlated subquery lookup.
        """
        from ...translator.function_inliner import PromotedFunctionRef

        func_name = expr.func_name
        source_expr = expr.source_expr

        # Strip library prefix for CTE name matching
        bare_name = func_name.rsplit(".", 1)[-1] if "." in func_name else func_name

        # Determine the source CTE name from the source_expr or current context
        cql_def_name = None
        if isinstance(source_expr, Identifier):
            sym = self.context.lookup_symbol(source_expr.name)
            if sym and sym.cte_name:
                cql_def_name = sym.cte_name

        # Fallback: use current resource_alias
        if not cql_def_name:
            resource_alias = self.context.resource_alias
            if resource_alias:
                sym = self.context.lookup_symbol(resource_alias)
                if sym and sym.cte_name:
                    cql_def_name = sym.cte_name

        if not cql_def_name:
            # Can't determine source — fall back to function call
            source_sql = self.translate(source_expr, boolean_context=False) if source_expr else SQLNull()
            return SQLFunctionCall(name=bare_name, args=[source_sql])

        # Check for exact match in _promoted_cte_keys
        key = (bare_name, cql_def_name)
        if key not in self.context._promoted_cte_keys:
            # No matching CTE — fall back to function call
            source_sql = self.translate(source_expr, boolean_context=False) if source_expr else SQLNull()
            return SQLFunctionCall(name=bare_name, args=[source_sql])

        # Generate deterministic CTE name (must match _build_function_promotion_cte)
        from ...translator.cte_manager import generate_function_cte_name
        fn_cte_name = generate_function_cte_name(bare_name, cql_def_name)
        source_alias = (
            source_expr.name
            if isinstance(source_expr, Identifier)
            else self.context.resource_alias or "E"
        )

        return self._make_function_cte_lookup(fn_cte_name, source_alias)
