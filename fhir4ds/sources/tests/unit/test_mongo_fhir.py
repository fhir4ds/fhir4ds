"""Unit tests for the Mongo-backed FHIR source adapter."""

from __future__ import annotations

import json

import duckdb
import pytest

from fhir4ds.sources import (
    MongoFhirServerSchema,
    MongoFhirServerSource,
    MongoResourceCollection,
)
from fhir4ds.sources.mongo_fhir import _redact_mongo_uri


def _make_con() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(":memory:", config={"allow_unsigned_extensions": True})


def _disable_extension_load(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        MongoFhirServerSource,
        "_load_mongo_extension",
        lambda self, con: None,
    )


class TestMongoFhirConstructor:
    def test_rejects_non_string_connection_string(self):
        with pytest.raises(TypeError, match="connection_string must be a string"):
            MongoFhirServerSource(None)  # type: ignore[arg-type]

    def test_rejects_empty_database_name(self):
        with pytest.raises(ValueError, match="database_name"):
            MongoFhirServerSchema(database_name="")

    def test_rejects_invalid_strategy(self):
        with pytest.raises(ValueError, match="collection_strategy"):
            MongoFhirServerSchema(collection_strategy="tables")  # type: ignore[arg-type]

    def test_rejects_non_string_strategy(self):
        with pytest.raises(TypeError, match="collection_strategy"):
            MongoFhirServerSchema(collection_strategy=["per_resource"])  # type: ignore[arg-type]

    def test_rejects_invalid_json_path(self):
        with pytest.raises(ValueError, match="resource_path"):
            MongoResourceCollection(
                resource_type="Patient",
                collection_name="Patient_4_0_0",
                resource_path="resource",
            )

    def test_shared_strategy_requires_collection_and_resource_types(self):
        src = MongoFhirServerSource(
            "mongodb://localhost:27017",
            schema=MongoFhirServerSchema(collection_strategy="shared"),
        )
        with pytest.raises(ValueError, match="shared_collection"):
            src._collection_specs()

    def test_rejects_invalid_shared_resource_type_path(self):
        with pytest.raises(ValueError, match="shared_resource_type_path"):
            MongoFhirServerSchema(shared_resource_type_path="resource.resourceType")

    def test_rejects_mutually_exclusive_collection_options(self):
        with pytest.raises(ValueError, match="mutually exclusive"):
            MongoFhirServerSchema(
                collection_strategy="explicit",
                collections=(
                    MongoResourceCollection(
                        resource_type="Patient",
                        collection_name="patients",
                    ),
                ),
                collection_mappings={"Patient": "patients"},
            )

    def test_rejects_strategy_incompatible_options(self):
        with pytest.raises(ValueError, match="per_resource"):
            MongoFhirServerSchema(
                collection_strategy="per_resource",
                resource_types=("Patient",),
                collection_mappings={"Patient": "patients"},
            )


