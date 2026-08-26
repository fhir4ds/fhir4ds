"""SOF-SQ-01 spec-compliance regression tests.

Anchored to the machine-readable sql-on-fhir-v2 Analytics Layer artifacts
(input/fsh/profiles/library-profiles.fsh, terminology.fsh, models.fsh on the
upstream branch carrying the SQLView profile; IG canonical
http://hl7.org/fhir/uv/sql-on-fhir per sushi-config.yaml).
"""

import base64

import pytest

from .. import (
    parse_library,
    SQLContent,
    SQLQuery,
    SQLView,
    SQLQueryParseError,
    SQLQUERY_PROFILE_CANONICAL,
    SQLVIEW_PROFILE_CANONICAL,
    SQLQUERY_PROFILE_CANONICALS,
    SQLVIEW_PROFILE_CANONICALS,
)

OFFICIAL_Q = "http://hl7.org/fhir/uv/sql-on-fhir/StructureDefinition/SQLQuery"
OFFICIAL_V = "http://hl7.org/fhir/uv/sql-on-fhir/StructureDefinition/SQLView"


def _lib(profile, type_code, sql="SELECT 1 AS x", **extra):
    d = {
        "resourceType": "Library",
        "id": "t",
        "meta": {"profile": [profile]},
        "status": "active",
        "type": {"coding": [{"code": type_code}]},
        "content": [
            {"contentType": "application/sql", "data": base64.b64encode(sql.encode()).decode()}
        ],
    }
    d.update(extra)
    return d


class TestProfileCanonicalRecognition:
    """QA-001: every published canonical form is recognized."""

    @pytest.mark.parametrize("canonical", sorted(SQLQUERY_PROFILE_CANONICALS))
    def test_sqlquery_canonical_forms_accepted(self, canonical):
        assert isinstance(parse_library(_lib(canonical, "sql-query")), SQLQuery)

    @pytest.mark.parametrize("canonical", sorted(SQLVIEW_PROFILE_CANONICALS))
    def test_sqlview_canonical_forms_accepted(self, canonical):
        assert isinstance(parse_library(_lib(canonical, "sql-view")), SQLView)

    def test_version_pinned_official_canonical_accepted(self):
        assert isinstance(
            parse_library(_lib(OFFICIAL_Q + "|1.0.0", "sql-query")), SQLQuery
        )

    def test_legacy_canonicals_still_recognized(self):
        assert isinstance(parse_library(_lib(SQLQUERY_PROFILE_CANONICAL, "sql-query")), SQLQuery)
        assert isinstance(parse_library(_lib(SQLVIEW_PROFILE_CANONICAL, "sql-view")), SQLView)

    def test_ambiguous_both_profiles_rejected(self):
        with pytest.raises(SQLQueryParseError, match="both"):
            parse_library(_lib(OFFICIAL_Q, "sql-query", meta={"profile": [OFFICIAL_Q, OFFICIAL_V]}))

    def test_missing_profile_rejected(self):
        lib = _lib(OFFICIAL_Q, "sql-query")
        del lib["meta"]
        with pytest.raises(SQLQueryParseError, match="profile"):
            parse_library(lib)


class TestLibraryTypeCoding:
    """QA-002: SQLQuery fixes type=sql-query; SQLView fixes type=sql-view."""

    def test_sqlview_requires_sql_view_code(self):
        with pytest.raises(SQLQueryParseError, match="sql-view"):
            parse_library(_lib(SQLVIEW_PROFILE_CANONICAL, "sql-query"))

    def test_sqlquery_rejects_sql_view_code(self):
        with pytest.raises(SQLQueryParseError, match="sql-query"):
            parse_library(_lib(SQLQUERY_PROFILE_CANONICAL, "sql-view"))


class TestStrictBase64:
    """QA-003: content.data must be strict base64."""

    def test_non_base64_garbage_rejected(self):
        with pytest.raises(SQLQueryParseError, match="base64"):
            parse_library(
                _lib(SQLQUERY_PROFILE_CANONICAL, "sql-query", content=[
                    {"contentType": "application/sql", "data": "%%%%"}
                ])
            )

    def test_base64_with_embedded_whitespace_rejected(self):
        good = base64.b64encode(b"SELECT 1").decode()
        with pytest.raises(SQLQueryParseError, match="base64"):
            parse_library(
                _lib(SQLQUERY_PROFILE_CANONICAL, "sql-query", content=[
                    {"contentType": "application/sql", "data": good[:4] + " " + good[4:]}
                ])
            )

    def test_non_utf8_payload_rejected(self):
        with pytest.raises(SQLQueryParseError, match="utf-8"):
            parse_library(
                _lib(SQLQUERY_PROFILE_CANONICAL, "sql-query", content=[
                    {"contentType": "application/sql",
                     "data": base64.b64encode(b"\xff\xfe\x00").decode()}
                ])
            )


