"""
Unit tests for JOIN conversion functionality.

Tests SQLJoin, SQLSelect with joins, and SQLQueryBuilder for
converting scalar subqueries to LEFT JOINs.
"""

import pytest
from ...translator.types import (
    PRECEDENCE,
    SQLBinaryOp,
    SQLExpression,
    SQLIdentifier,
    SQLJoin,
    SQLLiteral,
    SQLQualifiedIdentifier,
    SQLSelect,
)
from ...translator.queries import CTEReference, SQLQueryBuilder


class TestSQLJoin:
    """Tests for SQLJoin dataclass."""

    def test_left_join_basic(self):
        """Test basic LEFT JOIN generation."""
        join = SQLJoin(
            join_type="LEFT",
            table=SQLIdentifier(name="_sq_14"),
            alias="j1",
            on_condition=SQLBinaryOp(
                operator="=",
                left=SQLQualifiedIdentifier(parts=["j1", "patient_ref"]),
                right=SQLQualifiedIdentifier(parts=["p", "patient_id"]),
            ),
        )
        sql = join.to_sql()
        assert sql == "LEFT JOIN _sq_14 AS j1 ON j1.patient_ref = p.patient_id"

    def test_inner_join(self):
        """Test INNER JOIN generation."""
        join = SQLJoin(
            join_type="INNER",
            table=SQLIdentifier(name="conditions"),
            alias="c",
            on_condition=SQLBinaryOp(
                operator="=",
                left=SQLQualifiedIdentifier(parts=["c", "subject"]),
                right=SQLQualifiedIdentifier(parts=["p", "id"]),
            ),
        )
        sql = join.to_sql()
        assert sql == "INNER JOIN conditions AS c ON c.subject = p.id"

    def test_join_without_alias(self):
        """Test JOIN without alias."""
        join = SQLJoin(
            join_type="LEFT",
            table=SQLIdentifier(name="resources"),
            on_condition=SQLBinaryOp(
                operator="=",
                left=SQLQualifiedIdentifier(parts=["resources", "patient_ref"]),
                right=SQLQualifiedIdentifier(parts=["p", "patient_id"]),
            ),
        )
        sql = join.to_sql()
        assert sql == "LEFT JOIN resources ON resources.patient_ref = p.patient_id"

    def test_join_without_on_condition(self):
        """Test CROSS JOIN without ON condition."""
        join = SQLJoin(
            join_type="CROSS",
            table=SQLIdentifier(name="valueset_codes"),
            alias="vc",
        )
        sql = join.to_sql()
        assert sql == "CROSS JOIN valueset_codes AS vc"

    def test_join_case_insensitive_type(self):
        """Test that join_type is uppercased in output."""
        join = SQLJoin(
            join_type="left",
            table=SQLIdentifier(name="table1"),
            alias="t1",
        )
        sql = join.to_sql()
        assert sql.startswith("LEFT JOIN")


