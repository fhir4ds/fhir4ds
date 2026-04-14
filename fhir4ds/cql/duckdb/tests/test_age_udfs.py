"""
Unit tests for CQL Age UDFs.

Tests for age calculation functions:
- ageInYears, ageInMonths, ageInDays
- ageInHours, ageInMinutes, ageInSeconds
- ageInYearsAt, ageInMonthsAt, ageInDaysAt
"""

import pytest
import duckdb
from datetime import date

from ..udf.age import (
    ageInYears,
    ageInMonths,
    ageInDays,
    ageInHours,
    ageInMinutes,
    ageInSeconds,
    ageInYearsAt,
    ageInMonthsAt,
    ageInDaysAt,
    registerAgeUdfs,
)


@pytest.fixture
def patient_resource():
    """A valid FHIR Patient resource with birthDate."""
    return '{"resourceType": "Patient", "birthDate": "1990-05-15"}'


@pytest.fixture
def patient_no_birthdate():
    """A FHIR Patient resource without birthDate."""
    return '{"resourceType": "Patient", "name": [{"family": "Doe"}]}'


@pytest.fixture
def invalid_json():
    """Invalid JSON string."""
    return '{"resourceType": "Patient", "birthDate": "invalid'


# ========================================
# ageInYears tests
# ========================================

def test_age_in_years_valid(patient_resource):
    """Test ageInYears with valid patient resource."""
    result = ageInYears(patient_resource)
    assert result is not None
    # Born in 1990, should be around 34-35 years old
    assert result >= 34
    assert result <= 36


def test_age_in_years_null():
    """Test ageInYears with null input."""
    assert ageInYears(None) is None


def test_age_in_years_missing_birthdate(patient_no_birthdate):
    """Test ageInYears with missing birthDate."""
    assert ageInYears(patient_no_birthdate) is None


def test_age_in_years_invalid_json(invalid_json):
    """Test ageInYears with invalid JSON."""
    assert ageInYears(invalid_json) is None


def test_age_in_years_empty_string():
    """Test ageInYears with empty string."""
    assert ageInYears("") is None


# ========================================
# ageInMonths tests
# ========================================

def test_age_in_months_valid(patient_resource):
    """Test ageInMonths with valid patient resource."""
    result = ageInMonths(patient_resource)
    assert result is not None
    # Born in 1990, should be around 400+ months old
    assert result >= 400


def test_age_in_months_null():
    """Test ageInMonths with null input."""
    assert ageInMonths(None) is None


def test_age_in_months_missing_birthdate(patient_no_birthdate):
    """Test ageInMonths with missing birthDate."""
    assert ageInMonths(patient_no_birthdate) is None


# ========================================
# ageInDays tests
# ========================================

def test_age_in_days_valid(patient_resource):
    """Test ageInDays with valid patient resource."""
    result = ageInDays(patient_resource)
    assert result is not None
    # Born in 1990, should be around 12,000+ days old
    assert result >= 12000


def test_age_in_days_null():
    """Test ageInDays with null input."""
    assert ageInDays(None) is None


# ========================================
# ageInHours tests
# ========================================

def test_age_in_hours_valid(patient_resource):
    """Test ageInHours with valid patient resource."""
    result = ageInHours(patient_resource)
    assert result is not None
    # Born in 1990, should be around 300,000+ hours old
    assert result >= 300000


def test_age_in_hours_null():
    """Test ageInHours with null input."""
    assert ageInHours(None) is None


# ========================================
# ageInMinutes tests
# ========================================

def test_age_in_minutes_valid(patient_resource):
    """Test ageInMinutes with valid patient resource."""
    result = ageInMinutes(patient_resource)
    assert result is not None
    # Born in 1990, should be around 18 million minutes old
    assert result >= 18000000


def test_age_in_minutes_null():
    """Test ageInMinutes with null input."""
    assert ageInMinutes(None) is None


# ========================================
# ageInSeconds tests
# ========================================

def test_age_in_seconds_valid(patient_resource):
    """Test ageInSeconds with valid patient resource."""
    result = ageInSeconds(patient_resource)
    assert result is not None
    # Born in 1990, should be around 1 billion seconds old
    assert result >= 1000000000


def test_age_in_seconds_null():
    """Test ageInSeconds with null input."""
    assert ageInSeconds(None) is None


# ========================================
# ageInYearsAt tests
# ========================================

def test_age_in_years_at_valid(patient_resource):
    """Test ageInYearsAt with specific date."""
    # Born 1990-05-15, as of 2020-05-15 should be exactly 30
    result = ageInYearsAt(patient_resource, "2020-05-15")
    assert result == 30


def test_age_in_years_at_before_birthday(patient_resource):
    """Test ageInYearsAt before birthday in that year."""
    # Born 1990-05-15, as of 2020-05-14 should be 29
    result = ageInYearsAt(patient_resource, "2020-05-14")
    assert result == 29


