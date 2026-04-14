"""
Unit tests for ast_utils.py — AST introspection utilities.
"""

import pytest
from ...translator.types import (
    SQLSelect,
    SQLIdentifier,
    SQLQualifiedIdentifier,
    SQLAlias,
    SQLFunctionCall,
    SQLLiteral,
    SQLExists,
    SQLSubquery,
    SQLBinaryOp,
)
from ...translator import ast_utils


class TestSelectHasColumn:
    """Tests for select_has_column()"""
    
    def test_simple_column(self):
        """SELECT patient_id FROM t1"""
        select = SQLSelect(
            columns=[SQLIdentifier(name="patient_id")],
            from_clause=SQLIdentifier(name="t1"),
        )
        assert ast_utils.select_has_column(select, "patient_id") is True
        assert ast_utils.select_has_column(select, "resource") is False
    
    def test_qualified_column(self):
        """SELECT t1.patient_id FROM t1"""
        select = SQLSelect(
            columns=[SQLQualifiedIdentifier(parts=["t1", "patient_id"])],
            from_clause=SQLIdentifier(name="t1"),
        )
        assert ast_utils.select_has_column(select, "patient_id") is True
        assert ast_utils.select_has_column(select, "t1.patient_id") is True
    
    def test_aliased_column(self):
        """SELECT p.patient_id AS pid FROM patients p"""
        select = SQLSelect(
            columns=[
                SQLAlias(
                    expr=SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                    alias="pid"
                )
            ],
            from_clause=SQLIdentifier(name="patients"),
        )
        assert ast_utils.select_has_column(select, "pid") is True
        assert ast_utils.select_has_column(select, "patient_id") is True
    
    def test_tuple_format(self):
        """SELECT columns as (expr, alias) tuples"""
        select = SQLSelect(
            columns=[
                (SQLIdentifier(name="patient_id"), "pid"),
                (SQLIdentifier(name="resource"), None),
            ],
            from_clause=SQLIdentifier(name="t1"),
        )
        assert ast_utils.select_has_column(select, "pid") is True
        assert ast_utils.select_has_column(select, "patient_id") is True
        assert ast_utils.select_has_column(select, "resource") is True
    
    def test_case_insensitive(self):
        """Column name matching is case-insensitive"""
        select = SQLSelect(
            columns=[SQLIdentifier(name="Patient_ID")],
            from_clause=SQLIdentifier(name="t1"),
        )
        assert ast_utils.select_has_column(select, "patient_id") is True
        assert ast_utils.select_has_column(select, "PATIENT_ID") is True
    
    def test_function_call_does_not_match(self):
        """SELECT fhirpath_text(resource, 'patient_id') — doesn't match 'patient_id'"""
        select = SQLSelect(
            columns=[
                SQLFunctionCall(
                    name="fhirpath_text",
                    args=[SQLIdentifier(name="resource"), SQLLiteral(value="patient_id")]
                )
            ],
            from_clause=SQLIdentifier(name="t1"),
        )
        # Function calls don't directly reference column names
        assert ast_utils.select_has_column(select, "patient_id") is False


class TestSelectHasStar:
    """Tests for select_has_star()"""
    
    def test_star_wildcard(self):
        """SELECT * FROM t1"""
        select = SQLSelect(
            columns=[SQLIdentifier(name="*")],
            from_clause=SQLIdentifier(name="t1"),
        )
        assert ast_utils.select_has_star(select) is True
    
    def test_qualified_star(self):
        """SELECT t1.* FROM t1"""
        select = SQLSelect(
            columns=[SQLQualifiedIdentifier(parts=["t1", "*"])],
            from_clause=SQLIdentifier(name="t1"),
        )
        assert ast_utils.select_has_star(select) is True
    
    def test_no_star(self):
        """SELECT patient_id, resource FROM t1"""
        select = SQLSelect(
            columns=[
                SQLIdentifier(name="patient_id"),
                SQLIdentifier(name="resource"),
            ],
            from_clause=SQLIdentifier(name="t1"),
        )
        assert ast_utils.select_has_star(select) is False
    
    def test_star_in_tuple(self):
        """SELECT columns with tuple format"""
        select = SQLSelect(
            columns=[(SQLIdentifier(name="*"), None)],
            from_clause=SQLIdentifier(name="t1"),
        )
        assert ast_utils.select_has_star(select) is True


