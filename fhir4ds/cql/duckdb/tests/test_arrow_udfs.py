"""Unit tests for Tier 3 Arrow UDFs."""

import duckdb
import json
import pytest
from ..import register


@pytest.fixture
def con():
    con = duckdb.connect(":memory:")
    register(con, include_fhirpath=False)
    yield con
    con.close()


def make_patient(birth_date: str) -> str:
    """Create a minimal FHIR Patient resource."""
    return json.dumps({"resourceType": "Patient", "birthDate": birth_date})


class TestAgeUdfs:
    """Test vectorized age calculation UDFs."""

    def test_age_in_years_single(self, con):
        patient = make_patient("1990-06-15")
        result = con.execute("SELECT AgeInYears(?)", [patient]).fetchone()[0]
        # Age depends on current date, just verify it's reasonable
        # Born June 15, 1990, as of Feb 20, 2026: 35 years old
        assert 34 <= result <= 36

    def test_age_in_years_null(self, con):
        result = con.execute("SELECT AgeInYears(NULL)").fetchone()[0]
        assert result is None

    def test_age_in_years_batch(self, con):
        """Test batch processing with multiple rows."""
        patients = [
            make_patient("1990-01-01"),
            make_patient("2000-01-01"),
            make_patient("2010-01-01"),
        ]
        # Create a table and test batch processing
        con.execute("CREATE TABLE patients (resource VARCHAR)")
        for p in patients:
            con.execute("INSERT INTO patients VALUES (?)", [p])

        results = con.execute("SELECT AgeInYears(resource) FROM patients").fetchall()
        ages = [r[0] for r in results]

        # Ages should be in descending order (oldest first)
        assert ages[0] > ages[1] > ages[2]

    def test_age_in_months(self, con):
        patient = make_patient("2024-01-15")
        result = con.execute("SELECT AgeInMonths(?)", [patient]).fetchone()[0]
        # Born Jan 15, 2024, as of Feb 20, 2026: around 25 months
        assert result >= 24
        assert result <= 27

    def test_age_in_days(self, con):
        patient = make_patient("2026-02-01")
        # Use AgeInDaysAt with a fixed date to avoid time-sensitive assertions
        result = con.execute("SELECT AgeInDaysAt(?, ?)", [patient, "2026-02-20"]).fetchone()[0]
        assert result == 19

    def test_age_in_years_at(self, con):
        patient = make_patient("1990-05-15")
        result = con.execute(
            "SELECT AgeInYearsAt(?, ?)", [patient, "2020-05-15"]
        ).fetchone()[0]
        # Born May 15, 1990, as of May 15, 2020: exactly 30
        assert result == 30

    def test_age_in_years_at_before_birthday(self, con):
        patient = make_patient("1990-05-15")
        result = con.execute(
            "SELECT AgeInYearsAt(?, ?)", [patient, "2020-05-14"]
        ).fetchone()[0]
        # Born May 15, 1990, as of May 14, 2020: 29
        assert result == 29

    def test_age_in_months_at(self, con):
        patient = make_patient("1990-05-15")
        result = con.execute(
            "SELECT AgeInMonthsAt(?, ?)", [patient, "2020-05-15"]
        ).fetchone()[0]
        # Born May 15, 1990, as of May 15, 2020: exactly 360 months
        assert result == 360

    def test_age_in_days_at(self, con):
        patient = make_patient("1990-05-15")
        result = con.execute(
            "SELECT AgeInDaysAt(?, ?)", [patient, "1990-05-20"]
        ).fetchone()[0]
        # Born May 15, 1990, as of May 20, 1990: exactly 5 days
        assert result == 5

    def test_age_null_handling(self, con):
        """Test that all age functions handle nulls correctly."""
        null_tests = [
            "SELECT AgeInYears(NULL)",
            "SELECT AgeInMonths(NULL)",
            "SELECT AgeInDays(NULL)",
            "SELECT AgeInHours(NULL)",
            "SELECT AgeInMinutes(NULL)",
            "SELECT AgeInSeconds(NULL)",
            "SELECT AgeInYearsAt(NULL, '2020-01-01')",
            "SELECT AgeInMonthsAt(NULL, '2020-01-01')",
            "SELECT AgeInDaysAt(NULL, '2020-01-01')",
        ]
        for sql in null_tests:
            result = con.execute(sql).fetchone()[0]
            assert result is None, f"{sql} should return NULL"


class TestBatchProcessing:
    """Test that UDFs work correctly with batch processing."""

    def test_batch_age_calculations(self, con):
        """Test multiple age calculations in a single query."""
        con.execute("CREATE TABLE test_patients (resource VARCHAR)")
        patients = [
            make_patient("1980-01-01"),
            make_patient("1990-06-15"),
            make_patient("2000-12-31"),
            make_patient("2010-07-04"),
        ]
        for p in patients:
            con.execute("INSERT INTO test_patients VALUES (?)", [p])

        results = con.execute("""
            SELECT
                AgeInYears(resource) as years,
                AgeInMonths(resource) as months,
                AgeInDays(resource) as days
            FROM test_patients
            ORDER BY years DESC
        """).fetchall()

        # Verify we got 4 results
        assert len(results) == 4

        # Verify ordering (oldest first)
        years = [r[0] for r in results]
        assert years == sorted(years, reverse=True)

        # Verify months > years * 12 for all (basic sanity check)
        for years_val, months_val, days_val in results:
            assert months_val >= years_val * 12
            assert days_val >= years_val * 365

    def test_batch_with_nulls(self, con):
        """Test batch processing with NULL values mixed in."""
        con.execute("CREATE TABLE mixed_data (resource VARCHAR)")
        con.execute("INSERT INTO mixed_data VALUES (?)", [make_patient("1990-01-01")])
        con.execute("INSERT INTO mixed_data VALUES (NULL)")
        con.execute("INSERT INTO mixed_data VALUES (?)", [make_patient("2000-01-01")])

        results = con.execute(
            "SELECT AgeInYears(resource) FROM mixed_data"
        ).fetchall()

        assert results[0][0] is not None
        assert results[1][0] is None
        assert results[2][0] is not None
