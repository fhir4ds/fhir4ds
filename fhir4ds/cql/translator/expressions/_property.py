"""Property access translation: FHIR property navigation and choice types."""
from __future__ import annotations

import json
import logging
import re as _re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

from ...parser.ast_nodes import (
    AggregateExpression,
    AliasRef,
    AllExpression,
    AnyExpression,
    BinaryExpression,
    CaseExpression,
    CaseItem,
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

class PropertyMixin:
    """Mixin providing FHIR property access and choice-type translations."""
    @staticmethod
    def _arg_involves_query(node: Any) -> bool:
        """Return True if *node* is or transitively wraps a CQL Query.

        This is used to decide whether a CQL aggregate function call
        (Min, Max, …) will produce an SQL aggregate that must be wrapped
        in a scalar subquery.
        """
        from ...parser.ast_nodes import Query as CQLQuery, Property as CQLProperty
        if isinstance(node, CQLQuery):
            return True
        if isinstance(node, CQLProperty):
            return PropertyMixin._arg_involves_query(node.source)
        return False

    def _infer_source_shape(self, source: Any) -> RowShape:
        """
        Infer the shape of a property's source expression.

        Args:
            source: The source AST node (Retrieve, Identifier, etc.)

        Returns:
            RowShape indicating what the source produces.
        """
        from ...parser.ast_nodes import Retrieve

        if source is None:
            return RowShape.UNKNOWN

        # Retrieve always produces RESOURCE_ROWS
        if isinstance(source, Retrieve):
            return RowShape.RESOURCE_ROWS

        # Check if it's an identifier referencing a known definition
        if isinstance(source, Identifier):
            name = source.name
            # Look up definition metadata
            meta = self.context.definition_meta.get(name)
            if meta:
                return meta.shape
            # Check if it's an alias with known shape info
            if self.context.is_alias(name):
                symbol = self.context.lookup_symbol(name)
                if symbol and hasattr(symbol, 'shape'):
                    return symbol.shape

        return RowShape.UNKNOWN

    def _infer_fhirpath_func_for_property(self, path: str, boolean_context: bool) -> str:
        """Infer the appropriate fhirpath UDF using FHIR schema when available."""
        if boolean_context:
            return "fhirpath_bool"
        schema = getattr(self.context, 'fhir_schema', None) if self.context else None
        if schema:
            # Try to find the resource type from context for schema lookup
            resource_type = getattr(self.context, '_current_resource_type', None)
            if resource_type:
                udf = schema.get_udf_for_element(resource_type, path)
                if udf:
                    return udf
            # If no resource type, try common resource types
            for rt in ["Observation", "Condition", "Encounter", "Procedure", "MedicationRequest", "Patient"]:
                udf = schema.get_udf_for_element(rt, path)
                if udf:
                    return udf
        return "fhirpath_text"

    def _handle_scalar_property(
        self,
        source_sql: SQLExpression,
        path: str,
        boolean_context: bool
    ) -> SQLExpression:
        """
        Handle property access on a scalar source.

        Uses simple fhirpath call since source is single-valued.

        Args:
            source_sql: The translated source SQL expression
            path: The FHIRPath property path
            boolean_context: Whether this is in a boolean context

        Returns:
            SQL expression for the property access
        """
        func_name = self._infer_fhirpath_func_for_property(path, boolean_context)

        result = self._flatten_fhirpath_source(source_sql, path, func_name)
        return result

    def _handle_resource_rows_property(
        self,
        source: Any,
        source_sql: SQLExpression,
        path: str,
        boolean_context: bool
    ) -> SQLExpression:
        """
        Handle property access on a multi-row source using list_apply.

        When the source has multiple rows per patient, we need to apply
        the fhirpath function to each row and collect results.

        Args:
            source: The source AST node
            source_sql: The translated source SQL expression
            path: The FHIRPath property path
            boolean_context: Whether this is in a boolean context

        Returns:
            SQL expression using list_apply for row-by-row property extraction
        """
        func_name = self._infer_fhirpath_func_for_property(path, boolean_context)

        # Build: list_apply(source, x -> fhirpath_text(x, 'path'))
        # This applies fhirpath to each element in the source list
        return SQLFunctionCall(
            name="list_apply",
            args=[
                source_sql,
                SQLLambda(
                    param="x",
                    body=SQLFunctionCall(
                        name=func_name,
                        args=[SQLIdentifier(name="x"), SQLLiteral(value=path)],
                    ),
                ),
            ],
        )

    def _translate_property(self, prop: Property, boolean_context: bool = False) -> SQLExpression:
        """Translate a CQL property access to SQL (using fhirpath UDFs).

        This method uses shape-aware handling:
        - PATIENT_SCALAR sources use simple fhirpath calls
        - RESOURCE_ROWS sources use list_apply to apply fhirpath to each element
        """
        path = prop.path
        source = prop.source

        # Extension property mapping: use context's versioned paths
        source_name = source.name if isinstance(source, Identifier) else None
        ext_paths_map = self.context.extension_paths or {}
        if source_name and source_name in ext_paths_map:
            ext_paths = ext_paths_map[source_name]
            if path in ext_paths:
                path = ext_paths[path]

        # QICore extension property resolution: properties defined as FHIR extensions
        _ext_fhirpath = _get_qicore_extension_fhirpath(
            self.context.profile_registry, self.context.resource_type, path
        )
        if _ext_fhirpath is not None:
            path = _ext_fhirpath

        # Component filter query without return clause:
        # CQL: (singleton from (X.component C where C.code ~ "Systolic")).value
        # The outer .value is the implicit return path for the component query.
        if isinstance(source, UnaryExpression):
            op = source.operator.lower() if isinstance(source.operator, str) else source.operator
            if op == "singleton from" and isinstance(source.operand, Query):
                inner_q = source.operand
                if (not inner_q.return_clause
                        and self._is_component_filter_query_no_return(inner_q)):
                    return self._translate_component_filter_with_outer_path(
                        inner_q, path)

        # Handle choice types (value[x], effective[x], onset[x], etc.)
        is_choice_type = path.endswith("[x]") or self._is_choice_type_path(path)

        # Check column registry first for precomputed columns
        if isinstance(source, Identifier) and not self.context.is_alias(source.name):
            source_name = source.name
            if source_name not in self.context.includes:
                # Try column registry lookup
                col_name = self.context.column_registry.lookup(source_name, path)
                if col_name:
                    # Get the JOIN alias for this CTE
                    if self.context.query_builder:
                        meta = self.context.definition_meta.get(source_name)
                        shape = meta.shape if meta else RowShape.UNKNOWN
                        alias = self.context.query_builder.track_cte_reference(
                            source_name,
                            usage=ExprUsage.SCALAR,
                            shape=shape
                        )
                        return SQLQualifiedIdentifier(parts=[alias, col_name])

        # Shape-aware handling for Identifier sources referencing definitions
        if isinstance(source, Identifier) and not self.context.is_alias(source.name):
            source_name = source.name
            # Skip if this is an included library reference (handled below)
            if source_name not in self.context.includes:
                source_shape = self._infer_source_shape(source)
                if source_shape == RowShape.RESOURCE_ROWS:
                    # Source has multiple rows per patient — use a correlated
                    # subquery to extract the property from each row in the CTE.
                    # list_apply() cannot be used here because the CTE reference
                    # resolves to a single JOIN row (j1.resource), not a DuckDB LIST.
                    func_name = self._infer_fhirpath_func_for_property(path, boolean_context)
                    _outer_pid = self.context.resource_alias or self.context.patient_alias or "p"
                    result = SQLSubquery(query=SQLSelect(
                        columns=[SQLFunctionCall(
                            name=func_name,
                            args=[
                                SQLQualifiedIdentifier(parts=["_rr", "resource"]),
                                SQLLiteral(value=path),
                            ],
                        )],
                        from_clause=SQLAlias(
                            expr=SQLIdentifier(name=source_name, quoted=True),
                            alias="_rr",
                        ),
                        where=SQLBinaryOp(
                            operator="=",
                            left=SQLQualifiedIdentifier(parts=["_rr", "patient_id"]),
                            right=SQLQualifiedIdentifier(parts=[_outer_pid, "patient_id"]),
                        ),
                    ))
                    return result
                elif source_shape == RowShape.PATIENT_SCALAR:
                    # Source is scalar per patient - use simple fhirpath call
                    source_sql = self.translate(source, usage=ExprUsage.SCALAR)
                    if is_choice_type:
                        return self._translate_choice_type_property_from_source(source_sql, path, boolean_context)
                    return self._handle_scalar_property(source_sql, path, boolean_context)

        # Handle ParameterPlaceholder source (from function inlining)
        # The placeholder carries a SQL expression (e.g., SQLIdentifier("BetaBlockerOrdered"))
        # which references a query alias — we need to access .resource on it for fhirpath calls.
        # But if the SQL is already a function call (e.g., fhirpath_text result), it's a scalar
        # value and should NOT have .resource appended.
        if isinstance(source, ParameterPlaceholder):
            source_sql = source.sql_expr

            from ...translator.ast_utils import ast_get_name

            table_name = ast_get_name(source_sql)

            if isinstance(source_sql, SQLIdentifier):
                if source_sql.name.startswith('_lt_'):
                    # Lambda parameter — scalar JSON value, NOT a table row.
                    # Use directly as fhirpath source without .resource.
                    if is_choice_type:
                        return self._translate_choice_type_property_from_source(source_sql, path, boolean_context)
                    return self._make_fhirpath_call(source_sql, path, boolean_context)
                resource_col = SQLQualifiedIdentifier(parts=[source_sql.name, "resource"])
            elif isinstance(source_sql, SQLFunctionCall):
                # Already a function call result (scalar) — use flatten to combine paths
                func_name = "fhirpath_bool" if boolean_context else "fhirpath_text"
                return self._flatten_fhirpath_source(source_sql, path, func_name)
            elif isinstance(source_sql, (SQLSelect, SQLSubquery, SQLUnion, SQLIntersect, SQLExcept)):
                # The parameter resolved to a full query expression, but we
                # are inside a query scope where the source is already aliased
                # (e.g., IschemicStrokeEncounter).  Use that alias instead of
                # creating a dangling _param_src reference.
                if self.context.resource_alias:
                    resource_col = SQLQualifiedIdentifier(
                        parts=[self.context.resource_alias, "resource"]
                    )
                else:
                    # Wrap in a scalar subquery so the alias is properly scoped
                    inner = source_sql
                    if isinstance(inner, SQLSelect):
                        inner = SQLSubquery(query=inner)
                    elif not isinstance(inner, SQLSubquery):
                        inner = SQLSubquery(query=inner)
                    alias_name = "_param_src"
                    fhirpath_func = "fhirpath_bool" if boolean_context else "fhirpath_text"
                    return SQLSubquery(query=SQLSelect(
                        columns=[SQLFunctionCall(
                            name=fhirpath_func,
                            args=[
                                SQLQualifiedIdentifier(parts=[alias_name, "resource"]),
                                SQLLiteral(value=path),
                            ],
                        )],
                        from_clause=SQLAlias(expr=inner, alias=alias_name),
                    ))
            elif table_name:
                resource_col = SQLQualifiedIdentifier(parts=[table_name, "resource"])
            else:
                raise ValueError(
                    f"Cannot extract table name from ParameterPlaceholder "
                    f"source_sql of type {type(source_sql).__name__}"
                )

            if is_choice_type:
                return self._translate_choice_type_property(resource_col, path, boolean_context)
            return self._make_fhirpath_call(resource_col, path, boolean_context)

        if source is None:
            # Implicit source - use current context
            if self.context.resource_alias:
                # Property access on current resource - build proper qualified identifier
                resource_col = SQLQualifiedIdentifier(parts=[self.context.resource_alias, "resource"])
                if is_choice_type:
                    return self._translate_choice_type_property(resource_col, path, boolean_context)
                return self._make_fhirpath_call(resource_col, path, boolean_context)
            else:
                # No current resource - treat as simple property
                return SQLIdentifier(name=path)

        # Check if source is an included library reference (e.g., AdultOutpatientEncounters."Qualifying Encounters")
        if isinstance(source, Identifier):
            source_name = source.name
            if source_name in self.context.includes:
                # Check if this is a well-known library code constant (QICoreCommon, etc.)
                resolved = _resolve_library_code_constant(source_name, path, context=self.context)
                if resolved is not None:
                    return SQLLiteral(value=resolved)

                # This is a reference to a definition in an included library
                # Treat as a qualified identifier: LibraryName.DefinitionName
                full_name = f"{source_name}.{path}"
                # Return a subquery to the CTE
                # Note: The CTE will be created from the included library's definitions
                # during the optimization phases. We generate the reference now and
                # trust that the CTE will exist at execution time.
                if boolean_context:
                    # Use correlated EXISTS for boolean context
                    return self._build_correlated_exists(full_name)
                else:
                    subquery = SQLSubquery(query=SQLSelect(
                        columns=[SQLIdentifier(name="*")],
                        from_clause=SQLIdentifier(name=full_name, quoted=True)
                    ))
                    return subquery

        # Check if source is an alias with a stored SQL expression
        if isinstance(source, Identifier):
            source_name = source.name
            if self.context.is_alias(source_name):
                symbol = self.context.lookup_symbol(source_name)
                # Use getattr to safely get sql_expr (different SymbolInfo classes exist)
                sql_expr_val = getattr(symbol, 'sql_expr', None) if symbol else None
                # Also check sql_ref for translator.py SymbolInfo
                if not sql_expr_val:
                    sql_expr_val = getattr(symbol, 'sql_ref', None) if symbol else None

                # Check if this is a table alias (alias pointing to a CTE table reference)
                table_alias = getattr(symbol, 'table_alias', None) if symbol else None
                cte_name = getattr(symbol, 'cte_name', None) if symbol else None

                if table_alias:
                    # This alias points to a CTE table reference
                    # Property access should use: alias.resource or alias.column_name
                    resource_col = SQLQualifiedIdentifier(parts=[table_alias, "resource"])

                    # Check if the CTE has a precomputed column for this path
                    if cte_name:
                        col_name = self.context.column_registry.lookup(cte_name, path)
                        if col_name:
                            return SQLQualifiedIdentifier(parts=[table_alias, col_name])

                    # Check if the CTE returns a tuple (to_json(struct_pack(...))).
                    # CQL tuples are NOT FHIR resources — fhirpath_text cannot
                    # evaluate on them.  Use json_extract_string instead.
                    if cte_name and self._is_tuple_returning_definition(cte_name):
                        return SQLFunctionCall(
                            name="json_extract_string",
                            args=[resource_col, SQLLiteral(value=f"$.{path}")],
                        )

                    # Use fhirpath on the resource column.
                    # NOTE: dateTime properties (effectiveDateTime, recordedDate,
                    # etc.) must use fhirpath_text so that full timestamp
                    # precision is preserved for temporal operators like
                    # ``during``.  Precision-aware operators (``during day of``)
                    # apply their own CAST to DATE when needed.
                    func_name = "fhirpath_bool" if boolean_context else "fhirpath_text"

                    result = SQLFunctionCall(
                        name=func_name,
                        args=[
                            SQLQualifiedIdentifier(parts=[table_alias, "resource"]),
                            SQLLiteral(value=path)
                        ],
                    )
                    return result

                # Check if this is a union expression marker
                union_expr = getattr(symbol, 'union_expr', None) if symbol else None
                if sql_expr_val == "__UNION__" and union_expr is not None:
                    # Handle property access on a union - apply fhirpath to each operand and COALESCE
                    func_name = "fhirpath_bool" if boolean_context else "fhirpath_text"
                    coalesce_args = []
                    for operand in union_expr.operands:
                        coalesce_args.append(SQLFunctionCall(
                            name=func_name,
                            args=[operand, SQLLiteral(value=path)],
                        ))
                    return SQLFunctionCall(name="COALESCE", args=coalesce_args)
                elif sql_expr_val == "__UNION_CASE__" and union_expr is not None:
                    # Handle property access on a CASE containing a union
                    # Apply fhirpath to each UNION operand and COALESCE
                    func_name = "fhirpath_bool" if boolean_context else "fhirpath_text"
                    coalesce_args = []

                    # Check if union_expr is a structured SQLCase or a RawSQLExpression
                    if isinstance(union_expr, SQLCase):
                        for condition, result in union_expr.when_clauses:
                            if isinstance(result, SQLUnion):
                                for operand in result.operands:
                                    coalesce_args.append(SQLFunctionCall(
                                        name=func_name,
                                        args=[operand, SQLLiteral(value=path)],
                                    ))
                            else:
                                # Non-union result - apply fhirpath directly
                                coalesce_args.append(SQLFunctionCall(
                                    name=func_name,
                                    args=[result, SQLLiteral(value=path)],
                                ))
                    else:
                        # union_expr is a RawSQLExpression - just use it directly
                        # This won't fix the invalid SQL, but it will at least not crash
                        return SQLFunctionCall(
                            name=func_name,
                            args=[union_expr, SQLLiteral(value=path)],
                        )

                    return SQLFunctionCall(name="COALESCE", args=coalesce_args)


                # Handle alias with ast_expr but no sql_expr (e.g., inlined function query aliases)
                if not sql_expr_val and symbol and hasattr(symbol, 'ast_expr') and symbol.ast_expr:
                    ast_expr = symbol.ast_expr
                    if isinstance(ast_expr, SQLIdentifier) and not ast_expr.quoted:
                        if ast_expr.name.startswith('_lt_'):
                            # Lambda parameter — scalar JSON value, NOT a table row.
                            # Property access should apply fhirpath directly to the value
                            # without appending .resource.
                            if is_choice_type:
                                return self._translate_choice_type_property_from_source(ast_expr, path, boolean_context)
                            return self._make_fhirpath_call(ast_expr, path, boolean_context)
                        # Unquoted identifier (outer alias) — needs .resource for fhirpath
                        resource_col = SQLQualifiedIdentifier(parts=[ast_expr.name, "resource"])
                        if is_choice_type:
                            return self._translate_choice_type_property_from_source(resource_col, path, boolean_context)
                        return self._make_fhirpath_call(resource_col, path, boolean_context)

                if sql_expr_val:
                    # Check if the expression is a list operation (needs extraction for scalar use) - fixes B5
                    # First try AST-based check if we have it
                    from ...translator import ast_utils
                    if symbol and hasattr(symbol, 'ast_expr') and symbol.ast_expr:
                        from ...translator.ast_utils import (
                            ast_is_list_operation,
                            ast_is_boolean_result,
                        )
                        is_list_expr = ast_is_list_operation(symbol.ast_expr)
                        is_boolean_result = ast_is_boolean_result(symbol.ast_expr)

                        # Build source_ast from symbol.ast_expr
                        if is_list_expr and not is_boolean_result:
                            source_ast = SQLFunctionCall(name="list_extract", args=[symbol.ast_expr, SQLLiteral(value=1)])
                        else:
                            source_ast = symbol.ast_expr

                        # Check if ast_expr is a CTE or alias identifier (needs .resource)
                        if (isinstance(source_ast, SQLIdentifier)
                                and '.' not in source_ast.name
                                and not source_ast.name.endswith('.resource')):
                            if source_ast.quoted:
                                source_ast = SQLIdentifier(name=f'"{source_ast.name}".resource')
                            elif self.context.is_alias(source_ast.name):
                                source_ast = SQLQualifiedIdentifier(parts=[source_ast.name, "resource"])

                        # CRITICAL: Check if source_sql already is a fhirpath call (AST-based check)
                        if isinstance(source_sql, SQLFunctionCall) and source_sql.name and source_sql.name.startswith('fhirpath_'):
                            existing_func_type = ast_utils.infer_fhirpath_type_from_ast(source_sql)
                            existing_resource = source_sql.args[0] if source_sql.args and len(source_sql.args) >= 2 else None
                            existing_path = source_sql.args[1].value if (source_sql.args and len(source_sql.args) >= 2
                                                                          and hasattr(source_sql.args[1], 'value')) else None
                            new_path = f"{existing_path}.{path}" if existing_path else path
                            func_name = f"fhirpath_{existing_func_type}"
                            return SQLFunctionCall(
                                name=func_name,
                                args=[existing_resource, SQLLiteral(value=new_path)]
                            )

                        if is_choice_type:
                            return self._translate_choice_type_property_from_source(source_ast, path, boolean_context)
                        func_name = "fhirpath_bool" if boolean_context else "fhirpath_text"
                        return self._flatten_fhirpath_source(source_ast, path, func_name)
                    else:
                        # Legacy string fallback — no ast_expr available
                        logger.warning("Property translation using string fallback (no ast_expr) for sql_expr: %.80s", sql_expr_val)
                        # Try to check the source_sql AST node first if available
                        from ...translator.ast_utils import ast_is_list_operation
                        source_sql_node = getattr(symbol, 'sql_expr_ast', None) if symbol else None
                        if source_sql_node is not None:
                            is_list_expr = ast_is_list_operation(source_sql_node)
                        else:
                            is_list_expr = any(op in sql_expr_val for op in ['list_filter', 'jsonConcat', 'list_apply'])
                        is_boolean_result = any(op in sql_expr_val for op in ['> 0', '>= 0', '= 0', '< 0', '<= 0', '!= 0', '<> 0'])

                        # Build source_sql as an AST node rather than SQLRaw where possible
                        raw_source = SQLRaw(raw_sql=sql_expr_val)
                        if is_list_expr and not is_boolean_result:
                            raw_source = SQLFunctionCall(
                                name="list_extract",
                                args=[raw_source, SQLLiteral(value=1)],
                            )
                        elif (sql_expr_val.startswith('"') and sql_expr_val.endswith('"')
                              and '.' not in sql_expr_val):
                            # Quoted CTE name — use qualified identifier for .resource
                            cte_name = sql_expr_val.strip('"')
                            raw_source = SQLQualifiedIdentifier(parts=[cte_name, "resource"])

                        # CRITICAL: Check if source_sql already is a fhirpath call (AST-based check)
                        if isinstance(source_sql, SQLFunctionCall) and source_sql.name and source_sql.name.startswith('fhirpath_'):
                            existing_func_type = ast_utils.infer_fhirpath_type_from_ast(source_sql)
                            existing_resource = source_sql.args[0] if source_sql.args and len(source_sql.args) >= 2 else None
                            existing_path = source_sql.args[1].value if (source_sql.args and len(source_sql.args) >= 2
                                                                          and hasattr(source_sql.args[1], 'value')) else None
                            new_path = f"{existing_path}.{path}" if existing_path else path
                            func_name = f"fhirpath_{existing_func_type}"
                            return SQLFunctionCall(
                                name=func_name,
                                args=[existing_resource, SQLLiteral(value=new_path)]
                            )

                        source_sql = raw_source
                        if is_choice_type:
                            return self._translate_choice_type_property_from_source(source_sql, path, boolean_context)
                        func_name = "fhirpath_bool" if boolean_context else "fhirpath_text"
                        return self._flatten_fhirpath_source(source_sql, path, func_name)

        # Handle AliasRef source — resolve alias to its .resource column
        if isinstance(source, AliasRef):
            alias_name = source.name
            if self.context.is_alias(alias_name):
                symbol = self.context.lookup_symbol(alias_name)

                # Check table_alias first (set by _translate_query_on_alias for
                # inlined fluent function queries like hospitalizationWithObservation).
                table_alias = getattr(symbol, 'table_alias', None) if symbol else None
                _ar_cte = getattr(symbol, 'cte_name', None) if symbol else None
                if table_alias:
                    resource_col = SQLQualifiedIdentifier(parts=[table_alias, "resource"])
                    if _ar_cte:
                        col_name = self.context.column_registry.lookup(_ar_cte, path)
                        if col_name:
                            return SQLQualifiedIdentifier(parts=[table_alias, col_name])
                    func_name = "fhirpath_bool" if boolean_context else "fhirpath_text"
                    result = SQLFunctionCall(
                        name=func_name,
                        args=[resource_col, SQLLiteral(value=path)],
                    )
                    if is_choice_type:
                        return self._translate_choice_type_property(resource_col, path, boolean_context)
                    return result

                ast_expr = getattr(symbol, 'ast_expr', None) if symbol else None
                if isinstance(ast_expr, SQLIdentifier):
                    # Alias points to an identifier — need .resource for fhirpath
                    resource_col = SQLQualifiedIdentifier(parts=[ast_expr.name, "resource"])
                    if is_choice_type:
                        return self._translate_choice_type_property(resource_col, path, boolean_context)
                    return self._make_fhirpath_call(resource_col, path, boolean_context)
                elif isinstance(ast_expr, SQLFunctionCall):
                    # Already a function result — chain fhirpath
                    return self._make_fhirpath_call(ast_expr, path, boolean_context)

        # Unwrap 'as' type-cast to find the underlying alias for resource qualification.
        # CQL `(X as Type).property` has source=BinaryExpression('as', left=Identifier(X), ...)
        # which misses the Identifier alias handler above, but the inner Identifier IS an alias.
        _as_inner = source
        if isinstance(source, BinaryExpression) and source.operator == "as":
            _as_inner = source.left

        if isinstance(_as_inner, Identifier) and self.context.is_alias(_as_inner.name):
            sym = self.context.lookup_symbol(_as_inner.name)
            ta = getattr(sym, 'table_alias', None) if sym else None
            if ta:
                resource_col = SQLQualifiedIdentifier(parts=[ta, "resource"])
                if is_choice_type:
                    return self._translate_choice_type_property(resource_col, path, boolean_context)
                return self._make_fhirpath_call(resource_col, path, boolean_context)
            # Also check cte_name path
            cte = getattr(sym, 'cte_name', None) if sym else None
            if cte:
                meta = self.context.get_definition_meta(cte)
                col = "resource" if (meta and meta.has_resource) else self._get_definition_value_column(cte)
                resource_col = SQLQualifiedIdentifier(parts=[_as_inner.name, col])
                if is_choice_type:
                    return self._translate_choice_type_property(resource_col, path, boolean_context)
                return self._make_fhirpath_call(resource_col, path, boolean_context)

        # Handle ParameterPlaceholder from function inlining wrapped in 'as' cast.
        # ParameterPlaceholder carries an sql_expr that may be a bare alias identifier.
        if isinstance(_as_inner, ParameterPlaceholder) and _as_inner is not source:
            pp_sql = _as_inner.sql_expr
            if isinstance(pp_sql, SQLIdentifier) and self.context.is_alias(pp_sql.name):
                sym = self.context.lookup_symbol(pp_sql.name)
                ta = getattr(sym, 'table_alias', None) if sym else None
                if ta:
                    resource_col = SQLQualifiedIdentifier(parts=[ta, "resource"])
                    if is_choice_type:
                        return self._translate_choice_type_property(resource_col, path, boolean_context)
                    return self._make_fhirpath_call(resource_col, path, boolean_context)

        # CRITICAL: The source must be translated with SCALAR context
        # because FHIRPath functions need a single resource, not a collection.
        source_sql = self.translate(source, usage=ExprUsage.SCALAR)

        if is_choice_type:
            # Handle choice type with COALESCE
            return self._translate_choice_type_property_from_source(source_sql, path, boolean_context)

        # Determine the appropriate fhirpath function
        if boolean_context:
            func_name = "fhirpath_bool"
        else:
            # Default to text (most common)
            func_name = "fhirpath_text"

        # Build the FHIRPath expression
        if isinstance(source_sql, SQLIdentifier):
            source_str = source_sql.name
            # Check if it's a resource column reference
            if "." in source_str and (source_str.endswith(".resource") or source_str.endswith(".data")):
                return SQLFunctionCall(
                    name=func_name,
                    args=[SQLIdentifier(name=source_str), SQLLiteral(value=path)],
                )
            # Check if it's a quoted definition reference (CTE name)
            # In that case, use the resource column from that CTE
            elif source_sql.quoted:
                # This is a definition CTE reference - use its resource column
                return SQLFunctionCall(
                    name=func_name,
                    args=[SQLIdentifier(name=f'"{source_str}".resource'), SQLLiteral(value=path)],
                )
            else:
                # Property access on a non-resource - could be alias
                # If the identifier is a known query alias, it represents a CTE/subquery row
                # with (patient_id, resource) columns — qualify with .resource for fhirpath
                if self.context.is_alias(source_str):
                    resource_col = SQLQualifiedIdentifier(parts=[source_str, "resource"])
                    if is_choice_type:
                        return self._translate_choice_type_property_from_source(resource_col, path, boolean_context)
                    return SQLFunctionCall(
                        name=func_name,
                        args=[resource_col, SQLLiteral(value=path)],
                    )
                return SQLFunctionCall(
                    name=func_name,
                    args=[SQLIdentifier(name=source_str), SQLLiteral(value=path)],
                )

        # Check if source is a SQLSubquery referencing a definition CTE
        # e.g., (SELECT * FROM "Definition") - we need to use resource column
        if isinstance(source_sql, SQLSubquery) and isinstance(source_sql.query.from_clause, SQLIdentifier):
            from_name = source_sql.query.from_clause.name
            normalized_name = from_name.strip('"')

            # Check if this CTE is being tracked for JOIN conversion
            if self.context.query_builder:
                ref = self.context.query_builder.get_cte_reference(normalized_name)
                if ref:
                    # CTE is being JOINed - use column reference instead of subquery
                    if path == "resource":
                        return SQLQualifiedIdentifier(parts=[ref.alias, "resource"])
                    else:
                        return SQLFunctionCall(
                            name=func_name,
                            args=[
                                SQLQualifiedIdentifier(parts=[ref.alias, "resource"]),
                                SQLLiteral(value=path)
                            ]
                        )

            # Check if it's a quoted CTE reference (fallback - not being JOINed)
            if source_sql.query.from_clause.quoted:
                # Use the resource column from the CTE
                resource_col = f'"{from_name}".resource'
                return SQLFunctionCall(
                    name=func_name,
                    args=[SQLIdentifier(name=resource_col), SQLLiteral(value=path)],
                )

        # Check if source is SQLUnion - need special handling for scalar context
        if isinstance(source_sql, SQLUnion):
            # SQLUnion in scalar context is invalid SQL
            # We need to convert each operand and then combine
            # For fhirpath_text on a union, we need to apply to each subquery
            # and combine with COALESCE (first non-null result wins)
            coalesce_args = []
            for operand in source_sql.operands:
                coalesce_args.append(SQLFunctionCall(
                    name=func_name,
                    args=[operand, SQLLiteral(value=path)],
                ))
            return SQLFunctionCall(name="COALESCE", args=coalesce_args)

        # Narrow SELECT * subqueries to SELECT resource before passing to fhirpath.
        # CQL queries without return clauses produce SELECT * which returns all
        # columns (patient_id, resource, etc.) but fhirpath functions expect a
        # single JSON resource value.
        source_sql = self._narrow_to_resource_column(source_sql)

        # Flatten nested fhirpath calls: fhirpath_X(fhirpath_text(res, 'a'), 'b')
        # → fhirpath_X(res, 'a.b').  fhirpath_text extracts a sub-object as text;
        # chaining another fhirpath on that text is fragile (the UDF may receive a
        # string instead of JSON).  Combining paths into a single call is both
        # correct and more efficient.
        flattened = self._flatten_fhirpath_source(source_sql, path, func_name)
        # If flattening happened, the inner resource arg will differ from source_sql
        if flattened.args[0] is not source_sql:
            return flattened

        # Tuple property access: CQL tuples are translated to
        # to_json(struct_pack(...)) which produces plain JSON, not FHIR resources.
        # fhirpath_text cannot evaluate on non-FHIR JSON, so use
        # json_extract_string instead.
        if self._is_tuple_json_source(source_sql):
            return SQLFunctionCall(
                name="json_extract_string",
                args=[source_sql, SQLLiteral(value=f"$.{path}")],
            )

        # Complex source expression
        return SQLFunctionCall(
            name=func_name,
            args=[source_sql, SQLLiteral(value=path)],
        )

    # Well-known FHIR choice type element base names used when effective[x]
    # or similar [x]-suffixed paths appear in CQL. Only used for explicit [x].
    _KNOWN_CHOICE_PATHS = {"effective", "onset", "abatement", "performed",
                           "medication", "timing", "occurred", "serviced"}

    def _is_choice_type_path(self, path: str) -> bool:
        """
        Check if a path is a known choice type element.
        
        Uses FHIRSchemaRegistry for accurate type checking.
        Requires registry to be available in context.
        """
        # Quick check: if path ends with [x], it's definitely a choice type
        if path.endswith("[x]"):
            return True
            
        # Extract base path and resource type
        base_path = path.replace("[x]", "")
        resource_type = getattr(self.context, 'resource_type', None)
        
        # Use registry if available
        if resource_type and hasattr(self.context, 'fhir_schema') and self.context.fhir_schema:
            if self.context.fhir_schema.is_choice_element(resource_type, base_path):
                return True
        
        # Fallback: only treat paths with explicit [x] suffix or known temporal
        # choice types as choice. Simple properties like "value" are handled
        # by the FHIRPath UDF's choice type fallback.
        return base_path in self._KNOWN_CHOICE_PATHS

    def _get_choice_types_for_resource(self, resource_type: Optional[str], path: str) -> List[str]:
        """
        Get valid choice types for a specific resource and path.
        
        Uses FHIRSchemaRegistry to query actual FHIR StructureDefinitions.

        Args:
            resource_type: The FHIR resource type (e.g., "Observation", "Condition")
            path: The property path (may include [x] suffix)

        Returns:
            List of choice type suffixes to try for COALESCE
        """
        base_path = path.replace("[x]", "")

        # Try registry first
        if resource_type and hasattr(self.context, 'fhir_schema') and self.context.fhir_schema:
            types = self.context.fhir_schema.get_choice_types(resource_type, base_path)
            if types:
                return types

        # Fallback: use generated FHIR type data for choice type resolution
        try:
            from fhir4ds.fhirpath.duckdb.fhir_types_generated import CHOICE_TYPES
            choice_key = f"{resource_type}.{base_path}" if resource_type else None
            if choice_key and choice_key in CHOICE_TYPES:
                field_names = CHOICE_TYPES[choice_key]
                suffixes = []
                for fn in field_names:
                    if fn.startswith(base_path):
                        suffix = fn[len(base_path):]
                        if suffix:
                            suffixes.append(suffix)
                if suffixes:
                    return suffixes
        except ImportError:
            pass

        return []

    def _translate_choice_type_property(self, resource_col: SQLExpression, path: str, boolean_context: bool) -> SQLExpression:
        """Translate a choice type property using COALESCE."""
        # Get the base path (without [x])
        base_path = path.replace("[x]", "")

        # Get resource-specific choice types
        resource_type = getattr(self.context, 'resource_type', None)
        type_suffixes = self._get_choice_types_for_resource(resource_type, path)

        # Build COALESCE of determined types
        coalesce_args = []
        for suffix in type_suffixes:
            full_path = f"{base_path}{suffix}"
            fhirpath_call = SQLFunctionCall(
                name="fhirpath_text",
                args=[resource_col, SQLLiteral(value=full_path)],
            )
            coalesce_args.append(fhirpath_call)

        if not coalesce_args:
            # Fallback: let UDF resolve choice type at runtime
            return SQLFunctionCall(
                name="fhirpath_text",
                args=[resource_col, SQLLiteral(value=base_path)],
            )

        return SQLFunctionCall(name="COALESCE", args=coalesce_args)

    def _translate_choice_type_property_from_source(self, source_sql: SQLExpression, path: str, boolean_context: bool) -> SQLExpression:
        """Translate a choice type property from a source expression."""
        base_path = path.replace("[x]", "")

        # Handle SQLUnion specially - need to apply fhirpath to each operand
        if isinstance(source_sql, SQLUnion):
            # For each operand, recursively call this method with the same path
            # Then combine with COALESCE
            coalesce_args = []
            for operand in source_sql.operands:
                coalesce_args.append(
                    self._translate_choice_type_property_from_source(operand, path, boolean_context)
                )
            return SQLFunctionCall(name="COALESCE", args=coalesce_args)

        # Check if source is a SQLSubquery referencing a definition CTE
        # In that case, use the resource column from that CTE
        actual_source = source_sql
        if isinstance(source_sql, SQLSubquery) and isinstance(source_sql.query.from_clause, SQLIdentifier):
            if source_sql.query.from_clause.quoted:
                from_name = source_sql.query.from_clause.name
                actual_source = SQLIdentifier(name=f'"{from_name}".resource')
        elif isinstance(source_sql, SQLIdentifier):
            # Check if it's a quoted definition reference (CTE name) without .resource
            if source_sql.quoted and not source_sql.name.endswith('.resource'):
                actual_source = SQLIdentifier(name=f'"{source_sql.name}".resource')

        # Get resource-specific choice types
        resource_type = getattr(self.context, 'resource_type', None)
        type_suffixes = self._get_choice_types_for_resource(resource_type, path)

        coalesce_args = []
        for suffix in type_suffixes:
            full_path = f"{base_path}{suffix}"
            fhirpath_call = self._flatten_fhirpath_source(
                actual_source, full_path, "fhirpath_text"
            )
            coalesce_args.append(fhirpath_call)

        if not coalesce_args:
            # Fallback: let UDF resolve choice type at runtime
            return self._flatten_fhirpath_source(
                actual_source, base_path, "fhirpath_text"
            )

        return SQLFunctionCall(name="COALESCE", args=coalesce_args)

    @staticmethod
    def _is_tuple_json_source(sql: SQLExpression) -> bool:
        """Check if an SQL expression produces a CQL tuple (to_json(struct_pack(...))).

        CQL tuples are NOT FHIR resources, so fhirpath_text cannot evaluate
        on them.  Property access on tuples must use json_extract_string instead.
        """
        # Direct: to_json(struct_pack(...))
        if (isinstance(sql, SQLFunctionCall)
                and sql.name == "to_json"
                and sql.args
                and isinstance(sql.args[0], SQLFunctionCall)
                and sql.args[0].name == "struct_pack"):
            return True

        # Subquery wrapping a tuple: (SELECT to_json(struct_pack(...)) FROM ...)
        inner = None
        if isinstance(sql, SQLSubquery) and isinstance(sql.query, SQLSelect):
            inner = sql.query
        elif isinstance(sql, SQLSelect):
            inner = sql

        if inner and inner.columns and len(inner.columns) >= 1:
            col = inner.columns[0]
            if isinstance(col, SQLAlias):
                col = col.expr
            if (isinstance(col, SQLFunctionCall)
                    and col.name == "to_json"
                    and col.args
                    and isinstance(col.args[0], SQLFunctionCall)
                    and col.args[0].name == "struct_pack"):
                return True

        return False

    def _is_tuple_returning_definition(self, def_name: str) -> bool:
        """Check if a definition returns a CQL tuple.

        Examines the CQL AST to detect return clauses with TupleExpression,
        including patterns like First(Query(...return Tuple...)).
        """
        from ...parser.ast_nodes import (
            Query as CQLQuery, FunctionRef, TupleExpression,
        )
        if not hasattr(self.context, '_definition_cql_asts'):
            return False
        cql_ast = self.context._definition_cql_asts.get(def_name)
        if cql_ast is None:
            return False

        def _has_tuple_return(node) -> bool:
            if isinstance(node, CQLQuery) and node.return_clause:
                ret_expr = node.return_clause.expression
                if isinstance(ret_expr, TupleExpression):
                    return True
            if isinstance(node, FunctionRef) and getattr(node, 'name', '') in ('First', 'Last'):
                for arg in (getattr(node, 'arguments', None) or []):
                    if _has_tuple_return(arg):
                        return True
            return False

        return _has_tuple_return(cql_ast)

    @staticmethod
    def _narrow_to_resource_column(sql: SQLExpression) -> SQLExpression:
        """Narrow a multi-column SELECT/subquery to just the resource column.

        CQL queries without a return clause produce SELECT * which returns all
        table columns (patient_id, resource, etc.). When such a query is used
        as an argument to fhirpath functions, only the ``resource`` column is
        needed.  This method rewrites the SELECT list to ``resource`` while
        preserving FROM, WHERE, JOINs and other clauses.
        """

        def _is_star(sel: SQLSelect) -> bool:
            if not sel.columns:
                return True
            if (len(sel.columns) == 1
                    and isinstance(sel.columns[0], SQLIdentifier)
                    and sel.columns[0].name == '*'):
                return True
            return False

        def _get_from_alias(from_clause: Optional[SQLExpression]) -> Optional[str]:
            if isinstance(from_clause, SQLAlias):
                return from_clause.alias
            if isinstance(from_clause, SQLIdentifier):
                return from_clause.name.strip('"') if from_clause.quoted else from_clause.name
            return None

        def _rewrite(sel: SQLSelect) -> SQLSelect:
            alias = _get_from_alias(sel.from_clause)
            if alias:
                resource_col: SQLExpression = SQLQualifiedIdentifier(parts=[alias, "resource"])
            else:
                resource_col = SQLIdentifier(name="resource")
            return SQLSelect(
                columns=[resource_col],
                from_clause=sel.from_clause,
                joins=sel.joins,
                where=sel.where,
                group_by=sel.group_by,
                having=sel.having,
                order_by=sel.order_by,
                limit=sel.limit,
                distinct=sel.distinct,
            )

        if isinstance(sql, SQLSelect) and _is_star(sql):
            return _rewrite(sql)

        if isinstance(sql, SQLSubquery) and isinstance(sql.query, SQLSelect) and _is_star(sql.query):
            return SQLSubquery(query=_rewrite(sql.query))

        return sql

    @staticmethod
    def _flatten_fhirpath_source(source_sql: SQLExpression, path: str, func_name: str) -> SQLFunctionCall:
        """Build a fhirpath call, flattening nested fhirpath chains.

        If *source_sql* is already a ``fhirpath_*`` call like
        ``fhirpath_text(resource, 'a')``, and we want to build
        ``fhirpath_X(source_sql, 'b')``, flatten to
        ``fhirpath_X(resource, 'a.b')``.  This avoids passing a scalar text
        value where a JSON resource is expected (which causes ``from_json`` to
        crash on non-JSON strings like datetimes).
        """
        _FHIRPATH_FUNCS = frozenset({
            "fhirpath_text", "fhirpath_json", "fhirpath", "fhirpath_bool",
            "fhirpath_date", "fhirpath_number",
        })
        if (isinstance(source_sql, SQLFunctionCall)
                and source_sql.name in _FHIRPATH_FUNCS
                and len(source_sql.args) >= 2
                and isinstance(source_sql.args[1], SQLLiteral)):
            inner_path = source_sql.args[1].value
            # Flatten dot-paths including those with FHIRPath functions like
            # .where() — e.g. extension.where(url='...').value is valid FHIRPath
            if isinstance(inner_path, str):
                combined = f"{inner_path}.{path}"
                return SQLFunctionCall(
                    name=func_name,
                    args=[source_sql.args[0], SQLLiteral(value=combined)],
                )
        return SQLFunctionCall(
            name=func_name,
            args=[source_sql, SQLLiteral(value=path)],
        )

    def _make_fhirpath_call(self, resource_col: SQLExpression, path: str, boolean_context: bool) -> SQLExpression:
        """Create a fhirpath UDF call, flattening nested fhirpath chains."""
        func_name = "fhirpath_bool" if boolean_context else "fhirpath_text"
        return self._flatten_fhirpath_source(resource_col, path, func_name)

