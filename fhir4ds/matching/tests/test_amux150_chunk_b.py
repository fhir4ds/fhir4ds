"""AMUX-150 chunk B acceptance tests (19-34) — identity strategy.

Practitioner / Organization / Location on the SHARED matching engine
(entity_type scoping, per-type rule tables, per-type extractors), plus the
RelatedPerson piggyback on the pairwise Linkage writer.

Grounding: FEATURE_NON_CODED_DEDUP.md §3, §6 (tests 19-34).
"""

from __future__ import annotations

import json

import duckdb

from fhir4ds.matching import (
    CATEGORY1_RULES,
    APPROVAL_THRESHOLD,
    index_patient,
    match_patient,
)
from fhir4ds.matching.engine import match_fields
from fhir4ds.matching.entity_extractors import (
    extract_location_fields,
    extract_organization_fields,
    extract_practitioner_fields,
)
from fhir4ds.matching.entity_rules import (
    LOCATION_RULES,
    ORGANIZATION_RULES,
    PRACTITIONER_RULES,
)
from fhir4ds.matching.corpus import match_corpus
from fhir4ds.matching.linkage import load_linkage_resources
from fhir4ds.matching.related_person import match_related_persons
from fhir4ds.matching.store import index_entity

_NPI_SYSTEM = "http://hl7.org/fhir/sid/us-npi"
_CLIA_SYSTEM = "urn:oid:2.16.840.1.113883.4.82"
_TAX_SYSTEM = "urn:oid:2.16.840.1.113883.4.2"
_ACT = "http://terminology.hl7.org/CodeSystem/v3-ActCode"
_ROLE = "http://terminology.hl7.org/CodeSystem/v3-RoleCode"


def _pract(rid, *, family=None, given=None, npi=None, phones=(),
           emails=(), streets=()):
    resource = {"resourceType": "Practitioner", "id": rid, "active": True}
    if family or given:
        name = {"use": "official"}
        if family:
            name["family"] = family
        if given:
            name["given"] = list(given)
        resource["name"] = [name]
    if npi:
        resource["identifier"] = [{"system": _NPI_SYSTEM, "value": npi}]
    telecom = [{"system": "phone", "value": p} for p in phones] + \
              [{"system": "email", "value": e} for e in emails]
    if telecom:
        resource["telecom"] = telecom
    if streets:
        resource["address"] = [{"line": [s], "city": "Springfield",
                                "state": "IL", "postalCode": "62704"}
                               for s in streets]
    return resource


def _org(rid, *, name=None, aliases=(), npi=None, clia=None, tax=None,
         line=None, city="Springfield", phones=()):
    resource = {"resourceType": "Organization", "id": rid, "active": True}
    if name:
        resource["name"] = name
    if aliases:
        resource["alias"] = list(aliases)
    identifiers = []
    if npi:
        identifiers.append({"system": _NPI_SYSTEM, "value": npi})
    if clia:
        identifiers.append({"system": _CLIA_SYSTEM, "value": clia})
    if tax:
        identifiers.append({"system": _TAX_SYSTEM, "value": tax})
    if identifiers:
        resource["identifier"] = identifiers
    if line:
        resource["address"] = [{"line": [line], "city": city,
                                "state": "IL", "postalCode": "62704"}]
    if phones:
        resource["telecom"] = [{"system": "phone", "value": p}
                               for p in phones]
    return resource


def _loc(rid, *, name=None, line=None, city="Springfield", state="IL",
         postal="62704", phones=(), position=None):
    resource = {"resourceType": "Location", "id": rid,
                "status": "active"}
    if name:
        resource["name"] = name
    if line:
        resource["address"] = [{"line": [line], "city": city,
                                "state": state, "postalCode": postal}]
    if phones:
        resource["telecom"] = [{"system": "phone", "value": p}
                               for p in phones]
    if position:
        resource["position"] = position
    return resource


def _index_pract(conn, resource):
    index_entity(conn, "Practitioner", resource,
                 extract_practitioner_fields(resource))


def _index_org(conn, resource):
    index_entity(conn, "Organization", resource,
                 extract_organization_fields(resource))


def _index_loc(conn, resource):
    index_entity(conn, "Location", resource,
                 extract_location_fields(resource))


