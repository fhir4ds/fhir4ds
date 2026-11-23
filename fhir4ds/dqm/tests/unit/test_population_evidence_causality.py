"""QA-D9S-001 (v0.0.26 D9 SKEPTIC): population-audit evidence causality.

In population audit mode, evidence for a boolean population definition is
collected from the retrieve CTEs the definition transitively depends on.
Without re-applying the definition's correlated-EXISTS row filters (e.g.
``P.performed during day of "Measurement Period"``), that evidence cites
EVERY valueset-matching resource — including resources outside the
measurement period that played no causal role in the population decision.

These tests pin that evidence cites only criteria-satisfying resources,
through chained boolean definitions (population -> event define -> retrieve).
"""

import json

import pytest

CQL = """library D9S version '1.0.0'
using FHIR version '4.0.1'
valueset "Enc VS": 'http://example.org/ValueSet/enc'
valueset "Excl VS": 'http://example.org/ValueSet/excl'
parameter "Measurement Period" Interval<DateTime>
context Patient

define "QualEnc":
  [Encounter: "Enc VS"] E where E.period starts during day of "Measurement Period"
define "ExclEv":
  exists ([Procedure: "Excl VS"] P where P.performed during day of "Measurement Period")

define "Initial Population": exists "QualEnc"
define "Denominator": "Initial Population"
define "Denominator Exclusion": "Initial Population" and "ExclEv"
"""

MEASURE = {
    "resourceType": "Measure",
    "id": "d9s",
    "library": ["http://example.org/Library/D9S|1.0.0"],
    "group": [{"population": [
        {"code": {"coding": [{"code": "initial-population"}]},
         "criteria": {"expression": "Initial Population"}},
        {"code": {"coding": [{"code": "denominator"}]},
         "criteria": {"expression": "Initial Population"}},
        {"code": {"coding": [{"code": "denominator-exclusion"}]},
         "criteria": {"expression": "Denominator Exclusion"}},
    ]}],
}

VALUESETS = [
    {
        "resourceType": "ValueSet",
        "id": "enc",
        "url": "http://example.org/ValueSet/enc",
        "compose": {"include": [{"system": "http://snomed.info/sct",
                                 "concept": [{"code": "308335008"}]}]},
    },
    {
        "resourceType": "ValueSet",
        "id": "excl",
        "url": "http://example.org/ValueSet/excl",
        "compose": {"include": [{"system": "http://snomed.info/sct",
                                 "concept": [{"code": "428191000124101"}]}]},
    },
]


def _proc(pid, day, code):
    return {
        "resourceType": "Procedure",
        "id": f"pr-{pid}-{day}-{code}",
        "status": "completed",
        "subject": {"reference": f"Patient/{pid}"},
        "performedDateTime": day,
        "code": {"coding": [{"system": "http://snomed.info/sct", "code": code}]},
    }


@pytest.fixture()
def con(tmp_path):
    import fhir4ds
    from fhir4ds.cql.loader.fhir_loader import FHIRDataLoader
    for i, vs in enumerate(VALUESETS):
        (tmp_path / f"vs{i}.json").write_text(json.dumps(vs))
    con = fhir4ds.create_connection()
    loader = FHIRDataLoader(con)
    loader.load_resources([
        {"resourceType": "Patient", "id": "w1", "birthDate": "1980-01-01"},
        {"resourceType": "Encounter", "id": "e-w1",
         "status": "finished",
         "subject": {"reference": "Patient/w1"},
         "period": {"start": "2026-06-15", "end": "2026-06-15"},
         "type": [{"coding": [{"system": "http://snomed.info/sct",
                               "code": "308335008"}]}]},
        # winner: exclusion procedure inside the measurement period
        _proc("w1", "2026-06-15", "428191000124101"),
        # decoy: same code, outside the measurement period
        _proc("w1", "2025-06-15", "428191000124101"),
    ])
    return con, tmp_path


def _evaluate(con, tmp_path, cql_text, audit_mode):
    from fhir4ds.dqm.evaluator import MeasureEvaluator
    lib = tmp_path / "lib.cql"
    lib.write_text(cql_text)
    ev = MeasureEvaluator(con)
    return ev.evaluate(
        measure_bundle=MEASURE,
        cql_library_path=str(lib),
        parameters={"Measurement Period": ("2026-01-01", "2026-12-31")},
        valueset_paths=[str(tmp_path / f"vs{i}.json") for i in range(len(VALUESETS))],
        audit_mode=audit_mode,
    )


