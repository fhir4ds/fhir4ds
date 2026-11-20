"""AMUX-150 code-review CR-002 — per-entity approval-threshold enforcement.

Joel decision (2026-11-20): for entity_type != "Patient", a rule whose
effective P(collision) exceeds its rule set's approval threshold must NOT
link alone — it links only when corroborated such that the COMBINED
evidence (firing-rule P x the u-probabilities of additional exactly-agreeing
fields, the engine's existing product-combination semantics) is under
budget.

Patient behavior is byte-identical (the existing patient suite is the gate;
pinned here by an explicit no-enforcement check).

Grounding: evolution_amux150.json CR-002, FDD §3.3/§10 Q1.
"""

from __future__ import annotations

import json

import duckdb

from fhir4ds.matching import index_patient, match_patient
from fhir4ds.matching.audit import record_match_audit
from fhir4ds.matching.corpus import match_corpus
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
from fhir4ds.matching.store import index_entity

_NPI_SYSTEM = "http://hl7.org/fhir/sid/us-npi"


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
        identifiers.append(
            {"system": "urn:oid:2.16.840.1.113883.4.82", "value": clia})
    if tax:
        identifiers.append(
            {"system": "urn:oid:2.16.840.1.113883.4.2", "value": tax})
    if identifiers:
        resource["identifier"] = identifiers
    if line:
        resource["address"] = [{"line": [line], "city": city,
                                "state": "IL", "postalCode": "62704"}]
    if phones:
        resource["telecom"] = [{"system": "phone", "value": p}
                               for p in phones]
    return resource


def _loc(rid, *, name=None, line=None, phones=()):
    resource = {"resourceType": "Location", "id": rid, "status": "active"}
    if name:
        resource["name"] = name
    if line:
        resource["address"] = [{"line": [line], "city": "Springfield",
                                "state": "IL", "postalCode": "62704"}]
    if phones:
        resource["telecom"] = [{"system": "phone", "value": p}
                               for p in phones]
    return resource


def _pract(rid, *, family=None, given=None, npi=None, phones=(), streets=()):
    resource = {"resourceType": "Practitioner", "id": rid, "active": True}
    if family or given:
        name = {"use": "official", "family": family, "given": list(given)}
        resource["name"] = [name]
    if npi:
        resource["identifier"] = [{"system": _NPI_SYSTEM, "value": npi}]
    if phones:
        resource["telecom"] = [{"system": "phone", "value": p}
                               for p in phones]
    if streets:
        resource["address"] = [{"line": [s], "city": "Springfield",
                                "state": "IL", "postalCode": "62704"}
                               for s in streets]
    return resource


def _index_org(conn, resource):
    index_entity(conn, "Organization", resource,
                 extract_organization_fields(resource))


def _index_loc(conn, resource):
    index_entity(conn, "Location", resource,
                 extract_location_fields(resource))


def _index_pract(conn, resource):
    index_entity(conn, "Practitioner", resource,
                 extract_practitioner_fields(resource))


def _match_org(conn, resource):
    return match_fields(conn, extract_organization_fields(resource),
                        rules=ORGANIZATION_RULES,
                        entity_type="Organization")


def _match_loc(conn, resource):
    return match_fields(conn, extract_location_fields(resource),
                        rules=LOCATION_RULES, entity_type="Location")


def _match_pract(conn, resource):
    return match_fields(conn, extract_practitioner_fields(resource),
                        rules=PRACTITIONER_RULES,
                        entity_type="Practitioner")


