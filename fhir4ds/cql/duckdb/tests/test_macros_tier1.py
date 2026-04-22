"""
Unit tests for Tier 1 SQL macros.

Tests all CQL function macros for:
- Correctness (expected values)
- Null handling (CQL semantics)
- Index conversion (0-based to 1-based)
"""

import duckdb
import pytest

from ..import register


@pytest.fixture
def con():
    """Create a DuckDB connection with all CQL macros registered."""
    con = duckdb.connect(":memory:")
    register(con, include_fhirpath=False)
    yield con
    con.close()


class TestMathMacros:
    """Test math function macros."""

    def test_abs_positive(self, con):
        result = con.execute("SELECT Abs(-5)").fetchone()[0]
        assert result == 5

    def test_abs_negative(self, con):
        result = con.execute("SELECT Abs(5)").fetchone()[0]
        assert result == 5

    def test_abs_zero(self, con):
        result = con.execute("SELECT Abs(0)").fetchone()[0]
        assert result == 0

    def test_abs_null(self, con):
        result = con.execute("SELECT Abs(NULL)").fetchone()[0]
        assert result is None

    def test_ceiling(self, con):
        result = con.execute("SELECT Ceiling(4.3)").fetchone()[0]
        assert result == 5

    def test_ceiling_negative(self, con):
        result = con.execute("SELECT Ceiling(-4.3)").fetchone()[0]
        assert result == -4

    def test_floor(self, con):
        result = con.execute("SELECT Floor(4.7)").fetchone()[0]
        assert result == 4

    def test_floor_negative(self, con):
        result = con.execute("SELECT Floor(-4.7)").fetchone()[0]
        assert result == -5

    def test_round_no_precision(self, con):
        result = con.execute("SELECT Round(3.14159)").fetchone()[0]
        assert result == 3.0

    def test_round_with_precision(self, con):
        # Use RoundTo for precision rounding
        result = con.execute("SELECT RoundTo(3.14159, 2)").fetchone()[0]
        assert float(result) == 3.14

    def test_round_null(self, con):
        result = con.execute("SELECT Round(NULL)").fetchone()[0]
        assert result is None

    def test_sqrt(self, con):
        result = con.execute("SELECT Sqrt(16)").fetchone()[0]
        assert result == 4.0

    def test_power(self, con):
        result = con.execute("SELECT Power(2, 3)").fetchone()[0]
        assert result == 8.0

    def test_mod(self, con):
        result = con.execute("SELECT Mod(17, 5)").fetchone()[0]
        assert result == 2

    def test_div(self, con):
        result = con.execute("SELECT Div(17, 5)").fetchone()[0]
        assert result == 3


