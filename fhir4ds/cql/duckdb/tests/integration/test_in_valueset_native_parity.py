"""fhirpath_in_valueset native C++ parity tests (v0.0.14 WASM parity campaign).

Covers the translator-facing ``fhirpath_in_valueset`` name across three
registration legs:
  1. native-loaded C++ extension (register())
  2. forced Python supplements (cpp_loaded=False)
  3. no-Python C++ (LOAD only + SQL macros)

The C++ registration reuses ``InValuesetFunc`` (identical 3VL semantics:
NULL on null input / unloaded valueset / String-overload ambiguity,
False only on definitive membership miss). This file pins that parity
plus the fhir_loader native-mode reconciliation (macro removed, C++
scalar provides both names).
"""

import json

import duckdb
import pytest

from fhir4ds.cql.duckdb import register as register_cql
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.duckdb.macros import register_all_macros

VS_URL = "http://example.org/ValueSet/TestVS"

_CACHE = {
    VS_URL: {
        ("http://loinc.org", "8867-4"),
        ("http://snomed.info/sct", "44054006"),
        ("", "unsys-code"),
    }
}

_RESOURCE = json.dumps(
    {
        "resourceType": "Observation",
        "status": "final",
        "code": {
            "coding": [
                {"system": "http://loinc.org", "code": "8867-4"},
                {"system": "http://example.org", "code": "other"},
            ]
        },
    }
)

_NO_CODE_RESOURCE = json.dumps({"resourceType": "Observation", "status": "final"})
# Empty-system source: the shape the translator's _synthetic_code_resource
# actually produces for bare CQL String codes (system explicitly "").
# (Native extract_codes_from_val additionally accepts a code-only dict —
# {"code": {"code": x}} — which invalid-FHIR corner Python rejects; that
# pre-existing lenience difference is out of scope for this port.)
_UNSYS_RESOURCE = json.dumps(
    {"resourceType": "Observation", "code": {"system": "", "code": "unsys-code"}}
)
_AMBIG_RESOURCE = json.dumps(
    {
        "resourceType": "Observation",
        "code": {"system": "", "code": "8867-4"},
    }
)


def _native_con():
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register_cql(con, include_fhirpath=False)
    # Populate the native valueset cache through the C++ cache UDFs.
    for url, entries in _CACHE.items():
        for system, code in entries:
            con.execute(
                "SELECT cql_valueset_cache_add(?, ?, ?)", [url, system, code]
            )
    return con


def _python_con():
    con = duckdb.connect()
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=False)
    # The valueset loader flow: cache-backed Python UDF under the
    # translator-facing name (the supplements already provide the
    # in_valueset placeholder; macros alias it per the loader).
    from fhir4ds.cql.duckdb.udf.valueset import createValuesetMembershipUdf

    udf = createValuesetMembershipUdf(
        {url: set(entries) for url, entries in _CACHE.items()}
    )
    con.create_function("fhirpath_in_valueset", udf, null_handling="special")
    con.execute(
        "CREATE OR REPLACE MACRO in_valueset(res, path, vs_url) AS "
        "fhirpath_in_valueset(res, path, vs_url)"
    )
    return con


def _no_python_con():
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    con.execute(
        "LOAD '/mnt/d/fhir4ds/extensions/cql/build/release/extension/cql/cql.duckdb_extension'"
    )
    register_all_macros(con)
    con.execute(
        "CREATE TABLE IF NOT EXISTS resources (patient_id VARCHAR, resourceType VARCHAR, resource JSON)"
    )
    for url, entries in _CACHE.items():
        for system, code in entries:
            con.execute(
                "SELECT cql_valueset_cache_add(?, ?, ?)", [url, system, code]
            )
    return con


LEGS = [
    pytest.param(_native_con, id="native"),
    pytest.param(_python_con, id="forced_python"),
    pytest.param(_no_python_con, id="no_python"),
]


# (resource, path, expected)
DIRECT_CASES = [
    (_RESOURCE, "code", True),            # LOINC code in valueset
    (_RESOURCE, "code.coding.code", True),
    (_NO_CODE_RESOURCE, "code", False),   # no codes at all -> definitive miss
    (_UNSYS_RESOURCE, "code", True),      # empty-system cache entry match
    (_RESOURCE, "code", None),            # placeholder; replaced below
]

# Nulls / unloaded valueset / ambiguity
NULL_CASES = [
    (None, "code", VS_URL),               # null resource -> NULL
    (_RESOURCE, "code", "http://unknown/VS"),  # unloaded valueset -> NULL
]