def _match_pract(conn, resource, exclude=frozenset()):
    return match_fields(conn, extract_practitioner_fields(resource),
                        rules=PRACTITIONER_RULES,
                        entity_type="Practitioner", exclude=exclude)


def _match_org(conn, resource):
    return match_fields(conn, extract_organization_fields(resource),
                        rules=ORGANIZATION_RULES,
                        entity_type="Organization")


class TestPractitioner:
    def test_19_npi_alone_matches_p1(self):
        conn = duckdb.connect()
        _index_pract(conn, _pract("p1", family="House", given=["Gregory"],
                                  npi="1234567890"))
        result = _match_pract(conn, _pract(
            "p2", family="Wilson", given=["Greg"], npi="1234567890"))
        assert result.outcome == "match"
        assert result.rule_id == "P1"
        assert result.matched_ids == ("p1",)
        conn.close()

    def test_20_name_phone_matches_p2(self):
        conn = duckdb.connect()
        _index_pract(conn, _pract("p1", family="House",
                                  given=["Gregory"], phones=["5551234567"]))
        result = _match_pract(conn, _pract(
            "p2", family="House", given=["Gregory"], phones=["5551234567"]))
        assert result.outcome == "match"
        assert result.rule_id == "P2"
        conn.close()

    def test_21_fuzzy_name_match_type(self):
        conn = duckdb.connect()
        _index_pract(conn, _pract("p1", family="Smith",
                                  given=["Robert"], phones=["5551234567"]))
        result = _match_pract(conn, _pract(
            "p2", family="Smiht", given=["Bob"], phones=["5551234567"]))
        assert result.outcome == "match"
        assert result.rule_id == "P2"
        assert result.match_type == "fuzzy"
        conn.close()

    def test_22_name_only_never_links(self):
        conn = duckdb.connect()
        _index_pract(conn, _pract("father", family="Smith",
                                  given=["John"], phones=["5550001111"]))
        result = _match_pract(conn, _pract(
            "son", family="Smith", given=["John"], phones=["5559992222"]))
        assert result.outcome == "no_match"
        conn.close()

    def test_23_p4_phone_guard_drops_pair(self):
        conn = duckdb.connect()
        _index_pract(conn, _pract("a", family="House", given=["Gregory"],
                                  phones=["5550001111"],
                                  streets=["100 Main St"]))
        result = _match_pract(conn, _pract(
            "b", family="House", given=["Gregory"],
            phones=["5559992222"], streets=["100 Main St"]))
        assert result.outcome == "no_match"
        conn.close()

    def test_24_suffix_conflict_negates(self):
        conn = duckdb.connect()
        _index_pract(conn, _pract("jr", family="Smith",
                                  given=["John", "Jr"], npi="1234567890",
                                  phones=["5551234567"]))
        result = _match_pract(conn, _pract(
            "sr", family="Smith", given=["John", "Sr"], npi="1234567890",
            phones=["5551234567"]))
        assert result.outcome == "no_match"
        conn.close()

    def test_33_placeholder_name_never_crashes(self):
        conn = duckdb.connect()
        garbage = {"resourceType": "Practitioner", "id": "g1",
                   "name": [{"use": "official", "family": "???",
                             "given": ["!!!"]}]}
        fields = extract_practitioner_fields(garbage)
        assert not fields.get("first") and not fields.get("last")
        _index_pract(conn, garbage)
        result = _match_pract(conn, garbage)
        assert result.outcome == "no_match"
        conn.close()


