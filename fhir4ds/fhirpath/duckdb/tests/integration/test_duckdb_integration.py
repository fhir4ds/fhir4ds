"""
Integration tests for DuckDB FHIRPath extension.

Tests the extension with actual DuckDB SQL queries.
"""

import json
import pytest
import duckdb

from ...import register_fhirpath


@pytest.fixture
def con():
    """Create a DuckDB connection with FHIRPath registered."""
    conn = duckdb.connect()
    register_fhirpath(conn)
    yield conn
    conn.close()


@pytest.fixture
def sample_patients():
    """Create sample patient resources."""
    return [
        json.dumps({
            "resourceType": "Patient",
            "id": f"patient-{i}",
            "active": i % 2 == 0,
            "name": [{"given": ["John"], "family": "Doe"}],
            "gender": "male" if i % 2 == 0 else "female"
        })
        for i in range(10)
    ]


class TestBasicQueries:
    """Test basic FHIRPath queries in SQL."""

    def test_simple_path(self, con, sample_patients):
        """Test simple path navigation."""
        con.execute("CREATE TABLE resources (resource VARCHAR)")
        for p in sample_patients[:3]:
            con.execute("INSERT INTO resources VALUES (?)", [p])

        result = con.execute("SELECT fhirpath(resource, 'id') FROM resources").fetchall()
        assert len(result) == 3
        assert result[0][0] == ['patient-0']

    def test_nested_path(self, con, sample_patients):
        """Test nested path navigation."""
        con.execute("CREATE TABLE resources (resource VARCHAR)")
        for p in sample_patients[:3]:
            con.execute("INSERT INTO resources VALUES (?)", [p])

        result = con.execute("SELECT fhirpath(resource, 'name.given') FROM resources").fetchall()
        assert len(result) == 3
        assert 'John' in result[0][0]

    def test_missing_path(self, con, sample_patients):
        """Test missing path returns empty list."""
        con.execute("CREATE TABLE resources (resource VARCHAR)")
        con.execute("INSERT INTO resources VALUES (?)", [sample_patients[0]])

        result = con.execute("SELECT fhirpath(resource, 'nonexistent') FROM resources").fetchall()
        assert result[0][0] == []


class TestWhereClauses:
    """Test FHIRPath in WHERE clauses."""

    def test_filter_by_resource_type(self, con, sample_patients):
        """Test filtering by resourceType."""
        con.execute("CREATE TABLE resources (resource VARCHAR)")
        for p in sample_patients:
            con.execute("INSERT INTO resources VALUES (?)", [p])

        result = con.execute('''
            SELECT fhirpath(resource, 'id')
            FROM resources
            WHERE fhirpath(resource, 'resourceType') = ['Patient']
        ''').fetchall()
        assert len(result) == 10

    def test_filter_by_field(self, con, sample_patients):
        """Test filtering by field value."""
        con.execute("CREATE TABLE resources (resource VARCHAR)")
        for p in sample_patients:
            con.execute("INSERT INTO resources VALUES (?)", [p])

        result = con.execute('''
            SELECT fhirpath(resource, 'id')
            FROM resources
            WHERE fhirpath(resource, 'active') = ['True']
        ''').fetchall()
        # Patients 0, 2, 4, 6, 8 have active=True
        assert len(result) == 5


class TestCTEsAndJoins:
    """Test FHIRPath with CTEs and JOINs."""

    def test_with_cte(self, con, sample_patients):
        """Test FHIRPath in CTEs."""
        con.execute("CREATE TABLE resources (resource VARCHAR)")
        for p in sample_patients[:5]:
            con.execute("INSERT INTO resources VALUES (?)", [p])

        result = con.execute('''
            WITH patient_ids AS (
                SELECT fhirpath(resource, 'id') as pid
                FROM resources
            )
            SELECT pid FROM patient_ids WHERE pid != []
        ''').fetchall()
        assert len(result) == 5

    def test_self_join(self, con, sample_patients):
        """Test self-join with FHIRPath."""
        con.execute("CREATE TABLE resources (resource VARCHAR)")
        for p in sample_patients[:5]:
            con.execute("INSERT INTO resources VALUES (?)", [p])

        result = con.execute('''
            SELECT
                a.resource as r1,
                b.resource as r2
            FROM resources a
            JOIN resources b ON fhirpath(a.resource, 'gender') = fhirpath(b.resource, 'gender')
        ''').fetchall()
        # Each patient joins with others of same gender
        assert len(result) >= 5


class TestNullHandling:
    """Test NULL handling."""

    def test_null_resource(self, con):
        """Test with NULL resource."""
        con.execute("CREATE TABLE resources (resource VARCHAR)")
        con.execute("INSERT INTO resources VALUES (NULL)")

        result = con.execute("SELECT fhirpath(resource, 'id') FROM resources").fetchall()
        assert result[0][0] is None

    def test_null_expression(self, con, sample_patients):
        """Test with NULL expression."""
        con.execute("CREATE TABLE resources (resource VARCHAR)")
        con.execute("INSERT INTO resources VALUES (?)", [sample_patients[0]])

        result = con.execute("SELECT fhirpath(resource, NULL) FROM resources").fetchall()
        assert result[0][0] is None


class TestValidation:
    """Test expression validation."""

    def test_valid_expression(self, con):
        """Test validation of valid expression."""
        result = con.execute("SELECT fhirpath_is_valid('Patient.name.given')").fetchone()
        assert result[0] == True

    def test_whitespace_expression(self, con):
        """Test validation of whitespace-only expression - parser accepts but returns empty."""
        result = con.execute("SELECT fhirpath_is_valid('   ')").fetchone()
        # Parser accepts whitespace as valid (permissive)
        assert result[0] == True

    def test_empty_expression(self, con):
        """Test validation of empty expression."""
        result = con.execute("SELECT fhirpath_is_valid('')").fetchone()
        assert result[0] == False
