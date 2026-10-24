"""OMOP S1 (rev 2): the ConceptMap view + curated supplements.

Rev-2 shape: the STANDARD MONOLITHIC ConceptMap (all groups in one
resource) is the converter contract; the conceptmap VD flattens it into
one row per mapping (Muse-R1 functional dependency), materialized as
the omop.omop_conceptmap join target for event VDs.
"""

import json
from pathlib import Path

import pytest

import fhir4ds
from fhir4ds.viewdef.parser import parse_view_definition
from fhir4ds.viewdef.generator import SQLGenerator

OMOP_DIR = Path(__file__).parents[2] / "resources" / "omop"

ATHENA_STYLE = {
    "resourceType": "ConceptMap", "id": "athena-loinc", "status": "active",
    "group": [{"source": "http://loinc.org", "element": [
        {"code": "718-7", "target": [
            {"code": "3024929", "equivalence": "equal",
             "display": "Hemoglobin [Mass/volume] in Blood"}]}]}],
}

MULTI_TARGET = {
    "resourceType": "ConceptMap", "id": "multi", "status": "active",
    "group": [{"source": "http://loinc.org", "element": [
        {"code": "x1", "target": [{"code": "111", "equivalence": "unmatched"}]},
        {"code": "x2", "target": [
            {"code": "222", "equivalence": "equal"},
            {"code": "333", "equivalence": "wider"}]}]}],
}

LOCAL_CS = {
    "resourceType": "ConceptMap", "id": "local", "status": "active",
    "group": [{"source": "http://example.org/local-cs", "element": [
        {"code": "L1", "target": [{"code": "999", "equivalence": "equivalent"}]}]}],
}


def _run(con, *resources):
    for r in resources:
        con.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(r)])
    vd = parse_view_definition(json.loads((OMOP_DIR / "conceptmap-view.json").read_text()))
    sql = SQLGenerator(source_table="__vd_src").generate(vd)
    return con.execute(sql).fetchall()


@pytest.fixture()
def conn():
    con = fhir4ds.create_connection()
    con.execute("CREATE OR REPLACE TABLE __vd_src (resource JSON)")
    return con


class TestConceptMapView:
    def test_supplements_resolve(self, conn):
        sup = json.loads((OMOP_DIR / "conceptmap-supplements.json").read_text())
        rows = _run(conn, sup)
        # tuple: (vocabulary_id, source_system, concept_code, concept_id, ...)
        by = {(r[1], r[2]): r[3] for r in rows}
        assert by[("http://hl7.org/fhir/administrative-gender", "male")] == "8507"
        assert by[("http://hl7.org/fhir/administrative-gender", "female")] == "8532"
        assert by[("http://terminology.hl7.org/CodeSystem/v3-ActCode", "IMP")] == "9201"
        assert by[("http://terminology.hl7.org/CodeSystem/v3-ActCode", "AMB")] == "9202"
        assert by[("http://terminology.hl7.org/CodeSystem/v3-ActCode", "EMER")] == "9203"
        assert by[("http://terminology.hl7.org/CodeSystem/condition-category", "problem-list-item")] == "38000245"
        assert by[("http://terminology.hl7.org/CodeSystem/condition-category", "encounter-diagnosis")] == "43542353"

    def test_athena_style_conversion(self, conn):
        rows = _run(conn, ATHENA_STYLE)
        hit = [r for r in rows if r[2] == "718-7"]
        assert hit == [("LOINC", "http://loinc.org", "718-7", "3024929",
                        "Hemoglobin [Mass/volume] in Blood", "equal")]

    def test_vocabulary_derivation_fallback(self, conn):
        rows = _run(conn, LOCAL_CS)
        hit = [r for r in rows if r[2] == "L1"]
        # unknown source passes through verbatim in BOTH derived vocab and source_system
        assert hit[0][1] == "http://example.org/local-cs"

    def test_functional_dependency_first_target_only(self, conn):
        rows = _run(conn, MULTI_TARGET)
        hit = [r for r in rows if r[2] == "x2"]
        assert len(hit) == 1 and hit[0][3] == "222"
        assert [r for r in rows if r[2] == "x1"] == []

    def test_unmatched_equivalence_filtered(self, conn):
        rows = _run(conn, MULTI_TARGET)
        assert [r for r in rows if r[2] == "x1"] == []


class TestVocabularyTable:
    def test_closed_set_shape(self):
        vocab = json.loads((OMOP_DIR / "vocabulary.json").read_text())
        by_system = {e["system"]: e for e in vocab["vocabulary"]}
        assert by_system["http://loinc.org"]["vocabulary_id"] == "LOINC"
        assert by_system["http://snomed.info/sct"]["vocabulary_id"] == "SNOMED"
        assert by_system["http://www.nlm.nih.gov/research/umls/rxnorm"]["vocabulary_id"] == "RxNorm"
        assert by_system["http://hl7.org/fhir/sid/icd-10-cm"]["vocabulary_id"] == "ICD10CM"
        assert by_system["http://hl7.org/fhir/sid/ndc"]["vocabulary_id"] == "NDC"
        assert all("priority" in e for e in vocab["vocabulary"])
        assert by_system["http://snomed.info/sct"]["priority"] < by_system["http://hl7.org/fhir/sid/ndc"]["priority"]
