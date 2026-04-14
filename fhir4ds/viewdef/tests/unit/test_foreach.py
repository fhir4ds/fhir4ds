"""Unit tests for forEach and forEachOrNull handling.

Tests the UNNEST generation for flattening FHIRPath array
expressions into SQL rows using CROSS JOIN LATERAL (forEach)
or LEFT JOIN LATERAL (forEachOrNull).
"""

import pytest

from ...unnest import (
    generate_foreach_unnest,
    generate_foreachornull_unnest,
    UnnestGenerator,
    UnnestInfo,
)


class TestGenerateForeachUnnest:
    """Tests for CROSS JOIN LATERAL UNNEST generation."""

    def test_basic_foreach_unnest(self):
        """Test basic forEach UNNEST generation."""
        sql = generate_foreach_unnest("name", "t.resource", "name_elem")

        assert "CROSS JOIN LATERAL" in sql
        assert "unnest" in sql.lower()
        assert "fhirpath" in sql
        assert "name_elem" in sql
        assert "name_elem_table" in sql

    def test_foreach_with_complex_path(self):
        """Test forEach with complex FHIRPath expression."""
        sql = generate_foreach_unnest(
            "extension.where(url='birthplace')",
            "t.resource",
            "ext_elem"
        )

        assert "CROSS JOIN LATERAL" in sql
        assert "extension.where(url=''birthplace'')" in sql

    def test_foreach_structure(self):
        """Test the structure of forEach UNNEST."""
        sql = generate_foreach_unnest("telecom", "t.resource", "telecom_elem")

        # Should contain SELECT subquery
        assert "SELECT" in sql
        assert "as telecom_elem" in sql


class TestGenerateForeachornullUnnest:
    """Tests for LEFT JOIN LATERAL UNNEST generation."""

    def test_basic_foreachornull_unnest(self):
        """Test basic forEachOrNull UNNEST generation."""
        sql = generate_foreachornull_unnest("telecom", "t.resource", "telecom_elem")

        assert "LEFT JOIN LATERAL" in sql
        assert "unnest" in sql.lower()
        assert "fhirpath" in sql
        assert "telecom_elem" in sql
        assert "ON true" in sql

    def test_foreachornull_preserves_null_rows(self):
        """Test forEachOrNull uses LEFT JOIN to preserve null rows."""
        sql = generate_foreachornull_unnest("identifier", "t.resource", "id_elem")

        # LEFT JOIN preserves rows even when array is empty
        assert "LEFT JOIN LATERAL" in sql
        assert "ON true" in sql

    def test_foreachornull_structure(self):
        """Test the structure of forEachOrNull UNNEST."""
        sql = generate_foreachornull_unnest("address", "t.resource", "addr_elem")

        # Should have proper structure
        assert "SELECT" in sql
        assert "as addr_elem" in sql
        assert "addr_elem_table" in sql


class TestUnnestInfo:
    """Tests for UnnestInfo dataclass."""

    def test_unnest_info_attributes(self):
        """Test UnnestInfo stores all attributes."""
        info = UnnestInfo(
            sql="CROSS JOIN LATERAL (...)",
            element_alias="name_elem",
            table_alias="name_elem_table",
            path="name",
            is_foreach=True
        )

        assert info.sql == "CROSS JOIN LATERAL (...)"
        assert info.element_alias == "name_elem"
        assert info.table_alias == "name_elem_table"
        assert info.path == "name"
        assert info.is_foreach is True

    def test_unnest_info_for_foreachornull(self):
        """Test UnnestInfo for forEachOrNull."""
        info = UnnestInfo(
            sql="LEFT JOIN LATERAL (...)",
            element_alias="telecom_elem",
            table_alias="telecom_elem_table",
            path="telecom",
            is_foreach=False
        )

        assert info.is_foreach is False


