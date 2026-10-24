"""OMOP S1: the ConceptMap view + curated supplements (design §3).

Chain: ConceptMap RESOURCES (Athena-converted or curated supplements) →
the omop_conceptmap VD → long/thin rows (vocabulary_id, concept_code,
concept_id, concept_name, equivalence) — the join target for every
per-OMOP-table VD. Pins the Muse-R1 functional dependency: one row per
(vocabulary_id, concept_code), first equivalence-passing target only;
unmatched equivalences filtered; vocabulary_id derived from group.source
via the closed FHIR-system→vocabulary constant set with raw-URI fallback.
"""

import json
from pathlib import Path

import pytest

import fhir4ds
from fhir4ds.viewdef.parser import parse_view_definition
from fhir4ds.viewdef.generator import SQLGenerator

OMOP_DIR = Path(__file__).parents[2] / "resources" / "omop"


@pytest.fixture(scope="module")
def conn():
    con = fhir4ds.create_connection()
    con.execute("CREATE TABLE __vd_src (resource JSON)")
    for name in ("conceptmap-supplements.json",):
        resource = json.loads((OMOP_DIR / name).read_text())
        con.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(resource)])
    return con


def _rows(conn, **extra_resources):
    for r in extra_resources.get("resources", []):
        conn.execute("INSERT INTO __vd_src VALUES (?)", [json.dumps(r)])
    vd = parse_view_definition(json.loads((OMOP_DIR / "conceptmap-view.json").read_text()))
    sql = SQLGenerator(source_table="__vd_src").generate(vd)
    return conn.execute(sql).fetchall()


class TestConceptMapView:
    def test_supplements_resolve(self, conn):
        rows = _rows(conn)
        by = {(r[0], r[1]): r[2] for r in rows}
        assert by[("http://hl7.org/fhir/administrative-gender", "male")] == "8507"
        assert by[("http://hl7.org/fhir/administrative-gender", "female")] == "8532"
        assert by[("http://terminology.hl7.org/CodeSystem/v3-ActCode", "IMP")] == "9201"
        assert by[("http://terminology.hl7.org/CodeSystem/v3-ActCode", "AMB")] == "9202"
        assert by[("http://terminology.hl7.org/CodeSystem/v3-ActCode", "EMER")] == "9203"
        assert by[("http://terminology.hl7.org/CodeSystem/condition-category", "problem-list-item")] == "38000245"
        assert by[("http://terminology.hl7.org/CodeSystem/condition-category", "encounter-diagnosis")] == "43542353"

    def test_athena_style_conversion(self, conn):
        rows = _rows(conn, resources=[{
            "resourceType": "ConceptMap", "id": "athena", "status": "active",
            "group": [{"source": "http://loinc.org", "element": [
                {"code": "718-7", "target": [
                    {"code": "3024929", "equivalence": "equal",
                     "display": "Hemoglobin [Mass/volume] in Blood"}]}]}],
        }])
        hit = [r for r in rows if r[1] == "718-7"]
        assert hit == [("LOINC", "718-7", "3024929", "Hemoglobin [Mass/volume] in Blood", "equal")]

    def test_vocabulary_derivation_fallback(self, conn):
        # Unknown source URIs pass through verbatim (raw-URI fallback).
        rows = _rows(conn, resources=[{
            "resourceType": "ConceptMap", "id": "local", "status": "active",
            "group": [{"source": "http://example.org/local-cs", "element": [
                {"code": "L1", "target": [{"code": "999", "equivalence": "equivalent"}]}]}],
        }])
        hit = [r for r in rows if r[1] == "L1"]
        assert hit[0][0] == "http://example.org/local-cs"

    def test_functional_dependency_first_target_only(self, conn):
        # Muse R1: a code with multiple equivalence-passing targets yields
        # exactly ONE row (the first) — strict (vocab, code) -> concept_id.
        rows = _rows(conn, resources=[{
            "resourceType": "ConceptMap", "id": "multi", "status": "active",
            "group": [{"source": "http://loinc.org", "element": [
                {"code": "x2", "target": [
                    {"code": "222", "equivalence": "equal"},
                    {"code": "333", "equivalence": "wider"}]}]}],
        }])
        hit = [r for r in rows if r[1] == "x2"]
        assert hit == [("LOINC", "x2", "222", None, "equal")]

    def test_unmatched_equivalence_filtered(self, conn):
        rows = _rows(conn, resources=[{
            "resourceType": "ConceptMap", "id": "unm", "status": "active",
            "group": [{"source": "http://loinc.org", "element": [
                {"code": "x1", "target": [{"code": "111", "equivalence": "unmatched"}]}]}],
        }])
        assert [r for r in rows if r[1] == "x1"] == []


class TestVocabularyTable:
    def test_closed_set_shape(self):
        vocab = json.loads((OMOP_DIR / "vocabulary.json").read_text())
        entries = vocab["vocabulary"]
        by_system = {e["system"]: e for e in entries}
        assert by_system["http://loinc.org"]["vocabulary_id"] == "LOINC"
        assert by_system["http://snomed.info/sct"]["vocabulary_id"] == "SNOMED"
        assert by_system["http://www.nlm.nih.gov/research/umls/rxnorm"]["vocabulary_id"] == "RxNorm"
        assert by_system["http://hl7.org/fhir/sid/icd-10-cm"]["vocabulary_id"] == "ICD10CM"
        assert by_system["http://hl7.org/fhir/sid/ndc"]["vocabulary_id"] == "NDC"
        # Standard vocabs rank ahead of billing codes; every entry has a priority.
        assert all("priority" in e for e in entries)
        assert by_system["http://snomed.info/sct"]["priority"] < by_system["http://hl7.org/fhir/sid/ndc"]["priority"]