class TestOrganizationEnforcement:
    def test_org_name_addr_only_must_not_link(self):
        """CR-002 acceptance: O4 (org_name + addr_key, P ~ 2e-6) exceeds
        the org 1e-8 approval budget and has no corroborator -> no_match."""
        conn = duckdb.connect()
        _index_org(conn, _org("o5", name="Imaging Center",
                              line="100 Main St"))
        result = _match_org(conn, _org("o6", name="Imaging Center",
                                       line="100 Main St"))
        assert result.outcome == "no_match"
        # the refusal itself is auditable on the result
        assert result.threshold_enforcement is not None
        enf = result.threshold_enforcement
        assert enf["required"] is True
        assert enf["satisfied"] is False
        assert enf["rule_id"] == "O4"
        assert enf["threshold"] == 1e-8
        assert enf["firing_p"] > 1e-8
        assert enf["corroborating_fields"] == []
        conn.close()

    def test_org_name_addr_with_phone_corroborator_links(self):
        """CR-002 acceptance: the same O4 pair WITH an exactly-agreeing
        phone corroborator links — combined P = 2e-6 x 1e-6 = 2e-12,
        comfortably under the 1e-8 budget."""
        conn = duckdb.connect()
        _index_org(conn, _org("o5", name="Imaging Center",
                              line="100 Main St", phones=["2175550100"]))
        result = _match_org(conn, _org("o6", name="Imaging Center",
                                       line="100 Main St",
                                       phones=["2175550100"]))
        assert result.outcome == "match"
        assert result.rule_id == "O4"
        assert result.threshold_enforcement is not None
        enf = result.threshold_enforcement
        assert enf["required"] is True
        assert enf["satisfied"] is True
        assert enf["corroborating_fields"] == ["phone"]
        assert enf["combined_p"] <= 1e-8
        # confidence reflects the COMBINED evidence, not O4 alone
        assert result.confidence == 1.0 - enf["combined_p"]
        conn.close()

    def test_org_identifier_rules_under_budget_still_link_alone(self):
        """Over-enforcement guard: O3 (tax_id + org_name, P = 2e-9) stays
        under the 1e-8 budget — no corroboration required. O2 (CLIA)
        RETUNED to authored P = 1e-8 (Joel decision 2026-11-20, FHIR4-18):
        CLIA is a CMS-issued facility-unique identifier, so it links ALONE
        with no corroborator; a DISAGREEING CLIA never fires O2 at all."""
        conn = duckdb.connect()
        _index_org(conn, _org("o3", name="General Hospital",
                              tax="123456789"))
        result = _match_org(conn, _org("o4", name="General Hospital",
                                       tax="123456789"))
        assert (result.outcome, result.rule_id) == ("match", "O3")
        assert result.threshold_enforcement is None
        # O2 links ALONE: identical CLIA, no name on either side
        _index_org(conn, _org("o1", clia="22D1234567"))
        result = _match_org(conn, _org("o2", clia="22D1234567"))
        assert (result.outcome, result.rule_id) == ("match", "O2")
        assert result.threshold_enforcement is None
        # ...and with names that DISAGREE (no corroboration needed at 1e-8)
        _index_org(conn, _org("o9", name="Springfield Lab",
                              clia="22D2039876"))
        result = _match_org(conn, _org("o10", name="Shelbyville Lab",
                                       clia="22D2039876"))
        assert (result.outcome, result.rule_id) == ("match", "O2")
        # CLIA MISMATCH: a different CLIA never fires O2 -> refused
        _index_org(conn, _org("o11", clia="22D3111122"))
        result = _match_org(conn, _org("o12", clia="99D9876543"))
        result = _match_org(conn, _org("o12", clia="99D9876543"))
        assert result.outcome == "no_match"
        conn.close()

    def test_disagreeing_phone_is_not_corroboration(self):
        """A phone present on both sides but DISJOINT is no corroboration
        (exact-set intersection drives the product)."""
        conn = duckdb.connect()
        _index_org(conn, _org("o5", name="Imaging Center",
                              line="100 Main St", phones=["2175550100"]))
        result = _match_org(conn, _org("o6", name="Imaging Center",
                                       line="100 Main St",
                                       phones=["2175550199"]))
        assert result.outcome == "no_match"
        assert result.threshold_enforcement is not None
        assert result.threshold_enforcement["satisfied"] is False
        assert result.threshold_enforcement["corroborating_fields"] == []
        conn.close()


