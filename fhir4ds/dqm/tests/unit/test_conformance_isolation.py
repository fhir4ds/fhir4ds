"""Conformance runner isolation tests."""

import duckdb

from fhir4ds.cql.duckdb.udf.variable import registerVariableUdfs
from fhir4ds.dqm.tests.conformance.database import _fix_claim_encounter_refs
from fhir4ds.dqm.tests.conformance.runner import _clear_runtime_state


def test_clear_runtime_state_clears_connection_variables() -> None:
    con = duckdb.connect()
    registerVariableUdfs(con)
    con.execute("SELECT setvariable('patient_id', 'stale-patient')")

    _clear_runtime_state(con)

    assert con.execute("SELECT getvariable('patient_id')").fetchone()[0] == ""


def test_claim_encounter_repair_uses_stable_sorted_references() -> None:
    claim = {
        "resourceType": "Claim",
        "id": "claim-1",
        "item": [
            {"sequence": 1, "encounter": [{"reference": "Encounter/missing"}]},
        ],
    }

    fixed = _fix_claim_encounter_refs(claim, {"enc-b", "enc-a"})

    assert fixed["item"][0]["encounter"] == [
        {"reference": "Encounter/enc-a"},
        {"reference": "Encounter/enc-b"},
    ]
    assert claim["item"][0]["encounter"] == [{"reference": "Encounter/missing"}]