class TestOrganization:
    def test_25_rule_matrix(self):
        conn = duckdb.connect()
        # CLIA
        _index_org(conn, _org("o1", name="Springfield Lab",
                              clia="22D1234567"))
        result = _match_org(conn, _org("o2", name="Springfield Lab",
                                       clia="22D1234567"))
        assert (result.outcome, result.rule_id) == ("match", "O2")
        # tax_id + name
        _index_org(conn, _org("o3", name="General Hospital",
                              tax="123456789"))
        result = _match_org(conn, _org("o4", name="General Hospital",
                                       tax="123456789"))
        assert (result.outcome, result.rule_id) == ("match", "O3")
        # name + addr_key — CR-002 (2026-11-20): O4 (P ~ 2e-6) exceeds the
        # org 1e-8 approval budget -> must NOT link alone; WITH an exactly
        # agreeing phone corroborator (combined 2e-12) it links.
        _index_org(conn, _org("o5", name="Imaging Center",
                              line="100 Main St"))
        result = _match_org(conn, _org("o6", name="Imaging Center",
                                       line="100 Main St"))
        assert result.outcome == "no_match"
        _index_org(conn, _org("o5b", name="Imaging Center",
                              line="100 Main St", phones=["2175550100"]))
        result = _match_org(conn, _org("o6b", name="Imaging Center",
                                       line="100 Main St",
                                       phones=["2175550100"]))
        assert result.outcome == "match"
        assert result.rule_id == "O4"
        # name-only, different cities -> no_match
        _index_org(conn, _org("o7", name="City Clinic",
                              line="9 Elm St", city="Shelbyville"))
        result = _match_org(conn, _org("o8", name="City Clinic",
                                       line="100 Main St"))
        assert result.outcome == "no_match"
        conn.close()

    def test_26_alias_contributes_org_name(self):
        conn = duckdb.connect()
        _index_org(conn, _org("o1", name="General Hospital",
                              aliases=["General Health System"],
                              tax="123456789"))
        result = _match_org(conn, _org(
            "o2", name="General Health System",
            aliases=["General Hospital"], tax="123456789"))
        assert result.outcome == "match"
        assert result.rule_id == "O3"
        conn.close()


class TestLocation:
    def test_27_rule_matrix(self):
        conn = duckdb.connect()
        _index_loc(conn, _loc("l1", name="Main Pharmacy",
                              line="100 Main St"))
        result = match_fields(
            conn, extract_location_fields(
                _loc("l2", name="Main Pharmacy", line="100 Main St")),
            rules=LOCATION_RULES, entity_type="Location")
        assert result.outcome == "match"
        assert result.rule_id == "L1"
        _index_loc(conn, _loc("l3", name="Lab Draw Station",
                              position={"latitude": 39.7817,
                                        "longitude": -89.6501}))
        result = match_fields(
            conn, extract_location_fields(
                _loc("l4", name="Lab Draw Station",
                     position={"latitude": 39.7817,
                               "longitude": -89.6501})),
            rules=LOCATION_RULES, entity_type="Location")
        assert result.outcome == "match"
        assert result.rule_id == "L2"
        # same name, different address, no position -> no_match
        result = match_fields(
            conn, extract_location_fields(
                _loc("l5", name="Main Pharmacy", line="9 Elm St")),
            rules=LOCATION_RULES, entity_type="Location")
        assert result.outcome == "no_match"
        conn.close()

    def test_28_geo_key_rounding(self):
        near_a = extract_location_fields(_loc(
            "a", name="Campus Bldg A",
            position={"latitude": 39.7817, "longitude": -89.6501}))
        near_b = extract_location_fields(_loc(
            "b", name="Campus Bldg A",
            position={"latitude": 39.7840, "longitude": -89.6488}))
        far = extract_location_fields(_loc(
            "c", name="Campus Bldg A",
            position={"latitude": 39.8300, "longitude": -89.7000}))
        assert near_a["geo_key"] == near_b["geo_key"]
        assert near_a["geo_key"] != far["geo_key"]


class TestRelatedPerson:
    def test_29_piggyback(self):
        conn = duckdb.connect()
        rp = lambda rid, patient, code, period: {
            "resourceType": "RelatedPerson", "id": rid,
            "patient": {"reference": patient},
            "relationship": [{"coding": [{"system": _ROLE,
                                          "code": code}]}],
            "period": period}
        rps = [
            rp("r1", "Patient/p1", "WIFE",
               {"start": "2020-01-01", "end": "2024-01-01"}),
            rp("r2", "Patient/p2", "WIFE",
               {"start": "2021-06-01", "end": "2025-01-01"}),
            rp("r3", "Patient/p1", "SON",
               {"start": "2020-01-01", "end": "2024-01-01"}),
            rp("r4", "Patient/p2", "WIFE",
               {"start": "2025-06-01", "end": "2026-01-01"}),
        ]
        report = match_related_persons(
            conn, "run-rp", rps,
            membership={"p1": "p1", "p2": "p1"})
        assert report.pairs_matched == 1
        rows = conn.execute("SELECT linkage_id FROM linkage").fetchall()
        assert ("RelatedPerson/r1|RelatedPerson/r2",) in rows
        # rule provenance in the stored resource
        resources = load_linkage_resources(conn)
        assert resources[0]["extension"][0]["extension"][0] == \
            {"url": "ruleId", "valueString": "RP1"}
        conn.close()


