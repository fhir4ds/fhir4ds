"""Query translation mixin for CQL to SQL."""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from ...parser.ast_nodes import (
    BinaryExpression,
    CodeSelector,
    Identifier,
    MethodInvocation,
    Property,
    Query,
    QuerySource,
    Retrieve,
)
from ...translator.context import ExprUsage
from ...translator.function_inliner import ParameterPlaceholder
from ...translator.placeholder import (
    RetrievePlaceholder,
    contains_placeholder,
    find_all_placeholders,
)
from ...translator.types import (
    SQLAlias,
    SQLArray,
    SQLBinaryOp,
    SQLCase,
    SQLCast,
    SQLExists,
    SQLExpression,
    SQLFunctionCall,
    SQLIdentifier,
    SQLJoin,
    SQLLambda,
    SQLLambda2,
    SQLLiteral,
    SQLNull,
    SQLQualifiedIdentifier,
    SQLRaw,
    SQLSelect,
    SQLStructFieldAccess,
    SQLSubquery,
    SQLUnaryOp,
    SQLUnion,
    SQLIntersect,
    SQLExcept,
)
from ...translator.expressions._utils import (
    _contains_sql_subquery,
    _ensure_scalar_body,
    _is_list_returning_sql,
)

if TYPE_CHECKING:
    from ...translator.context import SQLTranslationContext
    from ...translator.expressions import ExpressionTranslator


def _demote_audit_struct_to_bool(expr: SQLExpression) -> SQLExpression:
    """Extract .result from audit-struct expressions so they can be used as SQL WHERE predicates.

    Audit macros (audit_and, audit_or, audit_not, audit_leaf) return
    STRUCT(result BOOLEAN, evidence ...) which DuckDB cannot use as a boolean
    predicate in WHERE/CASE WHEN clauses.  This helper wraps any audit macro call
    in a SQLStructFieldAccess(.result) so the expression yields a plain BOOLEAN.

    Uses SQLStructFieldAccess (a proper AST node) rather than SQLRaw so that
    Phase 3 placeholder resolution can still traverse into the expression.

    Recurses through SQL AND/OR, CASE WHEN conditions, NOT, and subqueries
    so that compound expressions that mix audit structs with plain booleans
    are handled correctly.
    """
    if isinstance(expr, SQLFunctionCall) and expr.name.startswith("audit_"):
        return SQLStructFieldAccess(expr=expr, field_name="result")
    if isinstance(expr, SQLBinaryOp) and expr.operator in ("AND", "OR"):
        new_left = _demote_audit_struct_to_bool(expr.left)
        new_right = _demote_audit_struct_to_bool(expr.right)
        if new_left is not expr.left or new_right is not expr.right:
            return SQLBinaryOp(left=new_left, operator=expr.operator, right=new_right)
    if isinstance(expr, SQLUnaryOp) and expr.operator == "NOT":
        new_operand = _demote_audit_struct_to_bool(expr.operand)
        if new_operand is not expr.operand:
            return SQLUnaryOp(operator="NOT", operand=new_operand)
    if isinstance(expr, SQLCase):
        changed = False
        new_whens = []
        for cond, result in expr.when_clauses:
            new_cond = _demote_audit_struct_to_bool(cond)
            if new_cond is not cond:
                changed = True
            new_whens.append((new_cond, result))
        if changed:
            return SQLCase(when_clauses=new_whens, else_clause=expr.else_clause)
    return expr


def _deep_demote_audit_in_sql(node: SQLExpression) -> SQLExpression:
    """Recursively walk an entire SQL AST and demote audit structs in boolean contexts.

    For non-boolean CTEs (RESOURCE_ROWS, PATIENT_MULTI_VALUE), the translator
    may leak audit macros into WHERE clauses and CASE WHEN conditions. This
    walker strips those audit structs so they evaluate as plain booleans.
    """
    # SQLSelect.columns can contain either SQLExpression nodes or (expr, alias)
    # tuples (both are valid per types.py).  Handle the tuple case so that
    # CASE WHEN conditions inside tuple-form columns are reached by the walker.
    if isinstance(node, tuple) and len(node) == 2:
        expr, alias = node
        new_expr = _deep_demote_audit_in_sql(expr)
        if new_expr is not expr:
            return (new_expr, alias)
        return node
    if isinstance(node, SQLSelect):
        # First, deep-walk the WHERE to fix nested CASE WHEN conditions that
        # contain audit structs (e.g. CAST(CASE WHEN audit_not(...) THEN ...
        # END AS TIMESTAMP) inside comparisons).  Then demote the top-level
        # to boolean for the WHERE predicate.
        new_where = node.where
        if new_where:
            new_where = _deep_demote_audit_in_sql(new_where)
            new_where = _demote_audit_struct_to_bool(new_where)
        new_from = _deep_demote_audit_in_sql(node.from_clause) if node.from_clause else None
        changed = (new_where is not node.where) or (new_from is not node.from_clause)
        new_cols = []
        for c in (node.columns or []):
            nc = _deep_demote_audit_in_sql(c)
            if nc is not c:
                changed = True
            new_cols.append(nc)
        new_joins = []
        for j in (node.joins or []):
            nj = _deep_demote_audit_in_sql(j)
            if nj is not j:
                changed = True
            new_joins.append(nj)
        if changed:
            return SQLSelect(
                columns=new_cols,
                from_clause=new_from,
                where=new_where,
                group_by=node.group_by,
                having=node.having,
                order_by=node.order_by,
                limit=node.limit,
                joins=new_joins,
                distinct=node.distinct,
            )
        return node
    if isinstance(node, SQLSubquery):
        new_q = _deep_demote_audit_in_sql(node.query)
        if new_q is not node.query:
            return SQLSubquery(query=new_q)
        return node
    if isinstance(node, SQLAlias):
        new_e = _deep_demote_audit_in_sql(node.expr)
        if new_e is not node.expr:
            return SQLAlias(expr=new_e, alias=node.alias)
        return node
    if isinstance(node, SQLJoin):
        new_t = _deep_demote_audit_in_sql(node.table)
        new_on = _demote_audit_struct_to_bool(node.on_condition) if node.on_condition else None
        if new_t is not node.table or new_on is not node.on_condition:
            return SQLJoin(join_type=node.join_type, table=new_t, on_condition=new_on)
        return node
    if isinstance(node, (SQLUnion, SQLIntersect, SQLExcept)):
        cls = type(node)
        new_ops = []
        changed = False
        for op in node.operands:
            new_op = _deep_demote_audit_in_sql(op)
            if new_op is not op:
                changed = True
            new_ops.append(new_op)
        if changed:
            kwargs = {"operands": new_ops}
            if isinstance(node, SQLUnion):
                kwargs["distinct"] = node.distinct
            return cls(**kwargs)
        return node
    if isinstance(node, SQLCase):
        return _demote_audit_struct_to_bool(node)
    if isinstance(node, SQLExists):
        new_sub = _deep_demote_audit_in_sql(node.subquery)
        if new_sub is not node.subquery:
            return SQLExists(subquery=new_sub)
        return node
    # Recurse into expression nodes that can contain nested CASE / audit structs.
    if isinstance(node, SQLCast):
        new_inner = _deep_demote_audit_in_sql(node.expression)
        if new_inner is not node.expression:
            return SQLCast(expression=new_inner, target_type=node.target_type, try_cast=node.try_cast)
        return node
    if isinstance(node, SQLFunctionCall):
        if node.args:
            changed = False
            new_args = []
            for a in node.args:
                na = _deep_demote_audit_in_sql(a)
                if na is not a:
                    changed = True
                new_args.append(na)
            if changed:
                return SQLFunctionCall(name=node.name, args=new_args, distinct=node.distinct)
        return node
    if isinstance(node, SQLBinaryOp):
        new_left = _deep_demote_audit_in_sql(node.left)
        new_right = _deep_demote_audit_in_sql(node.right)
        if new_left is not node.left or new_right is not node.right:
            return SQLBinaryOp(left=new_left, operator=node.operator, right=new_right)
        return node
    if isinstance(node, SQLUnaryOp):
        new_operand = _deep_demote_audit_in_sql(node.operand)
        if new_operand is not node.operand:
            return SQLUnaryOp(operator=node.operator, operand=new_operand, prefix=node.prefix)
        return node
    return node


import re as _re


