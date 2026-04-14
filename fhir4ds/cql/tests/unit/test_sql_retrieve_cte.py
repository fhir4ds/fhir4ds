"""
Unit tests for SQLRetrieveCTE and related functions.

Tests cover:
- SQLRetrieveCTE creation and SQL generation
- CTE deduplication
- MATERIALIZED hint
- Precomputed columns
"""

import pytest

from ...translator.types import (
    SQLAlias,
    SQLFunctionCall,
    SQLLiteral,
    SQLQualifiedIdentifier,
    SQLRetrieveCTE,
    deduplicate_retrieve_ctes,
)


class TestSQLAlias:
    """Tests for SQLAlias class."""

    def test_simple_alias(self):
        """Test simple alias generation."""
        expr = SQLQualifiedIdentifier(parts=["r", "resource"])
        alias = SQLAlias(expr=expr, alias="res")
        assert alias.to_sql() == "r.resource AS res"

    def test_alias_with_reserved_word(self):
        """Test alias that is a reserved word gets quoted."""
        expr = SQLLiteral(value=True)
        alias = SQLAlias(expr=expr, alias="select")
        assert alias.to_sql() == "TRUE AS \"select\""

    def test_alias_with_spaces(self):
        """Test alias with spaces gets quoted."""
        expr = SQLLiteral(value=42)
        alias = SQLAlias(expr=expr, alias="my column")
        assert alias.to_sql() == "42 AS \"my column\""

    def test_alias_with_special_chars(self):
        """Test alias with special characters gets quoted."""
        expr = SQLLiteral(value="test")
        alias = SQLAlias(expr=expr, alias="column-name")
        assert alias.to_sql() == "'test' AS \"column-name\""


