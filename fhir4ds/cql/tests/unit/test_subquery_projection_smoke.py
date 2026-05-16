"""Smoke test: verify DuckDB handles correlated scalar subqueries in SELECT lists.

This validates the core assumption behind the subquery projection approach
for let clause optimization. DuckDB must support correlated scalar subqueries
in SELECT at nesting depths comparable to what CMS1218 generates, including
EXISTS subqueries nested inside the correlated scalars.

This test serves as the Step 0 validation gate for the let clause subquery
projection plan. If these tests fail, the entire approach must be reconsidered.
"""
import pytest
import duckdb


@pytest.fixture
def conn():
    """Create an in-memory DuckDB connection with test data."""
    con = duckdb.connect()
    con.execute("""
        CREATE TABLE encounters (
            id VARCHAR,
            patient_id VARCHAR,
            status VARCHAR,
            period_start VARCHAR,
            period_end VARCHAR
        )
    """)
    con.execute("""
        CREATE TABLE conditions (
            id VARCHAR,
            encounter_id VARCHAR,
            patient_id VARCHAR,
            code VARCHAR,
            date VARCHAR,
            clinical_status VARCHAR
        )
    """)
    con.execute("""
        CREATE TABLE procedures (
            id VARCHAR,
            encounter_id VARCHAR,
            patient_id VARCHAR,
            code VARCHAR,
            date VARCHAR
        )
    """)
    con.execute("""
        INSERT INTO encounters VALUES
            ('E1', 'P1', 'finished', '2023-01-01', '2023-01-05'),
            ('E2', 'P1', 'finished', '2023-03-01', '2023-03-03'),
            ('E3', 'P2', 'finished', '2023-02-01', '2023-02-10'),
            ('E4', 'P2', 'cancelled', '2023-04-01', '2023-04-02')
    """)
    con.execute("""
        INSERT INTO conditions VALUES
            ('C1', 'E1', 'P1', 'diabetes', '2023-01-02', 'active'),
            ('C2', 'E1', 'P1', 'hypertension', '2023-01-03', 'active'),
            ('C3', 'E2', 'P1', 'diabetes', '2023-03-02', 'active'),
            ('C4', 'E3', 'P2', 'asthma', '2023-02-05', 'active'),
            ('C5', 'E3', 'P2', 'diabetes', '2023-02-06', 'resolved')
    """)
    con.execute("""
        INSERT INTO procedures VALUES
            ('PR1', 'E1', 'P1', 'surgery', '2023-01-04'),
            ('PR2', 'E3', 'P2', 'imaging', '2023-02-08'),
            ('PR3', 'E3', 'P2', 'surgery', '2023-02-09')
    """)
    yield con
    con.close()


class TestBasicScalarSubqueryProjection:
    """Level 1: Single-layer subquery projection."""

    def test_scalar_subquery_in_select(self, conn):
        """Correlated scalar subquery in SELECT list — basic case."""
        result = conn.execute("""
            SELECT __base.*
            FROM (
                SELECT
                    E.*,
                    (SELECT COUNT(*) FROM conditions c WHERE c.encounter_id = E.id) AS CondCount
                FROM encounters E
            ) AS __base
            WHERE __base.CondCount > 1
            ORDER BY __base.id
        """).fetchall()

        # E1 has 2 conditions (C1, C2), E3 has 2 conditions (C4, C5)
        assert len(result) == 2
        assert result[0][0] == "E1"
        assert result[1][0] == "E3"

    def test_multiple_scalar_subqueries_in_select(self, conn):
        """Multiple correlated scalar subqueries in same SELECT."""
        result = conn.execute("""
            SELECT __base.*
            FROM (
                SELECT
                    E.*,
                    (SELECT COUNT(*) FROM conditions c WHERE c.encounter_id = E.id) AS CondCount,
                    (SELECT MIN(c.date) FROM conditions c WHERE c.encounter_id = E.id) AS FirstCondDate
                FROM encounters E
            ) AS __base
            WHERE __base.CondCount > 0
              AND __base.FirstCondDate >= '2023-01-01'
            ORDER BY __base.id
        """).fetchall()

        assert len(result) == 3  # E1, E2, E3 all have conditions
        assert result[0][0] == "E1"
        assert result[1][0] == "E2"
        assert result[2][0] == "E3"