class TestStringMacros:
    """Test string function macros with index conversion."""

    def test_length(self, con):
        result = con.execute("SELECT Length('hello')").fetchone()[0]
        assert result == 5

    def test_length_null(self, con):
        result = con.execute("SELECT Length(NULL)").fetchone()[0]
        assert result is None

    def test_upper(self, con):
        result = con.execute("SELECT Upper('hello')").fetchone()[0]
        assert result == "HELLO"

    def test_lower(self, con):
        result = con.execute("SELECT Lower('HELLO')").fetchone()[0]
        assert result == "hello"

    def test_concat_both_values(self, con):
        result = con.execute("SELECT Concat('hello', ' world')").fetchone()[0]
        assert result == "hello world"

    def test_concat_null_propagates(self, con):
        # CQL/FHIRPath: Concat with null should return null
        result = con.execute("SELECT Concat(NULL, 'test')").fetchone()[0]
        assert result is None

    def test_concat_null_second(self, con):
        result = con.execute("SELECT Concat('test', NULL)").fetchone()[0]
        assert result is None

    def test_substring_start_only(self, con):
        # CQL: Substring("hello", 1) should return "ello" (0-based)
        result = con.execute("SELECT Substring('hello', 1)").fetchone()[0]
        assert result == "ello"

    def test_substring_with_length(self, con):
        # CQL: Substring("hello", 1, 3) should return "ell"
        result = con.execute("SELECT SubstringLen('hello', 1, 3)").fetchone()[0]
        assert result == "ell"

    def test_substring_start_at_zero(self, con):
        # CQL: Substring("hello", 0) should return "hello"
        result = con.execute("SELECT Substring('hello', 0)").fetchone()[0]
        assert result == "hello"

    def test_substring_null(self, con):
        result = con.execute("SELECT Substring(NULL, 0)").fetchone()[0]
        assert result is None

    @pytest.mark.skip(reason="CQL string IndexOf is handled by translator (strpos), not registered as macro")
    def test_indexof_found(self, con):
        # CQL: IndexOf("hello", "ll") should return 2 (0-based)
        result = con.execute("SELECT IndexOf('hello', 'll')").fetchone()[0]
        assert result == 2

    @pytest.mark.skip(reason="CQL string IndexOf is handled by translator (strpos), not registered as macro")
    def test_indexof_not_found(self, con):
        # CQL: IndexOf("hello", "xyz") should return -1
        result = con.execute("SELECT IndexOf('hello', 'xyz')").fetchone()[0]
        assert result == -1

    @pytest.mark.skip(reason="CQL string IndexOf is handled by translator (strpos), not registered as macro")
    def test_indexof_start(self, con):
        # CQL: IndexOf("hello", "h") should return 0
        result = con.execute("SELECT IndexOf('hello', 'h')").fetchone()[0]
        assert result == 0

    @pytest.mark.skip(reason="CQL string IndexOf is handled by translator (strpos), not registered as macro")
    def test_indexof_null(self, con):
        result = con.execute("SELECT IndexOf(NULL, 'test')").fetchone()[0]
        assert result is None

    def test_starts_with(self, con):
        result = con.execute("SELECT StartsWith('hello world', 'hello')").fetchone()[0]
        assert result is True

    def test_ends_with(self, con):
        result = con.execute("SELECT EndsWith('hello world', 'world')").fetchone()[0]
        assert result is True

    def test_contains(self, con):
        result = con.execute("SELECT Contains('hello world', 'llo')").fetchone()[0]
        assert result is True

    def test_replace(self, con):
        result = con.execute("SELECT Replace('hello', 'l', 'L')").fetchone()[0]
        assert result == "heLLo"

    def test_trim(self, con):
        result = con.execute("SELECT Trim('  hello  ')").fetchone()[0]
        assert result == "hello"

    def test_ltrim(self, con):
        result = con.execute("SELECT LTrim('  hello  ')").fetchone()[0]
        assert result == "hello  "

    def test_rtrim(self, con):
        result = con.execute("SELECT RTrim('  hello  ')").fetchone()[0]
        assert result == "  hello"


class TestLogicalMacros:
    """Test logical function macros (Tier 2)."""

    def test_xor_true_false(self, con):
        result = con.execute("SELECT Xor(true, false)").fetchone()[0]
        assert result is True

    def test_xor_true_true(self, con):
        result = con.execute("SELECT Xor(true, true)").fetchone()[0]
        assert result is False

    def test_xor_false_false(self, con):
        result = con.execute("SELECT Xor(false, false)").fetchone()[0]
        assert result is False

    def test_xor_false_true(self, con):
        result = con.execute("SELECT Xor(false, true)").fetchone()[0]
        assert result is True

    def test_implies_false_true(self, con):
        # CQL: false implies X = true
        result = con.execute("SELECT Implies(false, true)").fetchone()[0]
        assert result is True

    def test_implies_false_false(self, con):
        result = con.execute("SELECT Implies(false, false)").fetchone()[0]
        assert result is True

    def test_implies_true_true(self, con):
        result = con.execute("SELECT Implies(true, true)").fetchone()[0]
        assert result is True

    def test_implies_true_false(self, con):
        result = con.execute("SELECT Implies(true, false)").fetchone()[0]
        assert result is False

    def test_coalesce_first_not_null(self, con):
        result = con.execute("SELECT Coalesce('hello', 'world')").fetchone()[0]
        assert result == "hello"

    def test_coalesce_first_null(self, con):
        result = con.execute("SELECT Coalesce(NULL, 'world')").fetchone()[0]
        assert result == "world"


