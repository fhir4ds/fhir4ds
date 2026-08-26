"""FP-20 regression tests: §10/§12 uri-family field type reflection parity.

Pins (native C++ extension vs Python fallback parity), per R4:
- Meta.profile is `canonical` (canonical is a uri subtype), NOT `uri`.
- Meta.source is `uri`.
- Identifier.system / Telecom.system suffix typing stays `uri`.

FP-20 HISTORIAN QA-001 (2026-08-18): the native fhirFieldType chain
(evaluator.cpp) hardcoded profile -> "uri" and omitted source, while the
Python fallback suffix table (models/r4/fhir_path_to_type.json) lacked both
entries — a native-vs-fallback parity divergence and a spec typing error.
"""

from __future__ import annotations

import json

import duckdb

from fhir4ds.fhirpath.duckdb import register_fhirpath

RESOURCE = json.dumps(
    {
        "resourceType": "Patient",
        "id": "p1",
        "active": True,
        "gender": "male",
        "meta": {
            "source": "http://example.org/source",
            "profile": ["http://hl7.org/fhir/StructureDefinition/x"],
        },
        "identifier": [{"system": "http://acme.org/mrn", "value": "m1"}],
        "telecom": [{"system": "phone", "value": "555"}],
    }
)


def _native() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    if not register_fhirpath(con):
        raise RuntimeError("native fhirpath extension did not load")
    return con


def _fallback() -> duckdb.DuckDBPyConnection:
    old = duckdb.__version__
    duckdb.__version__ = "0.0.0-forced-python-fallback"
    try:
        con = duckdb.connect(config={"allow_unsigned_extensions": True})
        loaded = register_fhirpath(con)
    finally:
        duckdb.__version__ = old
    if loaded:
        raise RuntimeError("fallback forcing failed")
    return con


def _text(con: duckdb.DuckDBPyConnection, expr: str) -> str | None:
    return con.execute(
        "SELECT fhirpath_text(?::JSON, ?)", [RESOURCE, expr]
    ).fetchone()[0]


def test_meta_profile_type_is_canonical_fp20():
    for con in (_native(), _fallback()):
        try:
            assert _text(con, "meta.profile.type().name") == "canonical"
            assert _text(con, "meta.profile.first() is FHIR.canonical") == "true"
        finally:
            con.close()


def test_meta_profile_canonical_is_uri_subtype_fp20():
    # canonical <: uri <: string per R4 / type2Parent metadata.
    for con in (_native(), _fallback()):
        try:
            assert _text(con, "meta.profile.first() is FHIR.uri") == "true"
            assert _text(con, "meta.profile.first() is FHIR.string") == "true"
        finally:
            con.close()


def test_meta_source_type_is_uri_fp20():
    for con in (_native(), _fallback()):
        try:
            assert _text(con, "meta.source.type().name") == "uri"
            assert _text(con, "meta.source is FHIR.uri") == "true"
        finally:
            con.close()


def test_uri_family_field_typing_parity_fp20():
    exprs = [
        "meta.profile.type().name",
        "meta.source.type().name",
        "meta.profile.first() is FHIR.canonical",
        "meta.profile.first() is FHIR.uri",
        "meta.source is FHIR.uri",
        "identifier.system.type().name",
        "telecom.system.type().name",
        "gender.type().name",
        "id.type().name",
    ]
    native, fallback = _native(), _fallback()
    try:
        for expr in exprs:
            assert _text(native, expr) == _text(fallback, expr), expr
    finally:
        native.close()
        fallback.close()