class TestSQLSelectWithJoins:
    """Tests for SQLSelect with joins support."""

    def test_select_with_single_join(self):
        """Test SELECT with a single JOIN."""
        join = SQLJoin(
            join_type="LEFT",
            table=SQLIdentifier(name="_sq_14"),
            alias="bp",
            on_condition=SQLBinaryOp(
                operator="=",
                left=SQLQualifiedIdentifier(parts=["bp", "patient_ref"]),
                right=SQLQualifiedIdentifier(parts=["p", "patient_id"]),
            ),
        )
        select = SQLSelect(
            columns=[
                SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                SQLQualifiedIdentifier(parts=["bp", "resource"]),
            ],
            from_clause=SQLIdentifier(name="patients AS p"),
            joins=[join],
        )
        sql = select.to_sql()
        # SQLIdentifier quotes names with spaces/reserved words
        assert 'FROM "patients AS p"' in sql
        assert "LEFT JOIN _sq_14 AS bp ON bp.patient_ref = p.patient_id" in sql

    def test_select_with_multiple_joins(self):
        """Test SELECT with multiple JOINs."""
        join1 = SQLJoin(
            join_type="LEFT",
            table=SQLIdentifier(name="_sq_14"),
            alias="j1",
            on_condition=SQLBinaryOp(
                operator="=",
                left=SQLQualifiedIdentifier(parts=["j1", "patient_ref"]),
                right=SQLQualifiedIdentifier(parts=["p", "patient_id"]),
            ),
        )
        join2 = SQLJoin(
            join_type="LEFT",
            table=SQLIdentifier(name="_sq_15"),
            alias="j2",
            on_condition=SQLBinaryOp(
                operator="=",
                left=SQLQualifiedIdentifier(parts=["j2", "patient_ref"]),
                right=SQLQualifiedIdentifier(parts=["p", "patient_id"]),
            ),
        )
        select = SQLSelect(
            columns=[SQLQualifiedIdentifier(parts=["p", "patient_id"])],
            from_clause=SQLIdentifier(name="patients AS p"),
            joins=[join1, join2],
        )
        sql = select.to_sql()
        assert "LEFT JOIN _sq_14 AS j1" in sql
        assert "LEFT JOIN _sq_15 AS j2" in sql

    def test_select_without_joins(self):
        """Test that SELECT without joins still works."""
        select = SQLSelect(
            columns=[SQLQualifiedIdentifier(parts=["p", "patient_id"])],
            from_clause=SQLIdentifier(name="patients AS p"),
        )
        sql = select.to_sql()
        assert "JOIN" not in sql
        # SQLIdentifier quotes names with spaces/reserved words
        assert 'FROM "patients AS p"' in sql

    def test_select_with_joins_and_where(self):
        """Test SELECT with JOINs and WHERE clause."""
        join = SQLJoin(
            join_type="LEFT",
            table=SQLIdentifier(name="conditions"),
            alias="c",
            on_condition=SQLBinaryOp(
                operator="=",
                left=SQLQualifiedIdentifier(parts=["c", "patient_ref"]),
                right=SQLQualifiedIdentifier(parts=["p", "patient_id"]),
            ),
        )
        select = SQLSelect(
            columns=[SQLQualifiedIdentifier(parts=["p", "patient_id"])],
            from_clause=SQLIdentifier(name="patients AS p"),
            joins=[join],
            where=SQLBinaryOp(
                operator="=",
                left=SQLQualifiedIdentifier(parts=["c", "status"]),
                right=SQLLiteral(value="active"),
            ),
        )
        sql = select.to_sql()
        # JOIN should come before WHERE
        join_pos = sql.index("LEFT JOIN")
        where_pos = sql.index("WHERE")
        assert join_pos < where_pos


class TestCTEReference:
    """Tests for CTEReference dataclass."""

    def test_cte_reference_basic(self):
        """Test basic CTEReference creation."""
        ref = CTEReference(cte_name="_sq_14", semantic_alias="_sq_14", alias="j1")
        assert ref.cte_name == "_sq_14"
        assert ref.alias == "j1"
        assert ref.patient_correlated is True

    def test_cte_reference_non_patient_correlated(self):
        """Test CTEReference for non-patient correlated CTE."""
        ref = CTEReference(
            cte_name="global_valueset",
            semantic_alias="global_valueset",
            alias="gv",
            patient_correlated=False,
        )
        assert ref.patient_correlated is False


