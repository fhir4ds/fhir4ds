"""Query translation mixin for CQL to SQL."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from ...parser.ast_nodes import (
    BinaryExpression,
    ChoiceTypeSpecifier,
    CodeSelector,
    DateTimeLiteral,
    FunctionRef,
    Identifier,
    InstanceExpression,
    Interval,
    IntervalTypeSpecifier,
    ListExpression,
    ListTypeSpecifier,
    Literal,
    MethodInvocation,
    NamedTypeSpecifier,
    Property,
    Quantity,
    Query,
    QuerySource,
    Retrieve,
    TimeLiteral,
    TupleExpression,
    TupleTypeSpecifier,
    UnaryExpression,
)
from ...translator.context import ExprUsage, RowShape
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
    _canonical_fhir_r4_type_name,
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

    _CLINICAL_CQL_TYPES = {
        "code": "Code",
        "concept": "Concept",
        "valueset": "ValueSet",
        "codesystem": "CodeSystem",
        "vocabulary": "Vocabulary",
    }
    _VOCABULARY_SUBTYPES = {"ValueSet", "CodeSystem"}

    @staticmethod
    def _quantity_literal_preserving_sql(qty: Quantity) -> SQLLiteral:
        """Return raw Quantity JSON with authored integer/decimal spelling."""
        import json as _json

        result = SQLLiteral(
            value=_json.dumps(
                {
                    "value": qty.value,
                    "unit": qty.unit,
                    "system": "http://unitsofmeasure.org",
                }
            )
        )
        result.result_type = "Quantity"
        return result

    def _preserve_quantity_literals_in_array(
        self,
        source_expr: SQLExpression,
        source_ast: Any,
    ) -> SQLExpression:
        """Keep raw Quantity literals when a literal list becomes a query source.

        The normal Quantity literal path canonicalizes through parse_quantity().
        Native C++ parse_quantity serializes integer JSON numbers as ``1.0``,
        which is fine for most Quantity arithmetic but loses the authored
        precision needed by predecessor/successor through query aliases.
        """
        if not isinstance(source_expr, SQLArray) or not isinstance(source_ast, ListExpression):
            return source_expr
        if len(source_expr.elements) != len(source_ast.elements):
            return source_expr
        changed = False
        elements = []
        for sql_element, ast_element in zip(source_expr.elements, source_ast.elements):
            if isinstance(ast_element, Quantity):
                elements.append(self._quantity_literal_preserving_sql(ast_element))
                changed = True
            else:
                elements.append(sql_element)
        return SQLArray(elements=elements) if changed else source_expr

    def _static_clinical_type(self, node: Any) -> Optional[str]:
        """Return a statically known CQL clinical type for terminology values."""
        from ...parser.ast_nodes import InstanceExpression as _InstExpr
        from ...parser.ast_nodes import QualifiedIdentifier as _QualifiedIdentifier

        if isinstance(node, CodeSelector):
            return "Code"

        if isinstance(node, BinaryExpression):
            operator = node.operator.lower() if isinstance(node.operator, str) else node.operator
            if operator == "as":
                target = node.right
                target_name = None
                if isinstance(target, NamedTypeSpecifier):
                    target_name = target.name
                elif isinstance(target, Identifier):
                    target_name = target.name
                if target_name:
                    bare_target = self._bare_cql_type_name(target_name)
                    source_type = self._static_clinical_type(node.left)
                    if source_type is None:
                        return None
                    if bare_target == "Any":
                        return source_type
                    target_type = self._CLINICAL_CQL_TYPES.get((bare_target or "").lower())
                    if target_type and self._clinical_type_matches(source_type, target_type):
                        return source_type
                    return None
            if operator == "convert":
                target = node.right
                target_name = None
                if isinstance(target, NamedTypeSpecifier):
                    target_name = target.name
                elif isinstance(target, Identifier):
                    target_name = target.name
                if target_name:
                    bare_target = self._bare_cql_type_name(target_name)
                    source_type = self._static_clinical_type(node.left)
                    if bare_target == "Any":
                        return source_type
                    target_type = self._CLINICAL_CQL_TYPES.get((bare_target or "").lower())
                    if target_type is not None:
                        return target_type

        if isinstance(node, UnaryExpression) and node.operator == "singleton from":
            return self._static_clinical_type(node.operand)

        if isinstance(node, Query) and node.return_clause is not None:
            returned = node.return_clause.expression
            if isinstance(returned, Identifier):
                for let_clause in node.let_clauses:
                    if let_clause.alias == returned.name:
                        return self._static_clinical_type(let_clause.expression)
            return self._static_clinical_type(returned)

        if isinstance(node, _InstExpr):
            bare = self._bare_cql_type_name(node.type)
            return self._CLINICAL_CQL_TYPES.get((bare or "").lower())

        if isinstance(node, Identifier):
            meta = self.context.definition_meta.get(node.name)
            if meta and meta.cql_type:
                bare = self._bare_cql_type_name(meta.cql_type)
                clinical_type = self._CLINICAL_CQL_TYPES.get((bare or "").lower())
                if clinical_type is not None:
                    source = self._definition_source_ast(node.name, node)
                    if source is not None:
                        source_type = self._static_clinical_type(source)
                        if (
                            source_type in self._VOCABULARY_SUBTYPES
                            and clinical_type == "Vocabulary"
                        ):
                            return source_type
                    return clinical_type
            symbol = self.context.lookup_symbol(node.name)
            if symbol and getattr(symbol, "cql_type", None):
                bare = self._bare_cql_type_name(getattr(symbol, "cql_type", None))
                clinical_type = self._CLINICAL_CQL_TYPES.get((bare or "").lower())
                if clinical_type is not None:
                    return clinical_type
            if node.name in self.context.valuesets:
                return "ValueSet"
            if node.name in self.context.codesystems:
                return "CodeSystem"
            code_info = self.context.codes.get(node.name)
            if code_info:
                return "Concept" if code_info.get("is_concept") else "Code"

        if isinstance(node, _QualifiedIdentifier) and node.parts:
            if node.parts[0] in self.context.codesystems and len(node.parts) > 1:
                return "Code"
            code_info = self.context.codes.get(node.parts[-1])
            if code_info:
                return "Concept" if code_info.get("is_concept") else "Code"

        if isinstance(node, Property):
            if isinstance(node.source, Identifier) and node.source.name in self.context.includes:
                code_info = self.context.codes.get(node.path)
                if code_info:
                    return "Concept" if code_info.get("is_concept") else "Code"

        if isinstance(node, ParameterPlaceholder):
            return self._static_clinical_type_from_sql(node.sql_expr)

        return None

    def _static_clinical_type_from_sql(self, expr: SQLExpression) -> Optional[str]:
        """Infer clinical type from a pre-translated literal placeholder."""
        import json as _json

        if not isinstance(expr, SQLLiteral) or not isinstance(expr.value, str):
            return None
        text = expr.value.strip()
        if "|" in text and not text.startswith("{"):
            return "Code"
        if not text.startswith("{"):
            return None
        try:
            data = _json.loads(text)
        except (TypeError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        if isinstance(data.get("codes"), list):
            return "Concept"
        resource_type = data.get("resourceType")
        if resource_type in ("ValueSet", "CodeSystem"):
            return resource_type
        if "id" in data and "code" not in data:
            return "Vocabulary"
        if "code" in data:
            return "Code"
        return None

    def _clinical_type_matches(self, actual_type: str, target_type: str) -> bool:
        """Return true when actual CQL clinical type conforms to target type."""
        actual = self._CLINICAL_CQL_TYPES.get(actual_type.lower(), actual_type)
        target = self._CLINICAL_CQL_TYPES.get(target_type.lower(), target_type)
        if target == "Vocabulary":
            return actual in self._VOCABULARY_SUBTYPES
        return actual == target

    @staticmethod
    def _split_top_level_type_args(text: str) -> list[str]:
        """Split comma-separated type arguments without splitting nested types."""
        parts: list[str] = []
        start = 0
        angle_depth = 0
        brace_depth = 0
        for idx, char in enumerate(text):
            if char == "<":
                angle_depth += 1
            elif char == ">":
                angle_depth = max(0, angle_depth - 1)
            elif char == "{":
                brace_depth += 1
            elif char == "}":
                brace_depth = max(0, brace_depth - 1)
            elif char == "," and angle_depth == 0 and brace_depth == 0:
                part = text[start:idx].strip()
                if part:
                    parts.append(part)
                start = idx + 1
        tail = text[start:].strip()
        if tail:
            parts.append(tail)
        return parts

    @staticmethod
    def _split_top_level_field(text: str) -> tuple[str, str] | None:
        """Split ``name: Type`` for tuple type fields at the top-level colon."""
        angle_depth = 0
        brace_depth = 0
        for idx, char in enumerate(text):
            if char == "<":
                angle_depth += 1
            elif char == ">":
                angle_depth = max(0, angle_depth - 1)
            elif char == "{":
                brace_depth += 1
            elif char == "}":
                brace_depth = max(0, brace_depth - 1)
            elif char == ":" and angle_depth == 0 and brace_depth == 0:
                name = text[:idx].strip()
                value = text[idx + 1:].strip()
                if name and value:
                    return name, value
                return None
        return None

    def _normalize_structural_type_name(self, type_name: str) -> str:
        """Normalize namespaces inside structural type names for comparison."""
        name = str(type_name).strip()
        if name.startswith("List<") and name.endswith(">"):
            inner = self._normalize_structural_type_name(name[len("List<"):-1])
            return f"List<{inner}>"
        if name.startswith("Interval<") and name.endswith(">"):
            inner = self._normalize_structural_type_name(name[len("Interval<"):-1])
            return f"Interval<{inner}>"
        if name.startswith("Choice<") and name.endswith(">"):
            choices = [
                self._normalize_structural_type_name(part)
                for part in self._split_top_level_type_args(name[len("Choice<"):-1])
            ]
            return f"Choice<{', '.join(choices)}>"
        if name.startswith("Tuple {") and name.endswith("}"):
            inner = name[len("Tuple {"):-1].strip()
            fields = []
            for part in self._split_top_level_type_args(inner):
                field = self._split_top_level_field(part)
                if field is None:
                    continue
                field_name, field_type = field
                fields.append(
                    f"{field_name}: {self._normalize_structural_type_name(field_type)}"
                )
            return f"Tuple {{ {', '.join(fields)} }}"
        return self._bare_cql_type_name(name) or name

    def _tuple_type_elements_from_name(self, type_name: str) -> dict[str, str] | None:
        name = self._normalize_structural_type_name(type_name)
        if not (name.startswith("Tuple {") and name.endswith("}")):
            return None
        inner = name[len("Tuple {"):-1].strip()
        result: dict[str, str] = {}
        if not inner:
            return result
        for part in self._split_top_level_type_args(inner):
            field = self._split_top_level_field(part)
            if field is None:
                return None
            field_name, field_type = field
            result[field_name] = field_type
        return result

    def _type_specifier_name(self, specifier: Any) -> str:
        """Return a stable CQL type name for supported structural specifiers."""
        if isinstance(specifier, NamedTypeSpecifier):
            return specifier.name
        if isinstance(specifier, ListTypeSpecifier):
            return f"List<{self._type_specifier_name(specifier.element_type)}>"
        if isinstance(specifier, IntervalTypeSpecifier):
            return f"Interval<{self._type_specifier_name(specifier.point_type)}>"
        if isinstance(specifier, ChoiceTypeSpecifier):
            choices = ", ".join(
                self._type_specifier_name(choice)
                for choice in specifier.choices
            )
            return f"Choice<{choices}>"
        if isinstance(specifier, TupleTypeSpecifier):
            elements = ", ".join(
                f"{element.name}: {self._type_specifier_name(element.type)}"
                for element in specifier.elements
            )
            return f"Tuple {{ {elements} }}"
        return str(specifier)

    def _ensure_known_type_specifier_target(self, specifier: Any, operator: str) -> None:
        """Validate named leaves inside composite CQL type specifiers."""
        if isinstance(specifier, NamedTypeSpecifier):
            self._ensure_known_named_type_target(specifier.name, operator)
            return
        if isinstance(specifier, ListTypeSpecifier):
            self._ensure_known_type_specifier_target(specifier.element_type, operator)
            return
        if isinstance(specifier, IntervalTypeSpecifier):
            self._ensure_known_type_specifier_target(specifier.point_type, operator)
            return
        if isinstance(specifier, ChoiceTypeSpecifier):
            for choice in specifier.choices:
                self._ensure_known_type_specifier_target(choice, operator)
            return
        if isinstance(specifier, TupleTypeSpecifier):
            for element in specifier.elements:
                self._ensure_known_type_specifier_target(element.type, operator)
            return

    def _static_structural_type_name(self, node: Any) -> Optional[str]:
        """Infer exact CQL structural type when it is known before SQL execution."""
        if isinstance(node, UnaryExpression):
            operator = node.operator.lower() if isinstance(node.operator, str) else node.operator
            if operator == "singleton from":
                operand_type = self._static_structural_type_name(node.operand)
                if operand_type and operand_type.startswith("List<") and operand_type.endswith(">"):
                    return operand_type[5:-1]
                return operand_type
        if isinstance(node, DateTimeLiteral):
            if node.value.startswith("T"):
                return "Time"
            return "DateTime" if "T" in node.value else "Date"
        if isinstance(node, TimeLiteral):
            return "Time"
        if isinstance(node, Quantity):
            return "Quantity"
        if isinstance(node, InstanceExpression):
            bare = self._bare_cql_type_name(node.type)
            return bare
        if isinstance(node, TupleExpression):
            elements = []
            for element in node.elements:
                element_type = self._static_structural_type_name(element.type) or "Any"
                elements.append(f"{element.name}: {element_type}")
            return f"Tuple {{ {', '.join(elements)} }}"
        if isinstance(node, CodeSelector):
            return "Code"
        if isinstance(node, Literal):
            if node.value is None:
                return None
            literal_type = getattr(node, "type", None)
            if literal_type:
                return literal_type
            if isinstance(node.value, bool):
                return "Boolean"
            if isinstance(node.value, int):
                return "Integer"
            if isinstance(node.value, float):
                return "Decimal"
            if isinstance(node.value, str):
                return "String"
        if isinstance(node, ListExpression):
            element_types = [
                self._static_structural_type_name(element)
                for element in node.elements
            ]
            known = [item for item in element_types if item is not None]
            if not known:
                return "List<Any>"
            first = known[0]
            if all(item == first for item in known):
                return f"List<{first}>"
            return "List<Any>"
        if isinstance(node, Interval):
            point_types = []
            if node.low is not None:
                point_types.append(self._static_structural_type_name(node.low))
            if node.high is not None:
                point_types.append(self._static_structural_type_name(node.high))
            known = [item for item in point_types if item is not None]
            if not known:
                return "Interval<Any>"
            first = known[0]
            if all(item == first for item in known):
                return f"Interval<{first}>"
            return "Interval<Any>"
        if isinstance(node, FunctionRef):
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
                "date": "Date",
                "datetime": "DateTime",
                "time": "Time",
                "today": "Date",
                "now": "DateTime",
                "timeofday": "Time",
                "abs": "Decimal",
                "ceiling": "Integer",
                "floor": "Integer",
                "exp": "Decimal",
                "log": "Decimal",
                "ln": "Decimal",
            }.get(node.name.lower())
        if isinstance(node, Query):
            sources = node.source if isinstance(node.source, list) else [node.source]
            if node.return_clause and getattr(node.return_clause, "expression", None) is not None:
                returned = node.return_clause.expression
                if isinstance(returned, Identifier):
                    for source in sources:
                        if isinstance(source, QuerySource) and source.alias == returned.name:
                            return self._static_structural_type_name(source.expression)
                return self._static_structural_type_name(returned)
            if len(sources) == 1 and isinstance(sources[0], QuerySource):
                source_type = self._static_structural_type_name(sources[0].expression)
                if source_type and source_type.startswith("List<") and source_type.endswith(">"):
                    return source_type[5:-1]
                return source_type
        if isinstance(node, BinaryExpression):
            operator = node.operator.lower() if isinstance(node.operator, str) else node.operator
            if operator == "as":
                target = node.right
                if isinstance(target, NamedTypeSpecifier):
                    bare_target = target.name.split(".")[-1]
                    source_type = self._static_structural_type_name(node.left)
                    if bare_target == "Any":
                        return source_type
                    if (
                        bare_target == "Vocabulary"
                        and source_type in self._VOCABULARY_SUBTYPES
                    ):
                        return source_type
                    return target.name
                if isinstance(target, Identifier):
                    bare_target = target.name.split(".")[-1]
                    source_type = self._static_structural_type_name(node.left)
                    if bare_target == "Any":
                        return source_type
                    if (
                        bare_target == "Vocabulary"
                        and source_type in self._VOCABULARY_SUBTYPES
                    ):
                        return source_type
                    return target.name
                if isinstance(target, (ListTypeSpecifier, IntervalTypeSpecifier, ChoiceTypeSpecifier, TupleTypeSpecifier)):
                    target_name = self._type_specifier_name(target)
                    source_type = self._static_structural_type_name(node.left)
                    if source_type and self._structural_type_conforms(source_type, target_name):
                        return source_type
                    return target_name
            if operator == "convert":
                target = node.right
                if isinstance(target, NamedTypeSpecifier):
                    bare_target = self._bare_cql_type_name(target.name)
                    if bare_target == "Any":
                        return self._static_structural_type_name(node.left)
                    return target.name
                if isinstance(target, Identifier):
                    bare_target = self._bare_cql_type_name(target.name)
                    if bare_target == "Any":
                        return self._static_structural_type_name(node.left)
                    return target.name
                if isinstance(target, (ListTypeSpecifier, IntervalTypeSpecifier, ChoiceTypeSpecifier, TupleTypeSpecifier)):
                    return self._type_specifier_name(target)
        if isinstance(node, Identifier):
            if node.name in self.context.valuesets:
                return "ValueSet"
            if node.name in self.context.codesystems:
                return "CodeSystem"
            code_info = self.context.codes.get(node.name)
            if code_info:
                return "Concept" if code_info.get("is_concept") else "Code"
            meta = self.context.definition_meta.get(node.name)
            if meta and meta.cql_type and meta.cql_type != "Any":
                return meta.cql_type
            ast_def = self._definition_source_ast(node.name, node)
            if ast_def is not None and ast_def is not node:
                return self._static_structural_type_name(ast_def)
        if isinstance(node, Property) and isinstance(node.source, Identifier):
            source_ast = self.context._alias_source_asts.get(node.source.name)
            field_type = self._static_tuple_field_type(source_ast, node.path)
            if field_type:
                return field_type
        return None

    def _static_tuple_field_type(
        self,
        source_ast: Any,
        field_name: str,
        _depth: int = 0,
    ) -> Optional[str]:
        """Infer a tuple field type from a static query/list source."""
        if source_ast is None or _depth > 6:
            return None
        if isinstance(source_ast, ListExpression):
            field_types = [
                self._static_tuple_field_type(element, field_name, _depth + 1)
                for element in source_ast.elements
            ]
            known = [field_type for field_type in field_types if field_type]
            if not known:
                return None
            first = known[0]
            if all(field_type == first for field_type in known):
                return first
            return None
        if isinstance(source_ast, TupleExpression):
            for element in source_ast.elements:
                if element.name != field_name:
                    continue
                static_type = self._static_structural_type_name(element.type)
                if static_type:
                    return static_type
                inferred_type = self._infer_cql_type(element.type)
                return inferred_type if inferred_type != "Any" else None
        if isinstance(source_ast, Query):
            ret_expr = (
                source_ast.return_clause.expression
                if source_ast.return_clause is not None
                else None
            )
            if isinstance(ret_expr, TupleExpression):
                return self._static_tuple_field_type(ret_expr, field_name, _depth + 1)
            if isinstance(ret_expr, Identifier):
                sources = source_ast.source if isinstance(source_ast.source, list) else [source_ast.source]
                for source in sources:
                    if isinstance(source, QuerySource) and source.alias == ret_expr.name:
                        return self._static_tuple_field_type(source.expression, field_name, _depth + 1)
        if isinstance(source_ast, Identifier):
            meta = self.context.definition_meta.get(source_ast.name)
            if meta and meta.quantity_fields and field_name in meta.quantity_fields:
                return "Quantity"
            field_type = self._definition_tuple_field_type(source_ast.name, field_name, set())
            return field_type if field_type and field_type != "Any" else None
        return None

    def _is_static_non_null_structural_value(self, node: Any) -> bool:
        """Return true for AST values whose non-nullness is compile-time known."""
        if isinstance(node, (Quantity, DateTimeLiteral, TimeLiteral, ListExpression, Interval, InstanceExpression, TupleExpression, CodeSelector)):
            return True
        if isinstance(node, Literal):
            return node.value is not None
        if isinstance(node, Identifier):
            if (
                node.name in self.context.valuesets
                or node.name in self.context.codesystems
                or node.name in self.context.codes
            ):
                return True
            ast_defs = getattr(self.context, "_definition_cql_asts", {})
            ast_def = ast_defs.get(node.name)
            if ast_def is not None and ast_def is not node:
                return self._is_static_non_null_structural_value(ast_def)
        return False

    def _definition_ast_for_identifier(self, node: Any) -> Optional[Any]:
        if isinstance(node, Identifier):
            ast_def = self._definition_source_ast(node.name, node)
            if ast_def is not None and ast_def is not node:
                return ast_def
        return None

    def _definition_source_ast(self, name: str, current: Any = None) -> Optional[Any]:
        """Return the original CQL AST for a definition when available."""
        ast_defs = getattr(self.context, "_definition_cql_asts", {})
        ast_def = ast_defs.get(name)
        if ast_def is None:
            ast_def = self.context.expression_definitions.get(name)
        if ast_def is current:
            return None
        return ast_def

    def _static_conversion_source_node(self, node: Any) -> Optional[Any]:
        """Return the definition body for conversion operands that are safe to inline.

        Expression-level translation commonly turns definition references into
        patient-correlated CTE lookups. That is correct for data-dependent
        definitions, but literal/static aliases used by conversion operators
        should retain their scalar expression shape.
        """
        source = self._definition_ast_for_identifier(node)
        if source is not None and self._is_static_conversion_inline_candidate(source):
            return source
        return None

    def _is_static_conversion_inline_candidate(self, node: Any, depth: int = 0) -> bool:
        """True when *node* is a scalar expression with no retrieve/query dependency."""
        if depth > 8:
            return False
        if isinstance(node, (Literal, Quantity, DateTimeLiteral, TimeLiteral, CodeSelector)):
            return True
        if isinstance(node, InstanceExpression):
            return True
        if isinstance(node, Identifier):
            if (
                node.name in self.context.valuesets
                or node.name in self.context.codesystems
                or node.name in self.context.codes
            ):
                return True
            source = self._definition_ast_for_identifier(node)
            return (
                source is not None
                and self._is_static_conversion_inline_candidate(source, depth + 1)
            )
        if isinstance(node, FunctionRef):
            static_functions = {
                "canconvertquantity",
                "convertquantity",
                "convertstoboolean",
                "convertstodate",
                "convertstodatetime",
                "convertstodecimal",
                "convertstointeger",
                "convertstolong",
                "convertstoquantity",
                "convertstoratio",
                "convertstostring",
                "convertstotime",
                "date",
                "datetime",
                "time",
                "toboolean",
                "toconcept",
                "todate",
                "todatetime",
                "todecimal",
                "tointeger",
                "tolong",
                "toquantity",
                "toratio",
                "tostring",
                "totime",
            }
            if node.name.lower() not in static_functions:
                return False
            return all(
                self._is_static_conversion_inline_candidate(arg, depth + 1)
                for arg in (node.arguments or [])
            )
        if isinstance(node, BinaryExpression):
            operator = node.operator.lower() if isinstance(node.operator, str) else node.operator
            if operator in {"as", "convert"}:
                return self._is_static_conversion_inline_candidate(node.left, depth + 1)
            return (
                self._is_static_conversion_inline_candidate(node.left, depth + 1)
                and self._is_static_conversion_inline_candidate(node.right, depth + 1)
            )
        if isinstance(node, UnaryExpression):
            return self._is_static_conversion_inline_candidate(node.operand, depth + 1)
        if isinstance(node, ListExpression):
            return all(
                self._is_static_conversion_inline_candidate(item, depth + 1)
                for item in node.elements
            )
        if isinstance(node, Interval):
            return all(
                item is None or self._is_static_conversion_inline_candidate(item, depth + 1)
                for item in (node.low, node.high)
            )
        if isinstance(node, TupleExpression):
            return all(
                self._is_static_conversion_inline_candidate(element.type, depth + 1)
                for element in node.elements
            )
        return False

    def _structural_type_conforms(self, actual_type: str, target_type: str) -> bool:
        """Return true when a statically known CQL type conforms to a target."""
        actual = self._normalize_structural_type_name(actual_type)
        target = self._normalize_structural_type_name(target_type)
        if target in ("Any", "any"):
            return True
        if target == "Vocabulary" and actual in self._VOCABULARY_SUBTYPES:
            return True
        if actual.startswith("Choice<") and actual.endswith(">") and target.startswith("Choice<") and target.endswith(">"):
            actual_choices = self._split_top_level_type_args(actual[len("Choice<"):-1])
            target_choices = self._split_top_level_type_args(target[len("Choice<"):-1])
            return all(
                any(self._structural_type_conforms(actual_choice, target_choice) for target_choice in target_choices)
                for actual_choice in actual_choices
            )
        if target.startswith("Choice<") and target.endswith(">"):
            choices = self._split_top_level_type_args(target[len("Choice<"):-1])
            return any(self._structural_type_conforms(actual, choice) for choice in choices)
        if actual.startswith("Choice<") and actual.endswith(">"):
            return False
        if actual == target:
            return True
        if actual.startswith("List<") and target.startswith("List<"):
            actual_inner = actual[len("List<"):-1]
            target_inner = target[len("List<"):-1]
            return self._structural_type_conforms(actual_inner, target_inner)
        if actual.startswith("Interval<") and target.startswith("Interval<"):
            actual_inner = actual[len("Interval<"):-1]
            target_inner = target[len("Interval<"):-1]
            return self._structural_type_conforms(actual_inner, target_inner)
        actual_tuple = self._tuple_type_elements_from_name(actual)
        target_tuple = self._tuple_type_elements_from_name(target)
        if actual_tuple is not None and target_tuple is not None:
            for field_name, target_field_type in target_tuple.items():
                actual_field_type = actual_tuple.get(field_name)
                if actual_field_type is None:
                    return False
                if not self._structural_type_conforms(actual_field_type, target_field_type):
                    return False
            return True
        return False

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
                from ..patterns.retrieve import _VALUESET_PREFIX_CONFIG
                default_prefix = _VALUESET_PREFIX_CONFIG.get("default_prefix", "http://cts.nlm.nih.gov/fhir/ValueSet/")
                valueset = f"{default_prefix}{valueset}"

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

    # ------------------------------------------------------------------
    # Let-clause processing with CTE promotion
    # ------------------------------------------------------------------

    # Minimum reference count to promote a let variable to a CTE.
    # Below this threshold, the let expression is inlined at every reference.
    _LET_CTE_THRESHOLD = 3

    def _count_let_refs(self, ast_node, var_name: int) -> int:
        """Count how many times *var_name* appears as an Identifier in an AST subtree."""
        return self._count_let_refs_many(ast_node, {var_name}).get(var_name, 0)

    def _count_let_refs_many(self, ast_node, var_names: set[str]) -> dict[str, int]:
        """Count Identifier references for multiple let variables in one AST walk."""
        if not var_names:
            return {}

        counts = {name: 0 for name in var_names}
        # Use a stack to avoid recursion on deep ASTs
        stack = [ast_node]
        while stack:
            n = stack.pop()
            if n is None:
                continue
            if isinstance(n, Identifier) and id(n) != id(ast_node):
                # Use object identity on the `name` field isn't reliable
                # because Identifier may be subclassed; compare by name.
                name = getattr(n, 'name', None)
                if name in counts:
                    counts[name] += 1
                continue
            # Recurse into common AST node children
            for child in self._ast_children(n):
                stack.append(child)
        return counts

    @staticmethod
    def _ast_children(node) -> list:
        """Yield direct children of an AST node for tree walking."""
        children = []
        if hasattr(node, '__dataclass_fields__'):
            for f in node.__dataclass_fields__:
                v = getattr(node, f, None)
                if isinstance(v, list):
                    children.extend(v)
                elif hasattr(v, '__dataclass_fields__'):
                    children.append(v)
        # Handle tuple children (e.g., SQLCase when_clauses)
        return children

    def _rewrite_outer_aliases(self, ast_node, new_alias: str):
        """Rewrite outer-scope references in a SQL AST subtree for CTE bodies.

        When a let variable is promoted to a CTE, its expression may contain
        references that are only valid in the outer query scope:

        1. ``_pt`` qualified identifiers (the ``_patients`` table alias) are
           rewritten to use *new_alias* (the resource alias available in the
           CTE body's FROM clause).
        2. ``_lt_X`` identifiers (lambda parameters for let variable ``X``)
           are replaced with the stored let-variable expression, making the
           CTE body self-contained.

        Returns (rewritten_node, resolved_lets set).
        Returns (None, set) if an unresolvable ``_lt_`` reference is found
        (caller should fall back to inline).
        """
        if ast_node is None or not hasattr(ast_node, '__dataclass_fields__'):
            return ast_node, set()
        stack = [ast_node]
        unresolved = False
        resolved_lets = set()

        def _try_replace_lt(ref_node):
            """If ref_node is an _lt_ identifier, return replacement or set unresolved."""
            nonlocal unresolved
            if isinstance(ref_node, SQLIdentifier) and ref_node.name.startswith("_lt_"):
                let_name = ref_node.name[4:]
                if let_name in self.context.let_variables:
                    replacement = self.context.let_variables[let_name]
                    if isinstance(replacement, SQLSubquery):
                        # Check if the referenced let CTE has a _row_key column
                        _lt_cte_name, _match_res = self._let_lookup_info(replacement)
                        if _lt_cte_name:
                            return self._make_let_cte_lookup(
                                _lt_cte_name,
                                new_alias,
                                match_resource=_match_res,
                            )
                    resolved_lets.add(let_name)
                    return replacement
                else:
                    unresolved = True
            return None  # not an _lt_ ref

        while stack:
            n = stack.pop()
            if n is None or not hasattr(n, '__dataclass_fields__'):
                continue
            for f in n.__dataclass_fields__:
                v = getattr(n, f, None)
                if v is None:
                    continue
                # Case 1: _pt.col -> new_alias.col
                if isinstance(v, SQLQualifiedIdentifier) and v.parts and v.parts[0] == "_pt":
                    object.__setattr__(v, 'parts', [new_alias] + list(v.parts[1:]))
                # Case 2: direct field is _lt_ identifier
                elif isinstance(v, SQLIdentifier):
                    repl = _try_replace_lt(v)
                    if repl is not None:
                        setattr(n, f, repl)
                # Case 3: list — scan items for _lt_ identifiers AND recurse
                elif isinstance(v, list):
                    for i, item in enumerate(v):
                        if isinstance(item, SQLIdentifier):
                            repl = _try_replace_lt(item)
                            if repl is not None:
                                v[i] = repl
                        elif isinstance(item, SQLQualifiedIdentifier) and item.parts and item.parts[0] == "_pt":
                            object.__setattr__(item, 'parts', [new_alias] + list(item.parts[1:]))
                        elif item is not None and hasattr(item, '__dataclass_fields__'):
                            stack.append(item)
                        elif isinstance(item, tuple):
                            stack.extend(item)
                # Case 4: nested dataclass
                elif hasattr(v, '__dataclass_fields__'):
                    stack.append(v)
                elif isinstance(v, tuple):
                    stack.extend(v)
        if unresolved:
            return None, resolved_lets
        return ast_node, resolved_lets

    def _resource_row_key_expr(self, source_alias: str) -> SQLExpression:
        """Build a stable per-resource key expression for row-correlated CTE lookups."""
        resource_expr = SQLQualifiedIdentifier(parts=[source_alias, "resource"])
        resource_id = SQLFunctionCall(
            name="fhirpath_text",
            args=[resource_expr, SQLLiteral(value="id")],
        )
        if self.context._alias_resource_types.get(source_alias):
            return SQLFunctionCall(
                name="COALESCE",
                args=[
                    resource_id,
                    SQLCast(expression=resource_expr, target_type="VARCHAR"),
                ],
            )

        typed_id = SQLBinaryOp(
            left=SQLBinaryOp(
                left=SQLFunctionCall(
                    name="fhirpath_text",
                    args=[resource_expr, SQLLiteral(value="resourceType")],
                ),
                operator="||",
                right=SQLLiteral(value="/"),
            ),
            operator="||",
            right=resource_id,
        )
        return SQLFunctionCall(
            name="COALESCE",
            args=[
                typed_id,
                SQLCast(expression=resource_expr, target_type="VARCHAR"),
            ],
        )

    def _sql_references_column(self, node: SQLExpression | None, column_name: str) -> bool:
        """Return True when a SQL AST subtree references *column_name*."""
        stack = [node]
        while stack:
            current = stack.pop()
            if current is None:
                continue
            if isinstance(current, SQLIdentifier) and current.name == column_name:
                return True
            if isinstance(current, SQLQualifiedIdentifier) and current.parts:
                if any(part == column_name for part in current.parts):
                    return True
            if isinstance(current, tuple):
                stack.extend(current)
                continue
            if isinstance(current, list):
                stack.extend(current)
                continue
            if not hasattr(current, "__dataclass_fields__"):
                continue
            for field_name in current.__dataclass_fields__:
                stack.append(getattr(current, field_name, None))
        return False

    def _let_lookup_info(self, lookup: SQLExpression) -> tuple[str | None, bool]:
        """Extract the CTE name and row-key usage from a let lookup subquery."""
        if not isinstance(lookup, SQLSubquery) or not isinstance(lookup.query, SQLSelect):
            return None, False
        from_clause = lookup.query.from_clause
        cte_name = None
        if (
            isinstance(from_clause, SQLAlias)
            and isinstance(from_clause.expr, SQLIdentifier)
        ):
            cte_name = from_clause.expr.name
        return cte_name, self._sql_references_column(lookup.query.where, "_row_key")

    def _generate_let_cte_name(self, let_name: str) -> str:
        """Generate a deterministic let CTE name unique to the current definition."""
        import hashlib

        scope_name = self.context._current_definition or "__unknown__"
        safe_scope = _re.sub(r"[^A-Za-z0-9_]+", "_", scope_name).strip("_") or "scope"
        safe_let = _re.sub(r"[^A-Za-z0-9_]+", "_", let_name).strip("_") or "let"
        name_hash = hashlib.md5(f"{scope_name}:{let_name}".encode()).hexdigest()[:6]
        return f"_let_{safe_scope[:32]}_{safe_let[:24]}_{name_hash}"

    def _make_let_cte_lookup(self, cte_name: str, source_alias: str,
                              match_resource: bool = False) -> SQLExpression:
        """Build a correlated lookup into a promoted let-variable CTE."""
        where_cond = SQLBinaryOp(
            left=SQLQualifiedIdentifier(parts=["_lv", "patient_id"]),
            operator="=",
            right=SQLQualifiedIdentifier(parts=[source_alias, "patient_id"]),
        )
        if match_resource:
            where_cond = SQLBinaryOp(
                left=where_cond,
                operator="AND",
                right=SQLBinaryOp(
                    left=SQLQualifiedIdentifier(parts=["_lv", "_row_key"]),
                    operator="=",
                    right=self._resource_row_key_expr(source_alias),
                ),
            )
        return SQLSubquery(query=SQLSelect(
            columns=[SQLIdentifier(name="value")],
            from_clause=SQLAlias(
                expr=SQLIdentifier(name=cte_name, quoted=True),
                alias="_lv",
            ),
            where=where_cond,
        ))

    def _make_function_cte_lookup(self, cte_name: str, source_alias: str) -> SQLExpression:
        """Build (SELECT value FROM fn_cte WHERE patient_id AND _row_key = fhirpath_text(resource, 'id'))."""
        where_cond = SQLBinaryOp(
            left=SQLBinaryOp(
                left=SQLQualifiedIdentifier(parts=["_fv", "patient_id"]),
                operator="=",
                right=SQLQualifiedIdentifier(parts=[source_alias, "patient_id"]),
            ),
            operator="AND",
            right=SQLBinaryOp(
                left=SQLQualifiedIdentifier(parts=["_fv", "_row_key"]),
                operator="=",
                right=SQLFunctionCall(
                    name="fhirpath_text",
                    args=[
                        SQLQualifiedIdentifier(parts=[source_alias, "resource"]),
                        SQLLiteral(value="id"),
                    ],
                ),
            ),
        )
        return SQLSubquery(query=SQLSelect(
            columns=[SQLIdentifier(name="value")],
            from_clause=SQLAlias(
                expr=SQLIdentifier(name=cte_name, quoted=True),
                alias="_fv",
            ),
            where=where_cond,
        ))

    def _process_let_clauses(self, let_clauses: list, node=None) -> None:
        """Translate let clauses and register them in context.let_variables.

        For let variables referenced >= _LET_CTE_THRESHOLD times in the body
        (WHERE + RETURN), promotes the variable to a CTE and registers a
        lightweight lookup subquery instead of the full expression.

        Each variable is registered immediately so that subsequent let clauses
        in the same batch can reference earlier ones.
        """
        # Phase 1: count effective references for each let variable.
        # A let referenced only once directly may still be expanded many times
        # through downstream lets.  Walk the let chain backwards so promotion
        # decisions reflect the final inlined cost, not just direct mentions.
        ref_counts = {}
        if node is not None:
            let_names = {let_clause.alias for let_clause in let_clauses}
            body_ref_counts = {name: 0 for name in let_names}
            let_deps = {name: {} for name in let_names}

            if hasattr(node, 'where') and node.where:
                where_counts = self._count_let_refs_many(node.where, let_names)
                for name, count in where_counts.items():
                    body_ref_counts[name] += count
            if hasattr(node, 'return_clause') and node.return_clause:
                return_counts = self._count_let_refs_many(node.return_clause, let_names)
                for name, count in return_counts.items():
                    body_ref_counts[name] += count

            for let_clause in let_clauses:
                deps = let_deps[let_clause.alias]
                dep_counts = self._count_let_refs_many(let_clause.expression, let_names)
                for dep_name, dep_count in dep_counts.items():
                    if dep_name == let_clause.alias:
                        continue
                    if dep_count:
                        deps[dep_name] = dep_count

            ref_counts = dict(body_ref_counts)
            for let_clause in reversed(let_clauses):
                name = let_clause.alias
                multiplier = ref_counts.get(name, 0)
                if multiplier <= 0:
                    continue
                for dep_name, dep_count in let_deps.get(name, {}).items():
                    ref_counts[dep_name] = ref_counts.get(dep_name, 0) + (
                        multiplier * dep_count
                    )

        # Phase 2: translate each let clause and decide inline vs CTE.
        for let_clause in let_clauses:
            let_name = let_clause.alias
            _is_coll = isinstance(let_clause.expression, (Query, Retrieve))
            if _is_coll:
                self.context._let_clause_collection = True
            let_expr_sql = self.translate(let_clause.expression, usage=ExprUsage.SCALAR)
            if _is_coll:
                self.context._let_clause_collection = False
                let_expr_sql = _wrap_as_json_array_agg(let_expr_sql)

            # Decide: promote to CTE or inline?
            if (
                ref_counts.get(let_name, 0) >= self._LET_CTE_THRESHOLD
                and self.context.resource_alias
                and not _is_coll  # collection-typed lets can't be promoted
            ):
                self._promote_let_to_cte(let_name, let_expr_sql)
            else:
                self.context.let_variables[let_name] = let_expr_sql

    def _promote_let_to_cte(self, let_name: str, let_expr_sql: SQLExpression) -> None:
        """Promote a let variable to a CTE and register a lookup expression."""
        alias = self.context.resource_alias
        # Find the source CTE name from the symbol table
        cte_name = None
        sym = self.context.lookup_symbol(alias)
        if sym and sym.cte_name:
            cte_name = sym.cte_name

        if not cte_name:
            # Can't determine source — fall back to inline
            self.context.let_variables[let_name] = let_expr_sql
            return

        if (
            getattr(self.context, "_building_function_promotion_cte", False)
            and self._references_foreign_table_alias(let_expr_sql, alias)
        ):
            self.context.let_variables[let_name] = let_expr_sql
            return

        # Fix outer-scope references in let_expr_sql.
        # Inside the CTE body, only {alias} is available as a table alias.
        # Expressions translated in the outer query scope may reference:
        #  - _pt (the _patients table alias) -> rewrite to alias
        #  - _lt_X (lambda parameters for other let vars) -> substitute expressions
        # If any _lt_ reference can't be resolved, fall back to inline.
        fixed_expr, _resolved = self._rewrite_outer_aliases(let_expr_sql, alias)
        if fixed_expr is None:
            self.context.let_variables[let_name] = let_expr_sql
            return

        # Check if source CTE has a resource column.  Patient-only lookups are
        # ambiguous for multi-row resource sources, so resource-backed CTEs add
        # a row key derived from resourceType/id with full-resource fallback.
        meta = self.context.definition_meta.get(cte_name)
        _has_resource = bool(
            (meta.has_resource if meta else False)
            or self.context._alias_resource_types.get(alias)
        )

        let_cte_name = self._generate_let_cte_name(let_name)
        columns = [
            SQLQualifiedIdentifier(parts=[alias, "patient_id"]),
        ]
        if _has_resource:
            columns.append(SQLAlias(
                expr=self._resource_row_key_expr(alias),
                alias="_row_key",
            ))
        columns.append(SQLAlias(expr=fixed_expr, alias="value"))

        let_cte_body = SQLSelect(
            columns=columns,
            from_clause=SQLAlias(
                expr=SQLIdentifier(name=cte_name, quoted=True),
                alias=alias,
            ),
        )

        # Register the CTE grouped by the current definition name.
        # This allows injection right before the definition's CTE,
        # so the let-variable CTE can reference earlier definition CTEs.
        def_name = self.context._current_definition
        if def_name is None:
            def_name = "__unknown__"
        if def_name not in self.context._let_variable_ctes:
            self.context._let_variable_ctes[def_name] = {}
        self.context._let_variable_ctes[def_name][let_cte_name] = let_cte_body

        # Register a lightweight lookup expression
        lookup = self._make_let_cte_lookup(let_cte_name, alias, match_resource=_has_resource)
        self.context.let_variables[let_name] = lookup

    @staticmethod
    def _references_foreign_table_alias(node: SQLExpression, allowed_alias: str) -> bool:
        """Detect aliases that would be out of scope in a promoted let CTE."""
        allowed = {allowed_alias.lower(), "_pt"}
        stack = [node]
        seen = set()
        while stack:
            current = stack.pop()
            if current is None:
                continue
            current_id = id(current)
            if current_id in seen:
                continue
            seen.add(current_id)
            if isinstance(current, SQLQualifiedIdentifier):
                if current.parts:
                    alias = current.parts[0].lower()
                    if alias not in allowed and not alias.startswith("_lt_"):
                        return True
                continue
            if isinstance(current, (list, tuple)):
                stack.extend(current)
                continue
            if not hasattr(current, "__dataclass_fields__"):
                continue
            for field_name in current.__dataclass_fields__:
                stack.append(getattr(current, field_name, None))
        return False

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

        def _definition_has_resource_rows(name: str, visited: set[str] | None = None) -> bool:
            """Return whether a definition is resource-row shaped, including forward refs."""
            if visited is None:
                visited = set()
            if name in visited:
                return False
            visited.add(name)

            meta = self.context.definition_meta.get(name)
            if meta is not None:
                return meta.has_resource and meta.shape == RowShape.RESOURCE_ROWS

            ast_defs = getattr(self.context, "_definition_cql_asts", {})
            cql_ast = ast_defs.get(name)
            if cql_ast is None:
                expr_defs = getattr(self.context, "expression_definitions", {})
                cql_ast = expr_defs.get(name)
                if hasattr(cql_ast, "expression"):
                    cql_ast = cql_ast.expression
            if cql_ast is None:
                return False

            def _expr_has_resource_rows(expr) -> bool:
                if isinstance(expr, Retrieve):
                    return True
                if isinstance(expr, Identifier):
                    return _definition_has_resource_rows(expr.name, visited)
                if isinstance(expr, Property) and isinstance(expr.source, Identifier):
                    prefixed = f"{expr.source.name}.{expr.path}"
                    return _definition_has_resource_rows(prefixed, visited)
                if isinstance(expr, QuerySource):
                    return _expr_has_resource_rows(expr.expression)
                if isinstance(expr, Query):
                    if expr.return_clause is not None:
                        ret_expr = getattr(expr.return_clause, "expression", expr.return_clause)
                        sources = expr.source if isinstance(expr.source, list) else [expr.source]
                        if isinstance(ret_expr, Identifier):
                            for source in sources:
                                if isinstance(source, QuerySource) and source.alias == ret_expr.name:
                                    return _expr_has_resource_rows(source.expression)
                        return False
                    source = expr.source[0] if isinstance(expr.source, list) and expr.source else expr.source
                    return _expr_has_resource_rows(source)
                if isinstance(expr, BinaryExpression):
                    nested_op = getattr(expr, "operator", "")
                    if isinstance(nested_op, str) and nested_op.lower() in ("intersect", "union", "except"):
                        return (
                            _expr_has_resource_rows(expr.left)
                            or _expr_has_resource_rows(expr.right)
                        )
                return False

            return _expr_has_resource_rows(cql_ast)

        def _build_operand(expr_node):
            """Build a SELECT patient_id, resource FROM "CTE" subquery for a set operand."""
            if isinstance(expr_node, Identifier):
                name = expr_node.name
                if hasattr(self.context, '_definition_names') and name in self.context._definition_names:
                    if _definition_has_resource_rows(name):
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
            self._process_let_clauses(expanded.let_clauses, node=expanded)

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
            self._process_let_clauses(return_expr.let_clauses, node=return_expr)

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
            self._process_let_clauses(node.let_clauses, node=node)
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
        _outer_alias = self.context.resource_alias or self.context.patient_alias or "_pt"
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

        # Detect lambda scalar: symbol bound to a direct SQL expression (not a table/CTE).
        # This occurs in aggregate clause bodies where the source alias is bound to a
        # lambda parameter (e.g., M → _agg_y via add_alias(M, ast_expr=SQLIdentifier('_agg_y'))).
        _is_lambda_scalar = (
            _sym is not None
            and getattr(_sym, 'ast_expr', None) is not None
            and getattr(_sym, 'table_alias', None) is None
            and getattr(_sym, 'cte_name', None) is None
        )

        # Register inner CQL alias mapping to the real SQL table name
        if alias != source_name:
            if _is_lambda_scalar:
                # Source is a lambda scalar — bind inner alias directly to the
                # same SQL expression so that property accesses on it resolve
                # to the lambda parameter (e.g., _agg_y), not to M.resource.
                self.context.add_alias(alias, ast_expr=_sym.ast_expr)
            else:
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
        # For lambda scalars, resource_alias is not changed (no SQL table exists).
        _saved_resource_alias = self.context.resource_alias
        if not _is_lambda_scalar:
            self.context.resource_alias = source_name

        # Process let clauses
        if hasattr(node, 'let_clauses') and node.let_clauses:
            self._process_let_clauses(node.let_clauses, node=node)

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

    def _resource_type_kind_for_static_check(self, type_name: Optional[str]) -> tuple[Optional[str], bool, bool]:
        """Return (base_type, is_base_resource, is_named_profile) for a CQL type."""
        bare_type = self._bare_cql_type_name(type_name)
        if not bare_type:
            return None, False, False
        if bare_type == "Resource":
            return "Resource", True, False

        registry = getattr(self.context, "profile_registry", None)
        if registry is not None:
            negation = registry.get_negation_info(bare_type)
            if negation is not None:
                return negation[0], False, True
            resolved = registry.resolve_named_profile(bare_type)
            if resolved is not None:
                return resolved[0], False, True

        schema = getattr(self.context, "fhir_schema", None)
        if schema is not None and bare_type in getattr(schema, "resources", {}):
            return bare_type, True, False
        return None, False, False

    def _static_resource_type_check_result(
        self,
        left_operand: Any,
        target_type: str,
    ) -> Optional[bool]:
        """Resolve a resource/profile `is` check when the source type is known."""
        source_type = self._infer_resource_type_from_cql_expr(left_operand)
        source_bare = self._bare_cql_type_name(source_type)
        target_bare = self._bare_cql_type_name(target_type)
        if not source_bare or not target_bare:
            return None

        if target_bare == "Resource":
            return True
        if source_bare == target_bare:
            return True

        source_base, source_is_base_resource, _source_is_profile = (
            self._resource_type_kind_for_static_check(source_bare)
        )
        target_base, target_is_base_resource, _target_is_profile = (
            self._resource_type_kind_for_static_check(target_bare)
        )

        # A named profile is a subtype of its base resource type, so a
        # LaboratoryResultObservation source is always an Observation.
        if target_is_base_resource and source_base == target_bare:
            return True

        # Different base resources are mutually exclusive.  This safely prunes
        # branches such as Procedure source vs. Observation-profile target.
        if source_base and target_base and source_base != target_base:
            return False

        if (
            source_is_base_resource
            and target_is_base_resource
            and source_bare != target_bare
        ):
            return False

        return None

    def _extract_fhirpath_value_call(
        self,
        expr: SQLExpression,
    ) -> Optional[tuple[SQLExpression, str]]:
        """Return ``(resource, path)`` for direct FHIRPath scalar UDF calls."""
        if not isinstance(expr, SQLFunctionCall):
            return None
        if expr.name not in {
            "fhirpath_text",
            "fhirpath_number",
            "fhirpath_bool",
            "fhirpath_date",
            "fhirpath_timestamp",
            "fhirpath_json",
        }:
            return None
        if len(expr.args) < 2:
            return None
        path_arg = expr.args[1]
        if not isinstance(path_arg, SQLLiteral) or not isinstance(path_arg.value, str):
            return None
        return expr.args[0], path_arg.value

    def _fhirpath_type_name_check(
        self,
        expr: SQLExpression,
        bare_type: str,
    ) -> Optional[SQLExpression]:
        """Build a FHIRPath type().name check for direct FHIR value extracts."""
        canonical_type = _canonical_fhir_r4_type_name(bare_type)
        if canonical_type is None:
            return None
        extracted = self._extract_fhirpath_value_call(expr)
        if extracted is None:
            return None
        resource_expr, path = extracted
        type_name = SQLFunctionCall(
            name="fhirpath_text",
            args=[resource_expr, SQLLiteral(value=f"({path}).type().name")],
        )
        lowered = SQLFunctionCall(
            name="LOWER",
            args=[SQLCast(expression=type_name, target_type="VARCHAR")],
        )
        type_match = SQLBinaryOp(
            operator="=",
            left=lowered,
            right=SQLLiteral(value=canonical_type.lower()),
        )
        shape_check = self._fhir_coding_shape_check(
            SQLCast(expression=expr, target_type="VARCHAR"),
            canonical_type,
        )
        if shape_check is not None:
            ambiguous_complex_type = SQLBinaryOp(
                operator="OR",
                left=SQLBinaryOp(
                    operator="=",
                    left=lowered,
                    right=SQLLiteral(value="element"),
                ),
                right=SQLBinaryOp(
                    operator="=",
                    left=lowered,
                    right=SQLLiteral(value="backboneelement"),
                ),
            )
            type_match = SQLBinaryOp(
                operator="OR",
                left=type_match,
                right=SQLBinaryOp(
                    operator="AND",
                    left=ambiguous_complex_type,
                    right=shape_check,
                ),
            )
        return SQLBinaryOp(
            operator="AND",
            left=SQLBinaryOp(operator="IS NOT", left=type_name, right=SQLNull()),
            right=type_match,
        )

    def _fhir_coding_shape_check(
        self,
        text_value: SQLExpression,
        canonical_type: str,
    ) -> Optional[SQLExpression]:
        """Return a backend-parity fallback for native Coding reflection gaps."""
        if canonical_type.lower() != "coding":
            return None

        def _json_string(path: str) -> SQLExpression:
            return SQLFunctionCall(
                name="json_extract_string",
                args=[text_value, SQLLiteral(value=path)],
            )

        def _present(value: SQLExpression) -> SQLExpression:
            return SQLBinaryOp(operator="IS NOT", left=value, right=SQLNull())

        shape = SQLBinaryOp(
            operator="OR",
            left=_present(_json_string("$.system")),
            right=_present(_json_string("$.code")),
        )

        is_json = SQLFunctionCall(
            name="starts_with",
            args=[
                SQLFunctionCall(name="LTRIM", args=[text_value]),
                SQLLiteral(value="{"),
            ],
        )
        return SQLCase(
            when_clauses=[(is_json, shape)],
            else_clause=SQLLiteral(value=False),
        )

    def _is_cql_structural_list_expr(self, expr: SQLExpression) -> bool:
        """Return true when SQL produces a Children()/Descendants() list."""
        if isinstance(expr, SQLCast):
            return self._is_cql_structural_list_expr(expr.expression)
        if isinstance(expr, SQLCase):
            branch_values = [result for _, result in expr.when_clauses]
            if expr.else_clause is not None:
                branch_values.append(expr.else_clause)
            return any(self._is_cql_structural_list_expr(item) for item in branch_values)
        if isinstance(expr, SQLFunctionCall):
            name = expr.name.lower()
            if name in {"cqlchildren", "cqldescendants"}:
                return True
        return False

    def _is_cql_structural_item_expr(self, expr: SQLExpression) -> bool:
        """Return true when SQL produces one item from Children()/Descendants()."""
        if isinstance(expr, SQLCast):
            return self._is_cql_structural_item_expr(expr.expression)
        if isinstance(expr, SQLCase):
            branch_values = [result for _, result in expr.when_clauses]
            if expr.else_clause is not None:
                branch_values.append(expr.else_clause)
            return any(self._is_cql_structural_item_expr(item) for item in branch_values)
        if isinstance(expr, SQLFunctionCall):
            name = expr.name.lower()
            if name in {"list_extract", "array_extract", "elementat", "singletonfrom"} and expr.args:
                return self._is_cql_structural_list_expr(expr.args[0])
        return False

    @staticmethod
    def _cql_typed_value_expected_tags(bare_type: str) -> tuple[str, ...]:
        return {
            "boolean": ("Boolean",),
            "integer": ("Integer",),
            "long": ("Long",),
            "decimal": ("Decimal",),
            "string": ("String",),
            "date": ("Date",),
            "datetime": ("DateTime",),
            "time": ("Time",),
        }.get(bare_type.lower(), ())

    def _cql_typed_value_tag_condition(self, text_value: SQLExpression) -> SQLExpression:
        return SQLFunctionCall(
            name="starts_with",
            args=[
                SQLFunctionCall(name="LTRIM", args=[text_value]),
                SQLLiteral(value='{"__fhir4ds_cql_type"'),
            ],
        )

    def _cql_typed_value_type_check(
        self,
        expr: SQLExpression,
        bare_type: str,
    ) -> Optional[SQLExpression]:
        """Build a type check for one item emitted by Children()/Descendants()."""
        if not self._is_cql_structural_item_expr(expr):
            return None
        expected_tags = self._cql_typed_value_expected_tags(bare_type)
        if not expected_tags:
            return None
        text_value = SQLCast(expression=expr, target_type="VARCHAR")
        tag_type = SQLFunctionCall(
            name="json_extract_string",
            args=[text_value, SQLLiteral(value="$.__fhir4ds_cql_type")],
        )
        type_match: Optional[SQLExpression] = None
        for expected in expected_tags:
            check = SQLBinaryOp(
                operator="=",
                left=tag_type,
                right=SQLLiteral(value=expected),
            )
            type_match = check if type_match is None else SQLBinaryOp(operator="OR", left=type_match, right=check)
        if type_match is None:
            return None
        return SQLBinaryOp(
            operator="AND",
            left=self._cql_typed_value_tag_condition(text_value),
            right=type_match,
        )

    def _cql_typed_value_as_value(
        self,
        expr: SQLExpression,
        bare_type: str,
    ) -> Optional[SQLExpression]:
        """Return a typed SQL value for one Children()/Descendants() item."""
        type_check = self._cql_typed_value_type_check(expr, bare_type)
        if type_check is None:
            return None
        text_value = SQLCast(expression=expr, target_type="VARCHAR")
        raw_value = SQLFunctionCall(
            name="json_extract_string",
            args=[text_value, SQLLiteral(value="$.value")],
        )
        lower_type = bare_type.lower()
        if lower_type == "boolean":
            typed_value: SQLExpression = SQLCast(expression=raw_value, target_type="BOOLEAN", try_cast=True)
        elif lower_type == "integer":
            typed_value = SQLCast(expression=raw_value, target_type="INTEGER", try_cast=True)
        elif lower_type == "long":
            typed_value = SQLCast(expression=raw_value, target_type="BIGINT", try_cast=True)
        elif lower_type == "decimal":
            typed_value = SQLCast(expression=raw_value, target_type="DOUBLE", try_cast=True)
        elif lower_type == "string":
            typed_value = raw_value
        elif lower_type in {"date", "datetime", "time"}:
            typed_value = raw_value
        else:
            return None
        return SQLCase(when_clauses=[(type_check, typed_value)], else_clause=SQLNull())

    def _clinical_json_type_check(
        self,
        expr: SQLExpression,
        bare_type: str,
    ) -> Optional[SQLExpression]:
        """Build a runtime Code/Concept shape check for JSON clinical values."""
        target = self._CLINICAL_CQL_TYPES.get(bare_type.lower())
        if target not in {"Code", "Concept"}:
            return None
        text_value = SQLCast(expression=expr, target_type="VARCHAR")
        is_json = SQLFunctionCall(
            name="starts_with",
            args=[
                SQLFunctionCall(name="LTRIM", args=[text_value]),
                SQLLiteral(value="{"),
            ],
        )
        has_code = SQLBinaryOp(
            operator="IS NOT",
            left=SQLFunctionCall(
                name="json_extract_string",
                args=[text_value, SQLLiteral(value="$.code")],
            ),
            right=SQLNull(),
        )
        has_quantity_value = SQLBinaryOp(
            operator="IS NOT",
            left=SQLFunctionCall(
                name="json_extract_string",
                args=[text_value, SQLLiteral(value="$.value")],
            ),
            right=SQLNull(),
        )
        not_quantity = SQLUnaryOp(operator="NOT", operand=has_quantity_value)
        code_match = SQLBinaryOp(operator="AND", left=has_code, right=not_quantity)

        has_cql_concept_code = SQLBinaryOp(
            operator="IS NOT",
            left=SQLFunctionCall(
                name="json_extract_string",
                args=[text_value, SQLLiteral(value="$.codes[0].code")],
            ),
            right=SQLNull(),
        )
        has_fhir_codeable_concept_code = SQLBinaryOp(
            operator="IS NOT",
            left=SQLFunctionCall(
                name="json_extract_string",
                args=[text_value, SQLLiteral(value="$.coding[0].code")],
            ),
            right=SQLNull(),
        )
        concept_match = SQLBinaryOp(
            operator="OR",
            left=has_cql_concept_code,
            right=has_fhir_codeable_concept_code,
        )
        match = code_match if target == "Code" else concept_match
        return SQLCase(
            when_clauses=[(is_json, match)],
            else_clause=SQLLiteral(value=False),
        )

    def _cql_structural_list_type_check(
        self,
        expr: SQLExpression,
        type_name: str,
    ) -> Optional[SQLExpression]:
        """Build a List<T> type check for Children()/Descendants() results."""
        if not self._is_cql_structural_list_expr(expr):
            return None
        normalized = self._normalize_structural_type_name(type_name)
        if not (normalized.startswith("List<") and normalized.endswith(">")):
            return None

        not_null = SQLBinaryOp(operator="IS NOT", left=expr, right=SQLNull())
        inner_type = normalized[len("List<"):-1]
        if inner_type in ("Any", "any"):
            return not_null

        expected_tags = self._cql_typed_value_expected_tags(inner_type)
        if not expected_tags:
            return None

        item = SQLIdentifier(name="_cql_item")
        text_value = SQLCast(expression=item, target_type="VARCHAR")
        tag_type = SQLFunctionCall(
            name="json_extract_string",
            args=[text_value, SQLLiteral(value="$.__fhir4ds_cql_type")],
        )
        type_match: Optional[SQLExpression] = None
        for expected in expected_tags:
            check = SQLBinaryOp(
                operator="=",
                left=tag_type,
                right=SQLLiteral(value=expected),
            )
            type_match = check if type_match is None else SQLBinaryOp(operator="OR", left=type_match, right=check)
        if type_match is None:
            return None

        item_matches = SQLCase(
            when_clauses=[(self._cql_typed_value_tag_condition(text_value), type_match)],
            else_clause=SQLLiteral(value=False),
        )
        invalid_item = SQLBinaryOp(
            operator="AND",
            left=SQLBinaryOp(operator="IS NOT", left=item, right=SQLNull()),
            right=SQLUnaryOp(operator="NOT", operand=item_matches),
        )
        invalid_items = SQLFunctionCall(
            name="list_filter",
            args=[expr, SQLLambda(param="_cql_item", body=invalid_item)],
        )
        no_invalid_items = SQLBinaryOp(
            operator="=",
            left=SQLFunctionCall(
                name="array_length",
                args=[invalid_items, SQLLiteral(value=1)],
            ),
            right=SQLLiteral(value=0),
        )
        return SQLCase(
            when_clauses=[(not_null, no_invalid_items)],
            else_clause=SQLLiteral(value=False),
        )

    def _fhirpath_primitive_type_check(
        self,
        expr: SQLExpression,
        bare_type: str,
    ) -> Optional[SQLExpression]:
        """Build a runtime primitive type check for direct FHIRPath values."""
        extracted = self._extract_fhirpath_value_call(expr)
        if extracted is None:
            return None
        resource_expr, path = extracted
        expected_names = {
            "boolean": ("boolean",),
            "integer": ("integer",),
            "long": ("long", "integer64"),
            "decimal": ("decimal",),
            "string": ("string",),
            "date": ("date",),
            "datetime": ("datetime",),
            "instant": ("instant",),
            "time": ("time",),
        }.get(bare_type.lower())
        if not expected_names:
            return None

        type_name = SQLFunctionCall(
            name="fhirpath_text",
            args=[resource_expr, SQLLiteral(value=f"({path}).type().name")],
        )
        lowered = SQLFunctionCall(
            name="LOWER",
            args=[SQLCast(expression=type_name, target_type="VARCHAR")],
        )
        match: Optional[SQLExpression] = None
        for expected in expected_names:
            check = SQLBinaryOp(
                operator="=",
                left=lowered,
                right=SQLLiteral(value=expected),
            )
            match = check if match is None else SQLBinaryOp(operator="OR", left=match, right=check)
        if match is None:
            return None
        not_null = SQLBinaryOp(operator="IS NOT", left=type_name, right=SQLNull())
        return SQLBinaryOp(operator="AND", left=not_null, right=match)

    def _fhirpath_primitive_as_value(
        self,
        expr: SQLExpression,
        bare_type: str,
    ) -> Optional[SQLExpression]:
        """Return the typed SQL value for a direct FHIRPath primitive `as`."""
        extracted = self._extract_fhirpath_value_call(expr)
        if extracted is None:
            return None
        resource_expr, path = extracted
        text_value = SQLFunctionCall(
            name="fhirpath_text",
            args=[resource_expr, SQLLiteral(value=path)],
        )
        lower_type = bare_type.lower()
        if lower_type == "boolean":
            return SQLFunctionCall(
                name="fhirpath_bool",
                args=[resource_expr, SQLLiteral(value=path)],
            )
        if lower_type == "integer":
            return SQLCast(expression=text_value, target_type="INTEGER", try_cast=True)
        if lower_type == "long":
            return SQLCast(expression=text_value, target_type="BIGINT", try_cast=True)
        if lower_type == "decimal":
            return SQLCast(expression=text_value, target_type="DOUBLE", try_cast=True)
        if lower_type == "string":
            return text_value
        return None

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
        if isinstance(expr.right, IntervalTypeSpecifier):
            type_name = self._type_specifier_name(expr.right)
            self._ensure_known_type_specifier_target(expr.right, "is")
        elif isinstance(expr.right, ListTypeSpecifier):
            type_name = self._type_specifier_name(expr.right)
            self._ensure_known_type_specifier_target(expr.right, "is")
        elif isinstance(expr.right, (ChoiceTypeSpecifier, TupleTypeSpecifier)):
            type_name = self._type_specifier_name(expr.right)
            self._ensure_known_type_specifier_target(expr.right, "is")
        else:
            type_name = expr.right.name
            self._ensure_known_named_type_target(type_name, "is")

        # Strip FHIR/CQL namespace prefix for type matching
        bare_type = type_name.split(".")[-1] if "." in type_name else type_name

        if bare_type in ("Any", "any"):
            left = self.translate(expr.left, usage=ExprUsage.SCALAR)
            return SQLBinaryOp(
                operator="IS NOT",
                left=left,
                right=SQLNull(),
            )

        static_type = self._static_structural_type_name(expr.left)
        if static_type:
            normalized_static_type = self._normalize_structural_type_name(static_type)
            normalized_target_type = self._normalize_structural_type_name(type_name)
            choice_needs_runtime_check = (
                normalized_static_type.startswith("Choice<")
                and not normalized_target_type.startswith("Choice<")
            )
            if not choice_needs_runtime_check:
                if self._structural_type_conforms(static_type, type_name):
                    if self._is_static_non_null_structural_value(expr.left):
                        return SQLLiteral(value=True)
                    source_node = self._definition_ast_for_identifier(expr.left) or expr.left
                    left = self.translate(source_node, usage=ExprUsage.SCALAR)
                    return SQLBinaryOp(operator="IS NOT", left=left, right=SQLNull())
                return SQLLiteral(value=False)

        if isinstance(expr.right, ChoiceTypeSpecifier):
            combined: Optional[SQLExpression] = None
            for choice in expr.right.choices:
                check = self._translate_is_type_check(
                    BinaryExpression(operator="is", left=expr.left, right=choice)
                )
                combined = check if combined is None else SQLBinaryOp(operator="OR", left=combined, right=check)
            return combined if combined is not None else SQLLiteral(value=False)

        _PRIMITIVE_TYPES = {
            "DateTime", "dateTime", "Date", "date", "Time", "time",
            "String", "string", "Boolean", "boolean", "Integer", "integer",
            "Long", "long", "Decimal", "decimal", "instant",
        }
        if bare_type in _PRIMITIVE_TYPES and isinstance(expr.left, Identifier):
            meta = self.context.definition_meta.get(expr.left.name)
            meta_type = self._bare_cql_type_name(getattr(meta, "cql_type", None)) if meta else None
            if meta_type is None:
                symbol = self.context.lookup_symbol(expr.left.name)
                if symbol and getattr(symbol, "symbol_type", None) == "parameter":
                    meta_type = self._bare_cql_type_name(getattr(symbol, "cql_type", None))
            if meta_type in _PRIMITIVE_TYPES:
                left = self.translate(expr.left, usage=ExprUsage.SCALAR)
                if meta_type.lower() == bare_type.lower():
                    return SQLBinaryOp(operator="IS NOT", left=left, right=SQLNull())
                return SQLLiteral(value=False)

        if isinstance(expr.left, Quantity):
            return SQLLiteral(value=bare_type in ("Quantity", "quantity"))

        if isinstance(expr.left, Literal) and bare_type not in _PRIMITIVE_TYPES:
            return SQLLiteral(value=False)

        # --- Strategy 0: Compile-time clinical type resolution ---
        # CQL clinical values (Code, Concept, ValueSet, CodeSystem) often lower
        # to JSON/VARCHAR literals. Resolve their type identity before generic
        # FHIR resourceType probing, which only applies to FHIR resources.
        clinical_target = self._CLINICAL_CQL_TYPES.get(bare_type.lower())
        clinical_source = self._static_clinical_type(expr.left)
        if clinical_target is not None and clinical_source is not None:
            return SQLLiteral(
                value=self._clinical_type_matches(clinical_source, clinical_target)
            )

        static_resource_check = self._static_resource_type_check_result(expr.left, type_name)
        if static_resource_check is not None:
            return SQLLiteral(value=static_resource_check)

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

        cql_structural_list_check = self._cql_structural_list_type_check(resource_expr, type_name)
        if cql_structural_list_check is not None:
            return cql_structural_list_check

        clinical_runtime_check = self._clinical_json_type_check(resource_expr, bare_type)
        if clinical_runtime_check is not None:
            return clinical_runtime_check

        fhirpath_type_check = self._fhirpath_type_name_check(resource_expr, bare_type)
        if fhirpath_type_check is not None:
            return fhirpath_type_check

        # Strip FHIR/CQL namespace prefix for type matching
        bare_type = type_name.split(".")[-1] if "." in type_name else type_name

        # --- Strategy 1: CQL primitive types (bare string values) ---
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
                        'integer': {'integer'},
                        'long': {'long'},
                        'decimal': {'decimal'},
                        'boolean': {'boolean'},
                    }
                    _lit_types = _LIT_TYPE_MAP.get(_lit_type_lower)
                    if _lit_types is not None and _bare_lower not in _lit_types:
                        return SQLLiteral(value=False)
                    if _lit_types is not None and _bare_lower in _lit_types:
                        return SQLLiteral(value=True)

            fhirpath_type_check = self._fhirpath_primitive_type_check(resource_expr, bare_type)
            if fhirpath_type_check is not None:
                return fhirpath_type_check

            cql_typed_value_check = self._cql_typed_value_type_check(resource_expr, bare_type)
            if cql_typed_value_check is not None:
                return cql_typed_value_check

            # CQL `is` checks the *type* of the value, not just its format.
            # When the SQL value has a concrete type (INTEGER, DOUBLE, BOOLEAN, DATE, TIMESTAMP),
            # check typeof() against the expected CQL type. When the value is VARCHAR (FHIR JSON
            # extraction), fall back to the not-JSON-object format check.
            _CQL_TYPE_TO_SQL_TYPES = {
                "Integer": ("INTEGER", "SMALLINT", "TINYINT"),
                "integer": ("INTEGER", "SMALLINT", "TINYINT"),
                "Long": ("BIGINT",),
                "long": ("BIGINT",),
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
                # DuckDB typeof() may return parameterized names (e.g., 'DECIMAL(2,1)'),
                # so use starts_with for types that have precision/scale suffixes.
                _PARAMETERIZED_TYPES = {"DECIMAL"}
                typeof_call = SQLFunctionCall(name="typeof", args=[resource_expr])
                type_checks = []
                for t in expected_sql_types:
                    if t in _PARAMETERIZED_TYPES:
                        type_checks.append(SQLFunctionCall(
                            name="starts_with",
                            args=[typeof_call, SQLLiteral(value=t)],
                        ))
                    else:
                        type_checks.append(SQLBinaryOp(
                            operator="=",
                            left=typeof_call,
                            right=SQLLiteral(value=t),
                        ))
                type_match = type_checks[0]
                for tc in type_checks[1:]:
                    type_match = SQLBinaryOp(operator="OR", left=type_match, right=tc)
                if bare_type in ("Integer", "integer", "Long", "long", "Decimal", "decimal", "Boolean", "boolean"):
                    return SQLBinaryOp(operator="AND", left=not_null, right=type_match)
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
            # Period JSON: {"start": "...", "end": "..."} or internal CQL
            # interval JSON: {"low": "...", "high": "..."}.
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
                when_clauses=[(
                    is_json,
                    SQLBinaryOp(operator="OR", left=has_start_or_end, right=has_low_or_high),
                )],
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

        if bare_type in ("Ratio", "ratio"):
            is_json = SQLFunctionCall(
                name="starts_with",
                args=[
                    SQLFunctionCall(name="LTRIM", args=[resource_expr]),
                    SQLLiteral(value="{"),
                ],
            )
            has_numerator_denominator = SQLBinaryOp(
                operator="AND",
                left=SQLBinaryOp(
                    operator="IS NOT",
                    left=SQLFunctionCall(
                        name="json_extract",
                        args=[resource_expr, SQLLiteral(value="$.numerator")],
                    ),
                    right=SQLNull(),
                ),
                right=SQLBinaryOp(
                    operator="IS NOT",
                    left=SQLFunctionCall(
                        name="json_extract",
                        args=[resource_expr, SQLLiteral(value="$.denominator")],
                    ),
                    right=SQLNull(),
                ),
            )
            return SQLCase(
                when_clauses=[(is_json, has_numerator_denominator)],
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

                source_expr = self.translate(_src0_expr, usage=ExprUsage.LIST)
                source_expr = self._preserve_quantity_literals_in_array(
                    source_expr,
                    _src0_expr,
                )
                alias = _src0_alias
                # QA-014/QA-017: List literals used as query sources need
                # unnesting AND proper alias binding so WHERE/RETURN can
                # reference the iteration variable (e.g., ``from {1,2,3} X
                # where X > 1``).  Wrap in a SELECT so the alias becomes a
                # column name that downstream clauses can reference.
                if isinstance(source_expr, SQLArray) and alias:
                    _unnest_call = SQLFunctionCall(name="unnest", args=[source_expr])
                    _inner = SQLSelect(columns=[SQLAlias(expr=_unnest_call, alias=alias)])
                    source_expr = SQLSelect(
                        columns=[SQLIdentifier(name=alias)],
                        from_clause=SQLAlias(expr=SQLSubquery(query=_inner), alias="_list"),
                    )
                    self.context.add_alias(alias, table_alias=alias)
                    self.context._alias_source_asts[alias] = _src0_expr
                elif isinstance(source_expr, SQLArray):
                    source_expr = SQLFunctionCall(name="unnest", args=[source_expr])
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
                    source_expr = self._preserve_quantity_literals_in_array(
                        source_expr,
                        _pi_expr,
                    )
                    # List literals / array expressions must be unnested for FROM clause
                    if isinstance(source_expr, SQLArray) or (
                        isinstance(source_expr, SQLFunctionCall)
                        and _is_list_returning_sql(source_expr)
                    ):
                        source_expr = SQLFunctionCall(name="unnest", args=[source_expr])
                    if alias:
                        self.context.add_alias(alias, table_alias=alias)
                        self.context._alias_source_asts[alias] = _pi_expr

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
                        _sec_from_sql = self._preserve_quantity_literals_in_array(
                            _sec_from_sql,
                            _sec_expr_node,
                        )
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
                    _multi_return_alias_is_let = False
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
                            _multi_return_alias_is_let = True
                    finally:
                        self.context.resource_alias = _saved_ra
                        self.context.pop_scope()

                    # Build FROM clause: first secondary, then CROSS JOINs
                    _outer_alias = alias or self.context.resource_alias or "_pt"
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
                        # Build: SELECT primary.patient_id, <return_expr> AS resource|value
                        #        FROM primary CROSS JOIN sec1 CROSS JOIN sec2 ...
                        #        WHERE conditions
                        # Preserve the source column kind for alias returns so
                        # scalar set/query results stay addressable as `value`.
                        _multi_return_output_alias = "resource"
                        if _multi_return_alias_is_let:
                            _multi_return_output_alias = "value"
                        elif _multi_return_ast is not None and not isinstance(_multi_return_ast, TupleExpression):
                            _multi_return_output_alias = "value"
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
                            _multi_return_output_alias = _ret_col

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
                            SQLAlias(
                                expr=SQLCast(expression=_multi_return_sql, target_type="VARCHAR"),
                                alias=_multi_return_output_alias,
                            ),
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
                    source_expr = self.translate(source_expr_node, usage=ExprUsage.LIST)
                    source_expr = self._preserve_quantity_literals_in_array(
                        source_expr,
                        source_expr_node,
                    )
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

                    source_expr = self.translate(source_expr_node, usage=ExprUsage.LIST)
                    source_expr = self._preserve_quantity_literals_in_array(
                        source_expr,
                        source_expr_node,
                    )
                    alias = source_alias
                    # QA-017: List literals as query source need unnesting AND
                    # proper alias binding when the query has WHERE/RETURN that
                    # reference the iteration variable.  Only wrap when the
                    # query actually uses the alias in a filter or projection.
                    if isinstance(source_expr, SQLArray) and alias and (node.where or node.return_clause):
                        _unnest_call = SQLFunctionCall(name="unnest", args=[source_expr])
                        _inner = SQLSelect(columns=[SQLAlias(expr=_unnest_call, alias=alias)])
                        source_expr = SQLSelect(
                            columns=[SQLIdentifier(name=alias)],
                            from_clause=SQLAlias(expr=SQLSubquery(query=_inner), alias="_list"),
                        )
                        self.context.add_alias(alias, table_alias=alias)
                        self.context._alias_source_asts[alias] = source_expr_node

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
            # QA-017: Skip re-registration when the alias was already bound
            # by the list-literal source handler above (table_alias is set,
            # no CTE backing).
            _already_registered = False
            if not _alias_cte_name:
                _sym = self.context.lookup_symbol(alias)
                if _sym and getattr(_sym, 'table_alias', None) == alias:
                    _already_registered = True

            # Track the FHIR resource type for this alias (for fluent overload resolution)
            alias_rt = self._extract_query_source_resource_type(node)
            if alias_rt:
                self.context._alias_resource_types[alias] = alias_rt

            if not _already_registered:
                # Query sources that are set operations become FROM aliases
                # below. Register the AST here; once wrapped, table_alias will
                # let property access target <alias>.resource directly.
                if isinstance(source_expr, (SQLUnion, SQLIntersect, SQLExcept)):
                    self.context.add_alias(
                        alias,
                        ast_expr=source_expr,
                        cte_name=_alias_cte_name,
                    )
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
                self.context.add_alias(
                    alias,
                    table_alias=alias,
                    cte_name=provisional_cte_name,
                    ast_expr=source_expr,
                )
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
        # reference the correct outer alias instead of hardcoded "_pt".
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
                    self._process_let_clauses(node.let_clauses, node=node)

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
            self._process_let_clauses(node.let_clauses, node=node)

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
                outer_corr_alias = alias or self.context.resource_alias or "_pt"
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
                    elif _sort_ident_name and _sort_ident_name in self.context.let_variables:
                        # Let-binding identifier (e.g. CrLabTime from a let clause) —
                        # use the already-translated SQL expression directly.
                        sort_by = self.context.let_variables[_sort_ident_name]
                    elif not _sort_ident_name:
                        # Complex expression (e.g. effective.earliest()) — translate
                        sort_by = self.translate(sort_item.expression, usage=ExprUsage.SCALAR)
                    # else: simple identifier not in columns or let variables — skip sort
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
                # ── Single-source aggregate ───────────────────────────────
                # Detect typed-list starting values.
                # DuckDB's list_reduce requires the lambda body return type to
                # match the element type (VARCHAR), but a list accumulator body
                # returns VARCHAR[] — a type mismatch that causes a runtime
                # error.  Route these through the same recursive-CTE fold used
                # for multi-source aggregates so the accumulator is typed as a
                # list from the outset.  (CQL §19.27)
                from ...parser.ast_nodes import (
                    ListExpression as _ListExpression,
                    ListTypeSpecifier as _ListTypeSpec,
                    Literal as _ASTLiteral,
                )
                _starting_is_typed_list = (
                    agg.starting is not None
                    and isinstance(agg.starting, BinaryExpression)
                    and agg.starting.operator == 'as'
                    and isinstance(agg.starting.right, _ListTypeSpec)
                    and (
                        (
                            isinstance(agg.starting.left, _ASTLiteral)
                            and agg.starting.left.value is None
                        )
                        or (
                            isinstance(agg.starting.left, _ListExpression)
                            and not agg.starting.left.elements
                        )
                    )
                )

                if _starting_is_typed_list and alias:
                    # ── Single-source list-accumulator aggregate: recursive CTE fold ──
                    # source_list is the array expression (SQLArray or SQLFunctionCall).
                    if isinstance(source_list, SQLArray):
                        _arr_sql = source_list.to_sql()
                    elif isinstance(source_list, SQLFunctionCall) and source_list.name == "unnest":
                        _arr_sql = source_list.args[0].to_sql()
                    elif isinstance(source_list, SQLCast) and source_list.target_type.endswith("[]"):
                        _arr_sql = source_list.to_sql()
                    elif _is_list_returning_sql(source_list):
                        _arr_sql = source_list.to_sql()
                    else:
                        _arr_sql = f"[{source_list.to_sql()}]"

                    _distinct_kw = "DISTINCT " if agg.distinct else ""

                    self.context.push_scope()
                    try:
                        self.context.add_alias(
                            accum_name,
                            ast_expr=SQLQualifiedIdentifier(parts=["__fold", "__acc"]),
                        )
                        self.context.add_alias(
                            alias,
                            ast_expr=SQLQualifiedIdentifier(parts=["__xjn", alias]),
                        )
                        agg_body = self.translate(agg.expression, usage=ExprUsage.SCALAR)
                    finally:
                        self.context.pop_scope()

                    _body_sql = agg_body.to_sql()
                    _start_sql = (
                        "CAST(NULL AS VARCHAR[])"
                        if isinstance(agg.starting.left, _ASTLiteral)
                        else "CAST([] AS VARCHAR[])"
                    )
                    result = SQLRaw(
                        f"(WITH RECURSIVE __xj AS ("
                        f"SELECT {_distinct_kw}{alias} FROM "
                        f"unnest({_arr_sql}) AS __t0({alias})"
                        f"), __xjn AS ("
                        f"SELECT ROW_NUMBER() OVER () AS __rn, * FROM __xj"
                        f"), __fold(__acc, __rn) AS ("
                        f"SELECT {_start_sql}, CAST(0 AS BIGINT) "
                        f"UNION ALL "
                        f"SELECT {_body_sql}, __xjn.__rn "
                        f"FROM __fold JOIN __xjn ON __xjn.__rn = __fold.__rn + 1"
                        f") SELECT __acc FROM __fold ORDER BY __rn DESC LIMIT 1)"
                    )
                    result.result_type = "List<Any>"
                else:
                    # ── Single-source scalar aggregate: list_reduce pattern ──────────
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
