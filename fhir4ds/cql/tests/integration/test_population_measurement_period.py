"""Population-level Measurement Period edge cases."""

from __future__ import annotations

import duckdb

from fhir4ds.cql import FHIRDataLoader, evaluate_measure
from fhir4ds.cql.duckdb import register


def test_default_measurement_period_preserves_half_open_datetime_high(tmp_path):
    """A CQL-authored half-open DateTime parameter must exclude the high edge."""
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con)
    try:
        loader = FHIRDataLoader(con)
        for resource in [
            {"resourceType": "Patient", "id": "inside"},
            {
                "resourceType": "Encounter",
                "id": "inside-enc",
                "subject": {"reference": "Patient/inside"},
                "status": "finished",
                "period": {
                    "start": "2026-12-31T23:00:00",
                    "end": "2026-12-31T23:30:00",
                },
            },
            {"resourceType": "Patient", "id": "edge"},
            {
                "resourceType": "Encounter",
                "id": "edge-enc",
                "subject": {"reference": "Patient/edge"},
                "status": "finished",
                "period": {
                    "start": "2027-01-01T12:00:00",
                    "end": "2027-01-01T13:00:00",
                },
            },
        ]:
            loader.load_resource(resource)

        cql_path = tmp_path / "mp_half_open.cql"
        cql_path.write_text(
            """library Domain4MeasurementPeriod version '1.0.0'
using FHIR version '4.0.1'
context Patient
parameter "Measurement Period" Interval<DateTime> default Interval[@2026-01-01T00:00:00, @2027-01-01T00:00:00)
define "Qualifying Encounters":
  [Encounter] E where E.status = 'finished' and E.period during "Measurement Period"
define "Initial Population":
  exists "Qualifying Encounters"
"""
        )

        df = evaluate_measure(
            str(cql_path),
            con,
            output_columns={"initial_population": "Initial Population"},
        )
        rows = df.set_index("patient_id")["initial_population"].to_dict()

        assert rows == {"edge": False, "inside": True}
    finally:
        con.close()