class TestSQLQueryBuilder:
    """Tests for SQLQueryBuilder class."""

    def test_track_cte_reference_auto_alias(self):
        """Test tracking CTE reference with auto-generated alias."""
        builder = SQLQueryBuilder()
        alias = builder.track_cte_reference("_sq_14")
        assert alias == "j1"
        assert builder.has_references()

    def test_track_cte_reference_custom_alias(self):
        """Test tracking CTE reference with custom alias is ignored (auto-generated)."""
        builder = SQLQueryBuilder()
        # Note: The new API no longer accepts 'alias' parameter; alias is auto-generated
        alias = builder.track_cte_reference("_sq_14", semantic_alias="bp")
        assert alias == "j1"  # Auto-generated alias

    def test_track_multiple_references(self):
        """Test tracking multiple CTE references."""
        builder = SQLQueryBuilder()
        alias1 = builder.track_cte_reference("_sq_14")
        alias2 = builder.track_cte_reference("_sq_15")
        alias3 = builder.track_cte_reference("_sq_16")
        assert alias1 == "j1"
        assert alias2 == "j2"
        assert alias3 == "j3"

    def test_generate_joins(self):
        """Test generating JOIN clauses."""
        builder = SQLQueryBuilder()
        builder.track_cte_reference("_sq_14")
        builder.track_cte_reference("_sq_15")

        joins = builder.generate_joins(patient_alias="p")
        assert len(joins) == 2

        sql1 = joins[0].to_sql()
        sql2 = joins[1].to_sql()

        assert "LEFT JOIN _sq_14 AS j1" in sql1
        assert "j1.patient_id = p.patient_id" in sql1
        assert "LEFT JOIN _sq_15 AS j2" in sql2
        assert "j2.patient_id = p.patient_id" in sql2

    def test_get_column_reference(self):
        """Test getting column reference for tracked CTE."""
        builder = SQLQueryBuilder()
        builder.track_cte_reference("_sq_14", semantic_alias="bp")

        col_ref = builder.get_column_reference("_sq_14", "resource", semantic_alias="bp")
        assert col_ref.to_sql() == "j1.resource"

        col_ref2 = builder.get_column_reference("_sq_14", "status", semantic_alias="bp")
        assert col_ref2.to_sql() == "j1.status"

    def test_get_column_reference_untracked(self):
        """Test getting column reference for untracked CTE."""
        builder = SQLQueryBuilder()
        col_ref = builder.get_column_reference("some_cte", "resource")
        assert col_ref.to_sql() == "some_cte.resource"

    def test_has_references(self):
        """Test has_references method."""
        builder = SQLQueryBuilder()
        assert not builder.has_references()

        builder.track_cte_reference("_sq_14")
        assert builder.has_references()

    def test_clear(self):
        """Test clearing all tracked references."""
        builder = SQLQueryBuilder()
        builder.track_cte_reference("_sq_14")
        builder.track_cte_reference("_sq_15")

        assert builder.has_references()
        builder.clear()
        assert not builder.has_references()
        assert builder.join_counter == 0


class TestJoinConversionIntegration:
    """Integration tests for JOIN conversion."""

    def test_full_conversion_example(self):
        """
        Test full conversion from scalar subquery to JOIN.

        Before:
            SELECT p.patient_id,
                   fhirpath_text((SELECT sq.resource FROM _sq_14 sq WHERE sq.patient_ref = p.patient_id), 'status')
            FROM patients p

        After:
            SELECT p.patient_id, fhirpath_text(j1.resource, 'status')
            FROM patients p
            LEFT JOIN _sq_14 j1 ON j1.patient_ref = p.patient_id
        """
        # Track CTE reference
        builder = SQLQueryBuilder()
        alias = builder.track_cte_reference("_sq_14")

        # Build column reference (simulating fhirpath_text argument)
        resource_col = builder.get_column_reference("_sq_14", "resource")

        # Generate joins
        joins = builder.generate_joins("p")

        # Build the final SELECT
        select = SQLSelect(
            columns=[
                SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                # In real code, this would be a SQLFunctionCall
                resource_col,
            ],
            from_clause=SQLIdentifier(name="patients AS p"),
            joins=joins,
        )

        sql = select.to_sql()

        # Verify the structure
        assert "SELECT p.patient_id, j1.resource" in sql
        # SQLIdentifier quotes names with spaces/reserved words
        assert 'FROM "patients AS p"' in sql
        assert "LEFT JOIN _sq_14 AS j1 ON j1.patient_id = p.patient_id" in sql

    def test_join_order_follows_pattern(self):
        """
        Test that JOIN order follows pattern: Patients -> ValueSet CTEs -> Retrieval CTEs -> Definitions.

        The order should be determined by the order of track_cte_reference calls.
        """
        builder = SQLQueryBuilder()

        # Track in order: ValueSet CTE, Retrieval CTE, Definition
        # Note: alias parameter removed - semantic_alias is used for keying, auto-generated SQL alias
        builder.track_cte_reference("vs_blood_pressure", semantic_alias="vs1")
        builder.track_cte_reference("_sq_conditions", semantic_alias="c1")
        builder.track_cte_reference("bp_reading", semantic_alias="bp")

        joins = builder.generate_joins("p")

        # Verify order
        sql = " ".join([j.to_sql() for j in joins])
        vs_pos = sql.index("vs_blood_pressure")
        sq_pos = sql.index("_sq_conditions")
        bp_pos = sql.index("bp_reading")

        # Order should be: vs_blood_pressure, _sq_conditions, bp_reading
        assert vs_pos < sq_pos < bp_pos