class TestParameterUseCardinality:
    """QA-004: parameter.use is 1..1 — missing use must be rejected."""

    def test_missing_use_rejected(self):
        with pytest.raises(SQLQueryParseError, match="use"):
            parse_library(_lib(
                SQLQUERY_PROFILE_CANONICAL, "sql-query",
                parameter=[{"name": "p", "type": "string"}],
            ))

    def test_wrong_use_rejected(self):
        with pytest.raises(SQLQueryParseError, match="use"):
            parse_library(_lib(
                SQLQUERY_PROFILE_CANONICAL, "sql-query",
                parameter=[{"name": "p", "type": "string", "use": "out"}],
            ))


class TestSqlNameInvariant:
    """QA-005: label obeys sql-name ^[A-Za-z][A-Za-z0-9_]*$ (ASCII)."""

    @pytest.mark.parametrize("label", ["_leads_with_underscore", "1starts_digit", "éfoo", "has-dash", "has space"])
    def test_invalid_labels_rejected(self, label):
        from .. import SQLQueryValidationError
        with pytest.raises((SQLQueryParseError, SQLQueryValidationError), match="sql-name|label"):
            parse_library(_lib(
                SQLQUERY_PROFILE_CANONICAL, "sql-query",
                relatedArtifact=[{"type": "depends-on", "label": label, "resource": "http://x/VD/1"}],
            ))

    def test_valid_labels_accepted(self):
        lib = _lib(
            SQLQUERY_PROFILE_CANONICAL, "sql-query",
            relatedArtifact=[{"type": "depends-on", "label": "pt_1", "resource": "http://x/VD/1"}],
        )
        result = parse_library(lib)
        assert result.related_artifact[0].label == "pt_1"


class TestToDictRoundtrip:
    """QA-006: extra_fields survive parse_library → to_dict roundtrip."""

    def test_roundtrip_preserves_extra_fields(self):
        lib = _lib(
            SQLQUERY_PROFILE_CANONICAL, "sql-query",
            customExtension={"url": "http://example.org/x", "valueString": "keep"},
        )
        parsed = parse_library(lib)
        out = parsed.to_dict()
        assert out["customExtension"] == {"url": "http://example.org/x", "valueString": "keep"}
        assert out["content"][0]["data"] == lib["content"][0]["data"]
        # Roundtripped dict re-parses to an equal-typed library
        reparsed = parse_library(out)
        assert isinstance(reparsed, SQLQuery)
        assert reparsed.content[0].data == parsed.content[0].data
        assert reparsed.extra_fields == parsed.extra_fields

    def test_roundtrip_sqlview_with_related_and_content(self):
        lib = _lib(
            OFFICIAL_V, "sql-view",
            url="https://example.org/SQLView/V1",
            relatedArtifact=[{"type": "depends-on", "label": "src", "resource": "http://x/VD/1"}],
        )
        parsed = parse_library(lib)
        out = parsed.to_dict()
        reparsed = parse_library(out)
        assert isinstance(reparsed, SQLView)
        assert reparsed.related_artifact[0].label == "src"


