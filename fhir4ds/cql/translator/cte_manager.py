"""
CTE Management mixin for CQLToSQLTranslator.

This module contains methods responsible for creating, wrapping, and
normalizing Common Table Expressions (CTEs) during CQL-to-SQL translation.
The ``CTEManagerMixin`` class is intended to be used as a mixin with
``CQLToSQLTranslator`` and relies on attributes (``self._context``,
``self._retrieve_ctes``, etc.) initialised by the translator's ``__init__``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from ..translator.types import SQLExpression, SQLSelect, SQLJoin, SQLRetrieveCTE
    from ..translator.context import DefinitionMeta



def _flatten_audit_tree(expr: "SQLExpression") -> "SQLExpression":
    """Flatten nested audit_or/audit_and chains into a single flat struct_pack.

    DuckDB SQL macros use textual substitution.  A 7-level nested audit_or chain
    causes each leaf expression to appear 4^6 = 4096 times in the expanded SQL,
    making the DuckDB planner hang.

    This function collects all leaf terms and generates a flat struct_pack:

        struct_pack(
            result   := term1.result OR term2.result OR ...,
            evidence := CASE WHEN term1.result THEN term1.evidence ... END
        )

    Each leaf term appears at most 2-3 times → linear expansion.
    """
    from ..translator.types import SQLFunctionCall, SQLRaw  # noqa: PLC0415

    _OR_OPS = {"audit_or", "audit_or_all"}
    _AND_OP = "audit_and"
    _FLATTENABLE = _OR_OPS | {_AND_OP}

    if not isinstance(expr, SQLFunctionCall) or expr.name not in _FLATTENABLE:
        return expr

    top_op = expr.name

    # Collect all leaf terms by iterating the same-operator chain
    terms: list[SQLExpression] = []
    stack = [expr]
    while stack:
        node = stack.pop()
        if isinstance(node, SQLFunctionCall) and node.name == top_op:
            # Push right first so left is processed first (preserves order)
            stack.append(node.args[1])
            stack.append(node.args[0])
        else:
            terms.append(node)

    if len(terms) <= 2:
        # Nothing to flatten (would be the same as the original 2-arg macro call)
        return expr

    term_sqls = [t.to_sql() for t in terms]

    if top_op in _OR_OPS:
        result_expr = " OR ".join(f"({s}).result" for s in term_sqls)
        if top_op == "audit_or_all":
            # Concat evidence from all branches
            evidence_expr: str = f"COALESCE(({term_sqls[0]}).evidence, [])"
            for s in term_sqls[1:]:
                evidence_expr = f"list_concat({evidence_expr}, COALESCE(({s}).evidence, []))"
        else:
            # True-branch strategy: pick the first true branch's evidence
            when_clauses = " ".join(
                f"WHEN ({s}).result THEN COALESCE(({s}).evidence, [])"
                for s in term_sqls[:-1]
            )
            evidence_expr = (
                f"CASE {when_clauses} ELSE COALESCE(({term_sqls[-1]}).evidence, []) END"
            )
    else:
        # audit_and: ALL must be true; concat all evidence
        result_expr = " AND ".join(f"({s}).result" for s in term_sqls)
        evidence_expr = f"COALESCE(({term_sqls[0]}).evidence, [])"
        for s in term_sqls[1:]:
            evidence_expr = f"list_concat({evidence_expr}, COALESCE(({s}).evidence, []))"

    # SQLRaw is used here intentionally: this is a final-rendering-step helper called
    # only from _flatten_audit_tree() after all AST nodes in `terms` have been
    # serialized into `term_sqls`. Building a struct_pack from already-rendered SQL
    # strings is acceptable at this stage of the pipeline.
    return SQLRaw(f"struct_pack(result := {result_expr}, evidence := {evidence_expr})")


class CTEManagerMixin:
    """Mixin providing CTE management methods for CQLToSQLTranslator."""

    # ------------------------------------------------------------------
    # Small utility helpers
    # ------------------------------------------------------------------

    def _get_deduplicated_retrieve_ctes(self) -> List[SQLRetrieveCTE]:
        """
        Get deduplicated retrieve CTEs.

        Returns:
            List of SQLRetrieveCTE objects with duplicates removed.
        """
        return deduplicate_retrieve_ctes(self._retrieve_ctes)

    @staticmethod
    def _unique_cte_name(name: str, seen_lower: dict) -> str:
        """Return a CTE name unique under case-insensitive comparison.

        DuckDB treats CTE names case-insensitively even when double-quoted.
        If *name* collides (e.g. ``"date"`` vs ``"Date"``), append a numeric
        suffix to the later occurrence.
        """
        key = name.lower()
        if key not in seen_lower:
            seen_lower[key] = name
            return name
        suffix = 1
        while f"{name}_{suffix}".lower() in seen_lower:
            suffix += 1
        unique = f"{name}_{suffix}"
        seen_lower[unique.lower()] = unique
        return unique

    def _is_known_cte(self, cte_name: str, existing_ctes: dict = None) -> bool:
        """Check if a name refers to a registered CTE (retrieve or otherwise)."""
        if existing_ctes and cte_name in existing_ctes:
            return True
        return any(c.name == cte_name for c in self._retrieve_ctes)

    def _rewrite_cte_references(self, expr: Any, name_map: Dict[str, str]) -> Any:
        """Rewrite CTE references in a SQL AST without round-tripping through SQL strings."""
        if expr is None or not name_map:
            return expr

        from ..translator.types import (
            SQLAlias,
            SQLArray,
            SQLAuditStruct,
            SQLBinaryOp,
            SQLCast,
            SQLCase,
            SQLExcept,
            SQLEvidenceItem,
            SQLExists,
            SQLExtract,
            SQLFunctionCall,
            SQLIdentifier,
            SQLInterval,
            SQLIntersect,
            SQLJoin,
            SQLLambda,
            SQLList,
            SQLNamedArg,
            SQLQualifiedIdentifier,
            SQLSelect,
            SQLStructFieldAccess,
            SQLSubquery,
            SQLUnaryOp,
            SQLUnion,
            SQLWindowFunction,
        )

        if isinstance(expr, tuple) and len(expr) == 2:
            return (self._rewrite_cte_references(expr[0], name_map), expr[1])

        if isinstance(expr, SQLIdentifier):
            if expr.quoted and expr.name in name_map:
                return SQLIdentifier(name=name_map[expr.name], quoted=True)
            return expr

        if isinstance(expr, SQLQualifiedIdentifier):
            if not expr.parts:
                return expr
            first_part = expr.parts[0]
            normalized_first = (
                first_part[1:-1]
                if isinstance(first_part, str) and first_part.startswith('"') and first_part.endswith('"')
                else first_part
            )
            replacement = name_map.get(normalized_first)
            if replacement is None:
                return expr
            rewritten_first = (
                f'"{replacement}"'
                if isinstance(first_part, str) and first_part.startswith('"') and first_part.endswith('"')
                else replacement
            )
            return SQLQualifiedIdentifier(parts=[rewritten_first, *expr.parts[1:]])

        if isinstance(expr, SQLFunctionCall):
            return SQLFunctionCall(
                name=expr.name,
                args=[self._rewrite_cte_references(arg, name_map) for arg in expr.args],
                distinct=expr.distinct,
                order_by=[
                    (self._rewrite_cte_references(order_expr, name_map), direction)
                    for order_expr, direction in expr.order_by
                ] if expr.order_by else None,
            )

        if isinstance(expr, SQLBinaryOp):
            return SQLBinaryOp(
                operator=expr.operator,
                left=self._rewrite_cte_references(expr.left, name_map),
                right=self._rewrite_cte_references(expr.right, name_map),
            )

        if isinstance(expr, SQLUnaryOp):
            return SQLUnaryOp(
                operator=expr.operator,
                operand=self._rewrite_cte_references(expr.operand, name_map),
                prefix=expr.prefix,
            )

        if isinstance(expr, SQLCase):
            return SQLCase(
                when_clauses=[
                    (
                        self._rewrite_cte_references(condition, name_map),
                        self._rewrite_cte_references(result, name_map),
                    )
                    for condition, result in expr.when_clauses
                ],
                else_clause=self._rewrite_cte_references(expr.else_clause, name_map)
                if expr.else_clause else None,
                operand=self._rewrite_cte_references(expr.operand, name_map)
                if expr.operand else None,
            )

        if isinstance(expr, SQLArray):
            return SQLArray(
                elements=[self._rewrite_cte_references(elem, name_map) for elem in expr.elements]
            )

        if isinstance(expr, SQLList):
            return SQLList(
                items=[self._rewrite_cte_references(item, name_map) for item in expr.items]
            )

        if isinstance(expr, SQLLambda):
            return SQLLambda(
                param=expr.param,
                body=self._rewrite_cte_references(expr.body, name_map),
            )

        if isinstance(expr, SQLAlias):
            return SQLAlias(
                expr=self._rewrite_cte_references(expr.expr, name_map),
                alias=expr.alias,
                implicit_alias=expr.implicit_alias,
            )

        if isinstance(expr, SQLInterval):
            return SQLInterval(
                low=self._rewrite_cte_references(expr.low, name_map) if expr.low else None,
                high=self._rewrite_cte_references(expr.high, name_map) if expr.high else None,
                low_closed=expr.low_closed,
                high_closed=expr.high_closed,
            )

        if isinstance(expr, SQLCast):
            return SQLCast(
                expression=self._rewrite_cte_references(expr.expression, name_map),
                target_type=expr.target_type,
                try_cast=expr.try_cast,
            )

        if isinstance(expr, SQLJoin):
            return SQLJoin(
                join_type=expr.join_type,
                table=self._rewrite_cte_references(expr.table, name_map),
                alias=expr.alias,
                on_condition=self._rewrite_cte_references(expr.on_condition, name_map)
                if expr.on_condition else None,
            )

        if isinstance(expr, SQLSelect):
            return SQLSelect(
                columns=[
                    self._rewrite_cte_references(col, name_map)
                    for col in (expr.columns or [])
                ],
                from_clause=self._rewrite_cte_references(expr.from_clause, name_map)
                if expr.from_clause else None,
                joins=[
                    self._rewrite_cte_references(join, name_map)
                    for join in (expr.joins or [])
                ],
                where=self._rewrite_cte_references(expr.where, name_map)
                if expr.where else None,
                group_by=[
                    self._rewrite_cte_references(group_expr, name_map)
                    for group_expr in expr.group_by
                ] if expr.group_by else None,
                having=self._rewrite_cte_references(expr.having, name_map)
                if expr.having else None,
                order_by=[
                    (self._rewrite_cte_references(order_expr, name_map), direction)
                    for order_expr, direction in expr.order_by
                ] if expr.order_by else None,
                limit=expr.limit,
                distinct=expr.distinct,
            )

        if isinstance(expr, SQLSubquery):
            return SQLSubquery(
                query=self._rewrite_cte_references(expr.query, name_map),
            )

        if isinstance(expr, SQLExists):
            return SQLExists(
                subquery=self._rewrite_cte_references(expr.subquery, name_map),
            )

        if isinstance(expr, SQLUnion):
            return SQLUnion(
                operands=[self._rewrite_cte_references(op, name_map) for op in expr.operands],
                distinct=expr.distinct,
            )

        if isinstance(expr, SQLIntersect):
            return SQLIntersect(
                operands=[self._rewrite_cte_references(op, name_map) for op in expr.operands],
            )

        if isinstance(expr, SQLExcept):
            return SQLExcept(
                operands=[self._rewrite_cte_references(op, name_map) for op in expr.operands],
            )

        if isinstance(expr, SQLExtract):
            return SQLExtract(
                extract_field=expr.extract_field,
                source=self._rewrite_cte_references(expr.source, name_map)
                if expr.source else None,
            )

        if isinstance(expr, SQLNamedArg):
            return SQLNamedArg(
                name=expr.name,
                value=self._rewrite_cte_references(expr.value, name_map)
                if expr.value else None,
            )

        if isinstance(expr, SQLStructFieldAccess):
            return SQLStructFieldAccess(
                expr=self._rewrite_cte_references(expr.expr, name_map),
                field_name=expr.field_name,
            )

        if isinstance(expr, SQLWindowFunction):
            return SQLWindowFunction(
                function=expr.function,
                function_args=[
                    self._rewrite_cte_references(arg, name_map)
                    for arg in expr.function_args
                ],
                partition_by=[
                    self._rewrite_cte_references(partition_expr, name_map)
                    for partition_expr in expr.partition_by
                ],
                order_by=[
                    (self._rewrite_cte_references(order_expr, name_map), direction)
                    for order_expr, direction in expr.order_by
                ],
                frame_clause=expr.frame_clause,
            )

        if isinstance(expr, SQLEvidenceItem):
            return SQLEvidenceItem(
                target=self._rewrite_cte_references(expr.target, name_map),
                attribute=self._rewrite_cte_references(expr.attribute, name_map),
                value=self._rewrite_cte_references(expr.value, name_map),
                operator_str=expr.operator_str,
                threshold=self._rewrite_cte_references(expr.threshold, name_map),
                trace=list(expr.trace),
            )

        if isinstance(expr, SQLAuditStruct):
            return SQLAuditStruct(
                result_expr=self._rewrite_cte_references(expr.result_expr, name_map),
                evidence_expr=self._rewrite_cte_references(expr.evidence_expr, name_map),
            )

        return expr

    # ------------------------------------------------------------------
    # Core CTE wrapping
    # ------------------------------------------------------------------

    def _wrap_definition_cte(
        self,
        name: str,
        sql_ast: SQLExpression,
        meta: "DefinitionMeta",
    ) -> "SQLSelect":
        """
        Wrap a definition's SQL AST into a patient-scoped CTE based on its row shape.

        This is the core CTE wrapping method that uses metadata to mechanically
        determine the wrapping strategy - NO string inspection.

        Args:
            name: The definition name.
            sql_ast: The translated SQL expression AST.
            meta: The DefinitionMeta containing shape, cql_type, etc.

        Returns:
            SQLSelect AST node representing the CTE body.
        """
        from ..translator.context import RowShape
        from ..translator.types import (
            SQLSelect, SQLAlias, SQLIdentifier, SQLQualifiedIdentifier,
            SQLBinaryOp, SQLJoin, SQLUnion, SQLIntersect, SQLExcept,
            SQLStructFieldAccess, SQLSubquery
        )

        # Generate JOINs for any CTE references tracked during translation
        joins = self._generate_joins_for_definition(name)

        if meta.shape == RowShape.PATIENT_SCALAR:
            # Scalar values need to be wrapped with patient_id from _patients
            if meta.cql_type == "Boolean":
                from ..translator.types import SQLFunctionCall, SQLRaw
                # audit_and/or/not/leaf/or_all are already-complete audit struct trees —
                # skip the pre-compute CTE and use them directly (they carry their own
                # result + evidence semantics).
                # audit_comparison is NOT included here: it needs the pre-compute CTE so
                # that downstream compound definitions can use EXISTS(SELECT 1 FROM precte)
                # to correctly filter patients.  Without the pre-compute CTE, the audit
                # CTE returns ALL patients and compound definitions see everyone as True.
                _audit_fn_names = {"audit_and", "audit_or", "audit_or_all", "audit_not", "audit_leaf"}
                # audit_comparison also returns a struct, so its result must be extracted
                # when it appears in a WHERE clause (e.g. in the pre-compute CTE).
                _audit_struct_names = _audit_fn_names | {"audit_comparison"}
                should_flatten_audit_expr = False

                if self._context.audit_mode and self._context.audit_expressions:
                    # Audit mode: Use a two-CTE approach.
                    #
                    # Problem: complex correlated EXISTS subqueries inside audit_leaf(EXISTS(...))
                    # cause DuckDB's query binder to hang when the SQL contains many CTEs.
                    # DuckDB can plan WHERE EXISTS(...) efficiently as a semi-join, but the
                    # same expression inside a scalar projection (audit_leaf column) triggers
                    # exponential join-ordering work.
                    #
                    # Fix: Pre-compute which patients satisfy the condition in a non-audit CTE
                    # (using the fast WHERE EXISTS semi-join path), then have the audit CTE do
                    # a simple lookup: audit_leaf(EXISTS(SELECT 1 FROM precompute WHERE ...)).
                    #
                    # If the expression is already an audit_and/audit_or tree (it carries its own
                    # struct semantics), skip the pre-compute step and use it directly.
                    audit_expr = self._correlate_exists_ast(sql_ast, outer_alias="p")
                    is_already_audit = (
                        isinstance(audit_expr, SQLFunctionCall)
                        and audit_expr.name in _audit_fn_names
                    )

                    if not is_already_audit and hasattr(self, '_pending_precte'):
                        # Build the non-audit WHERE clause (fast semi-join)
                        where_expr = self._correlate_exists_ast(sql_ast, outer_alias="p")
                        is_comparison = (
                            isinstance(where_expr, SQLFunctionCall)
                            and where_expr.name == "audit_comparison"
                        )
                        if (isinstance(where_expr, SQLFunctionCall)
                                and where_expr.name in _audit_struct_names):
                            from ..translator.expressions._query import _demote_audit_struct_to_bool
                            where_expr = _demote_audit_struct_to_bool(where_expr)

                        # Generate a unique pre-compute CTE name
                        # TODO: Replace with AST node substitution
                        safe_name = name.replace('"', '').replace(' ', '_').replace('.', '_')[:60]
                        precte_name = f'__pre_{safe_name}'
                        from ..translator.types import CTEDefinition

                        if is_comparison:
                            # Two-column pre-compute: evaluate audit_comparison() once via a
                            # derived table so the full struct (including comparison evidence)
                            # is retained. The outer SELECT filters to patients who satisfy
                            # the comparison and also exposes _cmp_result for evidence retrieval.
                            cmp_expr = self._correlate_exists_ast(sql_ast, outer_alias="p")
                            inner_select = SQLSelect(
                                columns=[
                                    SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                                    SQLAlias(expr=cmp_expr, alias="_cmp_result"),
                                ],
                                from_clause=SQLAlias(
                                    expr=SQLIdentifier(name="_patients"),
                                    alias="p",
                                ),
                                joins=list(joins) if joins else None,
                            )
                            precte_query = SQLSelect(
                                columns=[
                                    SQLQualifiedIdentifier(parts=["_inner", "patient_id"]),
                                    SQLQualifiedIdentifier(parts=["_inner", "_cmp_result"]),
                                ],
                                from_clause=SQLAlias(
                                    expr=SQLSubquery(query=inner_select),
                                    alias="_inner",
                                ),
                                where=SQLStructFieldAccess(
                                    expr=SQLQualifiedIdentifier(parts=["_inner", "_cmp_result"]),
                                    field_name="result",
                                ),
                            )
                        else:
                            precte_query = SQLSelect(
                                columns=[SQLQualifiedIdentifier(parts=["p", "patient_id"])],
                                from_clause=SQLAlias(
                                    expr=SQLIdentifier(name="_patients"),
                                    alias="p",
                                ),
                                where=where_expr,
                                joins=list(joins) if joins else None,
                            )
                        precte_query = self._rewrite_cte_references(
                            precte_query,
                            getattr(self, "_precte_name_map", {}),
                        )

                        self._pending_precte.append(
                            CTEDefinition(
                                name=f'"{precte_name}"',
                                query=precte_query,
                            )
                        )

                        # Record mapping so downstream compound pre-compute CTEs can
                        # reference this one instead of the audit-mode version.
                        if not hasattr(self, '_precte_name_map'):
                            self._precte_name_map: Dict[str, str] = {}
                        self._precte_name_map[name.strip('"')] = precte_name

                        # Track which pre-compute CTEs are comparison-based (two-column
                        # with _cmp_result) vs one-column (patient_id only).
                        if not hasattr(self, '_comparison_prectes'):
                            self._comparison_prectes: set = set()
                        if is_comparison:
                            self._comparison_prectes.add(precte_name)

                        if is_comparison:
                            # Main audit CTE: retrieve the full comparison struct from the
                            # two-column pre-compute CTE.  Patients who do NOT satisfy the
                            # comparison are absent from the pre-compute CTE; COALESCE
                            # returns an absent sentinel via audit_leaf(false) for them.
                            audit_expr = SQLRaw(
                                f'COALESCE(\n'
                                f'  (SELECT __pre._cmp_result\n'
                                f'   FROM "{precte_name}" AS __pre\n'
                                f'   WHERE __pre.patient_id = p.patient_id),\n'
                                f'  audit_leaf(false)\n'
                                f')'
                            )
                        else:
                            # Main audit CTE: simple EXISTS lookup on the pre-compute result
                            lookup = SQLRaw(
                                f'EXISTS (SELECT 1 FROM "{precte_name}" AS __pre'
                                f' WHERE __pre.patient_id = p.patient_id)'
                            )
                            audit_expr = SQLFunctionCall(name="audit_leaf", args=[lookup])
                    else:
                        if not is_already_audit:
                            audit_expr = SQLFunctionCall(name="audit_leaf", args=[audit_expr])
                        else:
                            # Compound boolean definitions (is_already_audit=True) that skipped
                            # the pre-compute path still need a pre-compute CTE so that
                            # downstream non-boolean CTEs referencing them via EXISTS can filter
                            # to True-only patients (the audit CTE returns ALL patients).
                            if hasattr(self, '_pending_precte'):
                                from ..translator.expressions._query import _demote_audit_struct_to_bool
                                from ..translator.types import CTEDefinition
                                # Demote BEFORE flattening — audit_expr is still a proper AST
                                demoted_where = _demote_audit_struct_to_bool(audit_expr)
                                safe_name = name.replace('"', '').replace(' ', '_').replace('.', '_')[:60]
                                precte_name = f'__pre_{safe_name}'
                                precte_select = SQLSelect(
                                    columns=[SQLQualifiedIdentifier(parts=["p", "patient_id"])],
                                    from_clause=SQLAlias(
                                        expr=SQLIdentifier(name="_patients"),
                                        alias="p",
                                    ),
                                    where=demoted_where,
                                    joins=list(joins) if joins else None,
                                )
                                precte_select = self._rewrite_cte_references(
                                    precte_select,
                                    getattr(self, "_precte_name_map", {}),
                                )
                                self._pending_precte.append(
                                    CTEDefinition(
                                        name=f'"{precte_name}"',
                                        query=precte_select,
                                    )
                                )
                                if not hasattr(self, '_precte_name_map'):
                                    self._precte_name_map: Dict[str, str] = {}
                                self._precte_name_map[name.strip('"')] = precte_name

                            should_flatten_audit_expr = True

                    precte_map = getattr(self, "_precte_name_map", {})
                    if precte_map:
                        audit_expr = self._rewrite_cte_references(audit_expr, precte_map)
                    if should_flatten_audit_expr:
                        # Flatten deeply nested audit_or/audit_and trees to avoid
                        # exponential DuckDB macro expansion (4^N per level).
                        audit_expr = _flatten_audit_tree(audit_expr)

                    evidence_parts, evidence_joins = self._collect_audit_evidence_exprs(name, sql_ast)
                    if evidence_parts:
                        # Store the resource CTE names on meta so that compound definitions
                        # (e.g. "Numerator" referencing "Has Systolic Blood Pressure Less
                        # Than 140") can collect evidence transitively via Strategy 3.
                        # The pre-compute substitution below replaces CTE references with
                        # fast filter CTEs that have no _audit_result, so evidence would
                        # otherwise be lost in compound boolean expressions.
                        subquery_ctes = [
                            s[len('<SUBQUERY:'):-1]
                            for s in evidence_parts
                            if s.startswith('<SUBQUERY:')
                        ]
                        if subquery_ctes:
                            meta.source_resource_ctes = sorted(
                                set(getattr(meta, 'source_resource_ctes', []) + subquery_ctes)
                            )

                    # Inject evidence AFTER substitution so Strategy 4's references to
                    # original audit CTEs (_audit_result) are preserved.
                    if evidence_parts:
                        audit_expr = self._inject_audit_evidence(audit_expr, evidence_parts, definition_name=name)

                    # Merge evidence JOINs with existing definition JOINs
                    all_joins = list(joins) if joins else []
                    all_joins.extend(evidence_joins)
                    return SQLSelect(
                        columns=[
                            SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                            SQLAlias(expr=audit_expr, alias="_audit_result"),
                        ],
                        from_clause=SQLAlias(
                            expr=SQLIdentifier(name="_patients"),
                            alias="p",
                        ),
                        joins=all_joins if all_joins else None,
                    )

                # Normal mode: Boolean: SELECT p.patient_id FROM _patients AS p WHERE <expr>
                # Process the WHERE expression to convert subqueries to EXISTS
                where_expr = self._correlate_exists_ast(sql_ast, outer_alias="p")
                # Audit macros and audit_comparison return structs — extract .result for WHERE clause
                from ..translator.expressions._query import _demote_audit_struct_to_bool
                where_expr = _demote_audit_struct_to_bool(where_expr)
                return SQLSelect(
                    columns=[SQLQualifiedIdentifier(parts=["p", "patient_id"])],
                    from_clause=SQLAlias(
                        expr=SQLIdentifier(name="_patients"),
                        alias="p",
                    ),
                    where=where_expr,
                    joins=joins if joins else None,
                )
            else:
                # Non-boolean scalar: SELECT p.patient_id, <expr> AS value FROM _patients AS p
                # In audit mode, compute which RESOURCE_ROWS CTEs this scalar ultimately
                # depends on so comparison-based boolean definitions can collect evidence.
                if self._context.audit_mode:
                    src = self._resolve_source_resource_ctes(sql_ast)
                    if src:
                        meta.source_resource_ctes = sorted(src)
                # Check if we can use LEFT JOIN instead of scalar subquery
                if self._can_use_join_for_scalar(meta, sql_ast, joins):
                    # Use JOIN-based column reference instead of scalar subquery
                    value_expr = self._get_join_column_for_scalar(meta, sql_ast)
                    return SQLSelect(
                        columns=[
                            SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                            SQLAlias(expr=value_expr, alias=meta.value_column),
                        ],
                        from_clause=SQLAlias(
                            expr=SQLIdentifier(name="_patients"),
                            alias="p",
                        ),
                        joins=joins,
                    )
                else:
                    # Fallback to scalar subquery for complex cases
                    # Normalize bare SELECT * FROM "CTE" into a correlated
                    # single-column subquery so DuckDB gets exactly one column.
                    scalar_expr = sql_ast
                    inner_sel = sql_ast
                    if isinstance(inner_sel, SQLSubquery) and isinstance(inner_sel.query, SQLSelect):
                        inner_sel = inner_sel.query
                    # Match bare CTE references: no columns, or SELECT *
                    _is_star = (
                        inner_sel.columns
                        and len(inner_sel.columns) == 1
                        and isinstance(inner_sel.columns[0], SQLIdentifier)
                        and inner_sel.columns[0].name == "*"
                    ) if isinstance(inner_sel, SQLSelect) else False
                    if (isinstance(inner_sel, SQLSelect)
                            and (not inner_sel.columns or _is_star)
                            and inner_sel.from_clause):
                        from_ref = inner_sel.from_clause
                        if isinstance(from_ref, SQLAlias):
                            from_ref = from_ref.expr
                        if isinstance(from_ref, SQLIdentifier) and from_ref.quoted:
                            target_meta = self._context.definition_meta.get(from_ref.name)
                            if target_meta:
                                val_col = target_meta.value_column or "value"
                                alias_str = inner_sel.from_clause.alias if isinstance(inner_sel.from_clause, SQLAlias) else "sub"
                                scalar_expr = SQLSubquery(query=SQLSelect(
                                    columns=[SQLIdentifier(name=val_col)],
                                    from_clause=inner_sel.from_clause,
                                    joins=inner_sel.joins,
                                    where=SQLBinaryOp(
                                        operator="=",
                                        left=SQLQualifiedIdentifier(parts=[alias_str, "patient_id"]),
                                        right=SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                                    ) if not inner_sel.where else SQLBinaryOp(
                                        operator="AND",
                                        left=inner_sel.where,
                                        right=SQLBinaryOp(
                                            operator="=",
                                            left=SQLQualifiedIdentifier(parts=[alias_str, "patient_id"]),
                                            right=SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                                        ),
                                    ),
                                    order_by=inner_sel.order_by,
                                    limit=inner_sel.limit if inner_sel.limit else 1,
                                ))
                    # When the translated expression is a multi-column SELECT
                    # (e.g., SELECT alias.patient_id, CAST(...) AS resource),
                    # strip patient_id to produce a valid single-column scalar subquery.
                    if isinstance(scalar_expr, (SQLSubquery, SQLSelect)):
                        _inner = scalar_expr.query if isinstance(scalar_expr, SQLSubquery) else scalar_expr
                        if (isinstance(_inner, SQLSelect)
                                and _inner.columns
                                and len(_inner.columns) >= 2):
                            non_pid_cols = []
                            for col in _inner.columns:
                                is_pid = False
                                col_expr = col.expr if isinstance(col, SQLAlias) else col
                                if isinstance(col_expr, SQLQualifiedIdentifier) and col_expr.parts[-1] == "patient_id":
                                    is_pid = True
                                elif isinstance(col_expr, SQLIdentifier) and col_expr.name == "patient_id":
                                    is_pid = True
                                if not is_pid:
                                    non_pid_cols.append(col)
                            if len(non_pid_cols) == 1:
                                # Add patient_id correlation to the outer
                                # _patients AS p table so the scalar subquery
                                # only returns rows for the current patient.
                                _corr_where = _inner.where
                                _corr_alias = None
                                for col in _inner.columns:
                                    col_expr = col.expr if isinstance(col, SQLAlias) else col
                                    if isinstance(col_expr, SQLQualifiedIdentifier) and col_expr.parts[-1] == "patient_id":
                                        _corr_alias = col_expr.parts[0]
                                        break
                                if not _corr_alias and isinstance(_inner.from_clause, SQLAlias):
                                    _corr_alias = _inner.from_clause.alias
                                if _corr_alias:
                                    _pid_corr = SQLBinaryOp(
                                        operator="=",
                                        left=SQLQualifiedIdentifier(parts=[_corr_alias, "patient_id"]),
                                        right=SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                                    )
                                    _corr_where = (
                                        SQLBinaryOp(left=_corr_where, operator="AND", right=_pid_corr)
                                        if _corr_where else _pid_corr
                                    )
                                trimmed_sel = SQLSelect(
                                    columns=non_pid_cols,
                                    from_clause=_inner.from_clause,
                                    joins=_inner.joins,
                                    where=_corr_where,
                                    order_by=_inner.order_by,
                                    limit=_inner.limit,
                                    group_by=_inner.group_by,
                                    distinct=_inner.distinct,
                                )
                                scalar_expr = SQLSubquery(query=trimmed_sel)
                    return SQLSelect(
                        columns=[
                            SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                            SQLAlias(expr=scalar_expr, alias=meta.value_column),
                        ],
                        from_clause=SQLAlias(
                            expr=SQLIdentifier(name="_patients"),
                            alias="p",
                        ),
                        joins=joins if joins else None,
                    )
        elif meta.shape == RowShape.PATIENT_MULTI_VALUE:
            # Unwrap SQLSubquery → SQLSelect for structural inspection
            if isinstance(sql_ast, SQLSubquery) and isinstance(sql_ast.query, SQLSelect):
                sql_ast = sql_ast.query

            # Fix stale "p" alias references (same issue as RESOURCE_ROWS).
            from ..translator.ast_utils import replace_qualified_alias as _rqa_mv
            if isinstance(sql_ast, SQLSelect):
                _from_alias = None
                if isinstance(sql_ast.from_clause, SQLAlias):
                    _from_alias = sql_ast.from_clause.alias
                elif isinstance(sql_ast.from_clause, SQLIdentifier) and sql_ast.from_clause.quoted:
                    _from_alias = sql_ast.from_clause.name
                if _from_alias and _from_alias != "p":
                    sql_ast = _rqa_mv(sql_ast, "p", _from_alias)
            elif isinstance(sql_ast, (SQLUnion, SQLIntersect, SQLExcept)):
                _fixed_ops = []
                for _op in sql_ast.operands:
                    _inner = _op.query if isinstance(_op, SQLSubquery) and isinstance(_op.query, SQLSelect) else _op
                    _op_alias = None
                    if isinstance(_inner, SQLSelect):
                        if isinstance(_inner.from_clause, SQLAlias):
                            _op_alias = _inner.from_clause.alias
                        elif isinstance(_inner.from_clause, SQLIdentifier) and _inner.from_clause.quoted:
                            _op_alias = _inner.from_clause.name
                    if _op_alias and _op_alias != "p":
                        _fixed_ops.append(_rqa_mv(_op, "p", _op_alias))
                    else:
                        _fixed_ops.append(_op)
                _cls = type(sql_ast)
                if _cls == SQLUnion:
                    sql_ast = _cls(operands=_fixed_ops, distinct=sql_ast.distinct)
                else:
                    sql_ast = _cls(operands=_fixed_ops)

            # PATIENT_MULTI_VALUE: Query with RETURN clause projecting scalars
            # The AST has a FROM clause referencing a CTE that has patient_id
            # We need to ensure patient_id is in the SELECT list
            if isinstance(sql_ast, (SQLIntersect, SQLExcept)):
                # Set operations on projected values (e.g., return date from ... INTERSECT ...)
                # Each operand needs patient_id added and value column aliased
                new_operands = []
                for op in sql_ast.operands:
                    inner = op.query if isinstance(op, SQLSubquery) else op
                    if isinstance(inner, SQLSelect):
                        has_pid = self._select_has_patient_id(inner)
                        if not has_pid:
                            src_alias = self._get_source_alias(inner)
                            pid_col = SQLQualifiedIdentifier(parts=[src_alias, "patient_id"]) if src_alias else SQLIdentifier(name="patient_id")
                            val_cols = []
                            for col in inner.columns:
                                if isinstance(col, tuple):
                                    val_cols.append(col)
                                else:
                                    val_cols.append(SQLAlias(expr=col, alias="value"))
                            new_inner = SQLSelect(
                                columns=[pid_col] + val_cols,
                                from_clause=inner.from_clause,
                                where=inner.where,
                                joins=inner.joins,
                                group_by=inner.group_by,
                                having=inner.having,
                                order_by=inner.order_by,
                                distinct=inner.distinct,
                                limit=inner.limit,
                            )
                        else:
                            new_inner = inner
                        new_operands.append(SQLSubquery(query=new_inner) if isinstance(op, SQLSubquery) else new_inner)
                    else:
                        new_operands.append(op)
                if isinstance(sql_ast, SQLIntersect):
                    return SQLIntersect(operands=new_operands)
                else:
                    return SQLExcept(operands=new_operands)
            elif isinstance(sql_ast, SQLUnion):
                # UNION of multi-value definitions: normalize each operand to
                # (patient_id, value) so the actual projected values are preserved.
                # IMPORTANT: Must produce explicit columns, NOT "SELECT *", because
                # SQLUnion.to_sql() normalizes "SELECT *" to "patient_id, resource"
                # which is wrong for PATIENT_MULTI_VALUE definitions.
                new_operands = []
                for op in sql_ast.operands:
                    inner = op.query if isinstance(op, SQLSubquery) and isinstance(op.query, SQLSelect) else op
                    if isinstance(inner, SQLSelect):
                        cols = inner.columns or []
                        is_star = (len(cols) == 1 and isinstance(cols[0], SQLIdentifier) and cols[0].name == "*")
                        has_pid = self._select_has_patient_id(inner)
                        if is_star:
                            # Replace SELECT * with SELECT patient_id, value
                            # The source CTE may use "resource" instead of "value"
                            # — detect via definition_meta and alias if needed.
                            val_col_name = "value"
                            from_ref = inner.from_clause
                            if isinstance(from_ref, SQLAlias):
                                from_ref = from_ref.expr
                            if isinstance(from_ref, SQLIdentifier) and from_ref.quoted:
                                src_meta = self._context.definition_meta.get(from_ref.name)
                                if src_meta and src_meta.has_resource:
                                    val_col_name = "resource"
                            val_col: SQLExpression
                            if val_col_name == "resource":
                                val_col = SQLAlias(expr=SQLIdentifier(name="resource"), alias="value")
                            else:
                                val_col = SQLIdentifier(name="value")
                            new_inner = SQLSelect(
                                columns=[SQLIdentifier(name="patient_id"), val_col],
                                from_clause=inner.from_clause,
                                where=inner.where,
                                joins=inner.joins,
                                group_by=inner.group_by,
                                having=inner.having,
                                order_by=inner.order_by,
                                distinct=inner.distinct,
                                limit=inner.limit,
                            )
                        elif not has_pid:
                            src_alias = self._get_source_alias(inner)
                            pid_col = SQLQualifiedIdentifier(parts=[src_alias, "patient_id"]) if src_alias else SQLIdentifier(name="patient_id")
                            val_cols = []
                            for col in inner.columns:
                                if isinstance(col, tuple):
                                    val_cols.append(col)
                                else:
                                    val_cols.append(SQLAlias(expr=col, alias="value"))
                            new_inner = SQLSelect(
                                columns=[pid_col] + val_cols,
                                from_clause=inner.from_clause,
                                where=inner.where,
                                joins=inner.joins,
                                group_by=inner.group_by,
                                having=inner.having,
                                order_by=inner.order_by,
                                distinct=inner.distinct,
                                limit=inner.limit,
                            )
                        else:
                            new_inner = inner
                        new_operands.append(SQLSubquery(query=new_inner) if isinstance(op, SQLSubquery) else new_inner)
                    else:
                        new_operands.append(op)
                return SQLUnion(operands=new_operands, distinct=sql_ast.distinct)
            elif isinstance(sql_ast, SQLSelect):
                # Check if patient_id is already in columns
                has_patient_id = self._select_has_patient_id(sql_ast)
                if has_patient_id:
                    # Already has patient_id, just add JOINs if needed
                    if joins:
                        # Fix JOIN conditions: replace "p" alias with actual FROM alias
                        from ..translator.types import SQLAlias as SQLAlias2, SQLQualifiedIdentifier as SQLQI2
                        from_alias = None
                        if isinstance(sql_ast.from_clause, SQLAlias2):
                            from_alias = sql_ast.from_clause.alias
                        if from_alias and from_alias != "p":
                            fixed_joins = []
                            for j in joins:
                                on_cond = self._replace_patient_alias_in_condition(
                                    j.on_condition, "p", from_alias
                                )
                                fixed_joins.append(SQLJoin(
                                    join_type=j.join_type,
                                    table=j.table,
                                    alias=j.alias,
                                    on_condition=on_cond,
                                ))
                            joins = fixed_joins
                        existing = list(sql_ast.joins) if sql_ast.joins else []
                        return SQLSelect(
                            columns=sql_ast.columns,
                            from_clause=sql_ast.from_clause,
                            joins=existing + joins,
                            where=sql_ast.where,
                            group_by=sql_ast.group_by,
                            having=sql_ast.having,
                            order_by=sql_ast.order_by,
                            distinct=sql_ast.distinct,
                            limit=sql_ast.limit,
                        )
                    return sql_ast
                else:
                    # Need to add patient_id to the SELECT
                    # The patient_id should come from the source CTE (FROM clause)
                    # We need to determine the alias of the source table
                    source_alias = self._get_source_alias(sql_ast)
                    patient_id_col = SQLQualifiedIdentifier(parts=[source_alias, "patient_id"]) if source_alias else SQLIdentifier(name="patient_id")

                    # Alias the value column(s) as "value" for downstream references
                    value_columns = []
                    for col in sql_ast.columns:
                        if isinstance(col, tuple):
                            value_columns.append(col)
                        else:
                            value_columns.append((col, "value"))
                    new_columns = [patient_id_col] + value_columns
                    if joins:
                        # Fix JOIN conditions: replace "p" alias with actual FROM alias
                        from ..translator.types import SQLAlias as SQLAlias3, SQLQualifiedIdentifier as SQLQI3
                        from_alias = None
                        if isinstance(sql_ast.from_clause, SQLAlias3):
                            from_alias = sql_ast.from_clause.alias
                        if from_alias and from_alias != "p":
                            fixed_joins = []
                            for j in joins:
                                on_cond = self._replace_patient_alias_in_condition(
                                    j.on_condition, "p", from_alias
                                )
                                fixed_joins.append(SQLJoin(
                                    join_type=j.join_type,
                                    table=j.table,
                                    alias=j.alias,
                                    on_condition=on_cond,
                                ))
                            joins = fixed_joins
                        existing = list(sql_ast.joins) if sql_ast.joins else []
                        return SQLSelect(
                            columns=new_columns,
                            from_clause=sql_ast.from_clause,
                            joins=existing + joins,
                            where=sql_ast.where,
                            group_by=sql_ast.group_by,
                            having=sql_ast.having,
                            order_by=sql_ast.order_by,
                            distinct=sql_ast.distinct,
                            limit=sql_ast.limit,
                        )
                    return SQLSelect(
                        columns=new_columns,
                        from_clause=sql_ast.from_clause,
                        where=sql_ast.where,
                        group_by=sql_ast.group_by,
                        having=sql_ast.having,
                        order_by=sql_ast.order_by,
                        distinct=sql_ast.distinct,
                        limit=sql_ast.limit,
                    )
            else:
                # Non-SELECT/UNION expression (e.g., SQLFunctionCall like jsonConcat).
                # Wrap with patient_id from _patients and alias the expression as "value".
                return SQLSelect(
                    columns=[
                        SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                        SQLAlias(expr=sql_ast, alias="value"),
                    ],
                    from_clause=SQLAlias(
                        expr=SQLIdentifier(name="_patients"),
                        alias="p",
                    ),
                    joins=joins if joins else None,
                )
        elif meta.shape == RowShape.RESOURCE_ROWS:
            # Unwrap SQLSubquery → SQLSelect for structural inspection
            if isinstance(sql_ast, SQLSubquery) and isinstance(sql_ast.query, SQLSelect):
                sql_ast = sql_ast.query
            # RESOURCE_ROWS: AST already has patient_id from retrieve CTEs
            # Just ensure it's a proper SELECT and add any needed JOINs
            if isinstance(sql_ast, SQLSelect):
                has_pid = self._select_has_patient_id(sql_ast)
                if not has_pid:
                    # Status filter may have stripped patient_id (SELECT resource FROM ...).
                    # Recursively fix the inner query to re-add patient_id.
                    sql_ast = self._add_patient_id_recursive(sql_ast)

                # Tuple-returning queries produce to_json(struct_pack(...)) as
                # the data column.  Downstream code accesses it via alias.resource
                # so ensure the column is named "resource".
                sql_ast = self._normalize_nested_union_columns(sql_ast)

                # Fix stale "p" alias references in the entire AST BEFORE
                # _ensure_resource_column wraps with an intermediate alias.
                # During translate_library(), patient_alias is None so correlated
                # subqueries fall back to "p.patient_id".  PATIENT_SCALAR CTEs get
                # wrapped with FROM _patients AS p later, but RESOURCE_ROWS do not.
                # Replace "p" with the actual FROM alias of this CTE.
                from ..translator.types import SQLAlias, SQLQualifiedIdentifier
                from ..translator.ast_utils import replace_qualified_alias
                from_alias = None
                from_cte_name = None
                if isinstance(sql_ast.from_clause, SQLAlias):
                    from_alias = sql_ast.from_clause.alias
                    if isinstance(sql_ast.from_clause.expr, SQLIdentifier) and sql_ast.from_clause.expr.quoted:
                        from_cte_name = sql_ast.from_clause.expr.name
                elif isinstance(sql_ast.from_clause, SQLIdentifier) and sql_ast.from_clause.quoted:
                    from_alias = sql_ast.from_clause.name
                    from_cte_name = sql_ast.from_clause.name
                if from_alias and from_alias != "p":
                    sql_ast = replace_qualified_alias(sql_ast, "p", from_alias)

                # In audit mode, pass _audit_item through BEFORE _ensure_resource_column
                # so that the subquery wrapping can propagate it to the outer SELECT.
                if self._context.audit_mode and from_cte_name and isinstance(sql_ast, SQLSelect):
                    sql_ast = self._passthrough_audit_item(sql_ast, from_alias, from_cte_name, name)

                sql_ast = self._ensure_resource_column(sql_ast)

                if joins:
                    # Fix JOIN conditions: replace "p" alias with the actual FROM alias
                    if from_alias and from_alias != "p":
                        fixed_joins = []
                        for j in joins:
                            on_cond = self._replace_patient_alias_in_condition(
                                j.on_condition, "p", from_alias
                            )
                            fixed_joins.append(SQLJoin(
                                join_type=j.join_type,
                                table=j.table,
                                alias=j.alias,
                                on_condition=on_cond,
                            ))
                        joins = fixed_joins
                    existing = list(sql_ast.joins) if sql_ast.joins else []
                    return SQLSelect(
                        columns=sql_ast.columns,
                        from_clause=sql_ast.from_clause,
                        joins=existing + joins,
                        where=sql_ast.where,
                        group_by=sql_ast.group_by,
                        having=sql_ast.having,
                        order_by=sql_ast.order_by,
                        distinct=sql_ast.distinct,
                        limit=sql_ast.limit,
                    )
                return sql_ast
            elif isinstance(sql_ast, (SQLUnion, SQLExcept, SQLIntersect)):
                # Union/Except/Intersect from retrieve CTEs should carry patient_id.
                # However, when status filter wraps the source (SELECT resource FROM ...),
                # patient_id gets stripped. Detect this and re-add patient_id.
                # Also detect column count mismatches (e.g., scalar CTE + resource-row CTE
                # in population definitions) and normalize to patient_id only.

                # Fix stale "p" alias in each operand.
                from ..translator.ast_utils import replace_qualified_alias
                fixed_operands = []
                for op in sql_ast.operands:
                    inner_op = op
                    if isinstance(inner_op, SQLSubquery) and isinstance(inner_op.query, SQLSelect):
                        inner_op = inner_op.query
                    op_from_alias = None
                    if isinstance(inner_op, SQLSelect):
                        if isinstance(inner_op.from_clause, SQLAlias):
                            op_from_alias = inner_op.from_clause.alias
                        elif isinstance(inner_op.from_clause, SQLIdentifier) and inner_op.from_clause.quoted:
                            op_from_alias = inner_op.from_clause.name
                    if op_from_alias and op_from_alias != "p":
                        fixed_operands.append(replace_qualified_alias(op, "p", op_from_alias))
                    else:
                        fixed_operands.append(op)

                # Reconstruct the same set operation type
                if isinstance(sql_ast, SQLExcept):
                    sql_ast = SQLExcept(operands=fixed_operands)
                elif isinstance(sql_ast, SQLIntersect):
                    sql_ast = SQLIntersect(operands=fixed_operands)
                else:
                    sql_ast = SQLUnion(operands=fixed_operands, distinct=sql_ast.distinct)

                # Resolve SELECT * FROM "CTE" operands into explicit columns.
                # A UNION may mix RESOURCE_ROWS CTEs (patient_id, resource)
                # with PATIENT_MULTI_VALUE CTEs (patient_id, value).  Expand
                # the star so each operand explicitly selects the right columns,
                # promoting value → resource when needed.
                expanded_operands = []
                for op in sql_ast.operands:
                    inner = op
                    was_subquery = isinstance(inner, SQLSubquery) and isinstance(inner.query, SQLSelect)
                    if was_subquery:
                        inner = inner.query
                    if isinstance(inner, SQLSelect):
                        cols = inner.columns or []
                        is_star = (
                            len(cols) == 1
                            and isinstance(cols[0], SQLIdentifier)
                            and cols[0].name == "*"
                        )
                        if is_star and inner.from_clause:
                            from_ref = inner.from_clause
                            if isinstance(from_ref, SQLAlias):
                                from_ref = from_ref.expr
                            if isinstance(from_ref, SQLIdentifier) and from_ref.quoted:
                                ref_meta = self._context.definition_meta.get(from_ref.name)
                                if ref_meta and not ref_meta.has_resource:
                                    # CTE has (patient_id, value) — promote value AS resource
                                    val_col = ref_meta.value_column or "value"
                                    inner = SQLSelect(
                                        columns=[
                                            SQLIdentifier(name="patient_id"),
                                            SQLAlias(
                                                expr=SQLIdentifier(name=val_col),
                                                alias="resource",
                                            ),
                                        ],
                                        from_clause=inner.from_clause,
                                        where=inner.where,
                                        joins=inner.joins,
                                        order_by=inner.order_by,
                                        distinct=inner.distinct,
                                        limit=inner.limit,
                                    )
                                else:
                                    # CTE has (patient_id, resource) or is a retrieve CTE
                                    inner = SQLSelect(
                                        columns=[
                                            SQLIdentifier(name="patient_id"),
                                            SQLIdentifier(name="resource"),
                                        ],
                                        from_clause=inner.from_clause,
                                        where=inner.where,
                                        joins=inner.joins,
                                        order_by=inner.order_by,
                                        distinct=inner.distinct,
                                        limit=inner.limit,
                                    )
                    if was_subquery:
                        inner = SQLSubquery(query=inner)
                    expanded_operands.append(inner)
                if isinstance(sql_ast, SQLExcept):
                    sql_ast = SQLExcept(operands=expanded_operands)
                elif isinstance(sql_ast, SQLIntersect):
                    sql_ast = SQLIntersect(operands=expanded_operands)
                else:
                    sql_ast = SQLUnion(operands=expanded_operands, distinct=sql_ast.distinct)

                # Ensure each operand's data column is aliased as 'resource'.
                # Tuple-returning queries produce to_json(struct_pack(...)) without
                # an alias; UNION column names come from the first operand so the
                # resulting CTE column is the raw expression text, not 'resource'.
                resource_fixed = []
                for op in sql_ast.operands:
                    inner = op
                    was_subquery = isinstance(inner, SQLSubquery) and isinstance(inner.query, SQLSelect)
                    if was_subquery:
                        inner = inner.query
                    if isinstance(inner, SQLSelect):
                        inner = self._ensure_resource_column(inner)
                        if was_subquery:
                            inner = SQLSubquery(query=inner)
                    resource_fixed.append(inner)
                if isinstance(sql_ast, SQLExcept):
                    sql_ast = SQLExcept(operands=resource_fixed)
                elif isinstance(sql_ast, SQLIntersect):
                    sql_ast = SQLIntersect(operands=resource_fixed)
                else:
                    sql_ast = SQLUnion(operands=resource_fixed, distinct=sql_ast.distinct)

                if isinstance(sql_ast, SQLUnion):
                    if self._union_has_column_mismatch(sql_ast):
                        return self._normalize_union_to_patient_id(sql_ast)
                    has_pid = self._union_has_patient_id(sql_ast)
                    if has_pid:
                        return sql_ast
                    else:
                        return self._add_patient_id_to_union(sql_ast)
                return sql_ast
            else:
                # Non-SELECT/UNION expression (e.g., SQLFunctionCall like jsonConcat).
                # RESOURCE_ROWS definitions need patient_id and a resource column.
                # Wrap with patient_id from _patients and alias the expression as
                # "resource" so downstream UNION normalization can find it.
                return SQLSelect(
                    columns=[
                        SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                        SQLAlias(expr=sql_ast, alias="resource"),
                    ],
                    from_clause=SQLAlias(
                        expr=SQLIdentifier(name="_patients"),
                        alias="p",
                    ),
                    joins=joins if joins else None,
                )
        else:
            # UNKNOWN shape: Treat as PATIENT_SCALAR to ensure patient_id is present
            # Unwrap SQLSubquery → SQLSelect for structural inspection
            if isinstance(sql_ast, SQLSubquery) and isinstance(sql_ast.query, SQLSelect):
                sql_ast = sql_ast.query
            # Fix stale "p" alias references in UNKNOWN-shape CTEs.
            # Same issue as RESOURCE_ROWS: expressions translator falls back to
            # "p" when patient_alias is None during translate_library().
            from ..translator.ast_utils import replace_qualified_alias
            if isinstance(sql_ast, SQLSelect):
                from_alias = None
                if isinstance(sql_ast.from_clause, SQLAlias):
                    from_alias = sql_ast.from_clause.alias
                elif isinstance(sql_ast.from_clause, SQLIdentifier) and sql_ast.from_clause.quoted:
                    from_alias = sql_ast.from_clause.name
                if from_alias and from_alias != "p":
                    sql_ast = replace_qualified_alias(sql_ast, "p", from_alias)

                # Check if it already has patient_id
                has_patient_id = self._select_has_patient_id(sql_ast)
                if has_patient_id:
                    if joins:
                        if from_alias and from_alias != "p":
                            fixed_joins = []
                            for j in joins:
                                on_cond = self._replace_patient_alias_in_condition(
                                    j.on_condition, "p", from_alias
                                )
                                fixed_joins.append(SQLJoin(
                                    join_type=j.join_type,
                                    table=j.table,
                                    alias=j.alias,
                                    on_condition=on_cond,
                                ))
                            joins = fixed_joins
                        existing = list(sql_ast.joins) if sql_ast.joins else []
                        return SQLSelect(
                            columns=sql_ast.columns,
                            from_clause=sql_ast.from_clause,
                            joins=existing + joins,
                            where=sql_ast.where,
                            group_by=sql_ast.group_by,
                            having=sql_ast.having,
                            order_by=sql_ast.order_by,
                            distinct=sql_ast.distinct,
                            limit=sql_ast.limit,
                        )
                    return sql_ast
            # Wrap with patient_id from _patients
            # When sql_ast is a SELECT/UNION, check if it already contains patient_id
            # and use RESOURCE_ROWS treatment (pass through) rather than scalar subquery
            from ..translator.types import SQLSubquery, SQLUnion
            if isinstance(sql_ast, (SQLSelect, SQLUnion)):
                # Fix stale "p" alias in unions
                if isinstance(sql_ast, SQLUnion):
                    fixed_operands = []
                    for op in sql_ast.operands:
                        inner_op = op
                        if isinstance(inner_op, SQLSubquery) and isinstance(inner_op.query, SQLSelect):
                            inner_op = inner_op.query
                        op_from_alias = None
                        if isinstance(inner_op, SQLSelect):
                            if isinstance(inner_op.from_clause, SQLAlias):
                                op_from_alias = inner_op.from_clause.alias
                            elif isinstance(inner_op.from_clause, SQLIdentifier) and inner_op.from_clause.quoted:
                                op_from_alias = inner_op.from_clause.name
                        if op_from_alias and op_from_alias != "p":
                            fixed_operands.append(replace_qualified_alias(op, "p", op_from_alias))
                        else:
                            fixed_operands.append(op)
                    sql_ast = SQLUnion(operands=fixed_operands, distinct=sql_ast.distinct)

                # Check if the inner query has patient_id — if so, treat as RESOURCE_ROWS
                if isinstance(sql_ast, SQLSelect):
                    has_pid = self._select_has_patient_id(sql_ast)
                elif isinstance(sql_ast, SQLUnion):
                    has_pid = self._union_has_patient_id(sql_ast)
                else:
                    has_pid = False

                if has_pid:
                    if joins:
                        existing = list(sql_ast.joins) if sql_ast.joins and isinstance(sql_ast, SQLSelect) else []
                        if isinstance(sql_ast, SQLSelect):
                            return SQLSelect(
                                columns=sql_ast.columns,
                                from_clause=sql_ast.from_clause,
                                joins=existing + joins,
                                where=sql_ast.where,
                                group_by=sql_ast.group_by,
                                having=sql_ast.having,
                                order_by=sql_ast.order_by,
                                distinct=sql_ast.distinct,
                                limit=sql_ast.limit,
                            )
                    return sql_ast

                # No patient_id — try to add it recursively
                if isinstance(sql_ast, SQLSelect):
                    sql_ast = self._add_patient_id_recursive(sql_ast)
                    if self._select_has_patient_id(sql_ast):
                        return sql_ast
                elif isinstance(sql_ast, SQLUnion):
                    rewritten = self._add_patient_id_to_union(sql_ast)
                    return rewritten

                # Last resort: scalar subquery wrapping
                column_expr = SQLSubquery(query=sql_ast)
            else:
                column_expr = sql_ast
            return SQLSelect(
                columns=[
                    SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                    SQLAlias(expr=column_expr, alias=meta.value_column),
                ],
                from_clause=SQLAlias(
                    expr=SQLIdentifier(name="_patients"),
                    alias="p",
                ),
                joins=joins if joins else None,
            )

    # ------------------------------------------------------------------
    # CTE building helpers
    # ------------------------------------------------------------------

    def _build_definition_cte_with_patient_id(
        self,
        name: str,
        expr: SQLExpression,
        existing_ctes: Dict[str, tuple],
    ) -> tuple:
        """
        Build a CTE for a definition that includes patient_id.

        This method now delegates to _wrap_definition_cte for AST-based wrapping,
        using DefinitionMeta to determine the wrapping strategy.

        Args:
            name: The definition name.
            expr: The translated SQL expression.
            existing_ctes: Dictionary mapping name -> (quoted_name, has_resource).

        Returns:
            Tuple of (SQLExpression AST for CTE body, boolean indicating if resource column exists).
        """
        from ..translator.context import RowShape
        from ..translator.types import SQLSelect, SQLUnion, SQLSubquery, SQLAlias, SQLIdentifier, SQLQualifiedIdentifier

        # Get metadata for this definition
        meta = self._context.definition_meta.get(name)

        if meta is not None:
            # Gap 15: Identity definition passthrough
            # If this definition references exactly one other definition CTE
            # with the same shape, emit SELECT * FROM "target_cte" instead of
            # redundant LEFT JOIN + EXISTS wrapping.

            # Check for direct CTE reference (e.g., SDE."SDE Ethnicity" → SQLIdentifier)
            direct_ref = expr
            if isinstance(direct_ref, SQLSubquery) and isinstance(direct_ref.query, SQLSelect):
                inner = direct_ref.query
                if inner.from_clause and not inner.where and len(inner.columns or []) <= 1:
                    direct_ref = inner.from_clause
            if isinstance(direct_ref, SQLIdentifier) and direct_ref.quoted:
                target_name = direct_ref.name
                # Check both definition CTEs and retrieve CTEs
                _is_retrieve_cte = any(c.name == target_name for c in self._retrieve_ctes)
                if target_name in existing_ctes:
                    identity_select = SQLSelect(
                        from_clause=SQLIdentifier(name=target_name, quoted=True),
                    )
                    # Use target CTE's has_resource — the identity SELECT * inherits
                    # the target's columns, so resource presence must match the target.
                    _, target_has_resource = existing_ctes[target_name]
                    has_resource = target_has_resource
                    return (identity_select, has_resource)
                elif _is_retrieve_cte:
                    # Bare retrieve without WHERE clause (e.g., define 'X': [Condition])
                    # Retrieve CTEs always have resource columns.
                    identity_select = SQLSelect(
                        from_clause=SQLIdentifier(name=target_name, quoted=True),
                    )
                    return (identity_select, True)

            if meta.tracked_refs and len(meta.tracked_refs) == 1:
                ref_key = next(iter(meta.tracked_refs))
                target_name = ref_key[0] if isinstance(ref_key, tuple) else ref_key
                if target_name in existing_ctes:
                    target_meta = self._context.definition_meta.get(target_name)
                    # Allow identity passthrough when shapes match OR when
                    # meta.shape is UNKNOWN (stale from prior translate_library call)
                    shapes_compatible = (
                        target_meta and (
                            target_meta.shape == meta.shape
                            or meta.shape == RowShape.UNKNOWN
                        )
                    )
                    if shapes_compatible:
                        # Only use identity passthrough if the expression is
                        # structurally a simple CTE reference (SELECT * FROM cte,
                        # bare identifier, SELECT col FROM cte, or scalar
                        # alias.value). Complex expressions that merely
                        # *reference* one definition CTE (e.g. EXISTS queries)
                        # must NOT be short-circuited.
                        is_simple_ref = False
                        check_expr = expr
                        if isinstance(check_expr, SQLSubquery) and isinstance(check_expr.query, SQLSelect):
                            inner = check_expr.query
                            if inner.from_clause and not inner.where:
                                cols = inner.columns or []
                                if len(cols) <= 1:
                                    check_expr = inner.from_clause
                        if isinstance(check_expr, SQLSelect) and check_expr.from_clause and not check_expr.where:
                            cols = check_expr.columns or []
                            if len(cols) == 0:
                                check_expr = check_expr.from_clause
                        if isinstance(check_expr, SQLIdentifier) and check_expr.quoted:
                            is_simple_ref = True
                        if isinstance(check_expr, SQLAlias) and isinstance(check_expr.expr, SQLIdentifier):
                            is_simple_ref = True
                        # CTE reference via alias: alias.value or alias.resource
                        if isinstance(check_expr, SQLQualifiedIdentifier):
                            ref_info = next(iter(meta.tracked_refs.values()))
                            if (hasattr(ref_info, 'alias') and
                                    len(check_expr.parts) == 2 and
                                    check_expr.parts[0] == ref_info.alias and
                                    check_expr.parts[1] in ('value', 'resource')):
                                is_simple_ref = True

                        if is_simple_ref:
                            # Use target's has_resource (accounts for PATIENT_SCALAR
                            # definitions that store FHIR resources).
                            identity_select = SQLSelect(
                                from_clause=SQLIdentifier(name=target_name, quoted=True),
                            )
                            has_resource = (target_meta.has_resource if target_meta
                                            else meta.has_resource)
                            return (identity_select, has_resource)

            # Use the new AST-based wrapping approach
            wrapped_ast = self._wrap_definition_cte(name, expr, meta)
            # Fix nested UNIONs that reference CTEs with value columns.
            # to_sql() normalization hardcodes 'resource' but some CTEs use 'value'.
            wrapped_ast = self._normalize_nested_union_columns(wrapped_ast)
            # In audit mode, non-boolean CTEs may have audit macros leaked into
            # WHERE/CASE WHEN conditions from global expression translation.
            # Strip them for all shapes EXCEPT PATIENT_SCALAR Boolean (which
            # intentionally carries audit structs as its output column).
            _is_boolean_scalar = (
                meta.shape == RowShape.PATIENT_SCALAR
                and meta.cql_type == "Boolean"
            )
            if self._context.audit_mode and not _is_boolean_scalar:
                from ..translator.expressions._query import _deep_demote_audit_in_sql
                wrapped_ast = _deep_demote_audit_in_sql(wrapped_ast)
                # Non-boolean CTEs that reference boolean definitions via EXISTS
                # must point at the pre-compute CTE (only True patients) instead
                # of the audit CTE (all patients).
                precte_map = getattr(self, '_precte_name_map', {})
                if precte_map:
                    wrapped_ast = self._rewrite_cte_references(wrapped_ast, precte_map)
            # Determine has_resource from the actual wrapped AST, not just metadata.
            # The wrapping may produce (patient_id, value) even for RESOURCE_ROWS
            # shapes when the source CTE only has value columns.
            if isinstance(wrapped_ast, SQLSelect):
                has_resource = self._select_has_resource(wrapped_ast)
            else:
                has_resource = meta.shape == RowShape.RESOURCE_ROWS
            return (wrapped_ast, has_resource)

        # Fallback for definitions without metadata (should be rare)
        # Check if expression is already a proper SELECT with patient_id
        if isinstance(expr, SQLSelect):
            has_resource = self._select_has_resource(expr)
            # Use AST helper to determine if patient_id present
            if self._select_has_patient_id(expr):
                return (expr, has_resource)
            # Need to add patient_id
            wrapped = SQLSelect(
                columns=[SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                         SQLAlias(expr=SQLSubquery(query=expr), alias="value")],
                from_clause=SQLAlias(expr=SQLIdentifier(name="_patients"), alias="p"),
            )
            return (wrapped, False)

        if isinstance(expr, SQLUnion):
            return (expr, True)  # Union from retrieves has resource

        # Default fallback
        wrapped = SQLSelect(
            columns=[SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                     SQLAlias(expr=SQLSubquery(query=expr), alias="value")],
            from_clause=SQLAlias(expr=SQLIdentifier(name="_patients"), alias="p"),
        )
        return (wrapped, False)

    def _wrap_expression_in_select(
        self,
        expr: SQLExpression,
    ) -> "SQLSelect":
        """
        Wrap a non-SELECT expression in a SQLSelect for JOIN optimization.

        When an expression (boolean, EXISTS, comparison, etc.) has tracked JOINs,
        we need to wrap it in a SELECT statement so _build_cte_from_ast() can
        add the JOINs and convert correlated subqueries.

        Args:
            expr: The SQLExpression to wrap (e.g., SQLBinaryOp, SQLExists).

        Returns:
            SQLSelect with the expression in WHERE or SELECT clause.
        """
        from ..translator.types import (
            SQLSelect, SQLAlias, SQLIdentifier, SQLQualifiedIdentifier,
            SQLBinaryOp, SQLExists, SQLNull, SQLFunctionCall, SQLRaw
        )

        # FROM _patients AS p — the "p" alias is required for p.patient_id references
        patients_from = SQLAlias(
            expr=SQLIdentifier(name="_patients", quoted=False),
            alias="p"
        )

        # Check if expression is boolean-like (goes in WHERE clause)
        is_boolean = isinstance(expr, (SQLBinaryOp, SQLExists))
        if isinstance(expr, SQLBinaryOp):
            # Check if it's a boolean operator
            bool_ops = {'AND', 'OR', 'IS', 'IS NOT', '=', '!=', '<>', '<', '>', '<=', '>='}
            is_boolean = expr.operator.upper() in bool_ops

        # Audit macros return structs — extract .result for WHERE clause
        _audit_names = {"audit_and", "audit_or", "audit_or_all", "audit_not", "audit_leaf", "audit_comparison", "audit_breadcrumb", "compact_audit"}
        is_audit_struct = (
            isinstance(expr, SQLFunctionCall) and expr.name in _audit_names
        )
        if is_audit_struct:
            is_boolean = True

        if is_boolean:
            where_expr = expr
            if is_audit_struct:
                # Extract .result from the audit struct for the WHERE predicate
                from ..translator.expressions._query import _demote_audit_struct_to_bool
                where_expr = _demote_audit_struct_to_bool(where_expr)
            # Build: SELECT p.patient_id FROM _patients AS p WHERE <expr>
            return SQLSelect(
                columns=[SQLQualifiedIdentifier(parts=["p", "patient_id"])],
                from_clause=patients_from,
                where=where_expr,
                joins=[],  # JOINs will be added by _build_cte_from_ast
            )
        else:
            # Build: SELECT p.patient_id, <expr> AS value FROM _patients AS p
            return SQLSelect(
                columns=[
                    SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                    (expr, "value"),  # Tuple for aliased column
                ],
                from_clause=patients_from,
                joins=[],  # JOINs will be added by _build_cte_from_ast
            )

    def _build_cte_from_ast(
        self,
        name: str,
        select: "SQLSelect",
        existing_ctes: Dict[str, tuple],
    ) -> Optional[tuple]:
        """
        Build a CTE from a SQLSelect AST.

        This method processes the AST directly for better optimization,
        including CTE dependency detection and scalar subquery conversion.

        Args:
            name: The definition name.
            select: The SQLSelect AST to process.
            existing_ctes: Dictionary mapping name -> (quoted_name, has_resource).

        Returns:
            Tuple of (SQLExpression AST for CTE body, boolean indicating if resource column exists),
            or None if AST processing cannot handle this case (falls back to string-based).
        """
        from ..translator.types import SQLSelect, SQLIdentifier, SQLJoin, SQLBinaryOp, SQLQualifiedIdentifier, SQLSubquery, SQLAlias, SQLRaw

        # Unwrap SQLSubquery → SQLSelect for CTE body usage
        if isinstance(select, SQLSubquery) and isinstance(select.query, SQLSelect):
            select = select.query

        # Check for CTE dependencies using AST traversal
        cte_names = set(existing_ctes.keys())
        refs = self._find_cte_references(select, cte_names)

        has_resource = self._select_has_resource(select)

        # Track CTE references in query_builder
        for ref_name in refs:
            if self._context.query_builder:
                self._context.query_builder.track_cte_reference(ref_name)

        # Determine the patient alias based on which path we'll take
        # This is needed for scalar subquery conversion (JOINs need the right alias)
        patient_alias = "p"  # Default: FROM patients p

        # Check if we have a dependency on another CTE
        dep_cte = None
        dep_has_resource = False
        for dep_name, (dep_cte_name, has_res) in existing_ctes.items():
            if dep_name in refs:
                dep_cte = dep_cte_name
                dep_has_resource = has_res
                patient_alias = "d"  # FROM dep_cte d
                break

        # If no dependency, check if this is a retrieve from resources
        if dep_cte is None and self._is_ast_retrieve(select):
            patient_alias = "r"  # FROM resources r

        # Apply AST-based scalar subquery conversion AND add JOINs from tracked references
        # This ensures JOINs are placed inside the CTE definition, not at the final SELECT
        if self._context.query_builder and self._context.query_builder.has_references():
            cte_refs = self._context.query_builder.cte_references.copy()

            # First, convert any existing subquery nodes (for legacy code)
            select = self._convert_scalar_subqueries_to_joins_ast(select, cte_refs, patient_alias)

            # Second, add JOINs for tracked references (modern approach)
            # When expressions call track_cte_reference(), they return direct alias references
            # (e.g., j1.resource), so we need to generate the actual JOINs
            select = self._add_joins_from_tracked_refs(select, cte_refs, patient_alias)

        # Now route to the appropriate handler with the converted AST

        # Get the dependent CTE info if there's a dependency
        if dep_cte is not None:
            # This definition depends on another CTE
            # We need to wrap or modify the select appropriately
            return self._wrap_ast_with_patient_id(select, dep_cte, dep_has_resource, existing_ctes)

        # No dependencies - check if this is a retrieve from resources
        if self._is_ast_retrieve(select):
            # Modify the AST to include patient_id
            return self._modify_ast_retrieve_with_patient_id(select)

        # Check if this looks like a boolean/exists expression
        if self._is_ast_boolean_expression(select):
            return self._wrap_ast_boolean_with_patient_id(select, existing_ctes)

        # Check if this is a query expression with an aliased CTE reference in FROM clause
        # These need CROSS JOIN LATERAL to properly bind the alias
        from ..translator.types import SQLAlias, SQLIdentifier as SQLId
        if select.from_clause is not None:
            is_aliased_cte_ref = False
            is_cte_ref_without_alias = False
            cte_name_for_lateral = None

            if isinstance(select.from_clause, SQLAlias):
                # This is: SELECT ... FROM "CTE Name" AS alias WHERE ...
                # Check if the underlying expression is a CTE reference (identifier with colon)
                if isinstance(select.from_clause.expr, SQLId):
                    cte_name = select.from_clause.expr.name
                    if self._is_known_cte(cte_name, existing_ctes) or cte_name.startswith('"'):
                        is_aliased_cte_ref = True
                        cte_name_for_lateral = cte_name
            elif isinstance(select.from_clause, SQLId):
                # Check if this is a CTE reference without explicit alias
                cte_name = select.from_clause.name
                if self._is_known_cte(cte_name, existing_ctes):
                    is_cte_ref_without_alias = True
                    cte_name_for_lateral = cte_name

            if is_aliased_cte_ref or is_cte_ref_without_alias:
                # Wrap in CROSS JOIN LATERAL pattern for proper per-patient evaluation
                lateral = SQLSelect(
                    columns=[SQLQualifiedIdentifier(parts=["p", "patient_id"]), SQLQualifiedIdentifier(parts=["t", "*"])],
                    from_clause=SQLAlias(expr=SQLIdentifier(name="_patients"), alias="p"),
                    joins=[SQLJoin(join_type="CROSS JOIN LATERAL", table=SQLSubquery(query=select), alias="t")],
                )
                return (lateral, True)

        # Default case: wrap with patients table
        # Use AST-based check for patient_id presence
        if not self._select_has_patient_id(select):
            wrapped = SQLSelect(
                columns=[SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                         SQLAlias(expr=SQLSubquery(query=select), alias="value")],
                from_clause=SQLAlias(expr=SQLIdentifier(name="_patients"), alias="p"),
            )
            return (wrapped, False)

        # Return the AST as-is if it already has patient_id
        return (select, has_resource)

    # ------------------------------------------------------------------
    # Union / column normalization
    # ------------------------------------------------------------------

    def _normalize_nested_union_columns(self, ast: "SQLExpression") -> "SQLExpression":
        """Recursively fix UNION operands that reference CTEs with ``value`` columns.

        The ``to_sql()`` normalization in ``types.py`` hardcodes ``resource`` as
        the data column name.  However, some definition CTEs use ``value``
        (PATIENT_MULTI_VALUE shape).  This pass walks the entire AST and, for
        every UNION/INTERSECT/EXCEPT operand that is a bare CTE reference or
        ``SELECT * FROM "CTE"``, rewrites it to use the correct column name
        from ``definition_meta``.

        This must run *before* ``to_sql()`` so the SQL-level normalization
        in ``types.py`` sees operands with explicit column lists and does not
        need to guess column names.
        """
        from ..translator.types import (
            SQLSelect, SQLSubquery, SQLUnion, SQLIntersect, SQLExcept,
            SQLIdentifier, SQLAlias, SQLQualifiedIdentifier,
        )

        def _fix_set_operands(set_expr):
            """Normalize operands of a set expression."""
            fixed = []
            changed = False
            for op in set_expr.operands:
                new_op = _fix_operand(op)
                # Also recurse into the operand itself
                new_op = _walk(new_op)
                if new_op is not op:
                    changed = True
                fixed.append(new_op)
            if not changed:
                return set_expr
            if isinstance(set_expr, SQLUnion):
                return SQLUnion(operands=fixed, distinct=set_expr.distinct)
            elif isinstance(set_expr, SQLIntersect):
                return SQLIntersect(operands=fixed)
            else:
                return SQLExcept(operands=fixed)

        def _fix_operand(op):
            """Fix a single UNION operand to use correct column names."""
            # Case 1: Bare quoted identifier → SELECT patient_id, <col> FROM "CTE"
            cte_name = None
            from_clause = None

            if isinstance(op, SQLIdentifier) and op.quoted:
                cte_name = op.name
                from_clause = op
            elif isinstance(op, SQLSubquery) and isinstance(op.query, SQLIdentifier) and op.query.quoted:
                cte_name = op.query.name
                from_clause = op.query

            if cte_name and from_clause:
                meta = self._context.definition_meta.get(cte_name)
                if meta and not meta.has_resource:
                    val_col = meta.value_column or "value"
                    return SQLSubquery(query=SQLSelect(
                        columns=[
                            SQLIdentifier(name="patient_id"),
                            SQLAlias(expr=SQLIdentifier(name=val_col), alias="resource"),
                        ],
                        from_clause=from_clause,
                    ))
                elif meta:
                    return SQLSubquery(query=SQLSelect(
                        columns=[
                            SQLIdentifier(name="patient_id"),
                            SQLIdentifier(name="resource"),
                        ],
                        from_clause=from_clause,
                    ))
                return op

            # Case 2: SELECT * FROM "CTE" → expand with correct column names
            inner = op
            was_subquery = isinstance(inner, SQLSubquery) and isinstance(inner.query, SQLSelect)
            if was_subquery:
                inner = inner.query
            if isinstance(inner, SQLSelect):
                cols = inner.columns or []
                is_star = (
                    len(cols) == 1
                    and isinstance(cols[0], SQLIdentifier)
                    and cols[0].name == "*"
                )
                if is_star and inner.from_clause:
                    from_ref = inner.from_clause
                    if isinstance(from_ref, SQLAlias):
                        from_ref = from_ref.expr
                    if isinstance(from_ref, SQLIdentifier) and from_ref.quoted:
                        ref_name = from_ref.name
                        ref_meta = self._context.definition_meta.get(ref_name)
                        if ref_meta and not ref_meta.has_resource:
                            val_col = ref_meta.value_column or "value"
                            fixed_inner = SQLSelect(
                                columns=[
                                    SQLIdentifier(name="patient_id"),
                                    SQLAlias(
                                        expr=SQLIdentifier(name=val_col),
                                        alias="resource",
                                    ),
                                ],
                                from_clause=inner.from_clause,
                                where=inner.where,
                                joins=inner.joins,
                                order_by=inner.order_by,
                                distinct=inner.distinct,
                                limit=inner.limit,
                            )
                            return SQLSubquery(query=fixed_inner) if was_subquery else fixed_inner
                        elif ref_meta:
                            fixed_inner = SQLSelect(
                                columns=[
                                    SQLIdentifier(name="patient_id"),
                                    SQLIdentifier(name="resource"),
                                ],
                                from_clause=inner.from_clause,
                                where=inner.where,
                                joins=inner.joins,
                                order_by=inner.order_by,
                                distinct=inner.distinct,
                                limit=inner.limit,
                            )
                            return SQLSubquery(query=fixed_inner) if was_subquery else fixed_inner
            return op

        def _walk(node):
            """Recursively walk the AST and fix set expression operands."""
            if isinstance(node, (SQLUnion, SQLIntersect, SQLExcept)):
                return _fix_set_operands(node)
            if isinstance(node, SQLSubquery):
                new_q = _walk(node.query)
                if new_q is not node.query:
                    return SQLSubquery(query=new_q)
                return node
            if isinstance(node, SQLSelect):
                changed = False
                # Walk columns (correlated subqueries may contain UNIONs)
                new_cols = []
                for col in (node.columns or []):
                    new_col = _walk(col)
                    if new_col is not col:
                        changed = True
                    new_cols.append(new_col)
                # Walk FROM clause
                new_from = _walk(node.from_clause) if node.from_clause else node.from_clause
                if new_from is not node.from_clause:
                    changed = True
                # Walk WHERE
                new_where = _walk(node.where) if node.where else node.where
                if new_where is not node.where:
                    changed = True
                if changed:
                    return SQLSelect(
                        columns=new_cols,
                        from_clause=new_from,
                        where=new_where,
                        joins=node.joins,
                        group_by=node.group_by,
                        having=node.having,
                        order_by=node.order_by,
                        limit=node.limit,
                        distinct=node.distinct,
                    )
                return node
            if isinstance(node, SQLAlias):
                new_expr = _walk(node.expr)
                if new_expr is not node.expr:
                    return SQLAlias(expr=new_expr, alias=node.alias)
                return node
            return node

        return _walk(ast)

    def _normalize_union_to_patient_id(self, union: "SQLUnion") -> "SQLSelect":
        """Normalize a SQLUnion with mismatched columns to patient-scoped SELECT.

        For population definitions, CQL union means "patient is in this set if
        any branch includes them." We convert to OR of EXISTS checks, producing
        (patient_id, TRUE AS value) so downstream CTE references work.
        """
        from ..translator.types import (
            SQLSelect, SQLSubquery, SQLIdentifier, SQLAlias,
            SQLQualifiedIdentifier, SQLUnion as SQLUnionType,
            SQLBinaryOp, SQLExists, SQLUnaryOp, SQLLiteral,
        )
        conditions = []
        p_pid = SQLQualifiedIdentifier(parts=["p", "patient_id"])
        for op in (union.operands or []):
            inner = op
            if isinstance(inner, SQLSubquery):
                inner = inner.query
            # Check if the operand has patient_id column
            has_pid = False
            if isinstance(inner, SQLSelect) and inner.columns:
                has_pid = self._select_has_patient_id(inner)
            elif isinstance(inner, SQLSelect) and not inner.columns:
                has_pid = True  # SELECT * assumed to have patient_id

            if has_pid:
                exists_sub = SQLSelect(
                    columns=[SQLLiteral(value=1)],
                    from_clause=SQLAlias(
                        expr=SQLSubquery(query=inner),
                        alias="sub",
                    ),
                    where=SQLBinaryOp(
                        operator="=",
                        left=SQLQualifiedIdentifier(parts=["sub", "patient_id"]),
                        right=p_pid,
                    ),
                )
                conditions.append(SQLExists(subquery=SQLSubquery(query=exists_sub)))
            else:
                # Scalar operand (no patient_id): check if non-null
                operand = SQLSubquery(query=inner) if isinstance(inner, SQLSelect) else op
                conditions.append(SQLUnaryOp(
                    operator="IS NOT NULL",
                    operand=operand,
                    prefix=False,
                ))

        # Combine with OR
        if not conditions:
            return SQLSelect(
                columns=[p_pid, SQLAlias(expr=SQLLiteral(value=False), alias="value")],
                from_clause=SQLAlias(expr=SQLIdentifier(name="_patients"), alias="p"),
                where=SQLLiteral(value=False),
            )
        combined = conditions[0]
        for cond in conditions[1:]:
            combined = SQLBinaryOp(operator="OR", left=combined, right=cond)
        return SQLSelect(
            columns=[
                SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                SQLAlias(expr=SQLLiteral(value=True), alias="value"),
            ],
            from_clause=SQLAlias(expr=SQLIdentifier(name="_patients"), alias="p"),
            where=combined,
        )

    def _passthrough_audit_item(
        self,
        sql_ast: "SQLSelect",
        from_alias: str,
        from_cte_name: str,
        def_name: str,
    ) -> "SQLSelect":
        """Pass _audit_item through from the source CTE to this definition CTE.

        In audit mode, RESOURCE_ROWS definition CTEs must carry the _audit_item
        column from their underlying retrieve (or definition) CTE so that
        PATIENT_SCALAR Boolean definitions higher up can collect evidence.

        For example:
          "Qualifying Encounters" selects FROM "Encounter" which has _audit_item.
          Without passthrough, "Initial Population" (exists "Qualifying Encounters")
          cannot access the Encounter evidence.

        Args:
            sql_ast: The already-built RESOURCE_ROWS SELECT (post _ensure_resource_column).
            from_alias: The alias used for column references in sql_ast (e.g. "Encounter").
            from_cte_name: The actual CTE name to check against audit CTE registries.
            def_name: The definition name being built (registered if passthrough is added).

        Returns:
            Modified sql_ast with _audit_item appended (if applicable), unchanged otherwise.
        """
        from ..translator.types import SQLAlias, SQLQualifiedIdentifier, SQLSelect

        # Check if the source CTE has _audit_item (either a retrieve or a definition CTE)
        retrieve_cte_names = getattr(self._context, '_audit_retrieve_cte_names', set())
        definition_cte_names = getattr(self._context, '_audit_definition_cte_names', set())
        all_audit_cte_names = retrieve_cte_names | definition_cte_names
        if from_cte_name not in all_audit_cte_names:
            return sql_ast

        # Check if _audit_item is already in the SELECT columns to avoid duplication
        for col in (sql_ast.columns or []):
            col_expr = col.expr if isinstance(col, SQLAlias) else col
            if isinstance(col_expr, SQLQualifiedIdentifier) and col_expr.parts[-1] == '_audit_item':
                self._register_audit_definition_cte(def_name)
                return sql_ast
            from ..translator.types import SQLIdentifier as _SQLID
            if isinstance(col_expr, _SQLID) and col_expr.name == '_audit_item':
                self._register_audit_definition_cte(def_name)
                return sql_ast
            # SELECT * already includes _audit_item from the source CTE
            if isinstance(col_expr, _SQLID) and col_expr.name == '*':
                self._register_audit_definition_cte(def_name)
                return sql_ast

        # Add <from_alias>._audit_item AS _audit_item to the SELECT list
        ref = from_alias or from_cte_name
        audit_col = SQLAlias(
            expr=SQLQualifiedIdentifier(parts=[ref, '_audit_item']),
            alias='_audit_item',
        )
        new_sql = SQLSelect(
            columns=list(sql_ast.columns or []) + [audit_col],
            from_clause=sql_ast.from_clause,
            joins=sql_ast.joins,
            where=sql_ast.where,
            group_by=sql_ast.group_by,
            having=sql_ast.having,
            order_by=sql_ast.order_by,
            distinct=sql_ast.distinct,
            limit=sql_ast.limit,
        )
        self._register_audit_definition_cte(def_name)
        return new_sql

    def _register_audit_definition_cte(self, name: str) -> None:
        """Register a definition CTE as having an _audit_item column."""
        if not hasattr(self._context, '_audit_definition_cte_names'):
            self._context._audit_definition_cte_names = set()
        self._context._audit_definition_cte_names.add(name)

    def _resolve_source_resource_ctes(
        self,
        sql_ast: "SQLExpression",
        _visited: Optional[set] = None,
    ) -> set:
        """
        Recursively find all RESOURCE_ROWS CTE names that sql_ast transitively depends on.

        Handles three cases:
          - Retrieve CTEs (_audit_retrieve_cte_names) → return directly
          - RESOURCE_ROWS definition CTEs (_audit_definition_cte_names) → return directly
          - PATIENT_SCALAR non-boolean definition CTEs → use their pre-computed
            source_resource_ctes list (avoids re-scanning the whole sub-tree)

        Called when building PATIENT_SCALAR non-boolean CTEs so that comparison-based
        boolean definitions higher up can locate evidence via Strategy 3 in
        _collect_audit_evidence_exprs.
        """
        if _visited is None:
            _visited = set()

        retrieve_ctes = getattr(self._context, '_audit_retrieve_cte_names', set())
        definition_ctes = getattr(self._context, '_audit_definition_cte_names', set())

        cte_names: set = set()
        self._extract_cte_names_from_ast(sql_ast, cte_names)

        result: set = set()
        for cte_name in cte_names:
            if cte_name in _visited:
                continue
            _visited.add(cte_name)

            if cte_name in retrieve_ctes or cte_name in definition_ctes:
                result.add(cte_name)
                continue

            sub_meta = self._context.definition_meta.get(cte_name)
            if sub_meta is not None:
                if sub_meta.source_resource_ctes:
                    result.update(sub_meta.source_resource_ctes)
                elif sub_meta.has_resource:
                    from ..translator.context import RowShape as _RowShape
                    if sub_meta.shape == _RowShape.RESOURCE_ROWS:
                        # This is a RESOURCE_ROWS CTE with a resource column.
                        # _passthrough_audit_item may not have been called (e.g. when the
                        # definition generates a SQLUnion instead of a SQLSelect), so it
                        # may not be in _audit_definition_cte_names. Include it directly
                        # so _inject_audit_evidence can query its resource column via a
                        # correlated <SUBQUERY:...> subquery.
                        result.add(cte_name)

        return result