class TestMongoFhirSqlGeneration:
    def test_per_resource_strategy_builds_helix_collection_names(self):
        src = MongoFhirServerSource(
            "mongodb://localhost:27017",
            schema=MongoFhirServerSchema(resource_types=("Patient", "Observation")),
        )

        specs = src._collection_specs()

        assert specs is not None
        assert [(s.resource_type, s.collection_name) for s in specs] == [
            ("Patient", "Patient_4_0_0"),
            ("Observation", "Observation_4_0_0"),
        ]

    def test_explicit_mapping_supports_wrapped_resource_documents(self):
        spec = MongoResourceCollection(
            resource_type="Observation",
            collection_name="current_observations",
            resource_path="$.resource",
            id_path="$.resource.id",
            resource_type_path="$.resource.resourceType",
            current_filter={"status": {"$ne": "deleted"}},
        )
        src = MongoFhirServerSource(
            "mongodb://localhost:27017",
            schema=MongoFhirServerSchema(
                collection_strategy="explicit",
                collections=(spec,),
            ),
        )

        sql = src._current_resources_select()
        filter_json = src._filter_json(spec)

        assert "current_observations" in sql
        assert "json_extract(to_json(src)::JSON, '$.resource')" in sql
        assert "json_extract_string(row_json, '$.resource.id')" in sql
        assert "json_extract_string(row_json, '$.resource.resourceType')" in sql
        parsed_filter = json.loads(filter_json)
        assert parsed_filter["$and"][0] == {"resource.resourceType": "Observation"}
        assert {"status": {"$ne": "deleted"}} in parsed_filter["$and"]

    def test_mongo_scan_literals_are_sql_escaped(self):
        spec = MongoResourceCollection(
            resource_type="Patient",
            collection_name="Patient_4_0_0'); DROP TABLE resources; --",
        )
        src = MongoFhirServerSource(
            "mongodb://user:pass@host/fhir'; DROP TABLE x; --",
            schema=MongoFhirServerSchema(
                database_name="fhir'; DROP SCHEMA main; --",
                collection_strategy="explicit",
                collections=(spec,),
            ),
        )

        sql = src._mongo_scan_expression(spec)

        assert "fhir''; DROP TABLE x; --" in sql
        assert "fhir'; DROP TABLE x; --" not in sql
        assert "fhir''; DROP SCHEMA main; --" in sql
        assert "Patient_4_0_0''); DROP TABLE resources; --" in sql

    def test_filter_json_composes_current_deleted_hidden_and_resource_type(self):
        spec = MongoResourceCollection(
            resource_type="Observation",
            collection_name="Observation_4_0_0",
            current_filter={"tenant": "blue"},
            deleted_filter={"deleted": True},
        )
        src = MongoFhirServerSource("mongodb://localhost:27017")

        parsed = json.loads(src._filter_json(spec))

        assert parsed == {
            "$and": [
                {"resourceType": "Observation"},
                {"tenant": "blue"},
                {"$nor": [{"deleted": True}]},
                {
                    "meta.tag": {
                        "$not": {
                            "$elemMatch": {
                                "code": "hidden",
                                "system": "https://fhir.icanbwell.com/4_0_0/CodeSystem/server-behavior",
                            }
                        }
                    }
                },
            ]
        }

    def test_include_hidden_removes_hidden_filter(self):
        spec = MongoResourceCollection(
            resource_type="Patient",
            collection_name="Patient_4_0_0",
        )
        src = MongoFhirServerSource(
            "mongodb://localhost:27017",
            schema=MongoFhirServerSchema(include_hidden=True),
        )

        parsed = json.loads(src._filter_json(spec))

        assert parsed == {"resourceType": "Patient"}

    def test_patient_scope_filters_patient_collection_by_id(self):
        spec = MongoResourceCollection(
            resource_type="Patient",
            collection_name="Patient_4_0_0",
        )
        src = MongoFhirServerSource(
            "mongodb://localhost:27017",
            schema=MongoFhirServerSchema(include_hidden=True),
        )

        src.set_patient_scope(["p2", "p1", "p1"])
        parsed = json.loads(src._filter_json(spec))

        assert parsed == {
            "$and": [
                {"resourceType": "Patient"},
                {"id": {"$in": ["p1", "p2"]}},
            ]
        }

    def test_patient_scope_filters_non_patient_collection_by_reference_paths(self):
        spec = MongoResourceCollection(
            resource_type="Observation",
            collection_name="Observation_4_0_0",
        )
        src = MongoFhirServerSource(
            "mongodb://localhost:27017",
            schema=MongoFhirServerSchema(include_hidden=True),
        )

        src.set_patient_scope(["pat.1", "pat-2"])
        parsed = json.loads(src._filter_json(spec))

        assert parsed["$and"][0] == {"resourceType": "Observation"}
        patient_filter = parsed["$and"][1]
        assert patient_filter["$or"][0] == {
            "subject.reference": {"$in": ["Patient/pat-2", "Patient/pat.1"]}
        }
        assert patient_filter["$or"][1] == {
            "subject.reference": {
                "$regex": r"^https?://.*/Patient/(?:pat\-2|pat\.1)$"
            }
        }
        assert {"patient.reference": {"$in": ["Patient/pat-2", "Patient/pat.1"]}} in patient_filter["$or"]
        assert {"beneficiary.reference": {"$in": ["Patient/pat-2", "Patient/pat.1"]}} in patient_filter["$or"]

    def test_patient_scope_uses_wrapped_resource_path_for_reference_filters(self):
        spec = MongoResourceCollection(
            resource_type="Observation",
            collection_name="resources_current",
            resource_path="$.payload.resource",
            resource_type_path="$.payload.resource.resourceType",
        )
        src = MongoFhirServerSource(
            "mongodb://localhost:27017",
            schema=MongoFhirServerSchema(include_hidden=True),
        )

        src.set_patient_scope(["p1"])
        parsed = json.loads(src._filter_json(spec))

        assert parsed["$and"][0] == {"payload.resource.resourceType": "Observation"}
        assert parsed["$and"][1]["$or"][0] == {
            "payload.resource.subject.reference": {"$in": ["Patient/p1"]}
        }

    def test_empty_patient_scope_matches_no_documents(self):
        spec = MongoResourceCollection(
            resource_type="Patient",
            collection_name="Patient_4_0_0",
        )
        src = MongoFhirServerSource(
            "mongodb://localhost:27017",
            schema=MongoFhirServerSchema(include_hidden=True),
        )

        src.set_patient_scope([])

        assert json.loads(src._filter_json(spec)) == {
            "$and": [{"resourceType": "Patient"}, {"_id": {"$in": []}}]
        }

    def test_rejects_invalid_patient_scope(self):
        src = MongoFhirServerSource("mongodb://localhost:27017")

        with pytest.raises(TypeError, match="patient_ids"):
            src.set_patient_scope("p1")  # type: ignore[arg-type]

    def test_shared_strategy_supports_wrapped_path_configuration(self):
        src = MongoFhirServerSource(
            "mongodb://localhost:27017",
            schema=MongoFhirServerSchema(
                collection_strategy="shared",
                shared_collection="resources_current",
                shared_resource_path="$.payload.resource",
                shared_id_path="$.payload.resource.id",
                shared_resource_type_path="$.payload.resource.resourceType",
                resource_types=("Patient", "Observation"),
            ),
        )

        specs = src._collection_specs()
        assert specs is not None
        assert [spec.resource_type for spec in specs] == ["Patient", "Observation"]
        assert {spec.collection_name for spec in specs} == {"resources_current"}
        assert {
            (spec.resource_path, spec.id_path, spec.resource_type_path)
            for spec in specs
        } == {
            (
                "$.payload.resource",
                "$.payload.resource.id",
                "$.payload.resource.resourceType",
            )
        }

        parsed_filter = json.loads(src._filter_json(specs[0]))
        assert parsed_filter["$and"][0] == {
            "payload.resource.resourceType": "Patient"
        }
        assert "payload.resource.meta.tag" in parsed_filter["$and"][1]

    def test_private_scrub_patch_removes_only_configured_fields(self):
        src = MongoFhirServerSource("mongodb://localhost:27017")

        expr = src._scrubbed_resource_expression("resource_json")

        assert "json_merge_patch(resource_json" in expr
        assert '"_id":null' in expr
        assert '"_uuid":null' in expr
        assert '"_sourceId":null' in expr
        assert '"_sourceAssigningAuthority":null' in expr