def test_age_in_years_at_after_birthday(patient_resource):
    """Test ageInYearsAt after birthday in that year."""
    # Born 1990-05-15, as of 2020-05-16 should be 30
    result = ageInYearsAt(patient_resource, "2020-05-16")
    assert result == 30


def test_age_in_years_at_null_resource():
    """Test ageInYearsAt with null resource."""
    assert ageInYearsAt(None, "2020-01-01") is None


def test_age_in_years_at_null_date(patient_resource):
    """Test ageInYearsAt with null date."""
    assert ageInYearsAt(patient_resource, None) is None


def test_age_in_years_at_invalid_date(patient_resource):
    """Test ageInYearsAt with invalid date format."""
    assert ageInYearsAt(patient_resource, "not-a-date") is None


def test_age_in_years_at_datetime_format(patient_resource):
    """Test ageInYearsAt with datetime string."""
    # Should work with datetime strings too (takes first 10 chars)
    result = ageInYearsAt(patient_resource, "2020-05-15T10:30:00Z")
    assert result == 30


# ========================================
# ageInMonthsAt tests
# ========================================

def test_age_in_months_at_valid(patient_resource):
    """Test ageInMonthsAt with specific date."""
    # Born 1990-05-15, as of 2020-05-15 should be exactly 360 months (30 years)
    result = ageInMonthsAt(patient_resource, "2020-05-15")
    assert result == 360


def test_age_in_months_at_before_birthday(patient_resource):
    """Test ageInMonthsAt before day of month."""
    # Born 1990-05-15, as of 2020-05-14 should be 359 months
    result = ageInMonthsAt(patient_resource, "2020-05-14")
    assert result == 359


def test_age_in_months_at_null_resource():
    """Test ageInMonthsAt with null resource."""
    assert ageInMonthsAt(None, "2020-01-01") is None


# ========================================
# ageInDaysAt tests
# ========================================

def test_age_in_days_at_valid(patient_resource):
    """Test ageInDaysAt with specific date."""
    # Born 1990-05-15, as of 1990-05-20 should be 5 days
    result = ageInDaysAt(patient_resource, "1990-05-20")
    assert result == 5


def test_age_in_days_at_one_year(patient_resource):
    """Test ageInDaysAt after one year."""
    # Born 1990-05-15, as of 1991-05-15 should be 365 days
    result = ageInDaysAt(patient_resource, "1991-05-15")
    assert result == 365


def test_age_in_days_at_null_resource():
    """Test ageInDaysAt with null resource."""
    assert ageInDaysAt(None, "2020-01-01") is None


def test_age_in_days_at_before_birth(patient_resource):
    """Test ageInDaysAt with date before birth (returns 0 due to max)."""
    # The function uses max(0, ...) so negative days become 0
    result = ageInDaysAt(patient_resource, "1990-05-10")
    assert result == 0


# ========================================
# DuckDB Registration tests
# ========================================

def test_registration():
    """Test that UDFs can be registered with DuckDB."""
    con = duckdb.connect()
    registerAgeUdfs(con)

    patient = '{"resourceType": "Patient", "birthDate": "1990-05-15"}'

    # Test that functions are registered and callable
    result = con.execute("SELECT ageInYears(?)", [patient]).fetchone()
    assert result[0] is not None
    assert result[0] >= 34

    result = con.execute("SELECT ageInMonths(?)", [patient]).fetchone()
    assert result[0] is not None

    result = con.execute("SELECT ageInDays(?)", [patient]).fetchone()
    assert result[0] is not None

    result = con.execute("SELECT ageInYearsAt(?, ?)", [patient, "2020-05-15"]).fetchone()
    assert result[0] == 30

    con.close()


def test_registration_null_handling():
    """Test null handling through DuckDB."""
    con = duckdb.connect()
    registerAgeUdfs(con)

    result = con.execute("SELECT ageInYears(NULL)").fetchone()
    assert result[0] is None

    result = con.execute("SELECT ageInYearsAt(NULL, '2020-01-01')").fetchone()
    assert result[0] is None

    con.close()


def test_all_functions_registered():
    """Test that all age functions are properly registered."""
    con = duckdb.connect()
    registerAgeUdfs(con)

    patient = '{"resourceType": "Patient", "birthDate": "1990-05-15"}'

    functions = [
        ("ageInYears", [patient]),
        ("ageInMonths", [patient]),
        ("ageInDays", [patient]),
        ("ageInHours", [patient]),
        ("ageInMinutes", [patient]),
        ("ageInSeconds", [patient]),
        ("ageInYearsAt", [patient, "2020-01-01"]),
        ("ageInMonthsAt", [patient, "2020-01-01"]),
        ("ageInDaysAt", [patient, "2020-01-01"]),
    ]

    for func_name, params in functions:
        result = con.execute(f"SELECT {func_name}({', '.join(['?'] * len(params))})", params).fetchone()
        # Should not raise an error
        assert result is not None

    con.close()