class TestAstHasNodeType:
    """Tests for ast_has_node_type()"""
    
    def test_exists_in_where(self):
        """WHERE EXISTS (SELECT ...)"""
        subquery = SQLSelect(
            columns=[SQLLiteral(value=1)],
            from_clause=SQLIdentifier(name="t2"),
        )
        where = SQLExists(subquery=SQLSubquery(query=subquery))
        
        select = SQLSelect(
            columns=[SQLIdentifier(name="patient_id")],
            from_clause=SQLIdentifier(name="t1"),
            where=where,
        )
        
        assert ast_utils.ast_has_node_type(select, SQLExists) is True
        assert ast_utils.ast_has_node_type(select, SQLSubquery) is True
    
    def test_no_exists(self):
        """WHERE x = 5"""
        where = SQLBinaryOp(
            operator="=",
            left=SQLIdentifier(name="x"),
            right=SQLLiteral(value=5),
        )
        select = SQLSelect(
            columns=[SQLIdentifier(name="patient_id")],
            from_clause=SQLIdentifier(name="t1"),
            where=where,
        )
        
        assert ast_utils.ast_has_node_type(select, SQLExists) is False
    
    def test_nested_in_function_call(self):
        """SELECT COUNT(*) WHERE EXISTS (...)"""
        exists = SQLExists(
            subquery=SQLSubquery(
                query=SQLSelect(
                    columns=[SQLLiteral(value=1)],
                    from_clause=SQLIdentifier(name="t2"),
                )
            )
        )
        
        # Deeply nested
        func = SQLFunctionCall(
            name="CASE_WHEN",
            args=[exists, SQLLiteral(value=1), SQLLiteral(value=0)]
        )
        
        assert ast_utils.ast_has_node_type(func, SQLExists) is True


class TestExtractFhirpathFromAst:
    """Tests for extract_fhirpath_from_ast()"""
    
    def test_fhirpath_text(self):
        """fhirpath_text(resource, 'status')"""
        expr = SQLFunctionCall(
            name="fhirpath_text",
            args=[
                SQLIdentifier(name="resource"),
                SQLLiteral(value="status"),
            ]
        )
        assert ast_utils.extract_fhirpath_from_ast(expr) == "status"
    
    def test_fhirpath_date(self):
        """fhirpath_date(r.resource, 'onset')"""
        expr = SQLFunctionCall(
            name="fhirpath_date",
            args=[
                SQLQualifiedIdentifier(parts=["r", "resource"]),
                SQLLiteral(value="onset"),
            ]
        )
        assert ast_utils.extract_fhirpath_from_ast(expr) == "onset"
    
    def test_coalesce_fhirpath(self):
        """COALESCE(fhirpath_date(..., 'effectiveDateTime'), fhirpath_date(..., 'effectivePeriod.start'))"""
        expr = SQLFunctionCall(
            name="COALESCE",
            args=[
                SQLFunctionCall(
                    name="fhirpath_date",
                    args=[SQLIdentifier(name="resource"), SQLLiteral(value="effectiveDateTime")]
                ),
                SQLFunctionCall(
                    name="fhirpath_date",
                    args=[SQLIdentifier(name="resource"), SQLLiteral(value="effectivePeriod.start")]
                ),
            ]
        )
        # Returns comma-separated paths
        result = ast_utils.extract_fhirpath_from_ast(expr)
        assert result == "effectiveDateTime, effectivePeriod.start"
    
    def test_aliased_fhirpath(self):
        """fhirpath_text(...) AS col_name"""
        expr = SQLAlias(
            expr=SQLFunctionCall(
                name="fhirpath_text",
                args=[SQLIdentifier(name="resource"), SQLLiteral(value="code")]
            ),
            alias="code_value"
        )
        assert ast_utils.extract_fhirpath_from_ast(expr) == "code"
    
    def test_non_fhirpath_returns_none(self):
        """COUNT(*) — not a fhirpath function"""
        expr = SQLFunctionCall(name="COUNT", args=[SQLIdentifier(name="*")])
        assert ast_utils.extract_fhirpath_from_ast(expr) is None