class TestRoundtripFullFidelity:
    """QA-001: to_dict loses no Library data on the parse -> serialize
    roundtrip, including known-but-unmodeled FHIR fields and per-entry
    extras (content.extension/sqlText, relatedArtifact.display,
    parameter.documentation)."""

    FULL = {
        "resourceType": "Library",
        "id": "ex",
        "meta": {
            "profile": [OFFICIAL_Q + "|2.0.0"],
            "versionId": "5",
            "tag": [{"code": "t"}],
        },
        "url": "http://x/Lib",
        "name": "Ex",
        "version": "1",
        "title": "T",
        "status": "active",
        "type": {
            "coding": [{"system": "http://hl7.org/fhir/uv/sql-on-fhir/CodeSystem/LibraryTypesCodes",
                        "code": "sql-query", "display": "SQL Query Definition"}],
            "text": "sql",
        },
        "description": "keep me",
        "publisher": "HL7",
        "experimental": False,
        "date": "2026-01-01",
        "purpose": "p",
        "usage": "u",
        "copyright": "c",
        "language": "en",
        "identifier": [{"value": "i"}],
        "contact": [{"name": "n"}],
        "useContext": [{"code": {"text": "a"}, "valueCodeableConcept": {"text": "b"}}],
        "jurisdiction": [{"text": "US"}],
        "extension": [{"url": "http://x/ext", "valueString": "v"}],
        "unknownCustom": {"a": 1},
        "content": [{
            "contentType": "application/sql;dialect=duckdb",
            "data": base64.b64encode(b"SELECT 1").decode(),
            "extension": [{"url": "http://hl7.org/fhir/uv/sql-on-fhir/StructureDefinition/sql-text",
                           "valueString": "SELECT 1"}],
        }],
        "relatedArtifact": [{"type": "depends-on", "label": "v1",
                             "resource": "http://x/VD", "display": "d"}],
        "parameter": [{"name": "city", "type": "string", "use": "in",
                       "documentation": "doc", "min": 1, "max": "1"}],
    }

    def test_roundtrip_preserves_all_fields(self):
        q = parse_library(dict(self.FULL))
        out = q.to_dict()
        for key, value in self.FULL.items():
            if key == "content":
                for ck, cv in self.FULL["content"][0].items():
                    assert out["content"][0][ck] == cv
            else:
                assert out.get(key) == value, f"roundtrip lost {key}"

    def test_roundtrip_declared_canonical_not_rewritten(self):
        """QA-002: the official declared profile canonical survives verbatim."""
        q = parse_library(dict(self.FULL))
        assert q.to_dict()["meta"]["profile"] == [OFFICIAL_Q + "|2.0.0"]

    def test_to_dict_appends_profile_when_absent(self):
        # Direct construction (no source meta): to_dict must declare the
        # dataclass's profile canonical so the output re-parses.
        q = SQLQuery(status="active", content=[
            SQLContent(content_type="application/sql", data="SELECT 1")
        ])
        out = q.to_dict()
        assert out["meta"]["profile"] == [SQLQUERY_PROFILE_CANONICAL]
        assert isinstance(parse_library(out), SQLQuery)


class TestStatusRequired:
    """QA-004: Library.status is 1..1 on the base Library resource."""

    def test_missing_status_rejected(self):
        lib = _lib(OFFICIAL_Q, "sql-query")
        del lib["status"]
        with pytest.raises(SQLQueryParseError, match="status"):
            parse_library(lib)

    def test_empty_status_rejected(self):
        with pytest.raises(SQLQueryParseError, match="status"):
            parse_library(_lib(OFFICIAL_Q, "sql-query", status=""))


class TestParameterTypeIsFhirPrimitive:
    """QA-003: parameter.type must be a FHIR primitive (required binding)."""

    def test_non_fhir_type_rejected_at_parse(self):
        with pytest.raises(SQLQueryParseError, match="FHIR primitive"):
            parse_library(_lib(OFFICIAL_Q, "sql-query",
                               parameter=[{"name": "p", "type": "not-a-fhir-type", "use": "in"}]))

    def test_complex_type_rejected_at_parse(self):
        with pytest.raises(SQLQueryParseError, match="FHIR primitive"):
            parse_library(_lib(OFFICIAL_Q, "sql-query",
                               parameter=[{"name": "p", "type": "CodeableConcept", "use": "in"}]))

    @pytest.mark.parametrize("ptype", ["string", "integer", "boolean", "decimal", "dateTime"])
    def test_valid_primitives_accepted(self, ptype):
        q = parse_library(_lib(OFFICIAL_Q, "sql-query",
                               parameter=[{"name": "p", "type": ptype, "use": "in"}]))
        assert q.parameter[0].type == ptype


class TestTypeCodingSystem:
    """QA-005: type is fixed to LibraryTypesCodes; a foreign code system
    carrying the same code must not satisfy the fixed type."""

    def test_foreign_system_rejected(self):
        lib = _lib(OFFICIAL_Q, "sql-query")
        lib["type"] = {"coding": [{"system": "http://example.org/cs", "code": "sql-query"}]}
        with pytest.raises(SQLQueryParseError, match="LibraryTypesCodes"):
            parse_library(lib)

    def test_official_system_accepted(self):
        lib = _lib(OFFICIAL_Q, "sql-query")
        lib["type"] = {"coding": [{
            "system": "http://hl7.org/fhir/uv/sql-on-fhir/CodeSystem/LibraryTypesCodes",
            "code": "sql-query",
        }]}
        assert isinstance(parse_library(lib), SQLQuery)

    def test_absent_system_still_accepted(self):
        assert isinstance(parse_library(_lib(OFFICIAL_Q, "sql-query")), SQLQuery)
