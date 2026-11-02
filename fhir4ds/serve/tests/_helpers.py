"""Small helpers shared by the serve tests (no fixtures live here)."""

from __future__ import annotations

import base64
import json
import pathlib

from fhir4ds.serve.config import ServeConfig

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
LIBRARY_FIXTURES = FIXTURES / "libraries"
VIEWDEFINITION_FIXTURES = FIXTURES / "viewdefinitions"
RESOURCE_BUNDLE = FIXTURES / "resources" / "bundle.json"

SQLQUERY_PROFILE = "https://sql-on-fhir.org/ig/StructureDefinition/SQLQuery"


def serve_config(tmp_path, **overrides) -> ServeConfig:
    """A :class:`~fhir4ds.serve.config.ServeConfig` for tests.

    Every test gets a throwaway publish directory and no background flush
    thread, so runs never write into the repository and never race the
    publication tick. Tests that want a flush call ``/admin/flush``.
    """
    overrides.setdefault("publish_dir", str(tmp_path / "publish"))
    overrides.setdefault("flush_autostart", False)
    return ServeConfig(**overrides)


def view_fixture(name: str) -> dict:
    """Load one ViewDefinition fixture by its file stem (e.g. ``patient-view``)."""
    return json.loads((VIEWDEFINITION_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def library_fixture(name: str) -> dict:
    """Load one Library fixture by its file stem (e.g. ``Library-SqlOnFhirExample``)."""
    return json.loads((LIBRARY_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def load_json_directory(directory: pathlib.Path) -> list[dict]:
    """Load every JSON file in a fixture directory, sorted by name."""
    return [
        json.loads(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("*.json"))
    ]


def parameters(*entries: dict) -> dict:
    """Build a FHIR ``Parameters`` request body."""
    return {"resourceType": "Parameters", "parameter": list(entries)}


def parameters_resource(*entries: dict) -> dict:
    """Build a nested FHIR ``Parameters`` resource (the ``parameters`` parameter)."""
    return {"resourceType": "Parameters", "parameter": list(entries)}


def b64(text: str) -> str:
    """Base64-encode a SQL body for ``content[].data``."""
    return base64.b64encode(text.encode()).decode("ascii")


def sqlquery_library(
    library_id: str,
    sql: str,
    *,
    parameters_declared: tuple[tuple[str, str], ...] = (),
    related_artifact: tuple[tuple[str, str], ...] = (),
) -> dict:
    """Build a minimal SQLQuery Library resource from SQL text."""
    library: dict = {
        "resourceType": "Library",
        "id": library_id,
        "status": "active",
        "meta": {"profile": [SQLQUERY_PROFILE]},
        "type": {"coding": [{"code": "sql-query"}]},
        "content": [{"contentType": "application/sql", "data": b64(sql)}],
    }
    if parameters_declared:
        library["parameter"] = [
            {"name": name, "type": type_, "use": "in"} for name, type_ in parameters_declared
        ]
    if related_artifact:
        library["relatedArtifact"] = [
            {"type": "depends-on", "label": label, "resource": canonical}
            for label, canonical in related_artifact
        ]
    return library


def library_with_dependency(canonical: str) -> dict:
    """A SQLQuery whose only dependency points at ``canonical``."""
    return sqlquery_library(
        "dangling",
        "SELECT count(*) AS n FROM patient_view",
        related_artifact=(("patient_view", canonical),),
    )


#: Parameters of the IG's SqlOnFhirExample Library (verbatim fixture).
SQLONFHIR_PARAMETERS: tuple[tuple[str, str], ...] = (
    ("patient_id", "Patient/pt-1"),
    ("from_date", "2024-01-01"),
    ("to_date", "2024-12-31"),
)


def parameter_body(values: dict[str, str]) -> dict:
    """Wrap ``name -> string value`` pairs as a ``parameters`` request body."""
    return parameters(
        {
            "name": "parameters",
            "resource": parameters_resource(
                *[{"name": name, "valueString": value} for name, value in values.items()]
            ),
        }
    )


#: Shared API keys for tests (the guard is fail-closed without them).
TEST_ADMIN_KEY = "test-admin-key-0123456789"
TEST_WRITE_KEY = "test-write-key-0123456789"

TEST_KEY_HEADERS = {
    "X-Admin-Key": TEST_ADMIN_KEY,
    "X-Write-Key": TEST_WRITE_KEY,
}


def keyed_client(app):
    """A TestClient whose requests carry the shared test keys."""
    from fastapi.testclient import TestClient

    client = TestClient(app)
    client.headers.update(TEST_KEY_HEADERS)
    return client