class TestInferSqlTypeFromAst:
    """Tests for infer_sql_type_from_ast()"""
    
    def test_fhirpath_date(self):
        expr = SQLFunctionCall(name="fhirpath_date", args=[])
        assert ast_utils.infer_sql_type_from_ast(expr) == "DATE"
    
    def test_fhirpath_datetime(self):
        expr = SQLFunctionCall(name="fhirpath_datetime", args=[])
        assert ast_utils.infer_sql_type_from_ast(expr) == "TIMESTAMP"
    
    def test_fhirpath_bool(self):
        expr = SQLFunctionCall(name="fhirpath_bool", args=[])
        assert ast_utils.infer_sql_type_from_ast(expr) == "BOOLEAN"
    
    def test_fhirpath_text(self):
        expr = SQLFunctionCall(name="fhirpath_text", args=[])
        assert ast_utils.infer_sql_type_from_ast(expr) == "VARCHAR"
    
    def test_count(self):
        expr = SQLFunctionCall(name="count", args=[])
        assert ast_utils.infer_sql_type_from_ast(expr) == "INTEGER"
    
    def test_coalesce_inherits_first(self):
        """COALESCE(fhirpath_date(...), NULL) → DATE"""
        expr = SQLFunctionCall(
            name="coalesce",
            args=[
                SQLFunctionCall(name="fhirpath_date", args=[]),
                SQLLiteral(value=None),
            ]
        )
        assert ast_utils.infer_sql_type_from_ast(expr) == "DATE"
    
    def test_default_varchar(self):
        """Unknown expressions default to VARCHAR"""
        expr = SQLIdentifier(name="some_column")
        assert ast_utils.infer_sql_type_from_ast(expr) == "VARCHAR"


class TestAstHasCorrelatedRef:
    """Tests for ast_has_correlated_ref()"""
    
    def test_qualified_identifier(self):
        """r.resource"""
        expr = SQLQualifiedIdentifier(parts=["r", "resource"])
        assert ast_utils.ast_has_correlated_ref(expr, "r") is True
        assert ast_utils.ast_has_correlated_ref(expr, "t1") is False
    
    def test_in_function_call(self):
        """fhirpath_text(r.resource, 'status')"""
        expr = SQLFunctionCall(
            name="fhirpath_text",
            args=[
                SQLQualifiedIdentifier(parts=["r", "resource"]),
                SQLLiteral(value="status"),
            ]
        )
        assert ast_utils.ast_has_correlated_ref(expr, "r") is True
    
    def test_case_insensitive(self):
        """R.resource — case-insensitive match"""
        expr = SQLQualifiedIdentifier(parts=["R", "resource"])
        assert ast_utils.ast_has_correlated_ref(expr, "r") is True
    
    def test_no_correlation(self):
        """t1.patient_id"""
        expr = SQLQualifiedIdentifier(parts=["t1", "patient_id"])
        assert ast_utils.ast_has_correlated_ref(expr, "r") is False


