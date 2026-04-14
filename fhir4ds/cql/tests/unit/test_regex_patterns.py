"""
Unit tests for regex patterns used in CQL to SQL translation.

Tests the regex patterns for:
- FHIRPath function replacement (fhirpath_* -> column references)
- Correlated reference detection (outer table.resource references)
- Identifier detection (simple SQL identifiers)
- Invalid CASE + UNION ALL pattern detection
"""

import re
import pytest


# Regex patterns from the codebase (copied here for testing)

# Pattern to match fhirpath function calls and extract components
FHIRPATH_PATTERN = r"""fhirpath_(text|date|bool)\s*\(\s*([^,]+),\s*['"]([^'"]+)['"]\s*\)"""

# Pattern to detect correlated outer references like "BPExam.resource"
CORRELATED_REF_PATTERN = r'\b([A-Z][a-zA-Z0-9]*)\.resource\b'

# Pattern for simple SQL identifiers
SIMPLE_IDENTIFIER_PATTERN = r'^[A-Za-z_][A-Za-z0-9_]*$'

# Pattern to detect CASE with UNION ALL (invalid in scalar context)
CASE_UNION_PATTERN = r'CASE\s+WHEN.*?THEN\s*\(\s*SELECT.*?UNION\s+ALL'


class TestFhirpathReplacementPatterns:
    """Test regex for replacing fhirpath calls with column references."""

    def test_simple_property_match(self):
        """Test matching a simple fhirpath_text call with single property."""
        sql = "fhirpath_text(r.resource, 'active')"
        match = re.search(FHIRPATH_PATTERN, sql, re.IGNORECASE)

        assert match is not None
        assert match.group(1) == "text"
        assert match.group(2) == "r.resource"
        assert match.group(3) == "active"

    def test_dotted_property_match(self):
        """Test matching fhirpath call with dotted property path."""
        sql = "fhirpath_text(t1.resource, 'verificationStatus.coding.code')"
        match = re.search(FHIRPATH_PATTERN, sql, re.IGNORECASE)

        assert match is not None
        assert match.group(1) == "text"
        assert match.group(3) == "verificationStatus.coding.code"

    def test_date_function_match(self):
        """Test matching fhirpath_date function."""
        sql = "fhirpath_date(r.resource, 'onsetDateTime')"
        match = re.search(FHIRPATH_PATTERN, sql, re.IGNORECASE)

        assert match is not None
        assert match.group(1) == "date"
        assert match.group(3) == "onsetDateTime"

    def test_bool_function_match(self):
        """Test matching fhirpath_bool function."""
        sql = "fhirpath_bool(r.resource, 'active')"
        match = re.search(FHIRPATH_PATTERN, sql, re.IGNORECASE)

        assert match is not None
        assert match.group(1) == "bool"
        assert match.group(3) == "active"

    def test_extra_whitespace(self):
        """Test matching with extra whitespace in function call."""
        sql = "fhirpath_text(  r.resource  ,  'status'  )"
        match = re.search(FHIRPATH_PATTERN, sql, re.IGNORECASE)

        assert match is not None
        assert match.group(2).strip() == "r.resource"
        assert match.group(3) == "status"

    def test_no_match_different_param(self):
        """Test that non-matching patterns return None."""
        sql = "some_other_function(r.resource, 'active')"
        match = re.search(FHIRPATH_PATTERN, sql, re.IGNORECASE)

        assert match is None

    def test_no_match_different_path(self):
        """Test that paths without fhirpath prefix don't match."""
        sql = "resource->>'active'"
        match = re.search(FHIRPATH_PATTERN, sql, re.IGNORECASE)

        assert match is None

    def test_regex_metachar_in_path_escaped(self):
        """Test that regex metacharacters in path are handled correctly."""
        # Path with dots should be captured correctly
        sql = "fhirpath_text(r.resource, 'code.coding.code')"
        match = re.search(FHIRPATH_PATTERN, sql, re.IGNORECASE)

        assert match is not None
        assert match.group(3) == "code.coding.code"

    def test_multiple_replacements(self):
        """Test finding all fhirpath calls in a SQL expression."""
        sql = """
        SELECT
            fhirpath_text(r.resource, 'status') as status,
            fhirpath_date(r.resource, 'onsetDateTime') as onset,
            fhirpath_bool(r.resource, 'active') as active
        """
        matches = re.findall(FHIRPATH_PATTERN, sql, re.IGNORECASE)

        assert len(matches) == 3
        function_types = [m[0] for m in matches]
        assert "text" in function_types
        assert "date" in function_types
        assert "bool" in function_types