class TestPractitionerEnforcement:
    def test_practitioner_npi_anchor_survives_enforcement(self):
        """CR-002 practitioner check: P1 (NPI alone, P = 1e-9) is under the
        1e-8 practitioner budget — still links."""
        conn = duckdb.connect()
        _index_pract(conn, _pract("p1", family="House",
                                  given=["Gregory"], npi="1234567890"))
        result = _match_pract(conn, _pract(
            "p2", family="Housse", given=["Greg"], npi="1234567890"))
        assert (result.outcome, result.rule_id) == ("match", "P1")
        assert result.threshold_enforcement is None
        conn.close()

    def test_practitioner_p2_tier_survives_enforcement(self):
        """P2 (last* + first* + phone, P = 1e-10 exact / 3e-10 fuzzy) is
        under budget — still links."""
        conn = duckdb.connect()
        _index_pract(conn, _pract("p1", family="House",
                                  given=["Gregory"], phones=["2175550100"]))
        result = _match_pract(conn, _pract(
            "p2", family="House", given=["Gregory"],
            phones=["2175550100"]))
        assert (result.outcome, result.rule_id) == ("match", "P2")
        assert result.threshold_enforcement is None
        conn.close()

    def test_practitioner_p4_fuzzy_under_budget(self):
        """P4 fuzzy (last* + first* + street, P = 9e-9) stays under the
        1e-8 budget — enforcement must not break the authored tier."""
        conn = duckdb.connect()
        _index_pract(conn, _pract("p1", family="House",
                                  given=["Gregory"],
                                  streets=["100 Main St"]))
        result = _match_pract(conn, _pract(
            "p2", family="Housse", given=["Gregory"],
            streets=["100 Main St"]))
        assert (result.outcome, result.rule_id) == ("match", "P4")
        assert result.match_type == "fuzzy"
        assert result.threshold_enforcement is None
        conn.close()


class TestLocationEnforcement:
    def test_location_exact_at_threshold_links(self):
        """L1 exact (addr_key x loc_name = 1e-6) EQUALS the location budget
        1e-6 — 'exceeds' is strict, so it links without corroboration."""
        conn = duckdb.connect()
        _index_loc(conn, _loc("l1", name="Main Pharmacy",
                              line="100 Main St"))
        result = _match_loc(conn, _loc("l2", name="Main Pharmacy",
                                       line="100 Main St"))
        assert (result.outcome, result.rule_id) == ("match", "L1")
        assert result.threshold_enforcement is None
        conn.close()

    def test_location_fuzzy_name_requires_corroboration(self):
        """L1 with a FUZZY name (P = 2e-6) exceeds the 1e-6 location
        budget: no corroborator -> no_match; phone corroborator
        (2e-6 x 1e-6 = 2e-12) -> match."""
        conn = duckdb.connect()
        _index_loc(conn, _loc("l1", name="Main Pharmacy",
                              line="100 Main St"))
        result = _match_loc(conn, _loc("l2", name="Main Pharmacx",
                                       line="100 Main St"))
        assert result.outcome == "no_match"
        assert result.threshold_enforcement is not None
        assert result.threshold_enforcement["rule_id"] == "L1"
        assert result.threshold_enforcement["satisfied"] is False

        conn2 = duckdb.connect()
        _index_loc(conn2, _loc("l1", name="Main Pharmacy",
                               line="100 Main St", phones=["2175550100"]))
        result = _match_loc(conn2, _loc(
            "l2", name="Main Pharmacx", line="100 Main St",
            phones=["2175550100"]))
        assert (result.outcome, result.rule_id) == ("match", "L1")
        assert result.threshold_enforcement is not None
        assert result.threshold_enforcement["corroborating_fields"] \
            == ["phone"]
        conn2.close()