class TestSQLRetrieveCTE:
    """Tests for SQLRetrieveCTE class."""

    def test_basic_cte_creation(self):
        """Test basic CTE creation with resource type only."""
        cte = SQLRetrieveCTE(
            name="Condition",
            resource_type="Condition",
        )
        sql = cte.to_sql()

        assert "Condition" in sql
        assert "resourceType = 'Condition'" in sql
        assert "r.patient_ref" in sql
        assert "r.resource" in sql

    def test_cte_with_valueset(self):
        """Test CTE with ValueSet filter."""
        cte = SQLRetrieveCTE(
            name="Condition: Essential Hypertension",
            resource_type="Condition",
            valueset_url="http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.104.12.1011",
            valueset_alias="Essential Hypertension",
        )
        sql = cte.to_sql()

        assert "in_valueset" in sql
        assert "Essential Hypertension" in sql or "Condition:" in sql

    def test_materialized_hint_enabled(self):
        """Test MATERIALIZED hint is included when enabled."""
        cte = SQLRetrieveCTE(
            name="Observation",
            resource_type="Observation",
            materialized=True,
        )
        sql = cte.to_sql()

        assert "MATERIALIZED" in sql

    def test_materialized_hint_disabled(self):
        """Test MATERIALIZED hint is not included when disabled."""
        cte = SQLRetrieveCTE(
            name="Observation",
            resource_type="Observation",
            materialized=False,
        )
        sql = cte.to_sql()

        assert "MATERIALIZED" not in sql

    def test_cte_with_precomputed_columns(self):
        """Test CTE with precomputed columns."""
        # Create a precomputed column expression
        effective_date_expr = SQLAlias(
            expr=SQLFunctionCall(
                name="COALESCE",
                args=[
                    SQLFunctionCall(
                        name="fhirpath_date",
                        args=[
                            SQLQualifiedIdentifier(parts=["r", "resource"]),
                            SQLLiteral(value="effectiveDateTime"),
                        ],
                    ),
                    SQLFunctionCall(
                        name="fhirpath_date",
                        args=[
                            SQLQualifiedIdentifier(parts=["r", "resource"]),
                            SQLLiteral(value="effectivePeriod.start"),
                        ],
                    ),
                ],
            ),
            alias="effective_date"
        )

        cte = SQLRetrieveCTE(
            name="Condition",
            resource_type="Condition",
            precomputed_columns={"effective_date": effective_date_expr},
        )
        sql = cte.to_sql()

        assert "effective_date" in sql
        assert "COALESCE" in sql

    def test_cte_name_quoting_with_colon(self):
        """Test CTE name with colon gets quoted."""
        cte = SQLRetrieveCTE(
            name="Condition: Hypertension",
            resource_type="Condition",
        )
        sql = cte.to_sql()

        # Name with colon should be quoted
        assert '"Condition: Hypertension"' in sql

    def test_cte_name_quoting_with_space(self):
        """Test CTE name with space gets quoted."""
        cte = SQLRetrieveCTE(
            name="Essential Hypertension",
            resource_type="Condition",
        )
        sql = cte.to_sql()

        # Name with space should be quoted
        assert '"Essential Hypertension"' in sql

    def test_cte_name_without_special_chars(self):
        """Test CTE name without special characters is not quoted."""
        cte = SQLRetrieveCTE(
            name="Condition",
            resource_type="Condition",
        )
        sql = cte.to_sql()

        # Name without special chars should not be quoted
        assert '"Condition"' not in sql
        assert "Condition AS" in sql

    def test_distinct_in_cte(self):
        """Test that DISTINCT is included in the CTE query."""
        cte = SQLRetrieveCTE(
            name="Condition",
            resource_type="Condition",
        )
        sql = cte.to_sql()

        assert "SELECT DISTINCT" in sql

    def test_full_cte_sql_structure(self):
        """Test full CTE SQL structure is correct."""
        cte = SQLRetrieveCTE(
            name="Condition: Hypertension",
            resource_type="Condition",
            valueset_url="http://example.com/ValueSet/hypertension",
            materialized=True,
        )
        sql = cte.to_sql()

        # Check all expected parts are present
        assert sql.startswith('"Condition: Hypertension"')
        assert "AS MATERIALIZED" in sql
        assert "SELECT DISTINCT" in sql
        assert "r.patient_ref" in sql
        assert "r.resource" in sql
        assert "FROM resources r" in sql
        assert "resourceType = 'Condition'" in sql
        assert "in_valueset" in sql