class TestDateTimeMacros:
    """Test datetime function macros."""

    def test_year_extraction(self, con):
        result = con.execute("SELECT Year(DATE '2024-06-15')").fetchone()[0]
        assert result == 2024

    def test_month_extraction(self, con):
        result = con.execute("SELECT Month(DATE '2024-06-15')").fetchone()[0]
        assert result == 6

    def test_day_extraction(self, con):
        result = con.execute("SELECT Day(DATE '2024-06-15')").fetchone()[0]
        assert result == 15

    def test_days_between(self, con):
        result = con.execute(
            "SELECT DaysBetween(DATE '2024-01-01', DATE '2024-01-10')"
        ).fetchone()[0]
        assert result == 9

    def test_months_between(self, con):
        result = con.execute(
            "SELECT MonthsBetween(DATE '2024-01-15', DATE '2024-03-15')"
        ).fetchone()[0]
        assert result == 2

    def test_years_between(self, con):
        result = con.execute(
            "SELECT YearsBetween(DATE '2020-01-01', DATE '2024-01-01')"
        ).fetchone()[0]
        assert result == 4

    def test_date_constructor(self, con):
        result = con.execute("SELECT MakeDate(2024, 6, 15)").fetchone()[0]
        assert str(result) == "2024-06-15"


class TestConversionMacros:
    """Test type conversion macros."""

    def test_to_string_integer(self, con):
        result = con.execute("SELECT ToString(42)").fetchone()[0]
        assert result == "42"

    def test_to_integer(self, con):
        result = con.execute("SELECT ToInteger('42')").fetchone()[0]
        assert result == 42

    def test_to_boolean_true(self, con):
        result = con.execute("SELECT ToBoolean('true')").fetchone()[0]
        assert result is True

    def test_to_date(self, con):
        result = con.execute("SELECT ToDate('2024-06-15')").fetchone()[0]
        assert str(result) == "2024-06-15"


class TestAggregateMacros:
    """Test aggregate function macros (and built-in aggregates used by CQL)."""

    def test_count(self, con):
        """Count uses DuckDB built-in, not a macro."""
        result = con.execute("SELECT Count(x) FROM (SELECT unnest([1, 2, 3, 4, 5]) AS x)").fetchone()[0]
        assert result == 5

    def test_count_distinct(self, con):
        """Verify COUNT(DISTINCT x) works — this was broken when Count was a macro."""
        result = con.execute("SELECT COUNT(DISTINCT x) FROM (SELECT unnest([1, 2, 2, 3, 3]) AS x)").fetchone()[0]
        assert result == 3

    def test_sum(self, con):
        """Sum uses DuckDB built-in, not a macro."""
        result = con.execute("SELECT Sum(x) FROM (SELECT unnest([1, 2, 3, 4, 5]) AS x)").fetchone()[0]
        assert result == 15

    def test_min(self, con):
        """Min uses DuckDB built-in, not a macro."""
        result = con.execute("SELECT Min(x) FROM (SELECT unnest([3, 1, 4, 1, 5]) AS x)").fetchone()[0]
        assert result == 1

    def test_max(self, con):
        """Max uses DuckDB built-in, not a macro."""
        result = con.execute("SELECT Max(x) FROM (SELECT unnest([3, 1, 4, 1, 5]) AS x)").fetchone()[0]
        assert result == 5

    def test_avg(self, con):
        """Avg uses DuckDB built-in, not a macro."""
        result = con.execute("SELECT Avg(x) FROM (SELECT unnest([1, 2, 3, 4, 5]) AS x)").fetchone()[0]
        assert result == 3.0

    def test_median(self, con):
        result = con.execute("SELECT Median(x) FROM (SELECT unnest([1, 2, 3, 4, 5]) AS x)").fetchone()[0]
        assert result == 3.0

    def test_stddev(self, con):
        result = con.execute("SELECT StdDev(x) FROM (SELECT unnest([1, 2, 3, 4, 5]) AS x)").fetchone()[0]
        import math
        assert math.isclose(result, 1.5811388300841898, rel_tol=0.001)