class TestAuditAndCorpus:
    def test_match_audit_records_enforcement_decision(self):
        """The audit row carries the enforcement decision: rule, Ps,
        threshold, corroboration required/satisfied."""
        conn = duckdb.connect()
        _index_org(conn, _org("o5", name="Imaging Center",
                              line="100 Main St", phones=["2175550100"]))
        resource = _org("o6", name="Imaging Center", line="100 Main St",
                        phones=["2175550100"])
        index_entity(conn, "Organization", resource,
                     extract_organization_fields(resource))
        match_corpus(conn, "cr002-audit",
                     rules=ORGANIZATION_RULES,
                     entity_type="Organization")
        rows = conn.execute(
            "SELECT outcome, rule_id, evidence FROM match_audit "
            "WHERE run_id = 'cr002-audit' AND outcome = 'match' "
            "ORDER BY patient_id").fetchall()
        assert rows
        evidence = json.loads(rows[0][2])
        assert "thresholdEnforcement" in evidence
        enf = evidence["thresholdEnforcement"]
        assert enf["required"] is True
        assert enf["satisfied"] is True
        assert enf["rule_id"] == "O4"
        assert enf["threshold"] == 1e-8
        assert enf["firing_p"] > enf["threshold"]
        assert enf["combined_p"] <= enf["threshold"]
        assert enf["corroborating_fields"] == ["phone"]
        conn.close()

    def test_corpus_mode_refuses_over_budget_org_pair(self):
        """Corpus mode picks up the rule-set threshold: the name+addr-only
        org pair creates NO Linkage row under enforcement."""
        from fhir4ds.matching.linkage import load_linkage_resources
        conn = duckdb.connect()
        for rid in ("o5", "o6"):
            resource = _org(rid, name="Imaging Center", line="100 Main St")
            index_entity(conn, "Organization", resource,
                         extract_organization_fields(resource))
        report = match_corpus(conn, "cr002-corpus",
                              rules=ORGANIZATION_RULES,
                              entity_type="Organization")
        assert report.links_created == 0
        assert load_linkage_resources(conn) == []
        conn.close()

    def test_explicit_threshold_param_overrides(self):
        """``approval_threshold`` can be supplied explicitly (plain rule
        lists carry no threshold attribute) — here O3 (2e-9) is pushed over
        a 1e-10 budget and refused without corroboration."""
        conn = duckdb.connect()
        _index_org(conn, _org("o3", name="General Hospital",
                              tax="123456789"))
        result = match_fields(
            conn, extract_organization_fields(
                _org("o4", name="General Hospital", tax="123456789")),
            rules=list(ORGANIZATION_RULES),
            entity_type="Organization",
            approval_threshold=1e-10)
        assert result.outcome == "no_match"
        assert result.threshold_enforcement is not None
        assert result.threshold_enforcement["rule_id"] == "O3"
        conn.close()


class TestPatientByteCompatibility:
    def test_patient_results_carry_no_enforcement(self):
        """Patient path is untouched: no enforcement on the result, no
        thresholdEnforcement key in the audit evidence (the full patient
        suite is the byte-compat gate; this pins the surface explicitly)."""
        conn = duckdb.connect()
        base = {"resourceType": "Patient", "id": "pat-base",
                "name": [{"family": "Smith", "given": ["John"]}],
                "birthDate": "1990-01-01",
                "telecom": [{"system": "phone", "value": "2175550100"}]}
        index_patient(conn, base)
        result = match_patient(conn, {
            "resourceType": "Patient", "id": "pat-new",
            "name": [{"family": "Smith", "given": ["John"]}],
            "birthDate": "1990-01-01",
            "telecom": [{"system": "phone", "value": "2175550100"}]})
        assert result.outcome == "match"
        assert result.threshold_enforcement is None
        record_match_audit(conn, "cr002-patient", "pat-new", result)
        row = conn.execute(
            "SELECT evidence FROM match_audit WHERE run_id = "
            "'cr002-patient'").fetchone()
        evidence = json.loads(row[0])
        assert "thresholdEnforcement" not in evidence
        conn.close()