class TestDeduplicateRetrieveCTEs:
    """Tests for deduplicate_retrieve_ctes function."""

    def test_no_duplicates(self):
        """Test that unique CTEs are preserved."""
        ctes = [
            SQLRetrieveCTE(name="Condition: A", resource_type="Condition", valueset_url="http://a.com"),
            SQLRetrieveCTE(name="Observation: B", resource_type="Observation", valueset_url="http://b.com"),
        ]

        result = deduplicate_retrieve_ctes(ctes)

        assert len(result) == 2

    def test_exact_duplicates_removed(self):
        """Test that exact duplicates are removed."""
        ctes = [
            SQLRetrieveCTE(name="Condition: A", resource_type="Condition", valueset_url="http://a.com"),
            SQLRetrieveCTE(name="Condition: A Copy", resource_type="Condition", valueset_url="http://a.com"),
        ]

        result = deduplicate_retrieve_ctes(ctes)

        assert len(result) == 1
        # Should keep the first one
        assert result[0].name == "Condition: A"

    def test_same_resource_different_valueset(self):
        """Test CTEs with same resource type but different valuesets are kept."""
        ctes = [
            SQLRetrieveCTE(name="Condition: A", resource_type="Condition", valueset_url="http://a.com"),
            SQLRetrieveCTE(name="Condition: B", resource_type="Condition", valueset_url="http://b.com"),
        ]

        result = deduplicate_retrieve_ctes(ctes)

        assert len(result) == 2

    def test_same_valueset_different_resource(self):
        """Test CTEs with same valueset but different resource types are kept."""
        ctes = [
            SQLRetrieveCTE(name="Condition: A", resource_type="Condition", valueset_url="http://a.com"),
            SQLRetrieveCTE(name="Observation: A", resource_type="Observation", valueset_url="http://a.com"),
        ]

        result = deduplicate_retrieve_ctes(ctes)

        assert len(result) == 2

    def test_none_valueset_handling(self):
        """Test CTEs with None valueset URL are handled correctly."""
        ctes = [
            SQLRetrieveCTE(name="Condition", resource_type="Condition", valueset_url=None),
            SQLRetrieveCTE(name="Condition Copy", resource_type="Condition", valueset_url=None),
        ]

        result = deduplicate_retrieve_ctes(ctes)

        # Both have (Condition, None) as key, so should dedupe to 1
        assert len(result) == 1

    def test_empty_list(self):
        """Test empty list returns empty list."""
        result = deduplicate_retrieve_ctes([])
        assert result == []

    def test_multiple_duplicates(self):
        """Test multiple duplicates across different resource types."""
        ctes = [
            SQLRetrieveCTE(name="Condition: A", resource_type="Condition", valueset_url="http://a.com"),
            SQLRetrieveCTE(name="Condition: A2", resource_type="Condition", valueset_url="http://a.com"),
            SQLRetrieveCTE(name="Observation: B", resource_type="Observation", valueset_url="http://b.com"),
            SQLRetrieveCTE(name="Condition: A3", resource_type="Condition", valueset_url="http://a.com"),
            SQLRetrieveCTE(name="Observation: B2", resource_type="Observation", valueset_url="http://b.com"),
        ]

        result = deduplicate_retrieve_ctes(ctes)

        assert len(result) == 2
        resource_types = {cte.resource_type for cte in result}
        assert resource_types == {"Condition", "Observation"}


class TestSQLRetrieveCTEIntegration:
    """Integration tests for SQLRetrieveCTE with other SQL types."""

    def test_complex_precomputed_column(self):
        """Test CTE with complex precomputed column expression."""
        # Build a CASE expression for status
        status_expr = SQLFunctionCall(
            name="CASE",
            args=[
                SQLFunctionCall(
                    name="WHEN",
                    args=[
                        SQLFunctionCall(
                            name="fhirpath_bool",
                            args=[
                                SQLQualifiedIdentifier(parts=["r", "resource"]),
                                SQLLiteral(value="verificationStatus.coding.where(system='http://terminology.hl7.org/CodeSystem/condition-ver-status' and code='confirmed').exists()"),
                            ],
                        ),
                        SQLLiteral(value="confirmed"),
                    ],
                ),
            ],
        )

        cte = SQLRetrieveCTE(
            name="Condition",
            resource_type="Condition",
            precomputed_columns={"status": status_expr},
        )
        sql = cte.to_sql()

        assert "status" in sql

    def test_multiple_precomputed_columns(self):
        """Test CTE with multiple precomputed columns."""
        cte = SQLRetrieveCTE(
            name="Observation",
            resource_type="Observation",
            precomputed_columns={
                "effective_date": SQLAlias(
                    expr=SQLFunctionCall(
                        name="fhirpath_date",
                        args=[
                            SQLQualifiedIdentifier(parts=["r", "resource"]),
                            SQLLiteral(value="effectiveDateTime"),
                        ],
                    ),
                    alias="effective_date"
                ),
                "value": SQLAlias(
                    expr=SQLFunctionCall(
                        name="fhirpath_text",
                        args=[
                            SQLQualifiedIdentifier(parts=["r", "resource"]),
                            SQLLiteral(value="valueString"),
                        ],
                    ),
                    alias="value"
                ),
            },
        )
        sql = cte.to_sql()

        assert "effective_date" in sql
        assert "value" in sql
        assert "fhirpath_date" in sql
        assert "fhirpath_text" in sql