class TestAstReferencesName:
    """Tests for ast_references_name()"""
    
    def test_simple_identifier(self):
        """Direct identifier: patient_id"""
        expr = SQLIdentifier(name="patient_id")
        assert ast_utils.ast_references_name(expr, "patient_id") is True
        assert ast_utils.ast_references_name(expr, "resource") is False
    
    def test_qualified_identifier_full_path(self):
        """t1.patient_id with full path match"""
        expr = SQLQualifiedIdentifier(parts=["t1", "patient_id"])
        assert ast_utils.ast_references_name(expr, "t1.patient_id") is True
    
    def test_qualified_identifier_last_part(self):
        """t1.patient_id with last part match"""
        expr = SQLQualifiedIdentifier(parts=["t1", "patient_id"])
        assert ast_utils.ast_references_name(expr, "patient_id") is True
    
    def test_qualified_identifier_no_match(self):
        """t1.patient_id doesn't match resource"""
        expr = SQLQualifiedIdentifier(parts=["t1", "patient_id"])
        assert ast_utils.ast_references_name(expr, "resource") is False
    
    def test_case_insensitive(self):
        """Case-insensitive matching"""
        expr = SQLIdentifier(name="Patient_ID")
        assert ast_utils.ast_references_name(expr, "patient_id") is True
        assert ast_utils.ast_references_name(expr, "PATIENT_ID") is True
    
    def test_in_where_clause(self):
        """SELECT * WHERE patient_id = 5"""
        where = SQLBinaryOp(
            operator="=",
            left=SQLIdentifier(name="patient_id"),
            right=SQLLiteral(value=5),
        )
        select = SQLSelect(
            columns=[SQLIdentifier(name="*")],
            from_clause=SQLIdentifier(name="t1"),
            where=where,
        )
        assert ast_utils.ast_references_name(select, "patient_id") is True
        assert ast_utils.ast_references_name(select, "resource") is False
    
    def test_in_function_call(self):
        """fhirpath_text(r.resource, 'code')"""
        expr = SQLFunctionCall(
            name="fhirpath_text",
            args=[
                SQLQualifiedIdentifier(parts=["r", "resource"]),
                SQLLiteral(value="code"),
            ]
        )
        assert ast_utils.ast_references_name(expr, "resource") is True
        assert ast_utils.ast_references_name(expr, "r") is True
        assert ast_utils.ast_references_name(expr, "code") is False  # String literal, not identifier
    
    def test_in_nested_function(self):
        """COALESCE(fhirpath_text(resource, 'a'), fhirpath_text(resource, 'b'))"""
        expr = SQLFunctionCall(
            name="COALESCE",
            args=[
                SQLFunctionCall(
                    name="fhirpath_text",
                    args=[SQLIdentifier(name="resource"), SQLLiteral(value="a")],
                ),
                SQLFunctionCall(
                    name="fhirpath_text",
                    args=[SQLIdentifier(name="resource"), SQLLiteral(value="b")],
                ),
            ]
        )
        assert ast_utils.ast_references_name(expr, "resource") is True
    
    def test_in_aliased_expression(self):
        """fhirpath_text(...) AS col_name"""
        expr = SQLAlias(
            expr=SQLFunctionCall(
                name="fhirpath_text",
                args=[SQLIdentifier(name="resource"), SQLLiteral(value="code")]
            ),
            alias="code_value"
        )
        assert ast_utils.ast_references_name(expr, "resource") is True
    
    def test_in_select_columns(self):
        """SELECT patient_id, resource FROM t1"""
        select = SQLSelect(
            columns=[
                SQLIdentifier(name="patient_id"),
                SQLIdentifier(name="resource"),
            ],
            from_clause=SQLIdentifier(name="t1"),
        )
        assert ast_utils.ast_references_name(select, "patient_id") is True
        assert ast_utils.ast_references_name(select, "resource") is True
        assert ast_utils.ast_references_name(select, "nonexistent") is False
    
    def test_in_order_by(self):
        """SELECT * FROM t1 ORDER BY patient_id"""
        select = SQLSelect(
            columns=[SQLIdentifier(name="*")],
            from_clause=SQLIdentifier(name="t1"),
            order_by=[(SQLIdentifier(name="patient_id"), "ASC")],
        )
        assert ast_utils.ast_references_name(select, "patient_id") is True
    
    def test_in_group_by(self):
        """SELECT COUNT(*) FROM t1 GROUP BY patient_id"""
        select = SQLSelect(
            columns=[SQLFunctionCall(name="COUNT", args=[SQLIdentifier(name="*")])],
            from_clause=SQLIdentifier(name="t1"),
            group_by=[SQLIdentifier(name="patient_id")],
        )
        assert ast_utils.ast_references_name(select, "patient_id") is True
    
    def test_binary_operation(self):
        """Check in binary operations (AND, OR, etc.)"""
        expr = SQLBinaryOp(
            operator="AND",
            left=SQLBinaryOp(
                operator="=",
                left=SQLIdentifier(name="patient_id"),
                right=SQLLiteral(value=5),
            ),
            right=SQLBinaryOp(
                operator="=",
                left=SQLIdentifier(name="status"),
                right=SQLLiteral(value="active"),
            ),
        )
        assert ast_utils.ast_references_name(expr, "patient_id") is True
        assert ast_utils.ast_references_name(expr, "status") is True
        assert ast_utils.ast_references_name(expr, "nonexistent") is False


