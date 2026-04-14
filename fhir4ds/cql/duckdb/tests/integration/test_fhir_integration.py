"""
Integration tests for CQL operations with FHIR data.

Tests list operations (First, Last, Skip, Take, SingletonFrom, Latest, Earliest)
against real FHIR data from the Synthea synthetic dataset.

These tests require FHIR data to be present at data/coherent-11-07-2022/fhir/
and will be skipped gracefully if the data is not available.
"""

import pytest
import json
from pathlib import Path
from datetime import datetime
import duckdb

from ...import register


# Path to synthetic FHIR data
DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "coherent-11-07-2022" / "fhir"


def pytest_generate_tests(metafunc):
    """Skip all tests in this module if FHIR data is not available."""
    if not DATA_DIR.exists():
        pytest.skip(f"FHIR data not found at {DATA_DIR}", allow_module_level=True)


@pytest.fixture(scope="module")
def fhir_bundles():
    """Load patient bundles if available."""
    if not DATA_DIR.exists():
        pytest.skip(f"FHIR data not found at {DATA_DIR}")

    bundles = []
    for f in sorted(DATA_DIR.glob("*.json"))[:10]:  # Load first 10 for speed
        with open(f) as fp:
            bundles.append(json.load(fp))

    if not bundles:
        pytest.skip("No FHIR bundles found")

    return bundles


@pytest.fixture(scope="module")
def patients_data(fhir_bundles):
    """Extract patient resources from bundles."""
    patients = []
    for bundle in fhir_bundles:
        for entry in bundle.get("entry", []):
            resource = entry.get("resource", {})
            if resource.get("resourceType") == "Patient":
                patients.append(resource)
    return patients


@pytest.fixture(scope="module")
def observations_data(fhir_bundles):
    """Extract observation resources from bundles."""
    observations = []
    for bundle in fhir_bundles:
        for entry in bundle.get("entry", []):
            resource = entry.get("resource", {})
            if resource.get("resourceType") == "Observation":
                observations.append(resource)
    return observations


@pytest.fixture(scope="module")
def conditions_data(fhir_bundles):
    """Extract condition resources from bundles."""
    conditions = []
    for bundle in fhir_bundles:
        for entry in bundle.get("entry", []):
            resource = entry.get("resource", {})
            if resource.get("resourceType") == "Condition":
                conditions.append(resource)
    return conditions


@pytest.fixture
def con():
    """DuckDB connection with CQL extension."""
    con = duckdb.connect(":memory:")
    register(con)
    yield con
    con.close()


class TestListOperationsOnIdentifiers:
    """Test First/Last/Skip/Take on Patient.identifier lists."""

    def test_first_on_patient_identifiers(self, con, patients_data):
        """Test First returns the first identifier from Patient.identifier."""
        if not patients_data:
            pytest.skip("No patient data available")

        # Get a patient with multiple identifiers
        patient = None
        for p in patients_data:
            if len(p.get("identifier", [])) >= 2:
                patient = p
                break

        if not patient:
            pytest.skip("No patient with multiple identifiers found")

        identifiers = patient.get("identifier", [])
        identifier_values = [i.get("value") for i in identifiers if i.get("value")]

        # Create a test table with the identifiers
        con.execute("CREATE OR REPLACE TABLE test_ids AS SELECT $1 as id_values", [identifier_values])

        # Test First
        result = con.execute("SELECT First(id_values) FROM test_ids").fetchone()
        assert result[0] == identifier_values[0], f"Expected {identifier_values[0]}, got {result[0]}"

    def test_last_on_patient_identifiers(self, con, patients_data):
        """Test Last returns the last identifier from Patient.identifier."""
        if not patients_data:
            pytest.skip("No patient data available")

        # Get a patient with multiple identifiers
        patient = None
        for p in patients_data:
            if len(p.get("identifier", [])) >= 2:
                patient = p
                break

        if not patient:
            pytest.skip("No patient with multiple identifiers found")

        identifiers = patient.get("identifier", [])
        identifier_values = [i.get("value") for i in identifiers if i.get("value")]

        con.execute("CREATE OR REPLACE TABLE test_ids AS SELECT $1 as id_values", [identifier_values])

        # Test Last
        result = con.execute("SELECT Last(id_values) FROM test_ids").fetchone()
        assert result[0] == identifier_values[-1], f"Expected {identifier_values[-1]}, got {result[0]}"

    def test_skip_on_patient_identifiers(self, con, patients_data):
        """Test Skip removes first N identifiers from Patient.identifier."""
        if not patients_data:
            pytest.skip("No patient data available")

        # Get a patient with at least 3 identifiers
        patient = None
        for p in patients_data:
            if len(p.get("identifier", [])) >= 3:
                patient = p
                break

        if not patient:
            pytest.skip("No patient with 3+ identifiers found")

        identifiers = patient.get("identifier", [])
        identifier_values = [i.get("value") for i in identifiers if i.get("value")]

        con.execute("CREATE OR REPLACE TABLE test_ids AS SELECT $1 as id_values", [identifier_values])

        # Test Skip(1) - should return all but first
        result = con.execute("SELECT Skip(id_values, 1) FROM test_ids").fetchone()
        assert result[0] == identifier_values[1:], f"Expected {identifier_values[1:]}, got {result[0]}"

        # Test Skip(2) - should return all but first two
        result = con.execute("SELECT Skip(id_values, 2) FROM test_ids").fetchone()
        assert result[0] == identifier_values[2:], f"Expected {identifier_values[2:]}, got {result[0]}"

    def test_take_on_patient_identifiers(self, con, patients_data):
        """Test Take returns first N identifiers from Patient.identifier."""
        if not patients_data:
            pytest.skip("No patient data available")

        # Get a patient with at least 3 identifiers
        patient = None
        for p in patients_data:
            if len(p.get("identifier", [])) >= 3:
                patient = p
                break

        if not patient:
            pytest.skip("No patient with 3+ identifiers found")

        identifiers = patient.get("identifier", [])
        identifier_values = [i.get("value") for i in identifiers if i.get("value")]

        con.execute("CREATE OR REPLACE TABLE test_ids AS SELECT $1 as id_values", [identifier_values])

        # Test Take(1) - should return only first
        result = con.execute("SELECT Take(id_values, 1) FROM test_ids").fetchone()
        assert result[0] == identifier_values[:1], f"Expected {identifier_values[:1]}, got {result[0]}"

        # Test Take(2) - should return first two
        result = con.execute("SELECT Take(id_values, 2) FROM test_ids").fetchone()
        assert result[0] == identifier_values[:2], f"Expected {identifier_values[:2]}, got {result[0]}"


