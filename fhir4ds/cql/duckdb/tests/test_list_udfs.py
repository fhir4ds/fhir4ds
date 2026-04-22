"""
Unit tests for CQL List UDFs.

Tests for list operations:
- First, Last
- Skip, Take
- SingletonFrom
- Distinct
"""

import pytest
import duckdb


# ========================================
# Fixtures
# ========================================

@pytest.fixture
def con():
    """DuckDB connection with CQL functions registered."""
    con = duckdb.connect(":memory:")
    from ..import register
    register(con)
    yield con
    con.close()


# ========================================
# First tests
# ========================================

class TestFirst:
    """Tests for the First list operation."""

    def test_first_with_elements(self, con):
        """Test First with a list containing elements."""
        # First([1,2,3]) should return 1
        result = con.execute("SELECT First([1, 2, 3])").fetchone()
        assert result[0] == 1

    def test_first_empty(self, con):
        """Test First with an empty list."""
        # First([]) should return NULL
        result = con.execute("SELECT First([])").fetchone()
        assert result[0] is None

    def test_first_null_input(self, con):
        """Test First with NULL input."""
        # First(NULL) should return NULL
        result = con.execute("SELECT First(NULL)").fetchone()
        assert result[0] is None

    def test_first_single_element(self, con):
        """Test First with a single element list."""
        result = con.execute("SELECT First([42])").fetchone()
        assert result[0] == 42

    def test_first_with_strings(self, con):
        """Test First with string elements."""
        result = con.execute("SELECT First(['a', 'b', 'c'])").fetchone()
        assert result[0] == 'a'


# ========================================
# Last tests
# ========================================

class TestLast:
    """Tests for the Last list operation."""

    def test_last_with_elements(self, con):
        """Test Last with a list containing elements."""
        # Last([1,2,3]) should return 3
        result = con.execute("SELECT Last([1, 2, 3])").fetchone()
        assert result[0] == 3

    def test_last_empty(self, con):
        """Test Last with an empty list."""
        # Last([]) should return NULL
        result = con.execute("SELECT Last([])").fetchone()
        assert result[0] is None

    def test_last_null_input(self, con):
        """Test Last with NULL input."""
        # Last(NULL) should return NULL
        result = con.execute("SELECT Last(NULL)").fetchone()
        assert result[0] is None

    def test_last_single_element(self, con):
        """Test Last with a single element list."""
        result = con.execute("SELECT Last([42])").fetchone()
        assert result[0] == 42

    def test_last_with_strings(self, con):
        """Test Last with string elements."""
        result = con.execute("SELECT Last(['a', 'b', 'c'])").fetchone()
        assert result[0] == 'c'


# ========================================
# Skip tests
# ========================================

class TestSkip:
    """Tests for the Skip list operation."""

    def test_skip_positive(self, con):
        """Test Skip with positive count."""
        # Skip([1,2,3], 1) should return [2,3]
        result = con.execute("SELECT Skip([1, 2, 3], 1)").fetchone()
        assert result[0] == [2, 3]

    def test_skip_all(self, con):
        """Test Skip when skipping all elements."""
        # Skip([1,2,3], 5) should return []
        result = con.execute("SELECT Skip([1, 2, 3], 5)").fetchone()
        assert result[0] == []

    def test_skip_zero(self, con):
        """Test Skip with zero count."""
        # Skip([1,2,3], 0) should return [1,2,3]
        result = con.execute("SELECT Skip([1, 2, 3], 0)").fetchone()
        assert result[0] == [1, 2, 3]

    def test_skip_null_input(self, con):
        """Test Skip with NULL input."""
        # Skip(NULL, 1) should return NULL
        result = con.execute("SELECT Skip(NULL, 1)").fetchone()
        assert result[0] is None

    def test_skip_partial(self, con):
        """Test Skip with partial elements."""
        # Skip([1,2,3,4,5], 2) should return [3,4,5]
        result = con.execute("SELECT Skip([1, 2, 3, 4, 5], 2)").fetchone()
        assert result[0] == [3, 4, 5]

    def test_skip_empty_list(self, con):
        """Test Skip with empty list."""
        result = con.execute("SELECT Skip([], 2)").fetchone()
        assert result[0] == []


# ========================================
# Take tests
# ========================================

class TestTake:
    """Tests for the Take list operation."""

    def test_take_positive(self, con):
        """Test Take with positive count."""
        # Take([1,2,3], 2) should return [1,2]
        result = con.execute("SELECT Take([1, 2, 3], 2)").fetchone()
        assert result[0] == [1, 2]

    def test_take_all(self, con):
        """Test Take when taking more than available."""
        # Take([1,2,3], 5) should return [1,2,3]
        result = con.execute("SELECT Take([1, 2, 3], 5)").fetchone()
        assert result[0] == [1, 2, 3]

    def test_take_zero(self, con):
        """Test Take with zero count."""
        # Take([1,2,3], 0) should return []
        result = con.execute("SELECT Take([1, 2, 3], 0)").fetchone()
        assert result[0] == []

    def test_take_null_input(self, con):
        """Test Take with NULL input."""
        # Take(NULL, 1) should return NULL
        result = con.execute("SELECT Take(NULL, 1)").fetchone()
        assert result[0] is None

    def test_take_single(self, con):
        """Test Take with single element."""
        # Take([1,2,3], 1) should return [1]
        result = con.execute("SELECT Take([1, 2, 3], 1)").fetchone()
        assert result[0] == [1]

    def test_take_empty_list(self, con):
        """Test Take with empty list."""
        result = con.execute("SELECT Take([], 2)").fetchone()
        assert result[0] == []