class TestMongoFhirViewProjection:
    def test_register_projects_standard_resources_view(self, monkeypatch):
        _disable_extension_load(monkeypatch)

        src = MongoFhirServerSource(
            "mongodb://localhost:27017",
            schema=MongoFhirServerSchema(resource_types=("Patient", "Observation")),
        )

        def fake_scan(self, spec):
            if spec.resource_type == "Patient":
                return """(
                    SELECT
                        'mongo-id' AS _id,
                        'Patient' AS resourceType,
                        'pat-1' AS id,
                        'secret' AS _uuid
                )"""
            return """(
                SELECT
                    'Observation' AS resourceType,
                    'obs-1' AS id,
                    struct_pack(reference := 'Patient/pat-1') AS subject
            )"""

        monkeypatch.setattr(MongoFhirServerSource, "_mongo_scan_expression", fake_scan)
        con = _make_con()

        src.register(con)
        src.register(con)

        rows = con.execute("""
            SELECT
                id,
                resourceType,
                patient_ref,
                json_extract_string(resource, '$._id') AS private_id,
                json_extract_string(resource, '$._uuid') AS private_uuid
            FROM resources
            ORDER BY id
        """).fetchall()
        assert rows == [
            ("obs-1", "Observation", "pat-1", None, None),
            ("pat-1", "Patient", "pat-1", None, None),
        ]

        src.unregister(con)
        with pytest.raises(duckdb.CatalogException):
            con.execute("SELECT * FROM resources").fetchall()

    def test_unregister_before_register_is_safe(self):
        con = _make_con()
        src = MongoFhirServerSource("mongodb://localhost:27017")

        src.unregister(con)

        with pytest.raises(duckdb.CatalogException):
            con.execute("SELECT * FROM resources").fetchall()

    def test_supports_incremental_is_false(self):
        src = MongoFhirServerSource("mongodb://localhost:27017")

        assert src.supports_incremental() is False

    def test_absolute_patient_reference_is_normalized(self, monkeypatch):
        _disable_extension_load(monkeypatch)
        src = MongoFhirServerSource(
            "mongodb://localhost:27017",
            schema=MongoFhirServerSchema(resource_types=("Observation",)),
        )

        monkeypatch.setattr(
            MongoFhirServerSource,
            "_mongo_scan_expression",
            lambda self, spec: """(
                SELECT
                    'Observation' AS resourceType,
                    'obs-1' AS id,
                    struct_pack(reference := 'https://example.org/fhir/Patient/pat-abs') AS subject
            )""",
        )
        con = _make_con()

        src.register(con)

        assert con.execute("SELECT patient_ref FROM resources").fetchone() == ("pat-abs",)

    def test_non_patient_reference_does_not_normalize(self, monkeypatch):
        _disable_extension_load(monkeypatch)
        src = MongoFhirServerSource(
            "mongodb://localhost:27017",
            schema=MongoFhirServerSchema(resource_types=("Observation",)),
        )

        monkeypatch.setattr(
            MongoFhirServerSource,
            "_mongo_scan_expression",
            lambda self, spec: """(
                SELECT
                    'Observation' AS resourceType,
                    'obs-1' AS id,
                    struct_pack(reference := 'Group/group-1') AS subject
            )""",
        )
        con = _make_con()

        src.register(con)

        assert con.execute("SELECT patient_ref FROM resources").fetchone() == (None,)

    def test_wrapped_resource_layout_projects_resource_json(self, monkeypatch):
        _disable_extension_load(monkeypatch)
        src = MongoFhirServerSource(
            "mongodb://localhost:27017",
            schema=MongoFhirServerSchema(
                collection_strategy="explicit",
                collections=(
                    MongoResourceCollection(
                        resource_type="Observation",
                        collection_name="wrapped_observations",
                        resource_path="$.resource",
                        id_path="$.resource.id",
                        resource_type_path="$.resource.resourceType",
                    ),
                ),
            ),
        )
        monkeypatch.setattr(
            MongoFhirServerSource,
            "_mongo_scan_expression",
            lambda self, spec: """(
                SELECT
                    struct_pack(
                        resourceType := 'Observation',
                        id := 'obs-wrap',
                        subject := struct_pack(reference := 'Patient/pat-wrap')
                    ) AS resource,
                    'outside' AS id
            )""",
        )
        con = _make_con()

        src.register(con)

        row = con.execute("""
            SELECT id, resourceType, patient_ref, json_extract_string(resource, '$.id')
            FROM resources
        """).fetchone()
        assert row == ("obs-wrap", "Observation", "pat-wrap", "obs-wrap")