def _find_matching_paren(s: str, start: int) -> int:
    """Find the closing paren matching the open paren at *start*."""
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "(":
            depth += 1
        elif s[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


_CASE_WHEN_AUDIT_RE = _re.compile(r"CASE\s+WHEN\s+(audit_\w+)\(")
# Named-arg pattern: `:= audit_xxx(` inside struct_pack or similar
_NAMED_ARG_AUDIT_RE = _re.compile(r":=\s+(audit_\w+)\(")
# CASE result branch: `THEN audit_xxx(` or `ELSE audit_xxx(`
_CASE_RESULT_AUDIT_RE = _re.compile(r"(?:THEN|ELSE)\s+(audit_\w+)\(")
# SQL boolean operators: `AND audit_xxx(`, `OR audit_xxx(`
_BOOL_OP_AUDIT_RE = _re.compile(r"(?:AND|OR)\s+(audit_\w+)\(")


def _demote_audit_at_pattern(sql: str, pattern: "_re.Pattern[str]", group: int = 1) -> str:
    """Wrap ``audit_xxx(...)`` calls matched by *pattern* in ``struct_extract(..., 'result')``."""
    offset = 0
    while True:
        m = pattern.search(sql, offset)
        if not m:
            break
        func_name_start = m.start(group)
        open_paren = func_name_start + len(m.group(group))  # right after the name
        close_paren = _find_matching_paren(sql, open_paren)
        if close_paren < 0:
            offset = m.end()
            continue
        audit_call = sql[func_name_start : close_paren + 1]
        replacement = f"struct_extract({audit_call}, 'result')"
        sql = sql[:func_name_start] + replacement + sql[close_paren + 1 :]
        offset = func_name_start + len(replacement)
    return sql


def demote_audit_in_text(sql: str) -> str:
    """Text-level post-processing to fix bare ``audit_xxx(...)`` calls.

    After the AST is serialised to SQL text, some expressions may still
    contain bare audit macro calls that return STRUCTs instead of BOOLEANs.

    Handled patterns:
    * ``CASE WHEN audit_xxx(...)``  — boolean predicate context
    * ``:= audit_xxx(...)``        — named arg inside struct_pack
    """
    sql = _demote_audit_at_pattern(sql, _CASE_WHEN_AUDIT_RE)
    sql = _demote_audit_at_pattern(sql, _NAMED_ARG_AUDIT_RE)
    sql = _demote_audit_at_pattern(sql, _CASE_RESULT_AUDIT_RE)
    sql = _demote_audit_at_pattern(sql, _BOOL_OP_AUDIT_RE)
    return sql


def _wrap_as_json_array_agg(sql: SQLExpression) -> SQLExpression:
    """Wrap a collection query to aggregate all rows into a JSON array string.

    When a let-clause expression is a Query/Retrieve (returns multiple rows),
    the scalar translation picks one row arbitrarily.  This wrapper changes the
    query to aggregate ALL matching rows into a JSON array string so that
    downstream fhirpath() calls can navigate each element per FHIRPath
    collection semantics.

    Handles two column forms:
    - SELECT * → aggregate alias.resource
    - SELECT list(expr) → aggregate expr directly (replace list with string_agg)
    """
    inner_select = None
    if isinstance(sql, SQLSubquery) and isinstance(sql.query, SQLSelect):
        inner_select = sql.query
    elif isinstance(sql, SQLSelect):
        inner_select = sql

    if inner_select is None:
        return sql

    agg_target = None

    # Case 1: SELECT * → aggregate alias.resource
    _is_star = (
        not inner_select.columns
        or (
            len(inner_select.columns) == 1
            and isinstance(inner_select.columns[0], SQLIdentifier)
            and inner_select.columns[0].name == '*'
        )
    )
    if _is_star:
        from_alias = None
        if isinstance(inner_select.from_clause, SQLAlias):
            from_alias = inner_select.from_clause.alias
        agg_target = (
            SQLQualifiedIdentifier(parts=[from_alias, "resource"])
            if from_alias
            else SQLIdentifier(name="resource")
        )

    # Case 2: SELECT list(expr) → aggregate expr
    if agg_target is None and inner_select.columns:
        col0 = inner_select.columns[0]
        if (
            isinstance(col0, SQLFunctionCall)
            and col0.name == "list"
            and col0.args
        ):
            agg_target = col0.args[0]

    if agg_target is None:
        return sql

    # Build: COALESCE('[' || string_agg(agg_target, ',') || ']', '[]')
    agg_expr = SQLFunctionCall(
        name="COALESCE",
        args=[
            SQLBinaryOp(
                left=SQLBinaryOp(
                    left=SQLLiteral(value="["),
                    operator="||",
                    right=SQLFunctionCall(
                        name="string_agg",
                        args=[agg_target, SQLLiteral(value=",")],
                    ),
                ),
                operator="||",
                right=SQLLiteral(value="]"),
            ),
            SQLLiteral(value="[]"),
        ],
    )

    new_select = SQLSelect(
        columns=[agg_expr],
        from_clause=inner_select.from_clause,
        joins=inner_select.joins,
        where=inner_select.where,
    )

    if isinstance(sql, SQLSubquery):
        return SQLSubquery(query=new_select)
    return new_select


class QueryMixin:
    """Query translation methods."""

    def _translate_retrieve(self, node, boolean_context: bool = False, list_context: bool = True) -> SQLExpression:
        """
        Handle: [Condition: "Diabetes"], [Observation: "Lab Value"]

        Returns a placeholder that will be resolved to a CTE reference after CTEs are built.

        Args:
            node: The Retrieve AST node
            boolean_context: Ignored (placeholder handles all contexts)
            list_context: Ignored (placeholder handles all contexts)

        Returns:
            RetrievePlaceholder for the retrieve
        """
        # Get resource type (e.g., "Condition", "Observation")
        resource_type = getattr(node, 'type', None)
        if not resource_type:
            return SQLNull()

        # Normalize resource type (e.g., USCoreBloodPressureProfile -> Observation)
        profile_url = None
        registry = self.context.profile_registry
        resolved = registry.resolve_named_profile(resource_type)
        if resolved is not None:
            resource_type, profile_url = resolved

        # Get terminology filter if present
        terminology = getattr(node, 'terminology', None)
        valueset = None
        code_property = None

        if terminology:
            if isinstance(terminology, str):
                valueset_name = terminology
            elif isinstance(terminology, CodeSelector):
                cs_url = self.context.codesystems.get(terminology.system, terminology.system)
                valueset = f"urn:cql:code:{cs_url}|{terminology.code}"
                valueset_name = None
            else:
                if isinstance(terminology, Identifier):
                    valueset_name = terminology.name
                elif isinstance(terminology, BinaryExpression) and terminology.operator in ('in', '~', '='):
                    # Handle: [Resource: codePath in "ValueSet Name"]
                    # Handle: [Resource: code = "Code Name"]
                    left = terminology.left
                    if isinstance(left, Identifier):
                        code_property = left.name
                    right = terminology.right
                    if isinstance(right, Identifier):
                        valueset_name = right.name
                    else:
                        valueset_name = str(right)
                else:
                    valueset_name = str(terminology)

            if valueset is None and valueset_name is not None:
                # Get valueset URL from context
                valueset = self.context.valuesets.get(valueset_name, None)

            if valueset is None and valueset_name is not None:
                # Check if it's a code reference instead of a valueset
                code_info = self.context.codes.get(valueset_name)
                if code_info:
                    cs_name = code_info.get("codesystem", "")
                    cs_url = self.context.codesystems.get(cs_name, cs_name)
                    code_val = code_info.get("code", "")
                    valueset = f"urn:cql:code:{cs_url}|{code_val}"
                else:
                    valueset = valueset_name

            # If it's not already a URL, try common prefixes
            if valueset and not valueset.startswith('http') and not valueset.startswith('urn:'):
                valueset = f"http://cts.nlm.nih.gov/fhir/ValueSet/{valueset}"

        # Return placeholder
        return RetrievePlaceholder(
            resource_type=resource_type,
            valueset=valueset,
            profile_url=profile_url,
            code_property=code_property
        )

    def _translate_query_source(self, node, boolean_context: bool = False) -> SQLExpression:
        """Handle: [Condition: "Diabetes"] D (the source with alias)"""
        return self.translate(node.expression, boolean_context)

    def _try_set_op_source(self, src_expr, alias, node, usage):
        """Handle Query sources that are set operations (intersect/union/except).

        CQL pattern:
            ( "Definition A" intersect "Definition B" ) Alias
              where Alias.someProperty ...

        Each operand must select (patient_id, <col>) from its CTE so the
        set operation produces iterable rows.  The generic SCALAR translation
        path would add per-patient correlation and LIMIT 1 which is wrong here.

        Only handles operands that are RESOURCE_ROWS definitions (have a
        resource column).  Non-resource definitions (scalar values) fall
        through to the standard translation path.

        Returns the SQLIntersect/SQLUnion/SQLExcept expression, or None if
        the source is not a set operation we can handle.
        """
        if not isinstance(src_expr, BinaryExpression):
            return None
        op = getattr(src_expr, 'operator', '')
        if not isinstance(op, str):
            return None
        op_lower = op.lower()
        if op_lower not in ('intersect', 'union', 'except'):
            return None

        from ...translator.context import RowShape

        def _build_operand(expr_node):
            """Build a SELECT patient_id, resource FROM "CTE" subquery for a set operand."""
            if isinstance(expr_node, Identifier):
                name = expr_node.name
                if hasattr(self.context, '_definition_names') and name in self.context._definition_names:
                    meta = self.context.definition_meta.get(name)
                    if meta and meta.has_resource and meta.shape == RowShape.RESOURCE_ROWS:
                        return SQLSubquery(query=SQLSelect(
                            columns=[
                                SQLIdentifier(name="patient_id"),
                                SQLIdentifier(name="resource"),
                            ],
                            from_clause=SQLAlias(
                                expr=SQLIdentifier(name=name, quoted=True),
                                alias="sub",
                            ),
                        ))
                    # Non-resource definitions: fall through
                    return None
            # For nested set operations, recurse
            if isinstance(expr_node, BinaryExpression):
                nested_op = getattr(expr_node, 'operator', '')
                if isinstance(nested_op, str) and nested_op.lower() in ('intersect', 'union', 'except'):
                    nested = self._try_set_op_source(expr_node, alias, node, usage)
                    if nested is not None:
                        return SQLSubquery(query=nested) if not isinstance(nested, SQLSubquery) else nested
            return None

        left_op = _build_operand(src_expr.left)
        right_op = _build_operand(src_expr.right)
        if left_op is None or right_op is None:
            return None

        if op_lower == 'intersect':
            return SQLIntersect(operands=[left_op, right_op])
        elif op_lower == 'union':
            return SQLUnion(operands=[left_op, right_op])
        else:
            return SQLExcept(operands=[left_op, right_op])

    def _try_method_invocation_list_source(
        self, source_expr_node, alias, node, usage: ExprUsage,
    ):
        """Handle Query sources that are MethodInvocation (fluent function)
        calls returning lists.

        CQL pattern:
            (Alias.fluentFunction()) QueryAlias where conditions

        When a fluent function returns a list (its body is a Query with a
        return clause containing a sub-Query iterating over a backbone array
        on a let variable), we must UNNEST the result so the outer WHERE
        conditions apply per-element rather than on a scalar collapse.

        Returns translated SQL or None if this is not a matching pattern.
        """
        if not isinstance(source_expr_node, MethodInvocation):
            return None

        # Try to expand via FunctionInliner
        inliner = self.context.function_inliner
        if not inliner:
            return None

        expanded = inliner.expand_function(
            source_expr_node.method,
            source_expr_node.source,
            source_expr_node.arguments,
        )
        if not isinstance(expanded, Query):
            return None
        if not hasattr(expanded, 'return_clause') or not expanded.return_clause:
            return None

        # The expanded body must be a Query with a return clause whose
        # expression is itself a sub-Query iterating over a backbone array.
        return_expr = expanded.return_clause.expression
        if not isinstance(return_expr, Query):
            return None

        inner_source_node = return_expr.source
        if isinstance(inner_source_node, QuerySource):
            inner_source_expr = inner_source_node.expression
            inner_alias = inner_source_node.alias
        else:
            return None

        # The inner source should be a Property on an Identifier (let variable)
        if not isinstance(inner_source_expr, Property):
            return None
        prop_source = inner_source_expr.source
        prop_path = inner_source_expr.path
        prop_source_name = getattr(prop_source, 'name', None)
        if not prop_source_name or not prop_path:
            return None

        # ── Set up scope for the expanded body ──────────────────────
        self.context.push_scope()

        expanded_alias = getattr(expanded.source, 'alias', None)
        expanded_source = getattr(expanded.source, 'expression', None)

        # When the expanded source is a ParameterPlaceholder (from the old
        # SQL-level inlining path for double-inlined fluent functions like
        # isDiagnosisPresentOnAdmission → claimDiagnosis), the .name is the
        # CQL parameter name (e.g., 'encounter'), not the outer query alias
        # (e.g., 'EncounterWithSurgery').  Extract the actual SQL alias from
        # the carried sql_expr instead.
        from ...translator.function_inliner import ParameterPlaceholder
        if isinstance(expanded_source, ParameterPlaceholder):
            _sql = expanded_source.sql_expr
            if isinstance(_sql, SQLQualifiedIdentifier) and _sql.parts:
                exp_source_name = _sql.parts[0]
            elif isinstance(_sql, SQLIdentifier):
                exp_source_name = _sql.name
            else:
                exp_source_name = expanded_source.name
        else:
            exp_source_name = getattr(expanded_source, 'name', None)

        _saved_ra = self.context.resource_alias

        if exp_source_name and expanded_alias:
            if expanded_alias != exp_source_name:
                _sym = self.context.lookup_symbol(exp_source_name)
                _cte = (
                    getattr(_sym, 'cte_name', None)
                    or getattr(_sym, 'table_alias', None)
                    or exp_source_name
                ) if _sym else exp_source_name
                self.context.add_alias(
                    expanded_alias,
                    table_alias=exp_source_name,
                    cte_name=_cte,
                )
                if exp_source_name in self.context._alias_resource_types:
                    self.context._alias_resource_types[expanded_alias] = (
                        self.context._alias_resource_types[exp_source_name]
                    )
            self.context.resource_alias = exp_source_name

        # Process let clauses from the expanded body
        if hasattr(expanded, 'let_clauses') and expanded.let_clauses:
            for let_clause in expanded.let_clauses:
                let_name = let_clause.alias
                _is_coll = isinstance(let_clause.expression, (Query, Retrieve))
                if _is_coll:
                    self.context._let_clause_collection = True
                let_expr_sql = self.translate(
                    let_clause.expression, usage=ExprUsage.SCALAR,
                )
                if _is_coll:
                    self.context._let_clause_collection = False
                    let_expr_sql = _wrap_as_json_array_agg(let_expr_sql)
                self.context.let_variables[let_name] = let_expr_sql

        # Check that the property source resolves to a let variable
        if prop_source_name not in self.context.let_variables:
            self.context.resource_alias = _saved_ra
            self.context.pop_scope()
            return None

        let_sql = self.context.let_variables[prop_source_name]

        # ── Build UNNEST from the backbone array ────────────────────
        _lt_param = f"_lt_{alias}"

        _fhirpath_call = SQLFunctionCall(
            name="fhirpath",
            args=[let_sql, SQLLiteral(value=prop_path)],
        )
        _unnest_expr = SQLFunctionCall(
            name="unnest",
            args=[SQLFunctionCall(
                name="from_json",
                args=[_fhirpath_call, SQLLiteral(value='["VARCHAR"]')],
            )],
        )

        # Register aliases: both the outer alias (e.g. MajorFallOccurred)
        # and the inner alias (e.g. D) map to the same UNNEST'd element.
        self.context.add_alias(alias, ast_expr=SQLIdentifier(name=_lt_param))
        if inner_alias and inner_alias != alias:
            self.context.add_alias(
                inner_alias, ast_expr=SQLIdentifier(name=_lt_param),
            )

        # Process inner let clauses (from the return sub-query) if any
        if hasattr(return_expr, 'let_clauses') and return_expr.let_clauses:
            for let_clause in return_expr.let_clauses:
                let_name = let_clause.alias
                _is_coll = isinstance(let_clause.expression, (Query, Retrieve))
                if _is_coll:
                    self.context._let_clause_collection = True
                let_expr_sql = self.translate(
                    let_clause.expression, usage=ExprUsage.SCALAR,
                )
                if _is_coll:
                    self.context._let_clause_collection = False
                    let_expr_sql = _wrap_as_json_array_agg(let_expr_sql)
                self.context.let_variables[let_name] = let_expr_sql

        # Translate inner WHERE (from return sub-query, e.g. D.sequence in ...)
        _inner_where = None
        if return_expr.where:
            _inner_where = self.translate(
                return_expr.where, usage=ExprUsage.BOOLEAN,
            )

        # Translate outer WHERE (from the main query, e.g. Alias.onAdmission ...)
        _outer_where = None
        if node.where:
            _outer_where = self.translate(
                node.where, usage=ExprUsage.BOOLEAN,
            )

        # Process outer RETURN clause if any
        _return_expr_sql = SQLIdentifier(name=_lt_param)
        if node.return_clause:
            _return_expr_sql = self.translate(
                node.return_clause, usage=ExprUsage.SCALAR,
            )

        self.context.resource_alias = _saved_ra
        self.context.pop_scope()

        _return_expr_sql = _ensure_scalar_body(_return_expr_sql)

        # ── Combine WHERE conditions ────────────────────────────────
        _combined_where = _inner_where
        if _outer_where:
            if _combined_where:
                _combined_where = SQLBinaryOp(
                    left=_combined_where,
                    operator="AND",
                    right=_outer_where,
                )
            else:
                _combined_where = _outer_where

        # Demote audit structs to plain booleans for WHERE clause usage
        if _combined_where:
            _combined_where = _demote_audit_struct_to_bool(_combined_where)

        # ── Build the final SQL ─────────────────────────────────────
        # Inner: SELECT unnest(from_json(fhirpath(...), '["VARCHAR"]')) AS _lt_Alias
        _inner = SQLSelect(
            columns=[SQLAlias(expr=_unnest_expr, alias=_lt_param)],
        )

        if usage == ExprUsage.BOOLEAN or usage == ExprUsage.EXISTS:
            # For EXISTS/BOOLEAN: produce a SELECT that the exists handler
            # wraps in EXISTS(...)
            return SQLSelect(
                columns=[SQLLiteral(value=1)],
                from_clause=SQLAlias(
                    expr=SQLSubquery(query=_inner), alias="_lt_unnest",
                ),
                where=_combined_where,
            )

        # For SCALAR: produce list aggregation
        result = SQLSubquery(query=SQLSelect(
            columns=[SQLFunctionCall(name="list", args=[_return_expr_sql])],
            from_clause=SQLAlias(
                expr=SQLSubquery(query=_inner), alias="_lt_unnest",
            ),
            where=_combined_where,
        ))

        return result

    def _try_backbone_array_on_definition(
        self, src_expr, alias, node, usage: ExprUsage,
    ):
        """Handle queries iterating over backbone arrays from definitions.

        CQL pattern:
            "DefinitionName".backboneProperty Alias where ... return ...

        Also handles ParameterPlaceholder sources from function inlining:
            ParameterPlaceholder(sql_expr).backboneProperty Alias where ...

        The property is a multi-valued BackboneElement (e.g., Encounter.location).
        We UNNEST the array so each element is iterable with the given alias.

        Returns translated SQL or None if this is not a backbone array pattern.
        """
        if not isinstance(src_expr, Property):
            return None
        prop_source = src_expr.source
        prop_path = src_expr.path

        # Determine whether the source is a definition Identifier or a
        # ParameterPlaceholder from function inlining.  Both carry enough
        # information to detect backbone arrays and generate UNNEST.
        _is_placeholder = isinstance(prop_source, ParameterPlaceholder)
        _is_definition = isinstance(prop_source, Identifier)

        if not (_is_definition or _is_placeholder) or not prop_path:
            return None

        # For Identifiers, verify it references a known definition
        if _is_definition:
            def_name = prop_source.name
            if not hasattr(self.context, '_definition_names') or def_name not in self.context._definition_names:
                return None

        if not self.context.fhir_schema:
            return None

        # Determine resource type of the source
        _src_rt = None
        if _is_definition:
            def_name = prop_source.name
            _src_rt = self.context._alias_resource_types.get(def_name)
            if not _src_rt:
                meta = self.context.definition_meta.get(def_name)
                if meta and hasattr(meta, 'resource_type') and meta.resource_type:
                    _src_rt = meta.resource_type
        elif _is_placeholder:
            # Extract alias name from the SQL expression to look up resource type
            pp_sql = prop_source.sql_expr
            _pp_alias = None
            if isinstance(pp_sql, SQLIdentifier):
                _pp_alias = pp_sql.name
            elif isinstance(pp_sql, SQLQualifiedIdentifier) and pp_sql.parts:
                _pp_alias = pp_sql.parts[0]
            if _pp_alias:
                _src_rt = self.context._alias_resource_types.get(_pp_alias)
                if not _src_rt:
                    # Check definition meta for the alias
                    sym = self.context.lookup_symbol(_pp_alias) if hasattr(self.context, 'lookup_symbol') else None
                    cte_name = getattr(sym, 'cte_name', None) if sym else None
                    if cte_name:
                        meta = self.context.definition_meta.get(cte_name)
                        if meta and hasattr(meta, 'resource_type') and meta.resource_type:
                            _src_rt = meta.resource_type

        # Validate that the candidate resource type actually has the backbone
        # property.  Alias-based lookups can return a stale/wrong type (e.g.
        # Procedure instead of Encounter) because _alias_resource_types is
        # populated incrementally and may be polluted from earlier queries.
        # If the candidate fails, clear it so the fallback scan can try.
        if _src_rt:
            _cand_def = self.context.fhir_schema.resources.get(_src_rt)
            if _cand_def:
                _cand_elem = _cand_def.elements.get(f"{_src_rt}.{prop_path}")
                if not (
                    _cand_elem
                    and _cand_elem.cardinality
                    and _cand_elem.cardinality.endswith('*')
                    and 'BackboneElement' in _cand_elem.types
                ):
                    _src_rt = None  # Wrong type; fall through to scan
            else:
                _src_rt = None

        if not _src_rt:
            # Fallback: check all resource types for this backbone property
            for _rt_name, _rt_def in self.context.fhir_schema.resources.items():
                _felem = _rt_def.elements.get(f"{_rt_name}.{prop_path}")
                if (
                    _felem
                    and _felem.cardinality
                    and _felem.cardinality.endswith('*')
                    and 'BackboneElement' in _felem.types
                ):
                    _src_rt = _rt_name
                    break
        if not _src_rt:
            return None

        # ── This IS a backbone array on a definition. Generate UNNEST. ──
        _lt_param = f"_lt_{alias}"

        # Register alias so WHERE/RETURN can reference the backbone element
        self.context.push_scope()
        self.context.add_alias(alias, ast_expr=SQLIdentifier(name=_lt_param))

        # Process LET clauses
        if hasattr(node, 'let_clauses') and node.let_clauses:
            for let_clause in node.let_clauses:
                let_name = let_clause.alias
                _is_coll = isinstance(let_clause.expression, (Query, Retrieve))
                if _is_coll:
                    self.context._let_clause_collection = True
                let_expr_sql = self.translate(let_clause.expression, usage=ExprUsage.SCALAR)
                if _is_coll:
                    self.context._let_clause_collection = False
                    let_expr_sql = _wrap_as_json_array_agg(let_expr_sql)
                self.context.let_variables[let_name] = let_expr_sql
        _ba_where = None
        if node.where:
            _ba_where = _demote_audit_struct_to_bool(self.translate(node.where, usage=ExprUsage.BOOLEAN))

        # Process RETURN clause
        _ba_return = SQLIdentifier(name=_lt_param)
        if node.return_clause:
            _ba_return = self.translate(node.return_clause, usage=ExprUsage.SCALAR)

        # Process SORT clause (for First/Last with sort)
        _ba_order_by = None
        if hasattr(node, 'sort') and node.sort and node.sort.by:
            _ba_order_by = []
            for item in node.sort.by:
                if item.expression:
                    sort_expr_sql = self.translate(item.expression, usage=ExprUsage.SCALAR)
                    direction = (getattr(item, 'direction', None) or 'asc').upper()
                    _ba_order_by.append((sort_expr_sql, f"{direction} NULLS LAST"))

        self.context.pop_scope()

        _ba_return = _ensure_scalar_body(_ba_return)

        if _is_placeholder:
            # ParameterPlaceholder path: the resource is already available as
            # an SQL expression.  UNNEST directly from it without a CTE lookup
            # or patient_id correlation.
            pp_sql = prop_source.sql_expr
            if isinstance(pp_sql, SQLIdentifier):
                _resource_col = SQLQualifiedIdentifier(parts=[pp_sql.name, "resource"])
            elif isinstance(pp_sql, SQLQualifiedIdentifier):
                _resource_col = pp_sql
            else:
                _resource_col = pp_sql

            _fhirpath_call = SQLFunctionCall(
                name="fhirpath",
                args=[_resource_col, SQLLiteral(value=prop_path)],
            )
            _unnest_expr = SQLFunctionCall(
                name="unnest",
                args=[SQLFunctionCall(
                    name="from_json",
                    args=[_fhirpath_call, SQLLiteral(value='["VARCHAR"]')],
                )],
            )

            _inner = SQLSelect(
                columns=[SQLAlias(expr=_unnest_expr, alias=_lt_param)],
            )

            result = SQLSubquery(query=SQLSelect(
                columns=[SQLFunctionCall(name="list", args=[_ba_return], order_by=_ba_order_by)],
                from_clause=SQLAlias(expr=SQLSubquery(query=_inner), alias="_lt_unnest"),
                where=_ba_where,
            ))

            if usage == ExprUsage.BOOLEAN:
                return SQLBinaryOp(
                    left=SQLFunctionCall(name="array_length", args=[result]),
                    operator=">",
                    right=SQLLiteral(value=0),
                )
            return result

        # Definition Identifier path: use CTE lookup with patient_id correlation
        def_name = prop_source.name
        _bb_src = f"_bb_{alias}"

        _fhirpath_call = SQLFunctionCall(
            name="fhirpath",
            args=[
                SQLQualifiedIdentifier(parts=[_bb_src, "resource"]),
                SQLLiteral(value=prop_path),
            ],
        )
        _unnest_expr = SQLFunctionCall(
            name="unnest",
            args=[SQLFunctionCall(
                name="from_json",
                args=[_fhirpath_call, SQLLiteral(value='["VARCHAR"]')],
            )],
        )

        # Build patient_id correlation
        _outer_alias = self.context.resource_alias or self.context.patient_alias or "p"
        _patient_corr = SQLBinaryOp(
            left=SQLQualifiedIdentifier(parts=[_bb_src, "patient_id"]),
            operator="=",
            right=SQLQualifiedIdentifier(parts=[_outer_alias, "patient_id"]),
        )

        # Combine WHERE: patient_id correlation AND backbone element conditions
        _full_where = _patient_corr
        if _ba_where:
            _full_where = SQLBinaryOp(
                left=_patient_corr, operator="AND", right=_ba_where,
            )

        # Inner query: SELECT unnest(...) AS _lt_Alias
        #              FROM "Definition" AS _bb_Alias
        #              WHERE patient_id correlation
        _inner = SQLSelect(
            columns=[SQLAlias(expr=_unnest_expr, alias=_lt_param)],
            from_clause=SQLAlias(
                expr=SQLIdentifier(name=def_name, quoted=True),
                alias=_bb_src,
            ),
            where=_patient_corr,
        )

        # Outer query: SELECT list(return_expr) FROM (_inner) WHERE conditions
        result = SQLSubquery(query=SQLSelect(
            columns=[SQLFunctionCall(name="list", args=[_ba_return], order_by=_ba_order_by)],
            from_clause=SQLAlias(expr=SQLSubquery(query=_inner), alias="_bb_unnest"),
            where=_ba_where,
        ))

        if usage == ExprUsage.BOOLEAN:
            return SQLBinaryOp(
                left=SQLFunctionCall(name="array_length", args=[result]),
                operator=">",
                right=SQLLiteral(value=0),
            )

        return result

    @staticmethod
    def _extract_pp_base(pp_sql) -> str | None:
        """Extract the base table/CTE name from a ParameterPlaceholder's sql_expr.

        Handles:
        - SQLQualifiedIdentifier(["X", "resource"]) → "X"
        - SQLIdentifier("X") → "X" (unless lambda _lt_*)

        Does NOT unwrap SQLSubquery — those need a proper FROM clause with alias,
        not the inline alias-mapping path of _translate_query_on_alias.
        """
        if isinstance(pp_sql, SQLQualifiedIdentifier) and len(pp_sql.parts) >= 1:
            return pp_sql.parts[0] if isinstance(pp_sql.parts[0], str) else None
        if isinstance(pp_sql, SQLIdentifier):
            if not pp_sql.name.startswith('_lt_'):
                return pp_sql.name
            return None
        return None

    def _translate_query_on_alias(
        self, node, source_name: str, inner_alias: str | None,
    ) -> SQLExpression:
        """Translate a CQL Query whose source is a known query alias.

        When a fluent function is inlined, the body may have
        ``TheEncounter Visit return ...`` where ``TheEncounter`` resolves to
        an alias already in scope (e.g., from a ``with`` clause).  In that
        case we must NOT create a ``FROM alias`` subquery.  Instead we
        register the inner alias and translate let/where/return directly.

        ``source_name`` is the SQL table/CTE name that is valid in the
        current SQL scope.  ``inner_alias`` is the CQL alias that the body
        uses to reference the source (e.g., "Visit", "InptEncounter").
        """
        alias = inner_alias or source_name
        _sym = self.context.lookup_symbol(source_name)

        # Register inner CQL alias mapping to the real SQL table name
        if alias != source_name:
            _cte = (
                getattr(_sym, 'cte_name', None)
                or getattr(_sym, 'table_alias', None)
                or source_name
            ) if _sym else source_name
            self.context.add_alias(
                alias,
                table_alias=source_name,
                cte_name=_cte,
            )
            if source_name in self.context._alias_resource_types:
                self.context._alias_resource_types[alias] = (
                    self.context._alias_resource_types[source_name]
                )
        elif not _sym:
            # Source name not found in scope (barrier).  Register it so
            # property access (e.g., Visit.period) can resolve correctly.
            self.context.add_alias(
                alias,
                table_alias=source_name,
                cte_name=source_name,
            )

        # Use the real SQL table name as resource_alias so that generated
        # SQL references (e.g., fhirpath(X.resource, ...)) point to a valid
        # table, not to the CQL-level alias which has no FROM clause.
        _saved_resource_alias = self.context.resource_alias
        self.context.resource_alias = source_name

        # Process let clauses
        if hasattr(node, 'let_clauses') and node.let_clauses:
            for let_clause in node.let_clauses:
                let_name = let_clause.alias
                _is_coll = isinstance(let_clause.expression, (Query, Retrieve))
                if _is_coll:
                    self.context._let_clause_collection = True
                let_expr_sql = self.translate(
                    let_clause.expression, usage=ExprUsage.SCALAR,
                )
                if _is_coll:
                    self.context._let_clause_collection = False
                    let_expr_sql = _wrap_as_json_array_agg(let_expr_sql)
                self.context.let_variables[let_name] = let_expr_sql

        # Process return clause and/or WHERE.
        # When both WHERE and RETURN exist (e.g., inlined fluent function
        # ``EncounterList Visit where Diagnosis.isActive() return overlap``),
        # the WHERE acts as a guard: rows that fail the filter are excluded.
        # Wrap the RETURN in a CASE so filtered-out rows produce NULL.
        if hasattr(node, 'return_clause') and node.return_clause:
            return_sql = self.translate(node.return_clause, usage=ExprUsage.SCALAR)
            if hasattr(node, 'where') and node.where:
                where_sql = _demote_audit_struct_to_bool(self.translate(node.where, usage=ExprUsage.BOOLEAN))
                result = SQLCase(
                    when_clauses=[(where_sql, return_sql)],
                    else_clause=SQLNull(),
                )
            else:
                result = return_sql
        elif hasattr(node, 'where') and node.where:
            where_sql = _demote_audit_struct_to_bool(self.translate(node.where, usage=ExprUsage.BOOLEAN))
            result = SQLCase(
                when_clauses=[(
                    where_sql,
                    SQLQualifiedIdentifier(parts=[source_name, "resource"]),
                )],
                else_clause=SQLNull(),
            )
        else:
            result = SQLQualifiedIdentifier(parts=[source_name, "resource"])

        self.context.resource_alias = _saved_resource_alias
        return result

    def _translate_where_clause(self, node, boolean_context: bool = False) -> SQLExpression:
        """Handle WhereClause by translating its inner expression."""
        return self.translate(node.expression, boolean_context=True)

    def _translate_return_clause(self, node, boolean_context: bool = False) -> SQLExpression:
        """Handle ReturnClause by translating its inner expression."""
        return self.translate(node.expression, boolean_context=False)

    def _translate_is_type_check(self, expr: BinaryExpression) -> SQLExpression:
        """Translate CQL `is` type-check operator to SQL.

        CQL: ``Order is MedicationRequest`` — checks if the resource is of a given type.
        CQL: ``Order is MedicationNotRequested`` — checks if the resource conforms to a named profile.
        CQL: ``Order is Interval<DateTime>`` — checks if the value is a Period JSON.

        Strategies based on type_name:
        1. CQL primitive types (DateTime, String, etc.) — value is a bare string,
           not a JSON object.  Check: NOT starts_with(LTRIM(value), '{')
        1b. Interval types (Interval<DateTime>, Interval<Quantity>) — Period/Range JSON.
        2. CQL/FHIR complex data types without resourceType (Quantity, Timing) —
           JSON object distinguished by unique fields.
        3. Named profiles — check meta.profile array.
        4. FHIR resource types — check $.resourceType field.
        """
        from ...parser.ast_nodes import IntervalTypeSpecifier as _ITS
        if isinstance(expr.right, _ITS):
            type_name = f"Interval<{expr.right.point_type.name}>"
        else:
            type_name = expr.right.name

        # Strip FHIR/CQL namespace prefix for type matching
        bare_type = type_name.split(".")[-1] if "." in type_name else type_name

        # --- Strategy 0: Compile-time type resolution for InstanceExpression ---
        # When the left operand is an InstanceExpression with a known type,
        # resolve the `is` check at compile time.  CQL §2.1: Vocabulary is a
        # supertype of ValueSet and CodeSystem.
        from ...parser.ast_nodes import InstanceExpression as _InstExpr
        if isinstance(expr.left, _InstExpr):
            instance_type = expr.left.type.split(".")[-1] if "." in expr.left.type else expr.left.type
            _VOCABULARY_TYPES = {"ValueSet", "CodeSystem"}
            if bare_type == "Vocabulary" and instance_type in _VOCABULARY_TYPES:
                return SQLLiteral(value=True)
            if instance_type == bare_type:
                return SQLLiteral(value=True)

        left = self.translate(expr.left, usage=ExprUsage.SCALAR)
        resource_expr = left

        # When resource_expr is a bare table/CTE alias (SQLIdentifier), qualify
        # with .resource so json_extract_string accesses the JSON resource column
        # rather than the DuckDB row struct.  This commonly occurs when a fluent
        # function parameter placeholder resolves to a query-source alias.
        from ...translator.types import SQLIdentifier as _SQLId, SQLQualifiedIdentifier as _SQLQId
        if isinstance(resource_expr, _SQLId) and not isinstance(resource_expr, _SQLQId):
            alias_name = resource_expr.name
            symbol = self.context.lookup_symbol(alias_name)
            if symbol and getattr(symbol, 'table_alias', None):
                resource_expr = _SQLQId(parts=[alias_name, "resource"])

        # Strip FHIR/CQL namespace prefix for type matching
        bare_type = type_name.split(".")[-1] if "." in type_name else type_name

        # --- Strategy 1: CQL primitive types (bare string values) ---
        _PRIMITIVE_TYPES = {
            "DateTime", "dateTime", "Date", "date", "Time", "time",
            "String", "string", "Boolean", "boolean", "Integer", "integer",
            "Long", "long", "Decimal", "decimal", "instant",
        }
        if bare_type in _PRIMITIVE_TYPES:
            # Quick check: if the left operand is a CQL literal with a known type
            # that doesn't match the target, return false immediately.
            # CQL `is` is a type check: '5' is Integer → false (String ≠ Integer).
            from ...parser.ast_nodes import Literal as _ASTLiteral
            if isinstance(expr.left, _ASTLiteral):
                _lit_type = getattr(expr.left, 'type', None)
                if _lit_type:
                    _lit_type_lower = _lit_type.lower()
                    _bare_lower = bare_type.lower()
                    _LIT_TYPE_MAP = {
                        'string': {'string'},
                        'integer': {'integer', 'long'},
                        'long': {'integer', 'long'},
                        'decimal': {'decimal'},
                        'boolean': {'boolean'},
                    }
                    _lit_types = _LIT_TYPE_MAP.get(_lit_type_lower)
                    if _lit_types is not None and _bare_lower not in _lit_types:
                        return SQLLiteral(value=False)

            # CQL `is` checks the *type* of the value, not just its format.
            # When the SQL value has a concrete type (INTEGER, DOUBLE, BOOLEAN, DATE, TIMESTAMP),
            # check typeof() against the expected CQL type. When the value is VARCHAR (FHIR JSON
            # extraction), fall back to the not-JSON-object format check.
            _CQL_TYPE_TO_SQL_TYPES = {
                "Integer": ("INTEGER", "BIGINT", "SMALLINT", "TINYINT", "HUGEINT"),
                "integer": ("INTEGER", "BIGINT", "SMALLINT", "TINYINT", "HUGEINT"),
                "Long": ("INTEGER", "BIGINT", "SMALLINT", "TINYINT", "HUGEINT"),
                "long": ("INTEGER", "BIGINT", "SMALLINT", "TINYINT", "HUGEINT"),
                "Decimal": ("DOUBLE", "FLOAT", "DECIMAL"),
                "decimal": ("DOUBLE", "FLOAT", "DECIMAL"),
                "Boolean": ("BOOLEAN",),
                "boolean": ("BOOLEAN",),
                "Date": ("DATE",),
                "date": ("DATE",),
                "DateTime": ("TIMESTAMP", "TIMESTAMP WITH TIME ZONE"),
                "dateTime": ("TIMESTAMP", "TIMESTAMP WITH TIME ZONE"),
                "instant": ("TIMESTAMP", "TIMESTAMP WITH TIME ZONE"),
                "String": ("VARCHAR",),
                "string": ("VARCHAR",),
            }
            expected_sql_types = _CQL_TYPE_TO_SQL_TYPES.get(bare_type)
            cast_expr = SQLCast(expression=resource_expr, target_type="VARCHAR")
            is_not_json = SQLUnaryOp(
                operator="NOT",
                operand=SQLFunctionCall(
                    name="starts_with",
                    args=[
                        SQLFunctionCall(name="LTRIM", args=[cast_expr]),
                        SQLLiteral(value="{"),
                    ],
                ),
            )
            not_null = SQLBinaryOp(
                operator="IS NOT",
                left=resource_expr,
                right=SQLNull(),
            )
            if expected_sql_types and bare_type not in ("String", "string", "Time", "time"):
                # Build typeof-based check: when typeof(x) is a concrete non-VARCHAR type,
                # check it matches. When VARCHAR, use not-JSON format check (FHIR fallback).
                type_checks = [SQLBinaryOp(
                    operator="=",
                    left=SQLFunctionCall(name="typeof", args=[resource_expr]),
                    right=SQLLiteral(value=t),
                ) for t in expected_sql_types]
                type_match = type_checks[0]
                for tc in type_checks[1:]:
                    type_match = SQLBinaryOp(operator="OR", left=type_match, right=tc)
                # For VARCHAR values (FHIR polymorphic), use the not-JSON heuristic
                is_varchar = SQLBinaryOp(
                    operator="=",
                    left=SQLFunctionCall(name="typeof", args=[resource_expr]),
                    right=SQLLiteral(value="VARCHAR"),
                )
                combined = SQLBinaryOp(
                    operator="OR",
                    left=type_match,
                    right=SQLBinaryOp(operator="AND", left=is_varchar, right=is_not_json),
                )
                return SQLBinaryOp(operator="AND", left=not_null, right=combined)
            else:
                # String/Time types: not-JSON check is sufficient
                return SQLBinaryOp(operator="AND", left=not_null, right=is_not_json)

        # --- Strategy 1b: Interval types (Interval<DateTime>, Interval<Quantity>) ---
        # CQL `is Interval<DateTime>` checks if the value is a Period JSON
        # (has $.start or $.end fields). CQL `is Interval<Quantity>` checks
        # if the value is a Range JSON (has $.low or $.high fields).
        _interval_type = None
        if bare_type.startswith("Interval<") and bare_type.endswith(">"):
            _inner = bare_type[len("Interval<"):-1]
            # Normalize inner type (strip FHIR./System. prefix)
            _inner_bare = _inner.split(".")[-1] if "." in _inner else _inner
            if _inner_bare in ("DateTime", "dateTime", "Date", "date", "instant"):
                _interval_type = "datetime"
            elif _inner_bare in ("Quantity", "quantity"):
                _interval_type = "quantity"
        if _interval_type == "datetime":
            # Period JSON: {"start": "...", "end": "..."}
            # Use CASE WHEN to guard json_extract_string — DuckDB doesn't
            # short-circuit AND, so bare strings would crash json_extract.
            is_json = SQLFunctionCall(
                name="starts_with",
                args=[
                    SQLFunctionCall(name="LTRIM", args=[resource_expr]),
                    SQLLiteral(value="{"),
                ],
            )
            has_start_or_end = SQLBinaryOp(
                operator="OR",
                left=SQLBinaryOp(
                    operator="IS NOT",
                    left=SQLFunctionCall(
                        name="json_extract_string",
                        args=[resource_expr, SQLLiteral(value="$.start")],
                    ),
                    right=SQLNull(),
                ),
                right=SQLBinaryOp(
                    operator="IS NOT",
                    left=SQLFunctionCall(
                        name="json_extract_string",
                        args=[resource_expr, SQLLiteral(value="$.end")],
                    ),
                    right=SQLNull(),
                ),
            )
            return SQLCase(
                when_clauses=[(is_json, has_start_or_end)],
                else_clause=SQLLiteral(value=False),
            )
        if _interval_type == "quantity":
            # Range JSON: {"low": {...}, "high": {...}}
            is_json = SQLFunctionCall(
                name="starts_with",
                args=[
                    SQLFunctionCall(name="LTRIM", args=[resource_expr]),
                    SQLLiteral(value="{"),
                ],
            )
            has_low_or_high = SQLBinaryOp(
                operator="OR",
                left=SQLBinaryOp(
                    operator="IS NOT",
                    left=SQLFunctionCall(
                        name="json_extract_string",
                        args=[resource_expr, SQLLiteral(value="$.low")],
                    ),
                    right=SQLNull(),
                ),
                right=SQLBinaryOp(
                    operator="IS NOT",
                    left=SQLFunctionCall(
                        name="json_extract_string",
                        args=[resource_expr, SQLLiteral(value="$.high")],
                    ),
                    right=SQLNull(),
                ),
            )
            return SQLBinaryOp(operator="AND", left=is_json, right=has_low_or_high)

        # --- Strategy 2: Complex data types without resourceType ---
        if bare_type in ("Period", "period"):
            # Period JSON: {"start": "...", "end": "..."}
            # Use CASE WHEN to guard json_extract_string — DuckDB doesn't
            # short-circuit AND, so bare date strings would crash json_extract.
            is_json = SQLFunctionCall(
                name="starts_with",
                args=[
                    SQLFunctionCall(name="LTRIM", args=[resource_expr]),
                    SQLLiteral(value="{"),
                ],
            )
            has_start_or_end = SQLBinaryOp(
                operator="OR",
                left=SQLBinaryOp(
                    operator="IS NOT",
                    left=SQLFunctionCall(
                        name="json_extract_string",
                        args=[resource_expr, SQLLiteral(value="$.start")],
                    ),
                    right=SQLNull(),
                ),
                right=SQLBinaryOp(
                    operator="IS NOT",
                    left=SQLFunctionCall(
                        name="json_extract_string",
                        args=[resource_expr, SQLLiteral(value="$.end")],
                    ),
                    right=SQLNull(),
                ),
            )
            return SQLCase(
                when_clauses=[(is_json, has_start_or_end)],
                else_clause=SQLLiteral(value=False),
            )

        if bare_type in ("Range", "range"):
            # Range JSON: {"low": {...}, "high": {...}}
            is_json = SQLFunctionCall(
                name="starts_with",
                args=[
                    SQLFunctionCall(name="LTRIM", args=[resource_expr]),
                    SQLLiteral(value="{"),
                ],
            )
            has_low_or_high = SQLBinaryOp(
                operator="OR",
                left=SQLBinaryOp(
                    operator="IS NOT",
                    left=SQLFunctionCall(
                        name="json_extract_string",
                        args=[resource_expr, SQLLiteral(value="$.low")],
                    ),
                    right=SQLNull(),
                ),
                right=SQLBinaryOp(
                    operator="IS NOT",
                    left=SQLFunctionCall(
                        name="json_extract_string",
                        args=[resource_expr, SQLLiteral(value="$.high")],
                    ),
                    right=SQLNull(),
                ),
            )
            return SQLCase(
                when_clauses=[(is_json, has_low_or_high)],
                else_clause=SQLLiteral(value=False),
            )

        if bare_type in ("Quantity", "quantity"):
            # Quantity JSON has a "value" field. Use CASE WHEN to guard
            # json_extract_string from bare string values.
            is_json = SQLFunctionCall(
                name="starts_with",
                args=[
                    SQLFunctionCall(name="LTRIM", args=[resource_expr]),
                    SQLLiteral(value="{"),
                ],
            )
            return SQLCase(
                when_clauses=[(is_json, SQLBinaryOp(
                    operator="IS NOT",
                    left=SQLFunctionCall(
                        name="json_extract_string",
                        args=[resource_expr, SQLLiteral(value="$.value")],
                    ),
                    right=SQLNull(),
                ))],
                else_clause=SQLLiteral(value=False),
            )

        if bare_type in ("Timing", "timing"):
            # Timing JSON: has "event" or "repeat" field
            return SQLBinaryOp(
                operator="AND",
                left=SQLFunctionCall(
                    name="starts_with",
                    args=[
                        SQLFunctionCall(name="LTRIM", args=[resource_expr]),
                        SQLLiteral(value="{"),
                    ],
                ),
                right=SQLBinaryOp(
                    operator="OR",
                    left=SQLBinaryOp(
                        operator="IS NOT",
                        left=SQLFunctionCall(
                            name="json_extract_string",
                            args=[resource_expr, SQLLiteral(value="$.event")],
                        ),
                        right=SQLNull(),
                    ),
                    right=SQLBinaryOp(
                        operator="IS NOT",
                        left=SQLFunctionCall(
                            name="json_extract_string",
                            args=[resource_expr, SQLLiteral(value="$.repeat")],
                        ),
                        right=SQLNull(),
                    ),
                ),
            )

        # --- Strategy 3: Named profiles ---
        # Negation profiles (e.g. MedicationNotRequested) share a base FHIR
        # type with their positive counterpart (MedicationRequest).  The CQL
        # ``is`` check must distinguish them using the negation indicator
        # field (e.g. doNotPerform) recorded in the profile registry.
        registry = getattr(self.context, 'profile_registry', None)
        if registry is not None:
            negation = registry.get_negation_info(type_name)
            if negation is not None:
                base_type, neg_filter = negation
                resource_type_expr = SQLFunctionCall(
                    name="json_extract_string",
                    args=[resource_expr, SQLLiteral("$.resourceType")],
                )
                type_check = SQLBinaryOp(
                    operator="=", left=resource_type_expr, right=SQLLiteral(base_type)
                )
                if neg_filter == "doNotPerform":
                    neg_check = SQLBinaryOp(
                        operator="=",
                        left=SQLFunctionCall(
                            name="fhirpath_bool",
                            args=[resource_expr, SQLLiteral("doNotPerform")],
                        ),
                        right=SQLLiteral(True),
                    )
                elif neg_filter == "status_not_done":
                    neg_check = SQLBinaryOp(
                        operator="=",
                        left=SQLFunctionCall(
                            name="fhirpath_text",
                            args=[resource_expr, SQLLiteral("status")],
                        ),
                        right=SQLLiteral("not-done"),
                    )
                elif neg_filter == "status_cancelled":
                    neg_check = SQLBinaryOp(
                        operator="=",
                        left=SQLFunctionCall(
                            name="fhirpath_text",
                            args=[resource_expr, SQLLiteral("status")],
                        ),
                        right=SQLLiteral("cancelled"),
                    )
                else:
                    neg_check = None
                if neg_check is not None:
                    return SQLBinaryOp(operator="AND", left=type_check, right=neg_check)
                return type_check

            # Non-negation named profile: resolve to base type for
            # resourceType check below.
            resolved = registry.resolve_named_profile(type_name)
            if resolved is not None:
                type_name = resolved[0]

        # --- Strategy 3b: CQL Vocabulary abstract type (§2.1) ---
        # Vocabulary is a supertype of ValueSet and CodeSystem.
        if bare_type == "Vocabulary":
            resource_type_expr = SQLFunctionCall(
                name="json_extract_string",
                args=[resource_expr, SQLLiteral("$.resourceType")],
            )
            return SQLBinaryOp(
                operator="OR",
                left=SQLBinaryOp(
                    operator="=", left=resource_type_expr, right=SQLLiteral("ValueSet"),
                ),
                right=SQLBinaryOp(
                    operator="=", left=resource_type_expr, right=SQLLiteral("CodeSystem"),
                ),
            )

        # --- Strategy 4: FHIR resource types ---
        resource_type_expr = SQLFunctionCall(
            name="json_extract_string",
            args=[resource_expr, SQLLiteral("$.resourceType")],
        )
        return SQLBinaryOp(
            operator="=", left=resource_type_expr, right=SQLLiteral(type_name)
        )

    def _translate_named_type_specifier(self, node, boolean_context: bool = False) -> SQLExpression:
        """Handle NamedTypeSpecifier - type references like FHIR.dateTime."""
        # Type specifiers don't produce SQL, return null
        return SQLNull()

    def _translate_list_type_specifier(self, node, boolean_context: bool = False) -> SQLExpression:
        """Handle ListTypeSpecifier - list type references."""
        return SQLNull()

    def _translate_interval_type_specifier(self, node, boolean_context: bool = False) -> SQLExpression:
        """Handle IntervalTypeSpecifier - interval type references."""
        return SQLNull()

    def _translate_query(self, node, usage: ExprUsage = ExprUsage.LIST) -> SQLExpression:
        """
        Handle CQL Query expressions:
        - [Condition: "Diabetes"] D where D.status = 'confirmed'
        - [Encounter] E with [Condition] C such that C.subject = E.subject
        """
        # For backward compatibility with old callers
        if isinstance(usage, bool):
            usage = ExprUsage.BOOLEAN if usage else ExprUsage.LIST

        # Handle multi-source queries (source is a list)
        _multi_source_done = False  # set True when multi-source handler builds the full result
        _multi_source_info = []  # (alias, from_sql) tuples for aggregate handler
        if isinstance(node.source, list):
            # For multi-source queries, translate each source and cross-join
            # This is a simplification - proper handling needs correlated subqueries
            if len(node.source) == 1:
                # Check if single source is a known alias (e.g., from WITH clause
                # or fluent function inlining).  Extract the source expression node
                # to avoid premature translation that would produce FROM alias.
                _src0 = node.source[0]
                _src0_expr = _src0.expression if isinstance(_src0, QuerySource) else _src0
                _src0_name = getattr(_src0_expr, 'name', None)
                _src0_alias = getattr(_src0, 'alias', None) if isinstance(_src0, QuerySource) else getattr(_src0, 'alias', None)

                # Detect if source is a known alias.  This covers two cases:
                # 1. Identifier("InpatientEncounter") — direct alias reference
                # 2. ParameterPlaceholder with sql_expr referencing an alias
                #    (from fluent function inlining)
                _src0_is_alias = False
                _src0_alias_name = None  # the actual alias name in context
                if (
                    _src0_name
                    and isinstance(_src0_expr, Identifier)
                    and not getattr(_src0_expr, 'retrieve', None)
                    and self.context.is_alias(_src0_name)
                ):
                    _src0_is_alias = True
                    _src0_alias_name = _src0_name
                elif isinstance(_src0_expr, ParameterPlaceholder):
                    # ParameterPlaceholder comes from fluent function inlining.
                    # Only take the alias path when the sql_expr is a direct
                    # resource reference like SQLQualifiedIdentifier(["X", "resource"])
                    # or a plain SQLIdentifier.  List-typed params (e.g., fhirpath
                    # calls returning arrays) must go through the normal FROM path.
                    # Lambda parameters (_lt_*) are scalar JSON values inside
                    # list_transform — they are NOT table/CTE references and must
                    # NOT be routed through the alias path (which would append
                    # ".resource" via _translate_query_on_alias).
                    _pp_base = self._extract_pp_base(_src0_expr.sql_expr)
                    if _pp_base:
                        _src0_alias_name = _pp_base
                        _src0_is_alias = True

                if _src0_is_alias and _src0_alias_name:
                    # Source is a known alias — don't create FROM clause.
                    return self._translate_query_on_alias(
                        node, _src0_alias_name, _src0_alias,
                    )

                # ── Backbone array on definition reference ──────────────
                # CQL: "Definition".backboneArray Alias where ... return ...
                # The property accesses a multi-valued BackboneElement on a
                # CTE.  We must UNNEST the array so each element is iterable.
                _bb_done = self._try_backbone_array_on_definition(
                    _src0_expr, _src0_alias, node, usage,
                )
                if _bb_done is not None:
                    return _bb_done

                source_expr = self.translate(node.source[0], usage=ExprUsage.SCALAR)
                alias = _src0_alias
            else:
                # Multiple sources: CQL ``from A a, B b where cond return a``
                # Sources are plain QuerySource(alias, expression) nodes.
                # The outer from-query node carries the where/return/let clauses.
                from ...parser.ast_nodes import (
                    QuerySource as _QS,
                    Query as _CQLQuery,
                    WhereClause as _WC,
                    ListExpression as _ListExpr,
                )

                def _unwrap_source(src):
                    """Extract (alias, expression_node) from a source.

                    Handles both:
                    - Plain QuerySource(alias, Identifier/Retrieve)
                    - Legacy QuerySource('', Query(source=QS(alias, expr)))
                    """
                    if isinstance(src, _QS):
                        inner = src.expression
                        if isinstance(inner, _CQLQuery):
                            # Legacy wrapped format
                            qs = inner.source
                            if isinstance(qs, list) and len(qs) == 1:
                                qs = qs[0]
                            if isinstance(qs, _QS):
                                return qs.alias, qs.expression
                            return getattr(src, 'alias', None), qs
                        return src.alias, inner
                    return getattr(src, 'alias', None), src

                # --- 1. Translate the primary source (source[0]) ---
                alias, _pi_expr = _unwrap_source(node.source[0])

                # Translate definition reference as CTE FROM clause
                if isinstance(_pi_expr, Identifier) and _pi_expr.name in self.context._definition_names:
                    cte_name = _pi_expr.name
                    source_expr = SQLSelect(
                        columns=[SQLIdentifier(name="*")],
                        from_clause=SQLAlias(
                            expr=SQLIdentifier(name=cte_name, quoted=True),
                            alias=alias,
                        ),
                    )
                    self.context.add_alias(alias, table_alias=alias, cte_name=cte_name)
                else:
                    source_expr = self.translate(_pi_expr, usage=ExprUsage.SCALAR)
                    # List literals / array expressions must be unnested for FROM clause
                    if isinstance(source_expr, SQLArray) or (
                        isinstance(source_expr, SQLFunctionCall)
                        and _is_list_returning_sql(source_expr)
                    ):
                        source_expr = SQLFunctionCall(name="unnest", args=[source_expr])
                    if alias:
                        self.context.add_alias(alias, table_alias=alias)

                # --- 2. Build a single EXISTS with all secondary sources ---
                # Only the LAST source carries WHERE/RETURN/LET; intermediate
                # sources are plain alias+definition wrappers.  Put all secondary
                # sources in one EXISTS using CROSS JOINs so every alias is
                # visible to the WHERE clause.
                _multi_return_alias = None
                _multi_return_ast = None  # Non-alias return expression AST node
                _sec_infos: list = []  # (alias, from_sql, cte_name, ast_expr)

                for _sec in node.source[1:]:
                    _sec_alias, _sec_expr_node = _unwrap_source(_sec)

                    # Build FROM expression for this secondary source
                    if isinstance(_sec_expr_node, Identifier) and _sec_expr_node.name in self.context._definition_names:
                        _sec_from_sql = SQLSubquery(query=SQLSelect(
                            columns=[SQLIdentifier(name="*")],
                            from_clause=SQLIdentifier(name=_sec_expr_node.name, quoted=True),
                        ))
                        _sec_cte_name = _sec_expr_node.name
                    else:
                        _sec_from_sql = self.translate(_sec_expr_node, usage=ExprUsage.LIST)
                        _sec_cte_name = None
                        # List literals / array expressions must be unnested for FROM clause
                        if isinstance(_sec_from_sql, SQLArray) or (
                            isinstance(_sec_from_sql, SQLFunctionCall)
                            and _is_list_returning_sql(_sec_from_sql)
                        ):
                            _sec_from_sql = SQLFunctionCall(name="unnest", args=[_sec_from_sql])

                    _sec_infos.append((_sec_alias, _sec_from_sql, _sec_cte_name, _sec_expr_node))

                # Save multi-source info for aggregate handler
                _multi_source_info.append((alias, source_expr))
                for _sa, _sf, _, _ in _sec_infos:
                    _multi_source_info.append((_sa, _sf))

                # Capture RETURN expression from the outer from-query node
                if node.return_clause:
                    _ret_expr = (
                        node.return_clause.expression
                        if hasattr(node.return_clause, 'expression')
                        else node.return_clause
                    )
                    if isinstance(_ret_expr, Identifier):
                        _multi_return_alias = _ret_expr.name
                    else:
                        _multi_return_ast = _ret_expr

                if _sec_infos:
                    # Build subquery: push scope, register ALL secondary
                    # aliases, translate LET + WHERE + RETURN, then pop scope.
                    self.context.push_scope()
                    _saved_ra = self.context.resource_alias
                    _multi_return_sql = None
                    try:
                        for _sa, _, _scn, _ in _sec_infos:
                            self.context.add_alias(
                                _sa, table_alias=_sa, cte_name=_scn,
                            )
                        # Set resource_alias to last secondary (owns WHERE)
                        self.context.resource_alias = _sec_infos[-1][0]

                        # Translate LET clauses from the outer from-query node
                        if node.let_clauses:
                            for _lc in node.let_clauses:
                                _is_coll = isinstance(_lc.expression, (Query, Retrieve))
                                if _is_coll:
                                    self.context._let_clause_collection = True
                                _let_sql = self.translate(_lc.expression, usage=ExprUsage.SCALAR)
                                if _is_coll:
                                    self.context._let_clause_collection = False
                                    _let_sql = _wrap_as_json_array_agg(_let_sql)
                                self.context.let_variables[_lc.alias] = _let_sql

                        # Translate WHERE condition from the outer from-query node
                        _sec_where_sql = None
                        if node.where:
                            _where_node = node.where
                            _where_expr = (
                                _where_node.expression
                                if isinstance(_where_node, _WC)
                                else _where_node
                            )
                            _sec_where_sql = _demote_audit_struct_to_bool(self.translate(_where_expr, usage=ExprUsage.BOOLEAN))

                        # Translate computed RETURN expression (inside scope where all aliases + let vars are visible)
                        if _multi_return_ast is not None:
                            _multi_return_sql = self.translate(_multi_return_ast, usage=ExprUsage.SCALAR)
                        elif _multi_return_alias is not None and _multi_return_alias in self.context.let_variables:
                            # Return references a LET variable — use its translated SQL directly
                            _multi_return_sql = self.context.let_variables[_multi_return_alias]
                    finally:
                        self.context.resource_alias = _saved_ra
                        self.context.pop_scope()

                    # Build FROM clause: first secondary, then CROSS JOINs
                    _outer_alias = alias or self.context.resource_alias or "p"
                    _first_alias, _first_from, _, _ = _sec_infos[0]
                    _from_clause = SQLAlias(expr=_first_from, alias=_first_alias)
                    _joins: list = []
                    for _sa, _sf, _, _ in _sec_infos[1:]:
                        _joins.append(SQLJoin(
                            join_type="CROSS JOIN",
                            table=SQLAlias(expr=_sf, alias=_sa),
                            on_condition=None,
                        ))

                    # Patient-id correlations — skip for list literal sources
                    _all_list_sources = isinstance(_pi_expr, _ListExpr) and all(
                        isinstance(info[3], _ListExpr) for info in _sec_infos
                    )
                    _conds: list = []
                    if _sec_where_sql and not isinstance(_sec_where_sql, SQLLiteral):
                        _conds.append(_sec_where_sql)
                    if not _all_list_sources:
                        for _sa, _, _, _ast_expr in _sec_infos:
                            if not isinstance(_ast_expr, _ListExpr):
                                _conds.append(SQLBinaryOp(
                                    left=SQLQualifiedIdentifier(parts=[_sa, "patient_id"]),
                                    operator="=",
                                    right=SQLQualifiedIdentifier(parts=[_outer_alias, "patient_id"]),
                                ))
                    if _conds:
                        _full_cond = _conds[0]
                        for _c in _conds[1:]:
                            _full_cond = SQLBinaryOp(left=_full_cond, operator="AND", right=_c)
                    else:
                        _full_cond = None

                    if _multi_return_sql is not None or _multi_return_alias is not None:
                        # Computed or alias return: CROSS JOIN all sources and project the return expression
                        # Build: SELECT primary.patient_id, <return_expr> AS resource
                        #        FROM primary CROSS JOIN sec1 CROSS JOIN sec2 ...
                        #        WHERE conditions
                        # Always use 'resource' as the column alias to maintain
                        # consistency in UNIONs and downstream references.
                        # The shape inference handles whether the value is treated
                        # as JSON or scalar in the final SELECT.
                        if _multi_return_sql is None:
                            # Alias return (e.g., `return GlucoseTest`): project that alias's correct column
                            # Determine if the alias's CTE uses 'resource' or 'value' column
                            _ret_col = "resource"
                            # Check primary source first
                            if _multi_return_alias == alias and isinstance(_pi_expr, Identifier) and _pi_expr.name in self.context._definition_names:
                                _ret_col = self._get_definition_value_column(_pi_expr.name)
                            else:
                                # Check secondary sources
                                for _sa, _, _scn, _ in _sec_infos:
                                    if _sa == _multi_return_alias and _scn:
                                        _ret_col = self._get_definition_value_column(_scn)
                                        break
                            _multi_return_sql = SQLQualifiedIdentifier(parts=[_multi_return_alias, _ret_col])

                        _prim_from = source_expr.from_clause if isinstance(source_expr, SQLSelect) else (
                            SQLAlias(expr=source_expr, alias=alias) if alias else source_expr
                        )
                        _prim_where = source_expr.where if isinstance(source_expr, SQLSelect) else None
                        _prim_joins = source_expr.joins if isinstance(source_expr, SQLSelect) else None

                        # Add primary→secondary CROSS JOINs
                        _all_joins = list(_prim_joins or [])
                        _first_join = SQLJoin(
                            join_type="CROSS JOIN",
                            table=_from_clause,
                            on_condition=None,
                        )
                        _all_joins.append(_first_join)
                        _all_joins.extend(_joins)

                        # Combine primary WHERE with secondary conditions
                        if _prim_where and _full_cond:
                            _full_cond = SQLBinaryOp(left=_prim_where, operator="AND", right=_full_cond)
                        elif _prim_where:
                            _full_cond = _prim_where

                        _columns = [
                            SQLAlias(expr=SQLCast(expression=_multi_return_sql, target_type="VARCHAR"), alias="resource"),
                        ]
                        if not _all_list_sources:
                            _columns.insert(0, SQLQualifiedIdentifier(parts=[_outer_alias, "patient_id"]))

                        source_expr = SQLSelect(
                            columns=_columns,
                            from_clause=_prim_from,
                            where=_full_cond,
                            joins=_all_joins if _all_joins else None,
                        )
                    elif _all_list_sources:
                        # No return clause + all list-literal sources: return
                        # cross-product as JSON tuples (CQL R1.5 §10.2 — Multi-
                        # source queries return Tuple rows when no return is
                        # specified).
                        # Build:
                        #   (SELECT list(t.v) FROM (
                        #     SELECT json_object('A', CAST(A AS VARCHAR), ...) AS v
                        #     FROM (SELECT unnest AS A FROM unnest([2,3])) _t0
                        #     CROSS JOIN (SELECT unnest AS B FROM unnest([5,6])) _t1
                        #     ORDER BY A, B
                        #   ) t)
                        # Each unnest source is wrapped in a subquery that renames
                        # the DuckDB ``unnest`` column to the CQL alias name.
                        # ORDER BY ensures deterministic cross-product ordering.
                        _json_obj_args: list = []
                        _all_aliases = [alias] + [si[0] for si in _sec_infos]
                        for _a in _all_aliases:
                            _json_obj_args.append(SQLLiteral(value=_a))
                            _json_obj_args.append(SQLCast(
                                expression=SQLIdentifier(name=_a),
                                target_type="VARCHAR",
                            ))
                        _tuple_expr = SQLFunctionCall(
                            name="json_object", args=_json_obj_args,
                        )
                        # Wrap primary unnest: SELECT unnest AS <alias> FROM unnest(...)
                        _prim_inner = source_expr.from_clause if isinstance(source_expr, SQLSelect) else source_expr
                        _prim_wrapped = SQLSubquery(query=SQLSelect(
                            columns=[SQLAlias(
                                expr=SQLIdentifier(name="unnest"),
                                alias=alias,
                            )],
                            from_clause=_prim_inner,
                        ))
                        _prim_from_t = SQLAlias(expr=_prim_wrapped, alias="_t0")
                        # Wrap each secondary unnest similarly
                        _all_joins_t: list = []
                        for _idx, (_sa, _sf, _, _) in enumerate(_sec_infos):
                            _sec_wrapped = SQLSubquery(query=SQLSelect(
                                columns=[SQLAlias(
                                    expr=SQLIdentifier(name="unnest"),
                                    alias=_sa,
                                )],
                                from_clause=_sf,
                            ))
                            _all_joins_t.append(SQLJoin(
                                join_type="CROSS JOIN",
                                table=SQLAlias(expr=_sec_wrapped, alias=f"_t{_idx + 1}"),
                                on_condition=None,
                            ))
                        # Inner SELECT: rows with tuple JSON, ordered by aliases
                        _order_by = [(SQLIdentifier(name=_a), "ASC") for _a in _all_aliases]
                        _inner_select = SQLSelect(
                            columns=[SQLAlias(expr=_tuple_expr, alias="v")],
                            from_clause=_prim_from_t,
                            where=_full_cond,
                            joins=_all_joins_t if _all_joins_t else None,
                            order_by=_order_by,
                        )
                        # Outer SELECT: aggregate into list
                        _list_expr = SQLFunctionCall(
                            name="list",
                            args=[SQLQualifiedIdentifier(parts=["t", "v"])],
                        )
                        source_expr = SQLSubquery(query=SQLSelect(
                            columns=[_list_expr],
                            from_clause=SQLAlias(
                                expr=SQLSubquery(query=_inner_select),
                                alias="t",
                            ),
                        ))
                    else:
                        # No return clause + resource sources: use EXISTS pattern
                        _exists_sub = SQLSubquery(query=SQLSelect(
                            columns=[SQLLiteral(value=1)],
                            from_clause=_from_clause,
                            where=_full_cond,
                            joins=_joins if _joins else None,
                        ))
                        _exists_expr = SQLExists(subquery=_exists_sub)

                        if isinstance(source_expr, SQLSelect):
                            source_expr = SQLSelect(
                                columns=source_expr.columns,
                                from_clause=source_expr.from_clause,
                                where=(
                                    SQLBinaryOp(left=source_expr.where, operator="AND", right=_exists_expr)
                                    if source_expr.where else _exists_expr
                                ),
                                joins=source_expr.joins,
                            )
                        else:
                            source_expr = SQLSelect(
                                columns=[SQLIdentifier(name="*")],
                                from_clause=SQLAlias(expr=source_expr, alias=alias) if alias else source_expr,
                                where=_exists_expr,
                            )
                _multi_source_done = True
        else:
            # Single source
            # FIX #2: Check if source is a direct definition reference before translating
            # This prevents track_cte_reference from being called too early with SCALAR usage,
            # which would return j1.resource instead of the CTE name

            source_node = node.source

            # Handle QuerySource by checking its expression
            if isinstance(source_node, QuerySource):
                source_expr_node = source_node.expression
                source_alias = source_node.alias
            else:
                source_expr_node = source_node
                source_alias = getattr(source_node, 'alias', None)

            source_name = getattr(source_expr_node, 'name', None)

            # Check if this is a direct reference to a named definition (not a retrieve).
            # Use _definition_names (pre-registered before translation starts) rather than
            # context.definitions (populated incrementally as each definition is translated),
            # so forward references and same-pass references are both handled correctly.
            is_definition_ref = (
                source_name and
                isinstance(source_expr_node, Identifier) and
                not getattr(source_expr_node, 'retrieve', None) and
                hasattr(self.context, '_definition_names') and
                source_name in self.context._definition_names
            )

            if is_definition_ref:
                # Use CTE identifier directly - don't call translate() with SCALAR usage
                # which would trigger track_cte_reference and return j1.resource
                source_expr = SQLIdentifier(name=source_name, quoted=True)
                alias = source_alias
            elif (
                source_name
                and isinstance(source_expr_node, Identifier)
                and not getattr(source_expr_node, 'retrieve', None)
                and self.context.is_alias(source_name)
            ):
                # Source is a known query alias — use the shared helper
                return self._translate_query_on_alias(
                    node, source_name, source_alias,
                )
            elif isinstance(source_expr_node, ParameterPlaceholder):
                # ParameterPlaceholder from fluent function inlining.
                # Only take the alias path for direct resource references.
                # Lambda parameters (_lt_*) are scalar JSON values inside
                # list_transform — they must NOT be treated as table/CTE refs.
                _pp_base = self._extract_pp_base(source_expr_node.sql_expr)
                if _pp_base:
                    return self._translate_query_on_alias(
                        node, _pp_base, source_alias,
                    )
                else:
                    source_expr = self.translate(node.source, usage=ExprUsage.SCALAR)
                    alias = source_alias
            else:
                # Check for backbone array property on a definition
                _bb_done = self._try_backbone_array_on_definition(
                    source_expr_node, source_alias, node, usage,
                )
                if _bb_done is not None:
                    return _bb_done

                # Check for set operation (intersect/union/except) as query source.
                # These need special handling: operands should be full CTE selects
                # (patient_id + resource) without per-patient correlation, because
                # the set operation itself is the FROM clause that produces rows.
                _set_op_result = self._try_set_op_source(
                    source_expr_node, source_alias, node, usage,
                )
                if _set_op_result is not None:
                    source_expr = _set_op_result
                    alias = source_alias
                else:
                    # Check for MethodInvocation returning a list (e.g.,
                    # Alias.claimDiagnosis()) used as a query source.
                    # These need UNNEST so the outer WHERE applies per-element.
                    _method_done = self._try_method_invocation_list_source(
                        source_expr_node, source_alias, node, usage,
                    )
                    if _method_done is not None:
                        return _method_done

                    source_expr = self.translate(node.source, usage=ExprUsage.SCALAR)
                    alias = getattr(node.source, 'alias', None)

        # Register alias in context for property access
        # Store the source SQL expression so property access can use it
        # IMPORTANT: During Phase 1, we store the AST object, NOT the SQL string
        # This avoids calling to_sql() on expressions that may contain placeholders
        # Capture definition CTE name when the source is a definition reference
        _alias_cte_name = None
        if not isinstance(node.source, list):
            _src = node.source
            if isinstance(_src, QuerySource):
                _src = _src.expression
            _sn = getattr(_src, 'name', None)
            if _sn and isinstance(_src, Identifier) and hasattr(self.context, '_definition_names') and _sn in self.context._definition_names:
                _alias_cte_name = _sn
        if alias:
            # Track the FHIR resource type for this alias (for fluent overload resolution)
            alias_rt = self._extract_query_source_resource_type(node)
            if alias_rt:
                self.context._alias_resource_types[alias] = alias_rt
            # Don't store SQLUnion as a raw string - it will cause issues in scalar contexts
            # Instead, mark it so property access can handle it specially
            if isinstance(source_expr, SQLUnion):
                # For SQLUnion, we need to handle property access differently
                # Store a marker that indicates this is a union
                # Property access will need to apply fhirpath to each operand and COALESCE
                self.context.add_alias(alias, sql_expr="__UNION__", union_expr=source_expr)
            elif isinstance(source_expr, SQLCase):
                # Check if the SQLCase contains a SQLUnion in its THEN clauses
                # If so, we need special handling - use type checking, NOT to_sql()
                has_union = False
                for condition, result in source_expr.when_clauses:
                    if isinstance(result, SQLUnion):
                        has_union = True
                        break
                    # Check for SQLSubquery containing UNION (without calling to_sql)
                    if isinstance(result, SQLSubquery) and isinstance(result.query, SQLUnion):
                        has_union = True
                        break
                if has_union:
                    # Store the entire CASE expression but mark it for special handling
                    self.context.add_alias(alias, sql_expr="__UNION_CASE__", union_expr=source_expr)
                else:
                    # Store the AST object - don't call to_sql() during Phase 1
                    self.context.add_alias(alias, ast_expr=source_expr, cte_name=_alias_cte_name)
            else:
                # Store the AST object - don't call to_sql() during Phase 1
                # Property access will handle extraction if needed
                self.context.add_alias(alias, ast_expr=source_expr, cte_name=_alias_cte_name)

        # Start with the source query
        result = source_expr

        # Helper function to check if an expression is or contains a CTE reference
        def _is_cte_ref(expr):
            """Check if expression is a CTE reference (SQLIdentifier with quoted name or RetrievePlaceholder)."""
            if isinstance(expr, SQLIdentifier):
                return expr.quoted or ':' in expr.name or ' ' in expr.name
            if isinstance(expr, RetrievePlaceholder):
                return True
            return False

        def _contains_cte_ref(expr):
            """Check if expression is or contains a CTE reference."""
            if isinstance(expr, SQLIdentifier):
                return expr.quoted or ':' in expr.name or ' ' in expr.name
            if isinstance(expr, RetrievePlaceholder):
                return True
            # FIX: Handle DeferredTemplateSubstitution by checking _resource_expr
            if hasattr(expr, '_resource_expr'):
                return _contains_cte_ref(expr._resource_expr)
            if isinstance(expr, SQLCase):
                for cond, then_expr in expr.when_clauses:
                    if _contains_cte_ref(then_expr):
                        return True
            if isinstance(expr, SQLFunctionCall):
                for arg in expr.args:
                    if _contains_cte_ref(arg):
                        return True
            if isinstance(expr, SQLSelect) and expr.from_clause:
                return _contains_cte_ref(expr.from_clause)
            if isinstance(expr, SQLSubquery):
                return _contains_cte_ref(expr.query)
            if isinstance(expr, (SQLUnion, SQLIntersect, SQLExcept)):
                for op in expr.operands:
                    if _contains_cte_ref(op):
                        return True
            if isinstance(expr, SQLAlias):
                return _contains_cte_ref(expr.expr)
            if isinstance(expr, SQLQualifiedIdentifier):
                for part in expr.parts:
                    if isinstance(part, str) and (':' in part or ' ' in part):
                        return True
            return False

        # Helper to extract CTE name from expression
        def _get_cte_name(expr):
            """Get the CTE name from an expression (SQLIdentifier or RetrievePlaceholder)."""
            if isinstance(expr, SQLIdentifier):
                if expr.quoted or ':' in expr.name or ' ' in expr.name:
                    return expr.name
            if isinstance(expr, RetrievePlaceholder):
                # Return the placeholder key as the CTE name
                # The key format is (resource_type, valueset) which matches CTE naming
                return expr.key
            return None

        def _extract_cte_name(expr):
            """Extract the CTE name from an expression (recursive)."""
            if isinstance(expr, SQLIdentifier):
                if expr.quoted or ':' in expr.name or ' ' in expr.name:
                    return expr.name
            if isinstance(expr, RetrievePlaceholder):
                return expr.key
            # FIX: Handle DeferredTemplateSubstitution by checking _resource_expr
            if hasattr(expr, '_resource_expr'):
                return _extract_cte_name(expr._resource_expr)
            if isinstance(expr, SQLCase):
                for cond, then_expr in expr.when_clauses:
                    name = _extract_cte_name(then_expr)
                    if name:
                        return name
            if isinstance(expr, SQLFunctionCall):
                for arg in expr.args:
                    name = _extract_cte_name(arg)
                    if name:
                        return name
            if isinstance(expr, SQLSelect) and expr.from_clause:
                return _extract_cte_name(expr.from_clause)
            if isinstance(expr, SQLSubquery):
                return _extract_cte_name(expr.query)
            if isinstance(expr, (SQLUnion, SQLIntersect, SQLExcept)):
                for op in expr.operands:
                    name = _extract_cte_name(op)
                    if name:
                        return name
            if isinstance(expr, SQLAlias):
                return _extract_cte_name(expr.expr)
            return None

        # FIX #1 from SQL_GENERATION_ISSUES.md:
        # When a query source is a CTE reference (resolved placeholder) with an alias,
        # immediately wrap it in a SELECT with proper FROM clause structure.
        # This ensures the alias is bound at the correct point in the query.
        # When multi-source handling already built a complete SQLSelect with
        # EXISTS clauses, skip CTE-ref wrapping — the result is ready to use.
        if _multi_source_done:
            result = source_expr
        elif alias and _is_cte_ref(source_expr):
            # Get the CTE name/key
            cte_key = _get_cte_name(source_expr)
            if cte_key:
                if isinstance(source_expr, RetrievePlaceholder):
                    # KEEP the placeholder in the AST — Phase 3 (resolve_placeholders)
                    # will replace it with the correct CTE name later.
                    # This ensures Phase 2 can find all placeholders and build CTEs.
                    result = SQLSelect(
                        columns=[SQLIdentifier(name="*")],
                        from_clause=SQLAlias(
                            expr=source_expr,
                            alias=alias
                        )
                    )
                    provisional_cte_name = f"{source_expr.resource_type}: {source_expr.valueset}" if source_expr.valueset else source_expr.resource_type
                    self.context.add_alias(alias, table_alias=alias, cte_name=provisional_cte_name)
                else:
                    cte_name = cte_key if isinstance(cte_key, str) else str(cte_key)
                    result = SQLSelect(
                        columns=[SQLIdentifier(name="*")],
                        from_clause=SQLAlias(
                            expr=SQLIdentifier(name=cte_name, quoted=True),
                            alias=alias
                        )
                    )
                    self.context.add_alias(alias, table_alias=alias, cte_name=cte_name)
        elif alias and _contains_cte_ref(source_expr) and not isinstance(source_expr, (SQLFunctionCall, SQLCase)):
            # Source contains a CTE reference (e.g., SQLCase with CTE in THEN clause)
            # or a nested RetrievePlaceholder (e.g., inside DeferredTemplateSubstitution).
            # Skip when source is a SQLFunctionCall — the function IS the expression
            # to iterate over (e.g., collapse_intervals) and should not be flattened
            # into a bare CTE reference.

            # If source_expr is a set operation (UNION/INTERSECT/EXCEPT) containing
            # CTE refs or placeholders, keep the full set operation as the FROM source.
            # Phase 3 resolve_placeholders handles these natively.
            if isinstance(source_expr, (SQLUnion, SQLIntersect, SQLExcept)):
                inner_placeholders = find_all_placeholders(source_expr)
                provisional_cte_name = None
                if inner_placeholders:
                    p0 = inner_placeholders[0]
                    provisional_cte_name = f"{p0.resource_type}: {p0.valueset}" if p0.valueset else p0.resource_type
                result = SQLSelect(
                    columns=[SQLIdentifier(name="*")],
                    from_clause=SQLAlias(
                        expr=source_expr,
                        alias=alias
                    )
                )
                self.context.add_alias(alias, table_alias=alias, cte_name=provisional_cte_name or alias)
            elif contains_placeholder(source_expr):
                # Source contains unresolved placeholders. Extract the inner placeholder(s)
                # and use them directly as FROM sources so Phase 3 can resolve them to CTE names.
                # DeferredTemplateSubstitution wraps placeholders in filter expressions
                # (like list_filter) which can't be used as FROM clause sources.
                inner_placeholders = find_all_placeholders(source_expr)
                if inner_placeholders:
                    inner_placeholder = inner_placeholders[0]
                    provisional_cte_name = f"{inner_placeholder.resource_type}: {inner_placeholder.valueset}" if inner_placeholder.valueset else inner_placeholder.resource_type

                    # If source_expr is a SQLSelect/SQLSubquery with WHERE (e.g., from
                    # fluent function like isEncounterPerformed), preserve the full
                    # expression as a subquery so the WHERE clause is not lost.
                    inner_query = source_expr
                    if isinstance(inner_query, SQLSubquery):
                        inner_query = inner_query.query
                    if isinstance(inner_query, SQLSelect) and inner_query.where:
                        result = SQLSelect(
                            columns=[SQLIdentifier(name="*")],
                            from_clause=SQLAlias(
                                expr=SQLSubquery(query=inner_query) if not isinstance(source_expr, SQLSubquery) else source_expr,
                                alias=alias
                            )
                        )
                    else:
                        # Use the first placeholder as the FROM source
                        result = SQLSelect(
                            columns=[SQLIdentifier(name="*")],
                            from_clause=SQLAlias(
                                expr=inner_placeholder,
                                alias=alias
                            )
                        )
                    self.context.add_alias(alias, table_alias=alias, cte_name=provisional_cte_name)
                else:
                    cte_key = _extract_cte_name(source_expr)
                    result = SQLSelect(
                        columns=[SQLIdentifier(name="*")],
                        from_clause=SQLAlias(
                            expr=source_expr,
                            alias=alias
                        )
                    )
                    if isinstance(cte_key, tuple):
                        provisional_cte_name = f"{cte_key[0]}: {cte_key[1]}" if cte_key[1] else cte_key[0]
                    else:
                        provisional_cte_name = cte_key if isinstance(cte_key, str) else str(cte_key)
                    self.context.add_alias(alias, table_alias=alias, cte_name=provisional_cte_name)
            else:
                cte_key = _extract_cte_name(source_expr)
                if cte_key:
                    # Determine the CTE name
                    if isinstance(cte_key, tuple):
                        cte_name = f"{cte_key[0]}: {cte_key[1]}" if cte_key[1] else cte_key[0]
                    else:
                        cte_name = cte_key if isinstance(cte_key, str) else str(cte_key)

                    # When source_expr is an SQLSelect (or SQLSubquery wrapping one)
                    # with computed columns (e.g., from an inner query's return clause
                    # like `return date from X.effective`), preserve those columns
                    # instead of replacing with SELECT *.
                    # Note: translate() auto-wraps SQLSelect in SQLSubquery (line 345).
                    _inner_sel = None
                    if isinstance(source_expr, SQLSelect):
                        _inner_sel = source_expr
                    elif isinstance(source_expr, SQLSubquery) and isinstance(source_expr.query, SQLSelect):
                        _inner_sel = source_expr.query
                    if _inner_sel is not None and not (
                        len(_inner_sel.columns) == 1
                        and isinstance(_inner_sel.columns[0], SQLIdentifier)
                        and _inner_sel.columns[0].name in ("*", "resource")
                    ):
                        from ...translator.ast_utils import replace_qualified_alias
                        from_clause = _inner_sel.from_clause
                        # Detect old alias from FROM clause
                        _old_alias = None
                        if isinstance(from_clause, SQLAlias):
                            _old_alias = from_clause.alias
                            if from_clause.alias != alias:
                                from_clause = SQLAlias(expr=from_clause.expr, alias=alias)
                        else:
                            from_clause = SQLAlias(expr=from_clause, alias=alias)
                        # When flattening, rewrite column/WHERE references from
                        # the inner alias to the outer alias so they stay valid.
                        _cols = _inner_sel.columns
                        _where = _inner_sel.where
                        if _old_alias and _old_alias != alias:
                            _cols = [replace_qualified_alias(c, _old_alias, alias) for c in _cols]
                            if _where is not None:
                                _where = replace_qualified_alias(_where, _old_alias, alias)
                        result = SQLSelect(
                            columns=_cols,
                            from_clause=from_clause,
                            where=_where,
                            order_by=getattr(_inner_sel, 'order_by', None),
                        )
                    else:
                        result = SQLSelect(
                            columns=[SQLIdentifier(name="*")],
                            from_clause=SQLAlias(
                                expr=SQLIdentifier(name=cte_name, quoted=True),
                                alias=alias
                            )
                        )
                    # Preserve ast_expr from any prior registration so that
                    # computed return-clause expressions (e.g., intervals from
                    # inner query return clauses) remain accessible when the
                    # alias is later referenced in temporal operators.
                    _prev_sym = self.context.lookup_symbol(alias)
                    _prev_ast = getattr(_prev_sym, 'ast_expr', None) if _prev_sym else None
                    self.context.add_alias(alias, table_alias=alias, cte_name=cte_name, ast_expr=_prev_ast)

        # Set resource_alias so scalar subquery correlations (e.g., patient_id)
        # reference the correct outer alias instead of hardcoded "p".
        _saved_resource_alias = self.context.resource_alias
        if alias and not self.context.resource_alias:
            self.context.resource_alias = alias

        # ── Backbone array query path ──────────────────────────────
        # When a query iterates over a multi-valued backbone element
        # (e.g., Encounter.location EDLocation where ... return ...),
        # the scalar fhirpath_text() only returns the first element.
        # We must UNNEST the full array and process WHERE/RETURN/SORT
        # on the expanded rows inside a subquery.
        _backbone_array_done = False
        # Detect if WHERE clause has compound conditions (AND/OR) on backbone
        # sub-properties. Multiple conditions on different sub-properties
        # require per-element UNNEST — scalar fhirpath_text() can't correlate
        # conditions across individual backbone elements.
        _where_has_compound = False
        if node.where:
            _w = node.where
            if hasattr(_w, 'expression'):
                _w = _w.expression
            _stack = [_w]
            while _stack:
                _n = _stack.pop()
                if isinstance(_n, BinaryExpression):
                    if _n.operator in ('and', 'or'):
                        _where_has_compound = True
                        break
                    _stack.append(_n.left)
                    _stack.append(_n.right)
        if (
            not _multi_source_done
            and alias
            and isinstance(result, SQLFunctionCall)
            and result.name in ("fhirpath_text", "fhirpath", "json_extract_string", "json_extract")
            and len(result.args) >= 2
            and isinstance(result.args[1], SQLLiteral)
        ):
            _fhir_path = result.args[1].value
            _is_multi = False

            if result.name in ("json_extract_string", "json_extract") and isinstance(_fhir_path, str):
                # json_extract_string(alias.resource, '$.field') is produced when the
                # source is a tuple-returning CTE field.  When a Query iterates over
                # this field with an alias and WHERE or RETURN clause, the JSON array
                # must be unnested per-element — there is no BackboneElement schema
                # to consult for CQL tuple fields.  This also covers simple WHERE
                # exists checks (no return clause) so the gate check is not needed.
                if node.where or node.return_clause:
                    _is_multi = True
            else:
                _gate = (node.return_clause or getattr(node, 'sort', None) or _where_has_compound
                         or (node.where and getattr(self.context, '_let_clause_collection', False)))
                if _gate and isinstance(_fhir_path, str) and '.' not in _fhir_path:
                    # Existing fhirpath_text/fhirpath BackboneElement detection.
                    # Determine parent resource type from the fhirpath first arg
                    _src_rt = None
                    _arg0 = result.args[0]
                    if isinstance(_arg0, SQLQualifiedIdentifier) and _arg0.parts:
                        _base_alias = _arg0.parts[0] if isinstance(_arg0.parts[0], str) else None
                        if _base_alias:
                            _src_rt = self.context._alias_resource_types.get(_base_alias)
                    elif isinstance(_arg0, SQLIdentifier):
                        _src_rt = self.context._alias_resource_types.get(_arg0.name)

                    if _src_rt and self.context.fhir_schema:
                        _elem_key = f"{_src_rt}.{_fhir_path}"
                        _res_def = self.context.fhir_schema.resources.get(_src_rt)
                        if _res_def:
                            _elem = _res_def.elements.get(_elem_key)
                            if (_elem and _elem.cardinality and _elem.cardinality.endswith('*')
                                    and 'BackboneElement' in _elem.types):
                                _is_multi = True

                    # Fallback: when resource type is unknown (definition ref),
                    # check all loaded types for a multi-valued BackboneElement
                    if not _is_multi and not _src_rt and self.context.fhir_schema:
                        for _rt_name, _rt_def in self.context.fhir_schema.resources.items():
                            _felem = _rt_def.elements.get(f"{_rt_name}.{_fhir_path}")
                            if (
                                _felem
                                and _felem.cardinality
                                and _felem.cardinality.endswith('*')
                                and 'BackboneElement' in _felem.types
                            ):
                                _is_multi = True
                                break

            if _is_multi:
                _lt_param = f"_lt_{alias}"
                if result.name in ("json_extract_string", "json_extract"):
                    # The result is already a JSON array string — wrap directly.
                    _unnest_source = SQLFunctionCall(
                        name="from_json",
                        args=[result, SQLLiteral(value='["VARCHAR"]')],
                    )
                else:
                    _fhir_args = list(result.args)
                    _unnest_source = SQLFunctionCall(
                        name="from_json",
                        args=[
                            SQLFunctionCall(name="fhirpath", args=_fhir_args),
                            SQLLiteral(value='["VARCHAR"]'),
                        ],
                    )

                self.context.push_scope()
                self.context.add_alias(alias, ast_expr=SQLIdentifier(name=_lt_param))

                # Process LET clauses in the UNNEST scope
                if hasattr(node, 'let_clauses') and node.let_clauses:
                    for let_clause in node.let_clauses:
                        let_name = let_clause.alias
                        _is_coll = isinstance(let_clause.expression, (Query, Retrieve))
                        if _is_coll:
                            self.context._let_clause_collection = True
                        let_expr_sql = self.translate(let_clause.expression, usage=ExprUsage.SCALAR)
                        if _is_coll:
                            self.context._let_clause_collection = False
                            let_expr_sql = _wrap_as_json_array_agg(let_expr_sql)
                        self.context.let_variables[let_name] = let_expr_sql

                _ba_where = None
                if node.where:
                    _ba_where = _demote_audit_struct_to_bool(self.translate(node.where, usage=ExprUsage.BOOLEAN))

                _ba_return = SQLIdentifier(name=_lt_param)
                if node.return_clause:
                    _ba_return = self.translate(node.return_clause, usage=ExprUsage.SCALAR)

                self.context.pop_scope()

                _ba_return = _ensure_scalar_body(_ba_return)
                _inner_unnest = SQLSubquery(query=SQLSelect(
                    columns=[SQLAlias(
                        expr=SQLFunctionCall(name="unnest", args=[_unnest_source]),
                        alias=_lt_param,
                    )],
                ))
                _unnest_from = SQLAlias(expr=_inner_unnest, alias="_lt_unnest")

                # Don't add ORDER BY here — list() is an aggregate so
                # ORDER BY on non-aggregated columns is invalid.
                # Sorting is handled by list_sort in the First/Last handler.
                result = SQLSubquery(query=SQLSelect(
                    columns=[SQLFunctionCall(name="list", args=[_ba_return])],
                    from_clause=_unnest_from,
                    where=_ba_where,
                ))
                _backbone_array_done = True

        if _backbone_array_done:
            if usage == ExprUsage.BOOLEAN:
                self.context.resource_alias = _saved_resource_alias
                return SQLBinaryOp(
                    left=SQLFunctionCall(name="array_length", args=[result]),
                    operator=">",
                    right=SQLLiteral(value=0),
                )
            self.context.resource_alias = _saved_resource_alias
            return result

        # Detect list-source queries early: when the source is a genuine
        # DuckDB list expression (e.g., list_transform, from_json) and there's
        # an iteration alias with let clauses, ALL body processing (let,
        # where, return) must happen per-element inside a lambda scope.
        # Otherwise, let variables reference the full list instead of each element.
        # NOTE: fhirpath_text/fhirpath/collapse_intervals are NOT included here
        # because they return scalars (not arrays) and are converted to arrays
        # only in the return clause's list_transform path.
        _early_list_transform = False
        _early_lt_source = None
        _early_lt_param = None
        if (
            isinstance(result, SQLFunctionCall)
            and alias
            and _is_list_returning_sql(result)
            and (hasattr(node, 'let_clauses') and node.let_clauses)
        ):
            _early_list_transform = True
            _early_lt_source = result
            _early_lt_param = f"_lt_{alias}"
            self.context.push_scope()
            self.context.add_alias(alias, ast_expr=SQLIdentifier(name=_early_lt_param))
            # Replace result with a scalar placeholder — the actual wrapping
            # in list_transform/UNNEST happens after return clause processing.
            result = SQLIdentifier(name=_early_lt_param)

        # Process let clauses BEFORE the WHERE clause so that let-defined
        # variables (e.g., DischDisp) are available during WHERE translation.
        # Skip when multi-source handler already processed them.
        if not _multi_source_done and hasattr(node, 'let_clauses') and node.let_clauses:
            for let_clause in node.let_clauses:
                let_name = let_clause.alias
                _is_coll = isinstance(let_clause.expression, (Query, Retrieve))
                if _is_coll:
                    self.context._let_clause_collection = True
                let_expr_sql = self.translate(let_clause.expression, usage=ExprUsage.SCALAR)
                if _is_coll:
                    self.context._let_clause_collection = False
                    let_expr_sql = _wrap_as_json_array_agg(let_expr_sql)
                self.context.let_variables[let_name] = let_expr_sql

        # Apply WHERE clause if present (skip when multi-source already handled it)
        if not _multi_source_done and node.where:
            where_expr = _demote_audit_struct_to_bool(self.translate(node.where, usage=ExprUsage.BOOLEAN))
            if isinstance(result, SQLSelect):
                # Combine with existing WHERE
                if result.where:
                    result = SQLSelect(
                        columns=result.columns,
                        from_clause=result.from_clause,
                        where=SQLBinaryOp(
                            left=result.where,
                            operator="AND",
                            right=where_expr,
                        ),
                        group_by=result.group_by,
                        having=result.having,
                        order_by=result.order_by,
                        limit=result.limit,
                    )
                else:
                    result = SQLSelect(
                        columns=result.columns,
                        from_clause=result.from_clause,
                        where=where_expr,
                    )
            elif isinstance(result, SQLSubquery):
                # Unwrap subquery, add WHERE, rewrap
                inner = result.query
                if isinstance(inner, SQLSelect):
                    new_where = where_expr
                    if inner.where:
                        new_where = SQLBinaryOp(
                            left=inner.where,
                            operator="AND",
                            right=where_expr,
                        )
                    result = SQLSubquery(query=SQLSelect(
                        columns=inner.columns,
                        from_clause=inner.from_clause,
                        where=new_where,
                        group_by=inner.group_by,
                        having=inner.having,
                        order_by=inner.order_by,
                        limit=inner.limit,
                    ))
            else:
                # Source is an expression - need to filter based on WHERE
                # If result is a scalar (like fhirpath_text), we can't use it as a FROM clause
                # Instead, we need to evaluate the where_expr in context of the scalar result
                # For scalar sources with WHERE, the WHERE should be applied as a filter
                # on the condition, not as a table source

                # Check if result is a scalar expression (function call, literal, etc.)
                if isinstance(result, SQLCase):
                    # Check if the SQLCase contains SQLUnion in its THEN clauses
                    # If so, we need special handling to avoid UNION in scalar context
                    has_union_result = any(
                        isinstance(when_result, SQLUnion)
                        for _, when_result in result.when_clauses
                    )
                    if has_union_result:
                        # Distribute the where_expr into each branch and use COALESCE
                        # For each WHEN clause with SQLUnion, expand to individual cases
                        coalesce_args = []
                        for inner_cond, inner_result in result.when_clauses:
                            if isinstance(inner_result, SQLUnion):
                                # For each operand in the union, create a CASE
                                for operand in inner_result.operands:
                                    combined_cond = SQLBinaryOp(
                                        left=where_expr,
                                        operator="AND",
                                        right=inner_cond,
                                    )
                                    coalesce_args.append(SQLCase(
                                        when_clauses=[(combined_cond, operand)],
                                        else_clause=SQLNull(),
                                    ))
                            else:
                                # Non-union result - combine conditions normally
                                combined_cond = SQLBinaryOp(
                                    left=where_expr,
                                    operator="AND",
                                    right=inner_cond,
                                )
                                coalesce_args.append(SQLCase(
                                    when_clauses=[(combined_cond, inner_result)],
                                    else_clause=SQLNull(),
                                ))
                        # Handle the ELSE clause of the original CASE
                        if result.else_clause is not None:
                            coalesce_args.append(SQLCase(
                                when_clauses=[(where_expr, result.else_clause)],
                                else_clause=SQLNull(),
                            ))
                        result = SQLFunctionCall(name="COALESCE", args=coalesce_args)
                    else:
                        # Normal CASE without UNION - wrap normally
                        result = SQLCase(
                            when_clauses=[(where_expr, result)],
                            else_clause=SQLNull(),
                        )
                elif isinstance(result, (SQLFunctionCall, SQLLiteral, SQLBinaryOp, SQLUnaryOp)):
                    # Scalar expression with WHERE - combine into a CASE or conditional
                    # Use CASE WHEN where_expr THEN result ELSE NULL END pattern
                    result = SQLCase(
                        when_clauses=[(where_expr, result)],
                        else_clause=SQLNull(),
                    )
                elif isinstance(result, SQLSubquery):
                    # Subquery (from retrieve) - filter using list_filter pattern
                    # list_filter(subquery, condition) returns filtered array
                    # Need to wrap the where_expr as a lambda function
                    # Use SQLLambda to keep AST structure (don't call to_sql() during Phase 1)
                    result = SQLFunctionCall(
                        name="list_filter",
                        args=[
                            result,
                            SQLLambda(param="r", body=where_expr)
                        ]
                    )
                else:
                    # Determine if result is a table-like source or a scalar expression
                    # SQLIdentifier with quoted=True → CTE/table reference (valid FROM source)
                    # SQLQualifiedIdentifier (e.g., j1.value) → scalar column access
                    is_table_source = False
                    if isinstance(result, (SQLSelect, SQLUnion)):
                        is_table_source = True
                    elif isinstance(result, SQLIdentifier) and result.quoted:
                        is_table_source = True

                    if is_table_source:
                        source_alias = alias or "src"
                        result = SQLSubquery(query=SQLSelect(
                            columns=[SQLIdentifier(name=source_alias)],
                            from_clause=result,
                            where=where_expr,
                        ))
                    else:
                        # Scalar expression (QualifiedIdentifier, unquoted Identifier, etc.)
                        result = SQLCase(
                            when_clauses=[(where_expr, result)],
                            else_clause=SQLNull(),
                        )

        # After WHERE processing, check if result became a CASE with UNION in THEN
        # If so, update the alias to use __UNION_CASE__ marker
        if alias and isinstance(result, SQLCase):
            has_union_in_then = False
            for _, when_result in result.when_clauses:
                if isinstance(when_result, SQLUnion):
                    has_union_in_then = True
                    break
                # Check for SQLSubquery containing UNION (without calling to_sql)
                if isinstance(when_result, SQLSubquery) and isinstance(when_result.query, SQLUnion):
                    has_union_in_then = True
                    break
            if has_union_in_then:
                self.context.add_alias(alias, sql_expr="__UNION_CASE__", union_expr=result)

        # Handle with/without clauses (relationship queries)

        if hasattr(node, 'with_clauses') and node.with_clauses:
            for with_clause in node.with_clauses:
                is_without = getattr(with_clause, 'is_without', False)
                wc_alias = with_clause.alias
                wc_expr = with_clause.expression
                such_that = with_clause.such_that

                # Translate the source expression for the with clause
                # For definition references, bypass query_builder tracking to avoid
                # picking up the outer query's tracked alias (e.g., j1.resource)
                if isinstance(wc_expr, Identifier) and wc_expr.name in self.context._definition_names:
                    wc_source_sql = SQLSubquery(query=SQLSelect(
                        columns=[SQLIdentifier(name="*")],
                        from_clause=SQLIdentifier(name=wc_expr.name, quoted=True),
                    ))
                else:
                    wc_source_sql = self.translate(wc_expr, usage=ExprUsage.LIST)

                # Register alias with table_alias so property access uses
                # wc_alias.resource for fhirpath extraction.
                # Pass cte_name for definition references so scalar access
                # resolves to alias.resource/value instead of bare alias.
                _wc_cte_name = wc_expr.name if isinstance(wc_expr, Identifier) and wc_expr.name in self.context._definition_names else None
                self.context.push_scope()
                try:
                    self.context.add_alias(wc_alias, table_alias=wc_alias, cte_name=_wc_cte_name)
                    # Set resource_alias so Patient correlation uses the with-clause alias
                    old_resource_alias = self.context.resource_alias
                    self.context.resource_alias = wc_alias
                    # Translate the such_that condition
                    condition_sql = self.translate(such_that, usage=ExprUsage.BOOLEAN) if such_that else SQLLiteral(value=True)
                    self.context.resource_alias = old_resource_alias
                finally:
                    self.context.pop_scope()

                # Build the FROM clause for the EXISTS subquery
                # When the with-clause expression is a scalar (e.g., a CASE
                # expression from inlined fluent functions over sub-elements
                # like Claim.item), wrap it in a SELECT that provides
                # resource and patient_id columns so property access works.
                outer_corr_alias = alias or self.context.resource_alias or "p"
                if not isinstance(wc_source_sql, (SQLSelect, SQLSubquery, SQLUnion, SQLIntersect, SQLExcept, SQLIdentifier, SQLQualifiedIdentifier, SQLAlias, RetrievePlaceholder)):
                    wc_source_sql = SQLSubquery(query=SQLSelect(
                        columns=[
                            SQLAlias(expr=wc_source_sql, alias="resource"),
                            SQLAlias(
                                expr=SQLQualifiedIdentifier(parts=[outer_corr_alias, "patient_id"]),
                                alias="patient_id",
                            ),
                        ],
                    ))
                wc_from = SQLAlias(expr=wc_source_sql, alias=wc_alias) if not isinstance(wc_source_sql, SQLAlias) else wc_source_sql
                # Add patient_id correlation: correlate with the outer query alias
                patient_corr = SQLBinaryOp(
                    left=SQLQualifiedIdentifier(parts=[wc_alias, "patient_id"]),
                    operator="=",
                    right=SQLQualifiedIdentifier(parts=[outer_corr_alias, "patient_id"]),
                )
                if condition_sql and not isinstance(condition_sql, SQLLiteral):
                    full_condition = SQLBinaryOp(left=_demote_audit_struct_to_bool(condition_sql), operator="AND", right=patient_corr)
                else:
                    full_condition = patient_corr

                exists_subquery = SQLSubquery(query=SQLSelect(
                    columns=[SQLLiteral(value=1)],
                    from_clause=wc_from,
                    where=full_condition,
                ))
                exists_expr = SQLExists(subquery=exists_subquery) if not is_without else SQLUnaryOp(operator="NOT", operand=SQLExists(subquery=exists_subquery))

                # Add to existing WHERE clause
                if isinstance(result, SQLSelect):
                    if result.where:
                        new_where = SQLBinaryOp(left=result.where, operator="AND", right=exists_expr)
                    else:
                        new_where = exists_expr
                    result = SQLSelect(
                        columns=result.columns,
                        from_clause=result.from_clause,
                        where=new_where,
                        joins=result.joins,
                        group_by=result.group_by,
                        having=result.having,
                        order_by=result.order_by,
                        distinct=result.distinct,
                        limit=result.limit,
                    )
                elif isinstance(result, SQLSubquery) and isinstance(result.query, SQLSelect):
                    inner = result.query
                    if inner.where:
                        new_where = SQLBinaryOp(left=inner.where, operator="AND", right=exists_expr)
                    else:
                        new_where = exists_expr
                    result = SQLSubquery(query=SQLSelect(
                        columns=inner.columns,
                        from_clause=inner.from_clause,
                        where=new_where,
                        joins=inner.joins,
                        group_by=inner.group_by,
                        having=inner.having,
                        order_by=inner.order_by,
                        distinct=inner.distinct,
                        limit=inner.limit,
                    ))

        # Apply RETURN clause if present (skip when multi-source already handled it)
        if not _multi_source_done and node.return_clause:
            # Special case: when source is a list-producing function call
            # (e.g., collapse_intervals, fhirpath_text) with an iteration alias
            # and a return clause, use list_transform to apply per-element
            # instead of flattening into a scalar.
            _did_list_transform = False
            if isinstance(result, SQLFunctionCall) and alias:
                # Only use list_transform when the source actually produces a
                # list/array.  Scalar-returning functions (e.g., intervalEnd)
                # must fall through to the scalar return path below.
                _is_known_list_source = (
                    result.name in ("collapse_intervals", "fhirpath_text", "fhirpath")
                    or _is_list_returning_sql(result)
                )
                if _is_known_list_source:
                    _lt_source = result
                    if result.name == "collapse_intervals":
                        # collapse_intervals returns a JSON array string (VARCHAR),
                        # not a DuckDB list.  Wrap in from_json to convert to
                        # VARCHAR[] so list_transform can iterate.
                        _lt_source = SQLFunctionCall(
                            name="from_json",
                            args=[result, SQLLiteral(value='["VARCHAR"]')],
                        )
                    elif result.name in ("fhirpath_text", "fhirpath"):
                        # fhirpath_text returns a scalar VARCHAR.  For query
                        # iteration over sub-properties (e.g., Encounter.reasonReference D)
                        # we need the full JSON array from fhirpath(), converted to
                        # a DuckDB list so list_transform can iterate per element.
                        _fhir_args = list(result.args)
                        _lt_source = SQLFunctionCall(
                            name="from_json",
                            args=[
                                SQLFunctionCall(name="fhirpath", args=_fhir_args),
                                SQLLiteral(value='["VARCHAR"]'),
                            ],
                        )
                    _lt_param = f"_lt_{alias}"
                    self.context.push_scope()
                    try:
                        self.context.add_alias(alias, ast_expr=SQLIdentifier(name=_lt_param))
                        _lt_body = self.translate(node.return_clause, usage=ExprUsage.SCALAR)
                    finally:
                        self.context.pop_scope()

                    # DuckDB does not support subqueries inside lambda
                    # expressions.  When the body contains subqueries, use
                    # UNNEST + list() aggregation instead of list_transform.
                    # Pattern: (SELECT list(<body>) FROM (SELECT unnest(<source>) AS <param>) _t)
                    if _contains_sql_subquery(_lt_body):
                        _lt_body = _ensure_scalar_body(_lt_body)
                        _inner_unnest = SQLSubquery(query=SQLSelect(
                            columns=[SQLAlias(
                                expr=SQLFunctionCall(name="unnest", args=[_lt_source]),
                                alias=_lt_param,
                            )],
                        ))
                        _unnest_from = SQLAlias(expr=_inner_unnest, alias="_lt_unnest")
                        result = SQLSubquery(query=SQLSelect(
                            columns=[SQLFunctionCall(name="list", args=[_lt_body])],
                            from_clause=_unnest_from,
                        ))
                    else:
                        result = SQLFunctionCall(
                            name="list_transform",
                            args=[_lt_source, SQLLambda(param=_lt_param, body=_lt_body)]
                        )
                    _did_list_transform = True

            if not _did_list_transform:
                return_expr = self.translate(node.return_clause, usage=ExprUsage.SCALAR)
                _return_distinct = getattr(node.return_clause, 'distinct', False)
                # When early_list_transform is active, result is a lambda
                # parameter placeholder (e.g., _lt_DayNumber).  The return
                # expression already references the parameter directly, so
                # we just use return_expr as a scalar body — the wrapping
                # in list_transform / UNNEST happens after this block.
                if _early_list_transform:
                    result = return_expr
                elif isinstance(result, (SQLFunctionCall, SQLLiteral, SQLBinaryOp, SQLUnaryOp, SQLCase, SQLQualifiedIdentifier)):
                    # Scalar expression - can't use as FROM clause, just return the expression
                    result = return_expr
                elif isinstance(result, SQLIdentifier):
                    # Check if this identifier is an outer query alias vs. a CTE/table
                    # Outer aliases can't be used in FROM clauses of scalar subqueries
                    # in DuckDB (SELECT x FROM outer_alias is invalid)
                    if not result.quoted and self.context.is_alias(result.name):
                        # Alias from outer scope — return_expr already references it
                        result = return_expr
                    else:
                        result = SQLSelect(
                            columns=[return_expr],
                            from_clause=result,
                        )
                elif isinstance(result, SQLSelect):
                    # Reuse the existing SQLSelect to preserve FROM clause alias visibility
                    # The alias (e.g., BPExam) in "FROM CTE AS BPExam" must remain visible
                    # to the return expression
                    result = SQLSelect(
                        columns=[return_expr],
                        from_clause=result.from_clause,
                        where=result.where,
                        joins=result.joins,
                        group_by=result.group_by,
                        having=result.having,
                        order_by=result.order_by,
                        limit=result.limit,
                        distinct=result.distinct or _return_distinct,
                    )
                elif isinstance(result, SQLSubquery):
                    result = SQLSelect(
                        columns=[return_expr],
                        from_clause=result,
                        distinct=_return_distinct,
                    )
                else:
                    # Other types - wrap in subquery
                    result = SQLSelect(
                        columns=[return_expr],
                        from_clause=SQLSubquery(result),
                        distinct=_return_distinct,
                    )

        # If early list_transform scope was activated, wrap the result
        # (which is now a per-element scalar) in list_transform or UNNEST.
        if _early_list_transform:
            self.context.pop_scope()  # pop the lambda-parameter scope
            _lt_body = result
            if _contains_sql_subquery(_lt_body):
                _lt_body = _ensure_scalar_body(_lt_body)
                _inner_unnest = SQLSubquery(query=SQLSelect(
                    columns=[SQLAlias(
                        expr=SQLFunctionCall(name="unnest", args=[_early_lt_source]),
                        alias=_early_lt_param,
                    )],
                ))
                _unnest_from = SQLAlias(expr=_inner_unnest, alias="_lt_unnest")
                result = SQLSubquery(query=SQLSelect(
                    columns=[SQLFunctionCall(name="list", args=[_lt_body])],
                    from_clause=_unnest_from,
                ))
            else:
                result = SQLFunctionCall(
                    name="list_transform",
                    args=[_early_lt_source, SQLLambda(param=_early_lt_param, body=_lt_body)]
                )

        # Apply SORT clause if present (CQL §19.29)
        if node.sort and node.sort.by:
            sort_item = node.sort.by[0]
            direction = (getattr(sort_item, 'direction', None) or 'asc').upper()
            sort_order = 'ASC' if direction in ('ASC', 'ASCENDING') else 'DESC'
            nulls = 'NULLS LAST' if sort_order == 'ASC' else 'NULLS FIRST'

            if isinstance(result, SQLSelect):
                # Row-producing query: add ORDER BY
                if sort_item.expression:
                    # If the sort expression is a simple identifier matching an
                    # output column alias, reference the column directly instead
                    # of re-translating (which may resolve let-bindings that
                    # reference out-of-scope query aliases).
                    _sort_ident_name = getattr(sort_item.expression, 'name', None) if isinstance(sort_item.expression, Identifier) else None
                    _col_aliases = {c.alias for c in result.columns if isinstance(c, SQLAlias)} if result.columns else set()
                    sort_by = None
                    if _sort_ident_name and _sort_ident_name in _col_aliases:
                        sort_by = SQLIdentifier(name=_sort_ident_name)
                    elif not _sort_ident_name:
                        # Complex expression (e.g. effective.earliest()) — translate
                        sort_by = self.translate(sort_item.expression, usage=ExprUsage.SCALAR)
                    # else: identifier doesn't match any output column — skip sort
                    # to avoid referencing out-of-scope query aliases
                    if sort_by is not None:
                        result = SQLSelect(
                            columns=result.columns,
                            from_clause=result.from_clause,
                            where=result.where,
                            order_by=[(sort_by, f"{sort_order} {nulls}")],
                        )
                else:
                    # Sort by first/only column
                    if result.columns:
                        col = result.columns[0]
                        if isinstance(col, SQLAlias):
                            sort_col = SQLIdentifier(name=col.alias)
                        else:
                            sort_col = col
                        result = SQLSelect(
                            columns=result.columns,
                            from_clause=result.from_clause,
                            where=result.where,
                            order_by=[(sort_col, f"{sort_order} {nulls}")],
                        )
            elif isinstance(result, SQLArray):
                # Literal array: use DuckDB list_sort directly
                result = SQLFunctionCall(
                    name="list_sort",
                    args=[result, SQLLiteral(value=sort_order), SQLLiteral(value=nulls)],
                )
            # else: non-array, non-SELECT expression — sort not applicable
            # (DQM queries produce VARCHAR results from FHIRPath; sorting is
            #  handled at a different layer for those.)

        # Apply AGGREGATE clause if present (CQL §19.27)
        # aggregate <accumulator> [starting <init>]: <expression>
        # This is a fold/reduce over the list.
        if hasattr(node, 'aggregate') and node.aggregate:
            agg = node.aggregate
            accum_name = agg.identifier   # accumulator variable name (e.g., "Result")
            source_list = result

            # ── Multi-source + aggregate: recursive CTE fold ──────────
            # DuckDB's list_reduce can't handle multi-source aggregates because
            # the lambda only has (acc, elem) params but the body references
            # aliases from ALL sources.  Use a recursive CTE that cross-joins
            # all sources and folds row-by-row.
            if len(_multi_source_info) > 1:
                # Translate the starting value
                starting_sql = None
                if agg.starting is not None:
                    starting_sql = self.translate(agg.starting, usage=ExprUsage.SCALAR)

                # Build cross-join FROM clause for all sources
                _all_from_parts = []
                for idx, (_ms_alias, _ms_from) in enumerate(_multi_source_info):
                    # Extract the array expression for proper column-named unnest
                    if isinstance(_ms_from, SQLFunctionCall) and _ms_from.name == "unnest":
                        _arr_sql = _ms_from.args[0].to_sql()
                    elif isinstance(_ms_from, SQLArray):
                        _arr_sql = _ms_from.to_sql()
                    else:
                        # Scalar or other expression: wrap in single-element array
                        _arr_sql = f"[{_ms_from.to_sql()}]"
                    _all_from_parts.append(f"unnest({_arr_sql}) AS __t{idx}({_ms_alias})")

                _xj_from = " CROSS JOIN ".join(_all_from_parts)
                _distinct_kw = "DISTINCT " if agg.distinct else ""
                _all_aliases = [a for a, _ in _multi_source_info]

                # Translate the aggregate body with proper alias mappings
                self.context.push_scope()
                try:
                    self.context.add_alias(
                        accum_name,
                        ast_expr=SQLQualifiedIdentifier(parts=["__fold", "__acc"]),
                    )
                    for _ms_alias, _ in _multi_source_info:
                        self.context.add_alias(
                            _ms_alias,
                            ast_expr=SQLQualifiedIdentifier(parts=["__xjn", _ms_alias]),
                        )
                    agg_body = self.translate(agg.expression, usage=ExprUsage.SCALAR)
                finally:
                    self.context.pop_scope()

                _body_sql = agg_body.to_sql()
                _start_sql = starting_sql.to_sql() if starting_sql else "NULL"

                # Recursive CTE for multi-source fold: no SQLRecursiveCTE AST node
                # exists yet, so we build the SQL string. The alias bindings above
                # are proper AST nodes (SQLQualifiedIdentifier), ensuring the body
                # expression is translated through the AST pipeline.
                result = SQLRaw(
                    f"(WITH RECURSIVE __xj AS ("
                    f"SELECT {_distinct_kw}{', '.join(_all_aliases)} FROM "
                    f"(SELECT * FROM {_xj_from}) __src"
                    f"), __xjn AS ("
                    f"SELECT ROW_NUMBER() OVER () AS __rn, * FROM __xj"
                    f"), __fold(__acc, __rn) AS ("
                    f"SELECT CAST({_start_sql} AS BIGINT), CAST(0 AS BIGINT) "
                    f"UNION ALL "
                    f"SELECT {_body_sql}, __xjn.__rn "
                    f"FROM __fold JOIN __xjn ON __xjn.__rn = __fold.__rn + 1"
                    f") SELECT __acc FROM __fold ORDER BY __rn DESC LIMIT 1)"
                )
            else:
                # ── Single-source aggregate: list_reduce pattern ──────────
                # Apply distinct/all modifiers
                if agg.distinct:
                    source_list = SQLFunctionCall(name="list_distinct", args=[source_list])

                # Translate the starting value
                starting_sql = None
                if agg.starting is not None:
                    starting_sql = self.translate(agg.starting, usage=ExprUsage.SCALAR)

                # Translate the aggregation expression as a lambda body
                # The body references both the accumulator and the iteration alias
                _agg_lambda_x = f"_agg_x"  # accumulator param
                _agg_lambda_y = f"_agg_y"  # element param

                self.context.push_scope()
                try:
                    self.context.add_alias(accum_name, ast_expr=SQLIdentifier(name=_agg_lambda_x))
                    if alias:
                        self.context.add_alias(alias, ast_expr=SQLIdentifier(name=_agg_lambda_y))
                    agg_body = self.translate(agg.expression, usage=ExprUsage.SCALAR)
                finally:
                    self.context.pop_scope()

                # Build list_reduce call
                if starting_sql is not None:
                    # Prepend starting value so list_reduce uses it as initial accumulator
                    source_with_start = SQLFunctionCall(
                        name="list_prepend",
                        args=[starting_sql, source_list],
                    )
                    result = SQLFunctionCall(
                        name="list_reduce",
                        args=[source_with_start, SQLLambda2(params=[_agg_lambda_x, _agg_lambda_y], body=agg_body)],
                    )
                else:
                    # No starting value — per CQL §19.27, accumulator is initialized to null.
                    # Prepend NULL as initial value for list_reduce.
                    source_with_null = SQLFunctionCall(
                        name="list_prepend",
                        args=[SQLNull(), source_list],
                    )
                    result = SQLFunctionCall(
                        name="list_reduce",
                        args=[source_with_null, SQLLambda2(params=[_agg_lambda_x, _agg_lambda_y], body=agg_body)],
                    )

        # For boolean context, check if result exists
        if usage == ExprUsage.BOOLEAN:
            # Restore resource_alias before returning
            self.context.resource_alias = _saved_resource_alias
            # Check if result is a scalar expression (CASE, function call, etc.)
            # For scalars, use IS NOT NULL instead of array_length
            if isinstance(result, (SQLCase, SQLFunctionCall, SQLLiteral, SQLBinaryOp)):
                return SQLBinaryOp(
                    left=result,
                    operator="IS NOT",
                    right=SQLNull(),
                )
            # For array/list expressions, use array_length > 0
            return SQLBinaryOp(
                left=SQLFunctionCall(name="array_length", args=[result]),
                operator=">",
                right=SQLLiteral(value=0),
            )

        # Restore resource_alias
        self.context.resource_alias = _saved_resource_alias
        return result