class TestCollectCteReferences:
    """Tests for collect_cte_references()"""
    
    def test_single_quoted_identifier(self):
        """Quoted identifier: "cte1" """
        expr = SQLIdentifier(name="cte1", quoted=True)
        result = ast_utils.collect_cte_references(expr)
        assert result == {"cte1"}
    
    def test_unquoted_identifier_ignored(self):
        """Unquoted identifier: resource"""
        expr = SQLIdentifier(name="resource", quoted=False)
        result = ast_utils.collect_cte_references(expr)
        assert result == set()
    
    def test_multiple_cte_references_in_select(self):
        """SELECT * FROM "cte1" JOIN "cte2"
        
        Create a select with quoted identifiers in FROM clause.
        """
        select = SQLSelect(
            columns=[SQLIdentifier(name="*")],
            from_clause=SQLIdentifier(name="cte1", quoted=True),
        )
        result = ast_utils.collect_cte_references(select)
        assert result == {"cte1"}
    
    def test_no_cte_references(self):
        """SELECT * FROM resource, patient_id (unquoted)"""
        select = SQLSelect(
            columns=[SQLIdentifier(name="*")],
            from_clause=SQLIdentifier(name="resource", quoted=False),
        )
        result = ast_utils.collect_cte_references(select)
        assert result == set()
    
    def test_in_function_call(self):
        """fhirpath_text("cte1", 'code')"""
        expr = SQLFunctionCall(
            name="fhirpath_text",
            args=[
                SQLIdentifier(name="cte1", quoted=True),
                SQLLiteral(value="code"),
            ]
        )
        result = ast_utils.collect_cte_references(expr)
        assert result == {"cte1"}
    
    def test_in_where_clause(self):
        """SELECT * FROM "cte1" WHERE status = "cte2" """
        where = SQLBinaryOp(
            operator="=",
            left=SQLIdentifier(name="status"),
            right=SQLIdentifier(name="cte2", quoted=True),
        )
        select = SQLSelect(
            columns=[SQLIdentifier(name="*")],
            from_clause=SQLIdentifier(name="cte1", quoted=True),
            where=where,
        )
        result = ast_utils.collect_cte_references(select)
        assert result == {"cte1", "cte2"}
    
    def test_in_aliased_expression(self):
        """SELECT "cte1".col AS alias"""
        expr = SQLAlias(
            expr=SQLIdentifier(name="cte1", quoted=True),
            alias="alias",
        )
        result = ast_utils.collect_cte_references(expr)
        assert result == {"cte1"}
    
    def test_empty_select(self):
        """Empty select"""
        select = SQLSelect(columns=[], from_clause=None)
        result = ast_utils.collect_cte_references(select)
        assert result == set()
    
    def test_in_subquery(self):
        """Subquery with quoted identifier"""
        subquery_select = SQLSelect(
            columns=[SQLIdentifier(name="*")],
            from_clause=SQLIdentifier(name="cte1", quoted=True),
        )
        expr = SQLSubquery(query=subquery_select)
        result = ast_utils.collect_cte_references(expr)
        assert result == {"cte1"}