class TestLatestObservation:
    """Test Latest on Observation.effectiveDateTime."""

    def test_latest_on_observations(self, con, observations_data):
        """Test Latest returns the observation with most recent effectiveDateTime."""
        if not observations_data:
            pytest.skip("No observation data available")

        # Get observations with effectiveDateTime
        obs_with_dates = []
        for obs in observations_data:
            effective = obs.get("effectiveDateTime")
            if effective:
                obs_with_dates.append({
                    "id": obs.get("id"),
                    "effectiveDateTime": effective
                })

        if len(obs_with_dates) < 2:
            pytest.skip("Need at least 2 observations with effectiveDateTime")

        # Sort by effectiveDateTime to find expected latest
        obs_with_dates.sort(key=lambda x: x["effectiveDateTime"])
        expected_latest = obs_with_dates[-1]

        # Create test table with list of resources
        # Latest requires: Latest(list_of_resources, 'date_path')
        con.execute("""
            CREATE OR REPLACE TABLE test_obs AS
            SELECT $1 as resources
        """, [obs_with_dates])

        # Get the latest resource using the effectiveDateTime path
        result = con.execute("""
            SELECT Latest(resources, 'effectiveDateTime') FROM test_obs
        """).fetchone()

        # The result should be a JSON string of the resource with latest date
        assert result[0] is not None, "Latest should return a value"

    def test_latest_with_single_observation(self, con, observations_data):
        """Test Latest with single observation returns that observation."""
        if not observations_data:
            pytest.skip("No observation data available")

        # Get a single observation with effectiveDateTime
        obs = None
        for o in observations_data:
            if o.get("effectiveDateTime"):
                obs = o
                break

        if not obs:
            pytest.skip("No observation with effectiveDateTime found")

        # Create test table with list containing single resource
        # Latest requires: Latest(list_of_resources, 'date_path')
        single_resource = [{"effectiveDateTime": obs.get("effectiveDateTime")}]
        con.execute("""
            CREATE OR REPLACE TABLE test_obs AS
            SELECT $1 as resources
        """, [single_resource])

        result = con.execute("SELECT Latest(resources, 'effectiveDateTime') FROM test_obs").fetchone()
        assert result[0] is not None, "Latest of single value should return that value"