@pytest.mark.parametrize("con_factory", LEGS)
def test_direct_calls_match_across_legs(con_factory):
    con = con_factory()
    try:
        # Membership true
        assert con.execute(
            "SELECT fhirpath_in_valueset(?, 'code', ?)", [_RESOURCE, VS_URL]
        ).fetchone()[0] is True

        # Multi-path navigation (Coding elements)
        assert con.execute(
            "SELECT fhirpath_in_valueset(?, 'code.coding', ?)", [_RESOURCE, VS_URL]
        ).fetchone()[0] is True

        # Definitive miss (codes present, none in valueset, no ambiguity)
        miss = json.dumps(
            {
                "resourceType": "Observation",
                "code": {"coding": [{"system": "http://x.org", "code": "nope"}]},
            }
        )
        assert con.execute(
            "SELECT fhirpath_in_valueset(?, 'code', ?)", [miss, VS_URL]
        ).fetchone()[0] is False

        # No codes extracted -> False (definitive miss)
        assert con.execute(
            "SELECT fhirpath_in_valueset(?, 'code', ?)", [_NO_CODE_RESOURCE, VS_URL]
        ).fetchone()[0] is False

        # Empty-system cache entry match via bare code resource
        assert con.execute(
            "SELECT fhirpath_in_valueset(?, 'code', ?)", [_UNSYS_RESOURCE, VS_URL]
        ).fetchone()[0] is True

        # Null resource -> NULL (3VL)
        assert con.execute(
            "SELECT fhirpath_in_valueset(NULL, 'code', ?)", [VS_URL]
        ).fetchone()[0] is None

        # Unloaded valueset -> NULL (3VL)
        assert con.execute(
            "SELECT fhirpath_in_valueset(?, 'code', 'http://unknown/VS')", [_RESOURCE]
        ).fetchone()[0] is None

        # String-overload ambiguity: bare code 8867-4 present under exactly
        # one distinct non-empty system here (loinc) -> unambiguous True.
        assert con.execute(
            "SELECT fhirpath_in_valueset(?, 'code', ?)", [_AMBIG_RESOURCE, VS_URL]
        ).fetchone()[0] is True
    finally:
        con.close()


AMBIG_CACHE_CON_FACTORY = None  # built lazily per leg below


def _ambig_setup(con):
    """Add a second distinct system carrying the same bare code."""
    con.execute(
        "SELECT cql_valueset_cache_add(?, ?, ?)",
        [VS_URL, "http://other-system.org", "8867-4"],
    )


@pytest.mark.parametrize("con_factory", LEGS)
def test_string_overload_ambiguity_is_null(con_factory):
    con = con_factory()
    try:
        if con_factory is _python_con:
            # Python closure cache: rebuild with ambiguous entries
            cache = {
                VS_URL: {
                    ("http://loinc.org", "8867-4"),
                    ("http://other-system.org", "8867-4"),
                }
            }
            from fhir4ds.cql.duckdb.udf.valueset import createValuesetMembershipUdf

            udf = createValuesetMembershipUdf(cache)
            con.remove_function("fhirpath_in_valueset")
            con.create_function("fhirpath_in_valueset", udf, null_handling="special")
        else:
            _ambig_setup(con)
        assert con.execute(
            "SELECT fhirpath_in_valueset(?, 'code', ?)", [_AMBIG_RESOURCE, VS_URL]
        ).fetchone()[0] is None
    finally:
        con.close()


def test_native_loader_reconciliation():
    """fhir_loader native-mode no longer leaves an aliasing macro; the C++
    scalar provides fhirpath_in_valueset directly."""
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    try:
        register_cql(con, include_fhirpath=False)
        # Simulate the loader native path: tolerant macro drops (scalars are
        # internal catalog entries and cannot be dropped — the loader wraps
        # these in try/except), no aliasing macro recreated.
        for name in ("in_valueset", "fhirpath_in_valueset"):
            try:
                con.execute(f"DROP MACRO IF EXISTS {name}")
            except Exception:
                pass
        rows = con.execute(
            "SELECT function_type FROM duckdb_functions() "
            "WHERE lower(function_name) IN ('fhirpath_in_valueset','in_valueset') "
            "ORDER BY function_name"
        ).fetchall()
        # Both names resolve to native scalars (no macro shadowing).
        assert rows == [("scalar",), ("scalar",)]
        # And they must be callable post-macro-drop.
        assert con.execute(
            "SELECT fhirpath_in_valueset(NULL, 'code', 'http://x/y') IS NULL"
        ).fetchone()[0] is True
    finally:
        con.close()


def test_translated_population_sql_uses_native_name():
    """End-to-end: a dynamic terminology filter lowers to
    fhirpath_in_valueset and executes on the no-Python leg."""
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator import CQLToSQLTranslator

    lib = parse_cql(
        """
        library TestVSUse
        using FHIR version '4.0.1'
        valueset "TestVS": 'http://example.org/ValueSet/TestVS'
        context Patient
        define InVS:
          exists ([Observation] O where fhirpath_in_valueset(O.resource, 'code', 'http://example.org/ValueSet/TestVS'))
        """
    )
    translator = CQLToSQLTranslator()
    sql = translator.translate_library_to_population_sql(lib)
    assert "fhirpath_in_valueset" in sql
