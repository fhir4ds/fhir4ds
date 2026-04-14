"""
Unit tests for CQL clinical operators.

Tests for clinical aggregate functions:
- latest: Returns the most recent observation from a list
- earliest: Returns the oldest observation from a list

These functions work on FHIR-like JSON structures with date fields.
"""

import pytest
import duckdb
import json

from ..import register


@pytest.fixture
def con():
    """DuckDB connection with CQL functions registered."""
    con = duckdb.connect(":memory:")
    register(con)
    yield con
    con.close()


# ========================================
# Test data fixtures
# ========================================

@pytest.fixture
def single_observation():
    """A single FHIR Observation resource."""
    return json.dumps({
        "resourceType": "Observation",
        "id": "obs-1",
        "effectiveDateTime": "2024-01-15T10:00:00Z",
        "valueQuantity": {"value": 120, "unit": "mmHg"}
    })


@pytest.fixture
def multiple_observations():
    """Multiple FHIR Observation resources with different dates."""
    return [
        json.dumps({
            "resourceType": "Observation",
            "id": "obs-1",
            "effectiveDateTime": "2024-01-15T10:00:00Z",
            "valueQuantity": {"value": 120, "unit": "mmHg"}
        }),
        json.dumps({
            "resourceType": "Observation",
            "id": "obs-2",
            "effectiveDateTime": "2024-01-20T15:30:00Z",
            "valueQuantity": {"value": 118, "unit": "mmHg"}
        }),
        json.dumps({
            "resourceType": "Observation",
            "id": "obs-3",
            "effectiveDateTime": "2024-01-10T08:00:00Z",
            "valueQuantity": {"value": 125, "unit": "mmHg"}
        }),
    ]


@pytest.fixture
def observations_with_null_dates():
    """Observations with some null dates."""
    return [
        json.dumps({
            "resourceType": "Observation",
            "id": "obs-1",
            "effectiveDateTime": "2024-01-15T10:00:00Z",
            "valueQuantity": {"value": 120, "unit": "mmHg"}
        }),
        json.dumps({
            "resourceType": "Observation",
            "id": "obs-2",
            "valueQuantity": {"value": 118, "unit": "mmHg"}
        }),
        json.dumps({
            "resourceType": "Observation",
            "id": "obs-3",
            "effectiveDateTime": "2024-01-20T15:30:00Z",
            "valueQuantity": {"value": 122, "unit": "mmHg"}
        }),
    ]


@pytest.fixture
def observations_all_null_dates():
    """Observations with all null dates."""
    return [
        json.dumps({
            "resourceType": "Observation",
            "id": "obs-1",
            "valueQuantity": {"value": 120, "unit": "mmHg"}
        }),
        json.dumps({
            "resourceType": "Observation",
            "id": "obs-2",
            "valueQuantity": {"value": 118, "unit": "mmHg"}
        }),
    ]


@pytest.fixture
def empty_observations():
    """Empty list of observations."""
    return []


# ========================================
# latest() tests
# ========================================

def test_latest_single(con, single_observation):
    """Test latest with one observation returns it."""
    # When there's only one observation in a list, latest should return it
    result = con.execute(
        "SELECT latest(?, 'effectiveDateTime')",
        [[single_observation]]  # Pass as a list containing one observation
    ).fetchone()
    # Result should be the observation JSON or parsed content
    assert result[0] is not None


def test_latest_multiple(con, multiple_observations):
    """Test latest with multiple observations returns most recent."""
    # Create a table with the observations
    con.execute("CREATE TABLE obs (data JSON)")
    for obs in multiple_observations:
        con.execute("INSERT INTO obs VALUES (?)", [obs])

    # latest expects a list, so use ARRAY_AGG to aggregate
    # which is obs-2 with date 2024-01-20T15:30:00Z
    result = con.execute("SELECT latest(ARRAY_AGG(data), 'effectiveDateTime') FROM obs").fetchone()

    assert result[0] is not None
    # The result should contain the most recent observation
    result_json = result[0] if isinstance(result[0], str) else json.dumps(result[0])
    result_data = json.loads(result_json)
    assert result_data["id"] == "obs-2"


def test_latest_empty(con, empty_observations):
    """Test latest with empty list returns NULL."""
    # Empty list should return NULL
    result = con.execute(
        "SELECT latest(?, 'effectiveDateTime')",
        [empty_observations]
    ).fetchone()
    assert result[0] is None


def test_latest_null_dates(con, observations_all_null_dates):
    """Test latest with all null dates returns NULL."""
    # latest expects a list of resources
    result = con.execute(
        "SELECT latest(?, 'effectiveDateTime')",
        [observations_all_null_dates]
    ).fetchone()
    assert result[0] is None


def test_latest_mixed_dates(con, observations_with_null_dates):
    """Test latest with some null dates returns most recent non-null."""
    # Should return the observation with the most recent non-null date
    # which is obs-3 with date 2024-01-20T15:30:00Z
    result = con.execute(
        "SELECT latest(?, 'effectiveDateTime')",
        [observations_with_null_dates]
    ).fetchone()

    assert result[0] is not None
    result_json = result[0] if isinstance(result[0], str) else json.dumps(result[0])
    result_data = json.loads(result_json)
    assert result_data["id"] == "obs-3"