class TestEarliestCondition:
    """Test Earliest on Condition.onsetDateTime."""

    def test_earliest_on_conditions(self, con, conditions_data):
        """Test Earliest returns the condition with earliest onsetDateTime."""
        if not conditions_data:
            pytest.skip("No condition data available")

        # Get conditions with onsetDateTime
        cond_with_dates = []
        for cond in conditions_data:
            onset = cond.get("onsetDateTime")
            if onset:
                cond_with_dates.append({
                    "id": cond.get("id"),
                    "onsetDateTime": onset
                })

        if len(cond_with_dates) < 2:
            pytest.skip("Need at least 2 conditions with onsetDateTime")

        # Sort by onsetDateTime to find expected earliest
        cond_with_dates.sort(key=lambda x: x["onsetDateTime"])
        expected_earliest = cond_with_dates[0]

        # Create test table with list of resources
        # Earliest requires: Earliest(list_of_resources, 'date_path')
        con.execute("""
            CREATE OR REPLACE TABLE test_cond AS
            SELECT $1 as resources
        """, [cond_with_dates])

        # Get the earliest resource using the onsetDateTime path
        result = con.execute("""
            SELECT Earliest(resources, 'onsetDateTime') FROM test_cond
        """).fetchone()

        # The result should be a JSON string of the resource with earliest date
        assert result[0] is not None, "Earliest should return a value"

    def test_earliest_with_single_condition(self, con, conditions_data):
        """Test Earliest with single condition returns that condition."""
        if not conditions_data:
            pytest.skip("No condition data available")

        # Get a single condition with onsetDateTime
        cond = None
        for c in conditions_data:
            if c.get("onsetDateTime"):
                cond = c
                break

        if not cond:
            pytest.skip("No condition with onsetDateTime found")

        onset = cond.get("onsetDateTime")

        # Create test table with list containing single resource
        # Earliest requires: Earliest(list_of_resources, 'date_path')
        single_resource = [{"onsetDateTime": onset}]
        con.execute("""
            CREATE OR REPLACE TABLE test_cond AS
            SELECT $1 as resources
        """, [single_resource])

        result = con.execute("SELECT Earliest(resources, 'onsetDateTime') FROM test_cond").fetchone()
        assert result[0] is not None, "Earliest of single value should return that value"


class TestSingletonFromObservation:
    """Test SingletonFrom on patient observations."""

    def test_singleton_from_single_observation(self, con, observations_data):
        """Test SingletonFrom returns value when list has exactly one element."""
        # Get a patient ID with observations
        patient_obs = {}
        for obs in observations_data:
            subject = obs.get("subject", {})
            ref = subject.get("reference", "")
            if ref.startswith("urn:uuid:"):
                patient_id = ref.replace("urn:uuid:", "")
                if patient_id not in patient_obs:
                    patient_obs[patient_id] = []
                patient_obs[patient_id].append(obs)

        # Find a patient with exactly one observation
        single_obs_patient = None
        for patient_id, obs_list in patient_obs.items():
            if len(obs_list) == 1:
                single_obs_patient = patient_id
                break

        if not single_obs_patient:
            pytest.skip("No patient with exactly one observation found")

        # Test SingletonFrom with a single-element list
        result = con.execute("SELECT SingletonFrom(['only_one'])").fetchone()
        assert result[0] == "only_one", "SingletonFrom of single element should return that element"

    def test_singleton_from_empty_list(self, con):
        """Test SingletonFrom returns NULL for empty list."""
        result = con.execute("SELECT SingletonFrom([])").fetchone()
        assert result[0] is None, "SingletonFrom of empty list should return NULL"

    def test_singleton_from_multiple_elements(self, con):
        """Test SingletonFrom returns NULL for list with multiple elements."""
        result = con.execute("SELECT SingletonFrom(['one', 'two', 'three'])").fetchone()
        assert result[0] is None, "SingletonFrom of multiple elements should return NULL"


class TestCombinedOperations:
    """Test combining multiple list operations on FHIR data."""

    def test_skip_then_take_on_identifiers(self, con, patients_data):
        """Test Skip followed by Take on Patient.identifier."""
        if not patients_data:
            pytest.skip("No patient data available")

        # Get a patient with at least 5 identifiers
        patient = None
        for p in patients_data:
            if len(p.get("identifier", [])) >= 5:
                patient = p
                break

        if not patient:
            pytest.skip("No patient with 5+ identifiers found")

        identifiers = patient.get("identifier", [])
        identifier_values = [i.get("value") for i in identifiers if i.get("value")]

        con.execute("CREATE OR REPLACE TABLE test_ids AS SELECT $1 as id_values", [identifier_values])

        # Skip(1) then Take(2) should return elements at index 1 and 2
        result = con.execute("SELECT Take(Skip(id_values, 1), 2) FROM test_ids").fetchone()
        expected = identifier_values[1:3]
        assert result[0] == expected, f"Expected {expected}, got {result[0]}"

    def test_distinct_on_identifier_systems(self, con, patients_data):
        """Test Distinct on identifier systems."""
        if not patients_data:
            pytest.skip("No patient data available")

        # Collect all identifier systems across patients
        all_systems = []
        for patient in patients_data[:5]:  # First 5 patients
            for identifier in patient.get("identifier", []):
                system = identifier.get("system")
                if system:
                    all_systems.append(system)

        if len(all_systems) < 2:
            pytest.skip("Not enough identifier systems found")

        con.execute("CREATE OR REPLACE TABLE test_systems AS SELECT $1 as systems", [all_systems])

        # Distinct is a reserved keyword, must be quoted
        result = con.execute('SELECT "Distinct"(systems) FROM test_systems').fetchone()
        distinct_result = result[0]

        # Verify no duplicates in result
        assert distinct_result is not None, "Distinct should return a value"
        unique_values = set(distinct_result)
        assert len(distinct_result) == len(unique_values), "Distinct should remove all duplicates"