class TestMongoFhirErrors:
    def test_redacts_credentials_from_uri(self):
        redacted = _redact_mongo_uri(
            "mongodb://user:pass@host:27017/fhir?authMechanismProperties=AWS_SESSION_TOKEN:secret&tlsCertificateKeyFilePassword=topsecret"
        )

        assert "user" not in redacted
        assert "pass" not in redacted
        assert "secret" not in redacted
        assert "***:***@host:27017" in redacted

    def test_extension_errors_do_not_leak_raw_credentials(self):
        class FakeCon:
            def execute(self, sql):
                raise RuntimeError("extension failed")

        src = MongoFhirServerSource(
            "mongodb://user:pass@host:27017/fhir?tlsCertificateKeyFilePassword=topsecret"
        )

        with pytest.raises(Exception) as excinfo:
            src.register(FakeCon())

        message = str(excinfo.value)
        assert "user:pass" not in message
        assert "topsecret" not in message
        assert "***:***@host:27017" in message

    def test_missing_collection_configuration_raises_actionable_error(self, monkeypatch):
        _disable_extension_load(monkeypatch)

        class FakeCon:
            def execute(self, sql):
                raise RuntimeError("attach failed")

        src = MongoFhirServerSource("mongodb://user:pass@host:27017")

        with pytest.raises(Exception, match="resource_types, collections, or collection_mappings"):
            src.register(FakeCon())