def _cited_targets(cell):
    targets = set()
    for item in (cell.get("evidence") or []):
        for finding in (item.get("findings") or []):
            targets.add(finding.get("target"))
    return targets


class TestPopulationEvidenceCausality:
    def test_exclusion_evidence_excludes_out_of_period_decoy(self, con):
        con, tmp_path = con
        res = _evaluate(con, tmp_path, CQL, audit_mode="population")
        row = res.dataframe.to_dict("records")[0]
        assert row["denominator_exclusion"]["result"] is True
        targets = _cited_targets(row["denominator_exclusion"])
        assert "Procedure/pr-w1-2026-06-15-428191000124101" in targets, targets
        assert "Procedure/pr-w1-2025-06-15-428191000124101" not in targets, targets

    def test_exclusion_evidence_causality_full_mode(self, con):
        con, tmp_path = con
        res = _evaluate(con, tmp_path, CQL, audit_mode="full")
        row = res.dataframe.to_dict("records")[0]
        targets = _cited_targets(row["denominator_exclusion"])
        assert "Procedure/pr-w1-2026-06-15-428191000124101" in targets, targets
        assert "Procedure/pr-w1-2025-06-15-428191000124101" not in targets, targets


class TestSharedDefinitionPopulationJoinDedup:
    """QA-D9S-002: two populations referencing the same boolean definition
    must emit ONE LEFT JOIN in the final population SELECT, not one per
    population (DuckDB: "duplicate alias" BinderException, full audit mode)."""

    def test_two_populations_same_define_full_audit(self, con):
        con, tmp_path = con
        res = _evaluate(con, tmp_path, CQL, audit_mode="full")
        # Both columns are audit structs over the same "QualEnc" definition.
        records = res.dataframe.to_dict("records")
        assert len(records) == 1
        row = records[0]
        assert row["initial_population"]["result"] is True
        assert row["denominator"]["result"] is True

    def test_two_populations_same_define_population_audit(self, con):
        con, tmp_path = con
        res = _evaluate(con, tmp_path, CQL, audit_mode="population")
        records = res.dataframe.to_dict("records")
        assert len(records) == 1
        row = records[0]
        assert row["initial_population"]["result"] is True
        assert row["denominator"]["result"] is True


class TestAliasCountAttributionD9Historian:
    """QA-D9H-001 (v0.0.26 D9 HISTORIAN): count-based criteria bound to a
    named define must keep resource-level evidence attribution.

    ``define "NumCount": Count(<retrieve> P where ...)`` referenced by a
    population criterion (``"NumCount" >= 1``) previously lost the
    audit-evidence target entirely (target=null) even though the identical
    INLINE count comparison names the winning resources (QA-021 count
    attribution). The define's own SQL can synthesize the target twin
    (Case 3 count-unnest); it must be stored on the definition metadata so
    alias references recover it (Case 0)."""

    CQL_COUNT = CQL.replace(
        'define "Denominator Exclusion": "Initial Population" and "ExclEv"',
        'define "NumCount": Count([Procedure: "Excl VS"] P where '
        'P.performed during day of "Measurement Period")\n'
        'define "Denominator Exclusion": "Initial Population" and ("NumCount" >= 1)')

    def test_alias_count_evidence_names_winner_population_mode(self, con):
        con, tmp_path = con
        res = _evaluate(con, tmp_path, self.CQL_COUNT, audit_mode="population")
        row = res.dataframe.to_dict("records")[0]
        assert row["denominator_exclusion"]["result"] is True
        targets = _cited_targets(row["denominator_exclusion"])
        assert "Procedure/pr-w1-2026-06-15-428191000124101" in targets, targets
        assert "Procedure/pr-w1-2025-06-15-428191000124101" not in targets, targets

    def test_alias_count_evidence_names_winner_full_mode(self, con):
        con, tmp_path = con
        res = _evaluate(con, tmp_path, self.CQL_COUNT, audit_mode="full")
        row = res.dataframe.to_dict("records")[0]
        assert row["denominator_exclusion"]["result"] is True
        targets = _cited_targets(row["denominator_exclusion"])
        assert "Procedure/pr-w1-2026-06-15-428191000124101" in targets, targets
        assert "Procedure/pr-w1-2025-06-15-428191000124101" not in targets, targets