class TestEngineBackCompatAndIsolation:
    def test_30_patient_gate_unchanged(self):
        # The patient rule table and threshold are untouched by
        # generalization; the full existing patient suite is the
        # byte-for-byte gate (run separately). Pin the constants here.
        assert len(CATEGORY1_RULES) == 29
        assert APPROVAL_THRESHOLD == 2e-12
        conn = duckdb.connect()
        twin_a = {"resourceType": "Patient", "id": "pat1",
                  "name": [{"use": "official", "family": "House",
                            "given": ["Gregory"]}],
                  "birthDate": "1959-06-11",
                  "telecom": [{"system": "phone",
                               "value": "5551234567"}]}
        twin_b = {"resourceType": "Patient", "id": "pat2",
                  "name": [{"use": "official", "family": "House",
                            "given": ["Gregory"]}],
                  "birthDate": "1959-06-11",
                  "telecom": [{"system": "phone",
                               "value": "5551234567"}]}
        index_patient(conn, twin_a)
        result = match_patient(conn, twin_b, exclude=frozenset({"pat2"}))
        assert result.outcome == "match"
        conn.close()

    def test_31_corpus_mode_practitioner_deterministic(self):
        corpus = [
            _pract("a1", family="House", given=["Gregory"], npi="1234567890"),
            _pract("a2", family="Hause", given=["Gregory"], npi="1234567890",
                   phones=["5551234567"]),
            _pract("b1", family="Wilson", given=["Eric"],
                   phones=["5559876543"]),
        ]
        runs = []
        for order in ([0, 1, 2], [2, 1, 0], [1, 0, 2]):
            conn = duckdb.connect()
            for i in order:
                _index_pract(conn, corpus[i])
            report = match_corpus(conn, "run-b",
                                  rules=PRACTITIONER_RULES,
                                  entity_type="Practitioner")
            resources = load_linkage_resources(conn)
            runs.append((report.counts,
                         json.dumps(resources, sort_keys=True)))
            conn.close()
        assert runs[0] == runs[1] == runs[2]
        assert runs[0][1] != "[]"

    def test_32_entity_type_isolation(self):
        conn = duckdb.connect()
        _index_pract(conn, _pract("pr1", family="House",
                                  given=["Gregory"], phones=["5551234567"]))
        patient = {"resourceType": "Patient", "id": "pat1",
                   "name": [{"use": "official", "family": "House",
                             "given": ["Gregory"]}],
                   "telecom": [{"system": "phone",
                                "value": "5551234567"}]}
        # Patient matching never sees the Practitioner index rows.
        result = match_patient(conn, patient)
        assert result.outcome == "no_match"
        conn.close()

    def test_34_linkage_and_audit_with_extension(self):
        conn = duckdb.connect()
        _index_pract(conn, _pract("p1", family="House",
                                  given=["Gregory"], phones=["5551234567"]))
        _index_pract(conn, _pract("p2", family="Hause",
                                  given=["Gregory"], phones=["5551234567"]))
        report = match_corpus(conn, "run-34",
                              rules=PRACTITIONER_RULES,
                              entity_type="Practitioner")
        assert report.match_outcomes == 2  # p1~p2 from both directions
        resources = load_linkage_resources(conn)
        assert len(resources) == 1
        ext = resources[0]["extension"][0]
        assert ext["url"].endswith("/matching")
        urls = [e["url"] for e in ext["extension"]]
        assert "ruleId" in urls and "evidence" in urls
        audit = conn.execute(
            "SELECT patient_id, outcome, rule_id FROM match_audit "
            "WHERE run_id = 'run-34'").fetchall()
        assert len(audit) == 2
        conn.close()