class TestUnnestGenerator:
    """Tests for UnnestGenerator class."""

    def test_initialization(self):
        """Test UnnestGenerator initialization."""
        gen = UnnestGenerator("t.resource")

        assert gen.base_resource_var == "t.resource"
        assert len(gen.unnests) == 0

    def test_generate_foreach(self):
        """Test generating forEach through UnnestGenerator."""
        gen = UnnestGenerator("t.resource")
        info = gen.generate_foreach("name", "t.resource")

        assert isinstance(info, UnnestInfo)
        assert info.is_foreach is True
        assert "CROSS JOIN LATERAL" in info.sql
        assert len(gen.unnests) == 1

    def test_generate_foreachornull(self):
        """Test generating forEachOrNull through UnnestGenerator."""
        gen = UnnestGenerator("t.resource")
        info = gen.generate_foreachornull("telecom", "t.resource")

        assert isinstance(info, UnnestInfo)
        assert info.is_foreach is False
        assert "LEFT JOIN LATERAL" in info.sql
        assert len(gen.unnests) == 1

    def test_custom_alias(self):
        """Test using custom alias for unnested element."""
        gen = UnnestGenerator("t.resource")
        info = gen.generate_foreach("name", "t.resource", alias="custom_name")

        assert info.element_alias == "custom_name"
        assert "custom_name" in info.sql

    def test_auto_generated_alias(self):
        """Test automatic alias generation from path."""
        gen = UnnestGenerator("t.resource")
        info = gen.generate_foreach("patient.identifier", "t.resource")

        # Should use last part of path for alias
        assert "identifier" in info.element_alias

    def test_unique_aliases(self):
        """Test that multiple unnests get unique aliases."""
        gen = UnnestGenerator("t.resource")

        info1 = gen.generate_foreach("name", "t.resource")
        info2 = gen.generate_foreach("name", "t.resource")

        # Aliases should be different
        assert info1.element_alias != info2.element_alias

    def test_get_all_join_sql(self):
        """Test getting all JOIN SQL as combined string."""
        gen = UnnestGenerator("t.resource")
        gen.generate_foreach("name", "t.resource")
        gen.generate_foreach("telecom", "t.resource")

        combined = gen.get_all_join_sql()

        assert "CROSS JOIN LATERAL" in combined
        assert combined.count("CROSS JOIN LATERAL") == 2

    def test_get_current_resource_var(self):
        """Test getting current resource variable context."""
        gen = UnnestGenerator("t.resource")

        # Before any unnests, should return base
        assert gen.get_current_resource_var() == "t.resource"

        # After an unnest, should return the element alias
        info = gen.generate_foreach("name", "t.resource")
        assert gen.get_current_resource_var() == info.element_alias

    def test_clear(self):
        """Test clearing all unnests."""
        gen = UnnestGenerator("t.resource")
        gen.generate_foreach("name", "t.resource")
        gen.generate_foreach("telecom", "t.resource")

        gen.clear()

        assert len(gen.unnests) == 0
        assert gen.get_current_resource_var() == "t.resource"

    def test_pop(self):
        """Test popping the most recent unnest."""
        gen = UnnestGenerator("t.resource")
        gen.generate_foreach("name", "t.resource")
        gen.generate_foreach("telecom", "t.resource")

        popped = gen.pop()

        assert popped.path == "telecom"
        assert len(gen.unnests) == 1

    def test_pop_empty(self):
        """Test popping from empty generator."""
        gen = UnnestGenerator("t.resource")
        result = gen.pop()

        assert result is None

    def test_len(self):
        """Test len() returns number of unnests."""
        gen = UnnestGenerator("t.resource")
        assert len(gen) == 0

        gen.generate_foreach("name", "t.resource")
        assert len(gen) == 1

        gen.generate_foreach("telecom", "t.resource")
        assert len(gen) == 2

    def test_bool(self):
        """Test boolean evaluation of generator."""
        gen = UnnestGenerator("t.resource")
        assert not gen  # Empty is falsy

        gen.generate_foreach("name", "t.resource")
        assert gen  # Non-empty is truthy


class TestNestedForeach:
    """Tests for nested forEach structures."""

    def test_nested_unnests(self):
        """Test generating nested UNNEST joins."""
        gen = UnnestGenerator("t.resource")

        # First level unnest
        info1 = gen.generate_foreach("name", "t.resource", alias="name_elem")

        # Second level unnest using first element
        info2 = gen.generate_foreach("given", "name_elem", alias="given_elem")

        assert len(gen.unnests) == 2
        assert info1.element_alias == "name_elem"
        assert info2.element_alias == "given_elem"
        assert info2.sql == generate_foreach_unnest("given", "name_elem", "given_elem")