def test_latest_null_input(con):
    """Test latest with NULL input returns NULL."""
    result = con.execute("SELECT latest(NULL, 'effectiveDateTime')").fetchone()
    assert result[0] is None


# ========================================
# earliest() tests
# ========================================

def test_earliest_single(con, single_observation):
    """Test earliest with one observation returns it."""
    # When there's only one observation in a list, earliest should return it
    result = con.execute(
        "SELECT earliest(?, 'effectiveDateTime')",
        [[single_observation]]  # Pass as a list containing one observation
    ).fetchone()
    assert result[0] is not None


def test_earliest_multiple(con, multiple_observations):
    """Test earliest with multiple observations returns oldest."""
    # Create a table with the observations
    con.execute("CREATE TABLE obs_early (data JSON)")
    for obs in multiple_observations:
        con.execute("INSERT INTO obs_early VALUES (?)", [obs])

    # earliest expects a list, so use ARRAY_AGG to aggregate
    # which is obs-3 with date 2024-01-10T08:00:00Z
    result = con.execute("SELECT earliest(ARRAY_AGG(data), 'effectiveDateTime') FROM obs_early").fetchone()

    assert result[0] is not None
    result_json = result[0] if isinstance(result[0], str) else json.dumps(result[0])
    result_data = json.loads(result_json)
    assert result_data["id"] == "obs-3"


def test_earliest_empty(con, empty_observations):
    """Test earliest with empty list returns NULL."""
    # Empty list should return NULL
    result = con.execute(
        "SELECT earliest(?, 'effectiveDateTime')",
        [empty_observations]
    ).fetchone()
    assert result[0] is None


def test_earliest_null_input(con):
    """Test earliest with NULL input returns NULL."""
    result = con.execute("SELECT earliest(NULL, 'effectiveDateTime')").fetchone()
    assert result[0] is None


# ========================================
# Edge case tests
# ========================================

def test_latest_with_same_dates(con):
    """Test latest when multiple observations have the same date."""
    observations = [
        json.dumps({
            "resourceType": "Observation",
            "id": "obs-1",
            "effectiveDateTime": "2024-01-15T10:00:00Z",
            "valueQuantity": {"value": 120, "unit": "mmHg"}
        }),
        json.dumps({
            "resourceType": "Observation",
            "id": "obs-2",
            "effectiveDateTime": "2024-01-15T10:00:00Z",
            "valueQuantity": {"value": 118, "unit": "mmHg"}
        }),
    ]

    # When dates are the same, either observation is valid
    # The function should return one of them (implementation-defined)
    result = con.execute(
        "SELECT latest(?, 'effectiveDateTime')",
        [observations]
    ).fetchone()
    assert result[0] is not None


def test_earliest_mixed_dates(con, observations_with_null_dates):
    """Test earliest with some null dates returns oldest non-null."""
    # Should return the observation with the oldest non-null date
    # which is obs-1 with date 2024-01-15T10:00:00Z
    result = con.execute(
        "SELECT earliest(?, 'effectiveDateTime')",
        [observations_with_null_dates]
    ).fetchone()

    assert result[0] is not None
    result_json = result[0] if isinstance(result[0], str) else json.dumps(result[0])
    result_data = json.loads(result_json)
    assert result_data["id"] == "obs-1"


def test_latest_invalid_json(con):
    """Test latest with invalid JSON returns NULL for that entry."""
    observations = [
        '{"resourceType": "Observation", "effectiveDateTime": "2024-01-15T10:00:00Z"}',
        'not valid json',
        '{"resourceType": "Observation", "effectiveDateTime": "2024-01-20T15:30:00Z"}',
    ]

    # Should handle invalid JSON gracefully and return the most recent valid one
    result = con.execute(
        "SELECT latest(?, 'effectiveDateTime')",
        [observations]
    ).fetchone()
    # The most recent valid observation should be returned
    assert result[0] is not None


def test_earliest_date_only_format(con):
    """Test earliest with date-only format (no time component)."""
    observations = [
        json.dumps({
            "resourceType": "Observation",
            "id": "obs-1",
            "effectiveDateTime": "2024-01-15",
            "valueQuantity": {"value": 120, "unit": "mmHg"}
        }),
        json.dumps({
            "resourceType": "Observation",
            "id": "obs-2",
            "effectiveDateTime": "2024-01-10",
            "valueQuantity": {"value": 118, "unit": "mmHg"}
        }),
    ]

    # Should correctly parse date-only format
    result = con.execute(
        "SELECT earliest(?, 'effectiveDateTime')",
        [observations]
    ).fetchone()

    assert result[0] is not None
    result_json = result[0] if isinstance(result[0], str) else json.dumps(result[0])
    result_data = json.loads(result_json)
    assert result_data["id"] == "obs-2"