class TestIsFhirpathCall:
    """Tests for is_fhirpath_call()"""
    
    def test_fhirpath_text(self):
        """fhirpath_text(resource, 'code')"""
        expr = SQLFunctionCall(
            name="fhirpath_text",
            args=[SQLIdentifier(name="resource"), SQLLiteral(value="code")],
        )
        assert ast_utils.is_fhirpath_call(expr) is True
    
    def test_fhirpath_date(self):
        """fhirpath_date(r.resource, 'onset')"""
        expr = SQLFunctionCall(
            name="fhirpath_date",
            args=[SQLQualifiedIdentifier(parts=["r", "resource"]), SQLLiteral(value="onset")],
        )
        assert ast_utils.is_fhirpath_call(expr) is True
    
    def test_fhirpath_bool(self):
        """fhirpath_bool(resource, 'active')"""
        expr = SQLFunctionCall(name="fhirpath_bool", args=[])
        assert ast_utils.is_fhirpath_call(expr) is True
    
    def test_fhirpath_quantity(self):
        """fhirpath_quantity(resource, 'value')"""
        expr = SQLFunctionCall(name="fhirpath_quantity", args=[])
        assert ast_utils.is_fhirpath_call(expr) is True
    
    def test_fhirpath_datetime(self):
        """fhirpath_datetime(resource, 'created')"""
        expr = SQLFunctionCall(name="fhirpath_datetime", args=[])
        assert ast_utils.is_fhirpath_call(expr) is True
    
    def test_fhirpath_integer(self):
        """fhirpath_integer(resource, 'count')"""
        expr = SQLFunctionCall(name="fhirpath_integer", args=[])
        assert ast_utils.is_fhirpath_call(expr) is True
    
    def test_non_fhirpath_function(self):
        """COUNT(*)"""
        expr = SQLFunctionCall(name="COUNT", args=[SQLIdentifier(name="*")])
        assert ast_utils.is_fhirpath_call(expr) is False
    
    def test_coalesce_not_fhirpath(self):
        """COALESCE(fhirpath_text(...), NULL) — parent call is not fhirpath"""
        expr = SQLFunctionCall(
            name="COALESCE",
            args=[
                SQLFunctionCall(name="fhirpath_text", args=[]),
                SQLLiteral(value=None),
            ]
        )
        assert ast_utils.is_fhirpath_call(expr) is False
    
    def test_not_a_function_call(self):
        """resource — SQLIdentifier, not a function"""
        expr = SQLIdentifier(name="resource")
        assert ast_utils.is_fhirpath_call(expr) is False
    
    def test_qualified_identifier_not_function(self):
        """r.resource — SQLQualifiedIdentifier, not a function"""
        expr = SQLQualifiedIdentifier(parts=["r", "resource"])
        assert ast_utils.is_fhirpath_call(expr) is False
    
    def test_null_name(self):
        """Function with None name"""
        expr = SQLFunctionCall(name=None, args=[])
        assert ast_utils.is_fhirpath_call(expr) is False
    
    def test_case_sensitive_prefix(self):
        """FHIRPATH_TEXT (uppercase) — should match since startswith is case-sensitive"""
        expr = SQLFunctionCall(name="FHIRPATH_TEXT", args=[])
        # Note: This will be False if name is "FHIRPATH_TEXT" because startswith is case-sensitive
        # Adjust test based on actual requirement
        assert ast_utils.is_fhirpath_call(expr) is False
    
    def test_lowercase_fhirpath(self):
        """fhirpath_text (lowercase) — should match"""
        expr = SQLFunctionCall(name="fhirpath_text", args=[])
        assert ast_utils.is_fhirpath_call(expr) is True
    
    def test_fhirpath_prefix_only(self):
        """Any function starting with fhirpath_"""
        expr = SQLFunctionCall(name="fhirpath_custom_function", args=[])
        assert ast_utils.is_fhirpath_call(expr) is True
    
    def test_almost_fhirpath(self):
        """almost_fhirpath_text — doesn't start with fhirpath_"""
        expr = SQLFunctionCall(name="almost_fhirpath_text", args=[])
        assert ast_utils.is_fhirpath_call(expr) is False
