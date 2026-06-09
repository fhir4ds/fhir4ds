#!/usr/bin/env python3
"""Smoke test MongoFhirServerSource against a Mongo-backed FHIR fixture."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import fhir4ds
from fhir4ds.sources import (
    MongoFhirServerSchema,
    MongoFhirServerSource,
    MongoResourceCollection,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--uri",
        default=os.environ.get("FHIR4DS_MONGO_URI", "mongodb://localhost:27017"),
        help="MongoDB URI. Defaults to FHIR4DS_MONGO_URI or localhost.",
    )
    parser.add_argument(
        "--database",
        default=os.environ.get("FHIR4DS_MONGO_DATABASE", "fhir"),
        help="Mongo database name. Defaults to FHIR4DS_MONGO_DATABASE or fhir.",
    )
    parser.add_argument("--base-version", default="4_0_0")
    parser.add_argument(
        "--strategy",
        choices=["per_resource", "explicit", "shared"],
        default="per_resource",
        help="Mongo collection layout to test.",
    )
    parser.add_argument(
        "--resource-type",
        action="append",
        default=None,
        help="FHIR resource type to mount. May be repeated. Defaults to Patient and Observation.",
    )
    parser.add_argument(
        "--collection-map",
        action="append",
        default=None,
        metavar="RESOURCE=COLLECTION",
        help="Explicit strategy mapping. May be repeated.",
    )
    parser.add_argument(
        "--shared-collection",
        default=None,
        help="Shared collection name for --strategy shared.",
    )
    parser.add_argument("--resource-path", default="$")
    parser.add_argument("--id-path", default="$.id")
    parser.add_argument("--resource-type-path", default="$.resourceType")
    parser.add_argument("--include-hidden", action="store_true")
    parser.add_argument(
        "--expect-patient-id",
        default="fhir4ds-mongo-patient",
        help="Patient fixture ID that must be visible in resources.",
    )
    parser.add_argument(
        "--expect-observation-id",
        default="fhir4ds-mongo-observation",
        help="Observation fixture ID that must be visible in resources.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable smoke summary JSON.",
    )
    args = parser.parse_args()

    resource_types = tuple(args.resource_type or ["Patient", "Observation"])
    schema = _build_schema(args, resource_types)
    source = MongoFhirServerSource(args.uri, schema=schema)
    con = fhir4ds.create_connection(source=source)

    counts = con.execute("""
        SELECT resourceType, COUNT(*)::INTEGER AS resource_count
        FROM resources
        GROUP BY resourceType
        ORDER BY resourceType
    """).fetchall()
    fixture_rows = con.execute(
        """
        SELECT
            id,
            resourceType,
            patient_ref,
            fhirpath_text(resource, 'id') AS fhirpath_id
        FROM resources
        WHERE id IN (?, ?)
        ORDER BY id
        """,
        [args.expect_patient_id, args.expect_observation_id],
    ).fetchall()

    by_id = {row[0]: row for row in fixture_rows}
    missing = [
        expected_id
        for expected_id in [args.expect_patient_id, args.expect_observation_id]
        if expected_id not in by_id
    ]
    if missing:
        raise RuntimeError(
            "MongoFhirServerSource smoke did not find expected fixture id(s): "
            + ", ".join(missing)
        )

    patient = by_id[args.expect_patient_id]
    observation = by_id[args.expect_observation_id]
    if patient[2] != args.expect_patient_id:
        raise RuntimeError(
            f"Expected Patient patient_ref {args.expect_patient_id!r}, got {patient[2]!r}"
        )
    if observation[2] != args.expect_patient_id:
        raise RuntimeError(
            "Expected Observation patient_ref "
            f"{args.expect_patient_id!r}, got {observation[2]!r}"
        )
    for row in fixture_rows:
        if row[3] != row[0]:
            raise RuntimeError(
                f"FHIRPath id extraction mismatch for {row[0]!r}: {row[3]!r}"
            )

    summary = {
        "database": args.database,
        "strategy": args.strategy,
        "counts": [{"resourceType": rt, "count": count} for rt, count in counts],
        "fixture_rows": [
            {
                "id": row[0],
                "resourceType": row[1],
                "patient_ref": row[2],
                "fhirpath_id": row[3],
            }
            for row in fixture_rows
        ],
    }
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print("MongoFhirServerSource smoke passed")
        print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _build_schema(
    args: argparse.Namespace,
    resource_types: tuple[str, ...],
) -> MongoFhirServerSchema:
    if args.strategy == "per_resource":
        return MongoFhirServerSchema(
            database_name=args.database,
            base_version=args.base_version,
            collection_strategy="per_resource",
            resource_types=resource_types,
            include_hidden=args.include_hidden,
        )

    if args.strategy == "explicit":
        mappings = _parse_collection_maps(args.collection_map)
        collections = tuple(
            MongoResourceCollection(
                resource_type=resource_type,
                collection_name=mappings[resource_type],
                resource_path=args.resource_path,
                id_path=args.id_path,
                resource_type_path=args.resource_type_path,
            )
            for resource_type in resource_types
        )
        return MongoFhirServerSchema(
            database_name=args.database,
            collection_strategy="explicit",
            collections=collections,
            include_hidden=args.include_hidden,
        )

    if args.shared_collection is None:
        raise RuntimeError("--strategy shared requires --shared-collection")
    return MongoFhirServerSchema(
        database_name=args.database,
        collection_strategy="shared",
        shared_collection=args.shared_collection,
        shared_resource_path=args.resource_path,
        shared_id_path=args.id_path,
        shared_resource_type_path=args.resource_type_path,
        resource_types=resource_types,
        include_hidden=args.include_hidden,
    )


def _parse_collection_maps(values: list[str] | None) -> dict[str, str]:
    if not values:
        raise RuntimeError("--strategy explicit requires at least one --collection-map")
    mappings: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise RuntimeError(
                f"Invalid --collection-map {value!r}; expected RESOURCE=COLLECTION"
            )
        resource_type, collection_name = value.split("=", 1)
        resource_type = resource_type.strip()
        collection_name = collection_name.strip()
        if not resource_type or not collection_name:
            raise RuntimeError(
                f"Invalid --collection-map {value!r}; both sides must be non-empty"
            )
        mappings[resource_type] = collection_name
    return mappings


if __name__ == "__main__":
    raise SystemExit(main())