class TestExistsInScalarSubquery:
    """Level 2: EXISTS subqueries nested inside correlated scalar subqueries.

    This is the pattern that broke LATERAL joins — the key difference is
    that here the EXISTS is inside a scalar subquery in SELECT, not inside
    a lateral join's WHERE.
    """

    def test_exists_inside_scalar_subquery(self, conn):
        """EXISTS inside a correlated scalar subquery in SELECT."""
        result = conn.execute("""
            SELECT __base.*
            FROM (
                SELECT
                    E.*,
                    (SELECT COUNT(*) FROM conditions c
                     WHERE c.encounter_id = E.id
                       AND EXISTS (
                           SELECT 1 FROM procedures p
                           WHERE p.encounter_id = E.id
                             AND p.code = 'surgery'
                       )
                    ) AS CondWithSurgery
                FROM encounters E
            ) AS __base
            WHERE __base.CondWithSurgery > 0
            ORDER BY __base.id
        """).fetchall()

        # E1 has conditions and a surgery procedure (PR1)
        # E3 has conditions and a surgery procedure (PR3)
        assert len(result) == 2
        assert result[0][0] == "E1"
        assert result[1][0] == "E3"

    def test_not_exists_inside_scalar_subquery(self, conn):
        """NOT EXISTS inside a correlated scalar subquery in SELECT."""
        result = conn.execute("""
            SELECT __base.*
            FROM (
                SELECT
                    E.*,
                    (SELECT COUNT(*) FROM conditions c
                     WHERE c.encounter_id = E.id
                       AND NOT EXISTS (
                           SELECT 1 FROM procedures p
                           WHERE p.encounter_id = E.id
                       )
                    ) AS CondNoProcedure
                FROM encounters E
            ) AS __base
            WHERE __base.CondNoProcedure > 0
            ORDER BY __base.id
        """).fetchall()

        # E2 has a condition (C3) but no procedures for E2
        assert len(result) == 1
        assert result[0][0] == "E2"


class TestDeepNesting:
    """Level 3: 3-4 levels of nesting — comparable to CMS1218 depth."""

    def test_triple_nested_correlated_subqueries(self, conn):
        """3 levels: outer WHERE → scalar subquery → EXISTS → scalar subquery."""
        result = conn.execute("""
            SELECT __base.*
            FROM (
                SELECT
                    E.*,
                    (SELECT COUNT(*) FROM conditions c
                     WHERE c.encounter_id = E.id
                       AND c.clinical_status = 'active'
                       AND EXISTS (
                           SELECT 1 FROM procedures p
                           WHERE p.encounter_id = E.id
                             AND p.date > (SELECT MIN(c2.date) FROM conditions c2 WHERE c2.encounter_id = E.id)
                       )
                    ) AS ActiveCondWithProcedureAfterFirstCond
                FROM encounters E
            ) AS __base
            WHERE __base.ActiveCondWithProcedureAfterFirstCond > 0
            ORDER BY __base.id
        """).fetchall()

        # E1: has active conditions (C1, C2) and procedure PR1 (2023-01-04)
        # after first condition date (2023-01-02)
        assert len(result) >= 1
        assert result[0][0] == "E1"

    def test_projection_with_aggregation_in_inner(self, conn):
        """Subquery projection with aggregation in the inner scalar subqueries."""
        result = conn.execute("""
            SELECT __base.*
            FROM (
                SELECT
                    E.patient_id,
                    (SELECT string_agg(DISTINCT c.code, ',') FROM conditions c
                     WHERE c.patient_id = E.patient_id
                       AND c.clinical_status = 'active'
                    ) AS ActiveConditions
                FROM encounters E
                WHERE E.status = 'finished'
                GROUP BY E.patient_id
            ) AS __base
            WHERE __base.ActiveConditions IS NOT NULL
            ORDER BY __base.patient_id
        """).fetchall()

        assert len(result) == 2  # P1 and P2 both have finished encounters with active conditions


class TestPatientIdPropagation:
    """Verify patient_id remains accessible through the projection wrapper."""

    def test_patient_id_through_star_expansion(self, conn):
        """patient_id must be accessible as __base.patient_id after * expansion."""
        result = conn.execute("""
            SELECT __base.patient_id, __base.CondCount
            FROM (
                SELECT
                    E.*,
                    (SELECT COUNT(*) FROM conditions c WHERE c.encounter_id = E.id) AS CondCount
                FROM encounters E
            ) AS __base
            WHERE __base.CondCount > 0
            ORDER BY __base.patient_id, __base.id
        """).fetchall()

        assert len(result) == 3
        # patient_id should be accessible
        assert result[0][0] == "P1"
        assert result[1][0] == "P1"
        assert result[2][0] == "P2"

    def test_correlation_via_patient_id_in_outer_where(self, conn):
        """Outer WHERE can use patient_id from the projected subquery."""
        result = conn.execute("""
            SELECT __base.id, __base.CondCount
            FROM (
                SELECT
                    E.*,
                    (SELECT COUNT(*) FROM conditions c WHERE c.encounter_id = E.id) AS CondCount
                FROM encounters E
            ) AS __base
            WHERE __base.patient_id = 'P1' AND __base.CondCount > 0
            ORDER BY __base.id
        """).fetchall()

        assert len(result) == 2  # E1 and E2 for patient P1
        assert result[0][0] == "E1"
        assert result[1][0] == "E2"
