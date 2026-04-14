"""
Tests for the SystemResolver OID ↔ URL normalization.
"""

import pytest
from fhir4ds.cql.duckdb.udf.system_resolver import SystemResolver


class TestSystemResolver:
    """Test OID → URL normalization."""

    def test_snomed_oid_to_url(self):
        assert SystemResolver.normalize("urn:oid:2.16.840.1.113883.6.96") == "http://snomed.info/sct"

    def test_loinc_oid_to_url(self):
        assert SystemResolver.normalize("urn:oid:2.16.840.1.113883.6.1") == "http://loinc.org"

    def test_rxnorm_oid_to_url(self):
        assert SystemResolver.normalize("urn:oid:2.16.840.1.113883.6.88") == "http://www.nlm.nih.gov/research/umls/rxnorm"

    def test_icd10cm_oid_to_url(self):
        assert SystemResolver.normalize("urn:oid:2.16.840.1.113883.6.90") == "http://hl7.org/fhir/sid/icd-10-cm"

    def test_cpt_oid_to_url(self):
        assert SystemResolver.normalize("urn:oid:2.16.840.1.113883.6.12") == "http://www.ama-assn.org/go/cpt"

    def test_cvx_oid_to_url(self):
        assert SystemResolver.normalize("urn:oid:2.16.840.1.113883.12.292") == "http://hl7.org/fhir/sid/cvx"

    def test_ndc_oid_to_url(self):
        assert SystemResolver.normalize("urn:oid:2.16.840.1.113883.6.69") == "http://hl7.org/fhir/sid/ndc"


class TestSNOMEDNormalization:
    """Test SNOMED module-specific URL normalization."""

    def test_snomed_base_url_unchanged(self):
        assert SystemResolver.normalize("http://snomed.info/sct") == "http://snomed.info/sct"

    def test_snomed_us_module_normalized(self):
        assert SystemResolver.normalize("http://snomed.info/sct/731000124108") == "http://snomed.info/sct"

    def test_snomed_versioned_module_normalized(self):
        assert SystemResolver.normalize("http://snomed.info/sct/731000124108/version/20240301") == "http://snomed.info/sct"

    def test_snomed_international_module_normalized(self):
        assert SystemResolver.normalize("http://snomed.info/sct/900000000000207008") == "http://snomed.info/sct"


class TestPassthrough:
    """Test that already-canonical URLs and unknown systems pass through."""

    def test_canonical_url_passthrough(self):
        assert SystemResolver.normalize("http://loinc.org") == "http://loinc.org"

    def test_unknown_url_passthrough(self):
        url = "http://example.com/CodeSystem/custom"
        assert SystemResolver.normalize(url) == url

    def test_unknown_oid_passthrough(self):
        oid = "urn:oid:1.2.3.4.5.6.7.8.9"
        assert SystemResolver.normalize(oid) == oid

    def test_none_returns_none(self):
        assert SystemResolver.normalize(None) is None

    def test_empty_string_passthrough(self):
        assert SystemResolver.normalize("") == ""


class TestReverseMapping:
    """Test URL → OID reverse lookup."""

    def test_snomed_url_to_oid(self):
        assert SystemResolver.to_oid("http://snomed.info/sct") == "urn:oid:2.16.840.1.113883.6.96"

    def test_loinc_url_to_oid(self):
        assert SystemResolver.to_oid("http://loinc.org") == "urn:oid:2.16.840.1.113883.6.1"

    def test_unknown_url_passthrough(self):
        url = "http://example.com/CodeSystem/custom"
        assert SystemResolver.to_oid(url) == url

    def test_none_returns_none(self):
        assert SystemResolver.to_oid(None) is None