class TestCorrelatedReferenceDetection:
    """Test regex for detecting correlated outer references."""

    def test_detect_correlated_ref(self):
        """Test detecting simple correlated reference like BPExam.resource."""
        sql = "SELECT * FROM conditions WHERE fhirpath_bool(BPExam.resource, 'active')"
        match = re.search(CORRELATED_REF_PATTERN, sql)

        assert match is not None
        assert match.group(1) == "BPExam"

    def test_detect_multi_word_alias(self):
        """Test detecting multi-word PascalCase alias."""
        sql = "EssentialHypertension.resource"
        match = re.search(CORRELATED_REF_PATTERN, sql)

        assert match is not None
        assert match.group(1) == "EssentialHypertension"

    def test_no_match_lowercase(self):
        """Test that lowercase aliases don't match (r.resource should not match)."""
        sql = "r.resource"
        match = re.search(CORRELATED_REF_PATTERN, sql)

        # r is lowercase, so should NOT match the PascalCase pattern
        assert match is None

    def test_no_match_column_only(self):
        """Test that bare 'resource' column doesn't match."""
        sql = "SELECT resource FROM table"
        match = re.search(CORRELATED_REF_PATTERN, sql)

        # Just 'resource' without alias prefix shouldn't match
        assert match is None

    def test_no_match_different_column(self):
        """Test that other columns don't match."""
        sql = "BPExam.other_column"
        match = re.search(CORRELATED_REF_PATTERN, sql)

        assert match is None

    def test_extract_alias_name(self):
        """Test extracting the alias name from correlated reference."""
        sql = "DiabetesCondition.resource"
        match = re.search(CORRELATED_REF_PATTERN, sql)

        assert match is not None
        # The capturing group should extract just the alias
        assert match.group(1) == "DiabetesCondition"


class TestIdentifierDetection:
    """Test regex for simple identifier detection."""

    def test_simple_identifier(self):
        """Test valid simple identifier."""
        assert re.match(SIMPLE_IDENTIFIER_PATTERN, "patient_id") is not None
        assert re.match(SIMPLE_IDENTIFIER_PATTERN, "PatientID") is not None
        assert re.match(SIMPLE_IDENTIFIER_PATTERN, "_private") is not None

    def test_qualified_identifier(self):
        """Test qualified identifier (should match as simple)."""
        # Note: This pattern is for single identifiers, not qualified ones
        # Qualified identifiers like "r.resource" would need different handling
        assert re.match(SIMPLE_IDENTIFIER_PATTERN, "r") is not None
        # The full qualified name would NOT match
        assert re.match(SIMPLE_IDENTIFIER_PATTERN, "r.resource") is None

    def test_quoted_identifier(self):
        """Test that quoted identifiers don't match simple pattern."""
        # Quoted identifiers with special chars shouldn't match
        assert re.match(SIMPLE_IDENTIFIER_PATTERN, '"my-column"') is None

    def test_no_match_subquery(self):
        """Test that subquery syntax doesn't match."""
        assert re.match(SIMPLE_IDENTIFIER_PATTERN, "(SELECT 1)") is None

    def test_no_match_function_call(self):
        """Test that function calls don't match."""
        assert re.match(SIMPLE_IDENTIFIER_PATTERN, "COUNT(*)") is None
        assert re.match(SIMPLE_IDENTIFIER_PATTERN, "fhirpath_text()") is None

    def test_no_match_unnest(self):
        """Test that UNNEST expressions don't match."""
        assert re.match(SIMPLE_IDENTIFIER_PATTERN, "UNNEST(array)") is None

    def test_numeric_suffix_valid(self):
        """Test that identifiers with numbers (not starting) are valid."""
        assert re.match(SIMPLE_IDENTIFIER_PATTERN, "column123") is not None
        assert re.match(SIMPLE_IDENTIFIER_PATTERN, "t1") is not None

    def test_starting_digit_invalid(self):
        """Test that identifiers starting with digit are invalid."""
        assert re.match(SIMPLE_IDENTIFIER_PATTERN, "123column") is None