# ========================================
# SingletonFrom tests
# ========================================

class TestSingletonFrom:
    """Tests for the SingletonFrom list operation."""

    def test_singleton_single(self, con):
        """Test SingletonFrom with single element."""
        # SingletonFrom([1]) should return 1 (as string due to VARCHAR return type)
        result = con.execute("SELECT SingletonFrom([1])").fetchone()
        assert result[0] == '1'

    def test_singleton_empty(self, con):
        """Test SingletonFrom with empty list."""
        # SingletonFrom([]) should return NULL
        result = con.execute("SELECT SingletonFrom([])").fetchone()
        assert result[0] is None

    def test_singleton_multiple(self, con):
        """Test SingletonFrom with multiple elements raises error per CQL spec."""
        with pytest.raises(duckdb.InvalidInputException, match="SingletonFrom"):
            con.execute("SELECT SingletonFrom([1, 2])").fetchone()

    def test_singleton_null_input(self, con):
        """Test SingletonFrom with NULL input."""
        # SingletonFrom(NULL) should return NULL
        result = con.execute("SELECT SingletonFrom(NULL)").fetchone()
        assert result[0] is None

    def test_singleton_string(self, con):
        """Test SingletonFrom with string element."""
        result = con.execute("SELECT SingletonFrom(['hello'])").fetchone()
        assert result[0] == 'hello'


# ========================================
# Distinct tests
# ========================================

class TestDistinct:
    """Tests for the Distinct list operation."""

    def test_distinct_duplicates(self, con):
        """Test Distinct with duplicate elements."""
        # "Distinct"([1,2,2,3]) should return [1,2,3]
        # Note: Distinct is a reserved keyword, so we use quotes
        result = con.execute('SELECT "Distinct"([1, 2, 2, 3])').fetchone()
        # Order may vary, so compare as sets
        assert set(result[0]) == {1, 2, 3}

    def test_distinct_empty(self, con):
        """Test Distinct with empty list."""
        # "Distinct"([]) should return []
        result = con.execute('SELECT "Distinct"([])').fetchone()
        assert result[0] == []

    def test_distinct_null_input(self, con):
        """Test Distinct with NULL input."""
        # "Distinct"(NULL) should return NULL
        result = con.execute('SELECT "Distinct"(NULL)').fetchone()
        assert result[0] is None

    def test_distinct_no_duplicates(self, con):
        """Test Distinct with no duplicates."""
        # "Distinct"([1,2,3]) should return [1,2,3]
        result = con.execute('SELECT "Distinct"([1, 2, 3])').fetchone()
        assert set(result[0]) == {1, 2, 3}

    def test_distinct_all_same(self, con):
        """Test Distinct with all same elements."""
        # "Distinct"([1,1,1]) should return [1]
        result = con.execute('SELECT "Distinct"([1, 1, 1])').fetchone()
        assert result[0] == [1] or set(result[0]) == {1}

    def test_distinct_strings(self, con):
        """Test Distinct with string elements."""
        result = con.execute('SELECT "Distinct"([\'a\', \'b\', \'a\', \'c\'])').fetchone()
        assert set(result[0]) == {'a', 'b', 'c'}


# ========================================
# Combined operations tests
# ========================================

class TestCombinedOperations:
    """Tests combining multiple list operations."""

    def test_skip_then_take(self, con):
        """Test Skip followed by Take."""
        # Take(Skip([1,2,3,4,5], 2), 2) should return [3,4]
        result = con.execute("SELECT Take(Skip([1, 2, 3, 4, 5], 2), 2)").fetchone()
        assert result[0] == [3, 4]

    def test_distinct_then_first(self, con):
        """Test Distinct followed by First."""
        # First("Distinct"([1,1,2,2,3])) should return an element from the distinct set
        # Note: Distinct is a reserved keyword, so we use quotes
        # Note: list_distinct does not guarantee order, so First returns any element
        result = con.execute('SELECT First("Distinct"([1, 1, 2, 2, 3]))').fetchone()
        # Result should be one of the distinct values
        assert result[0] in (1, 2, 3, '1', '2', '3')

    def test_distinct_then_last(self, con):
        """Test Distinct followed by Last."""
        # Last("Distinct"([1,1,2,2,3])) should return an element from the distinct set
        # Note: Distinct is a reserved keyword, so we use quotes
        # Note: list_distinct does not guarantee order, so Last returns any element
        result = con.execute('SELECT Last("Distinct"([1, 1, 2, 2, 3]))').fetchone()
        # Result should be one of the distinct values
        assert result[0] in (1, 2, 3, '1', '2', '3')

    def test_take_then_singleton(self, con):
        """Test Take followed by SingletonFrom."""
        # SingletonFrom(Take([1,2,3], 1)) should return 1 (as string)
        result = con.execute("SELECT SingletonFrom(Take([1, 2, 3], 1))").fetchone()
        assert result[0] == '1'