class TestCaseUnionDetection:
    """Test regex for detecting invalid CASE with UNION ALL."""

    def test_detect_invalid_pattern(self):
        """Test detecting CASE WHEN with UNION ALL in THEN clause."""
        sql = """
        CASE WHEN X = 1 THEN (SELECT a FROM t1 UNION ALL SELECT a FROM t2)
        """
        match = re.search(CASE_UNION_PATTERN, sql, re.IGNORECASE | re.DOTALL)

        assert match is not None

    def test_detect_with_whitespace(self):
        """Test detecting pattern with varied whitespace."""
        sql = """
        CASE  WHEN  condition  THEN  (  SELECT  *  FROM  t1  UNION  ALL  SELECT  *  FROM  t2 )
        """
        match = re.search(CASE_UNION_PATTERN, sql, re.IGNORECASE | re.DOTALL)

        assert match is not None

    def test_safe_case_no_union(self):
        """Test that CASE without UNION ALL doesn't match."""
        sql = "CASE WHEN X = 1 THEN 'a' ELSE 'b' END"
        match = re.search(CASE_UNION_PATTERN, sql, re.IGNORECASE | re.DOTALL)

        assert match is None

    def test_safe_union_no_case(self):
        """Test that UNION ALL without CASE doesn't match."""
        sql = "SELECT a FROM t1 UNION ALL SELECT a FROM t2"
        match = re.search(CASE_UNION_PATTERN, sql, re.IGNORECASE | re.DOTALL)

        assert match is None

    def test_safe_simple_case(self):
        """Test that simple CASE expressions are safe."""
        sql = "CASE WHEN active THEN 1 ELSE 0 END"
        match = re.search(CASE_UNION_PATTERN, sql, re.IGNORECASE | re.DOTALL)

        assert match is None

    def test_nested_case_with_union(self):
        """Test detecting nested CASE with UNION ALL."""
        sql = """
        CASE
            WHEN condition1 THEN (SELECT 1 UNION ALL SELECT 2)
            ELSE 0
        END
        """
        match = re.search(CASE_UNION_PATTERN, sql, re.IGNORECASE | re.DOTALL)

        assert match is not None


class TestAdditionalPatterns:
    """Additional tests for edge cases and real-world patterns."""

    def test_fhirpath_with_qualified_resource(self):
        """Test fhirpath with fully qualified resource reference."""
        sql = 'fhirpath_text("Condition: Essential Hypertension".resource, \'status\')'
        # This should still match the pattern
        match = re.search(FHIRPATH_PATTERN, sql, re.IGNORECASE)

        # The pattern should capture the qualified reference
        assert match is not None

    def test_multiple_correlated_refs_in_subquery(self):
        """Test finding multiple correlated references."""
        sql = """
        SELECT * FROM outer_table o
        WHERE EXISTS (
            SELECT 1 FROM inner_table i
            WHERE OuterTable.resource = i.ref
            AND OtherAlias.resource = i.ref2
        )
        """
        matches = re.findall(CORRELATED_REF_PATTERN, sql)

        assert len(matches) == 2
        assert "OuterTable" in matches
        assert "OtherAlias" in matches

    def test_fhirpath_case_insensitive(self):
        """Test that fhirpath matching is case insensitive."""
        patterns = [
            "fhirpath_text(r.resource, 'status')",
            "FHIRPATH_TEXT(r.resource, 'status')",
            "Fhirpath_Text(r.resource, 'status')",
        ]

        for sql in patterns:
            match = re.search(FHIRPATH_PATTERN, sql, re.IGNORECASE)
            assert match is not None, f"Failed to match: {sql}"

    def test_identifier_with_underscore_prefix(self):
        """Test identifiers starting with underscore."""
        assert re.match(SIMPLE_IDENTIFIER_PATTERN, "_internal_id") is not None
        assert re.match(SIMPLE_IDENTIFIER_PATTERN, "__dunder__") is not None

    def test_case_union_multiline(self):
        """Test CASE UNION detection across multiple lines."""
        sql = """
        CASE
            WHEN some_condition
            THEN (
                SELECT col FROM table1
                UNION ALL
                SELECT col FROM table2
            )
        END
        """
        match = re.search(CASE_UNION_PATTERN, sql, re.IGNORECASE | re.DOTALL)

        assert match is not None
