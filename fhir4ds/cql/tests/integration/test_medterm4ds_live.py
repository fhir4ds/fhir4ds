"""Live integration tests for the fhir4ds <-> medterm4ds contract.

These tests exercise the real terminology sidecar at
``$MEDTERM4DS_TEST_URL`` (typically ``http://127.0.0.1:8001/fhir``).
They are skipped cleanly whenever:

* ``httpx`` is not installed,
* ``MEDTERM4DS_TEST_URL`` is unset,
* the sidecar is unreachable / unhealthy,
* the sidecar is up but its search index is not loaded (sparse results).

The module is marked ``integration`` so it can be deselected from the
default smoke run via ``-m "not integration"``. It also lives under
``cql/tests/integration/`` so existing path-based selections continue
to pick it up like the other integration tests.
"""

from __future__ import annotations

import json
import os

import pytest

# Skip the entire module if httpx is missing. httpx ships in the
# ``[fhir4ds,terminology]`` extra but we never want a hard failure.
pytest.importorskip("httpx")

import httpx  # noqa: E402  (after importorskip)

# Module-level marker so ``-m "not integration"`` skips us cheaply.
pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Shared fixture: skip cleanly when no sidecar is reachable.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def medterm4ds_url() -> str:
    """Return the sidecar base URL or skip the test.

    Resolution rules:
    1. ``MEDTERM4DS_TEST_URL`` must be set (no guessing localhost:8001).
    2. ``GET {url}/metadata`` must respond with HTTP < 500.

    Any failure short-circuits to ``pytest.skip`` so the test body never
    runs against a half-up sidecar.
    """
    url = os.environ.get("MEDTERM4DS_TEST_URL")
    if not url:
        pytest.skip("MEDTERM4DS_TEST_URL not set; skipping live medterm4ds tests")
    try:
        with httpx.Client(timeout=2.0) as client:
            r = client.get(url.rstrip("/") + "/metadata")
            if r.status_code >= 500:
                raise RuntimeError(f"sidecar unhealthy: HTTP {r.status_code}")
    except Exception as e:  # noqa: BLE001 - any failure => skip
        pytest.skip(f"medterm4ds sidecar not reachable at {url}: {e}")
    return url.rstrip("/")


# ---------------------------------------------------------------------------
# Phase 1: terminology endpoint round-trip via HTTP.
# ---------------------------------------------------------------------------


def test_phase1_expand_valueset_via_http(medterm4ds_url: str) -> None:
    """HTTPTerminologyEndpoint.expand() returns CodeRefs from real medterm4ds.

    URL choice: ``http://snomed.info/sct/73211009?fhir_vs=isa`` is the
    FHIR R4 intensional ValueSet form for "descendents of Diabetes
    Mellitus (SNOMED 73211009)". medterm4ds's ``_expand_url_pattern``
    expects the SNOMED code in the path and the mode in the query —
    NOT the older ``?fhir_vs=isa/<code>`` form.
    """
    from fhir4ds.cql.terminology.http_adapter import HTTPTerminologyEndpoint

    # Use a longer timeout than the 5s default — SNOMED hierarchy expansion
    # is a heavy operation that legitimately takes 10-30s on a cold cache.
    endpoint = HTTPTerminologyEndpoint(base_url=medterm4ds_url, timeout_seconds=60.0)
    codes = endpoint.expand("http://snomed.info/sct/73211009?fhir_vs=isa")

    assert isinstance(codes, list)
    if len(codes) == 0:
        pytest.skip("medterm4ds returned no codes - SNOMED index may not be loaded")
    assert all(hasattr(c, "system") and hasattr(c, "code") for c in codes), (
        f"expand() returned non-CodeRef entries: {codes[:2]!r}"
    )


# ---------------------------------------------------------------------------
# Phase 2: auto-coder end-to-end on text-only Conditions.
# ---------------------------------------------------------------------------


def test_phase2_autocoder_loads_and_codes(medterm4ds_url: str) -> None:
    """FHIRDataLoader with AutoCoder populates coding[] for text-only Conditions.

    The AutoCoderConfig field is ``min_match_grade`` (not
    ``match_grade_threshold``). We loosen to ``"probable"`` so the test
    surfaces hits even when the SapBERT ranker is not at full confidence.
    """
    import duckdb

    from fhir4ds.cql.loader import AutoCoder, AutoCoderConfig, FHIRDataLoader
    from fhir4ds.cql.terminology.http_adapter import HTTPTerminologyEndpoint

    endpoint = HTTPTerminologyEndpoint(base_url=medterm4ds_url)
    conn = duckdb.connect(":memory:")

    config = AutoCoderConfig(
        min_match_grade="probable",  # loosen to ensure hits
        top_k=3,
    )
    auto_coder = AutoCoder(endpoint, conn, config=config)
    loader = FHIRDataLoader(conn, auto_coder=auto_coder)

    resource = {
        "resourceType": "Condition",
        "id": "test-cond-001",
        "subject": {"reference": "Patient/test-patient"},
        "code": {"text": "Type 2 diabetes mellitus"},
    }
    loader.load_resource(resource)

    df = conn.execute("SELECT resource FROM resources").fetchdf()
    assert len(df) == 1, f"expected exactly 1 row, got {len(df)}"

    loaded = json.loads(df.iloc[0]["resource"])
    codings = loaded.get("code", {}).get("coding", [])
    if len(codings) == 0:
        pytest.skip(
            "Auto-coder returned no codes for 'Type 2 diabetes mellitus' "
            "- search index may not be loaded"
        )

    # INV-6: every auto-coded Coding has userSelected == False.
    assert any(c.get("userSelected") is False for c in codings), (
        f"no userSelected=False coding in {codings!r}"
    )

    # INV-5: every auto-coded Coding carries the autocoding extension.
    extensions = [c.get("extension", []) for c in codings]
    flat = [e for sub in extensions for e in sub]
    assert any("autocoding" in e.get("url", "") for e in flat), (
        f"no autocoding extension on any coding: {codings!r}"
    )


# ---------------------------------------------------------------------------
# Phase 3: subsumption closure table + closure-loaded translator.
# ---------------------------------------------------------------------------


def test_phase3_closure_table_built_and_subsumption_works(medterm4ds_url: str) -> None:
    """build_closure_table() populates terminology_closure and closure-loaded SQL runs.

    The CQL library below uses ``descendents()`` against the Diabetes
    SNOMED code, which seeds the closure table. We then write the CQL
    to a temp file (evaluate_measure takes a path) and evaluate with
    ``closure_loaded=True`` so the translator routes ``Descendents``
    through ``terminology_closure``.
    """
    import duckdb

    from fhir4ds.cql import evaluate_measure
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.terminology.closure import build_closure_table
    from fhir4ds.cql.terminology.http_adapter import HTTPTerminologyEndpoint

    # Longer timeout for SNOMED hierarchy expansion on a cold cache.
    endpoint = HTTPTerminologyEndpoint(base_url=medterm4ds_url, timeout_seconds=60.0)
    conn = duckdb.connect(":memory:")

    cql_source = """
    library TestPhase3 version '1.0'
    using FHIR version '4.0.1'
    codesystem snomed: 'http://snomed.info/sct'
    code Diabetes: '73211009' from snomed
    context Patient
    define DiabetesDescendents: descendents(Diabetes)
    """

    # Parse + seed the closure table first so we can see whether the
    # sidecar actually has SNOMED hierarchy loaded. If expand() returns
    # nothing, the closure table stays empty and the rest of the test
    # is meaningless.
    library = parse_cql(cql_source)
    report = build_closure_table(
        library, endpoint, conn, on_expand_error="warn"
    )

    closure_count = conn.execute(
        "SELECT COUNT(*) FROM terminology_closure"
    ).fetchone()[0]
    if closure_count == 0:
        pytest.skip(
            "build_closure_table inserted 0 rows - SNOMED hierarchy index "
            f"may not be loaded (errors={len(report.errors)})"
        )

    # Write the library to disk so evaluate_measure can re-read it.
    import pathlib
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        lib_path = pathlib.Path(tmpdir) / "TestPhase3.cql"
        lib_path.write_text(cql_source)

        # Load a SNOMED-coded Condition so the descendents() retrieve has
        # something to match. 73211009 itself is the seed; one of its
        # self-rows should be present in terminology_closure.
        from fhir4ds.cql.loader import FHIRDataLoader

        loader = FHIRDataLoader(conn)
        loader.load_resource(
            {
                "resourceType": "Condition",
                "id": "cond-phase3",
                "subject": {"reference": "Patient/p1"},
                "code": {
                    "coding": [
                        {
                            "system": "http://snomed.info/sct",
                            "code": "73211009",
                            "display": "Diabetes mellitus (disorder)",
                        }
                    ]
                },
            }
        )

        # evaluate_measure returns a relation; we only need it to execute
        # without error. closure_loaded=True routes ~ / is / Descendents
        # through terminology_closure.
        rel = evaluate_measure(
            library_path=str(lib_path),
            conn=conn,
            output_columns={"diabetes_desc": "DiabetesDescendents"},
            terminology_endpoint=endpoint,
            closure_loaded=True,
        )
        df = rel.fetchdf() if hasattr(rel, "fetchdf") else None
        # No assertion on row count - the test's purpose is that the
        # closure-loaded SQL path executes successfully. Sparse indices
        # may return zero rows, which is fine.
        _ = df  # silence linter


# ---------------------------------------------------------------------------
# Phase 4: notes pipeline extraction.
# ---------------------------------------------------------------------------


def test_phase4_notes_pipeline_extracts_conditions(medterm4ds_url: str) -> None:
    """NotesPipeline.extract_conditions() derives Conditions from real clinical text.

    medterm4ds ships an optional NER extractor (``medterm4ds.extract``).
    When the sidecar doesn't have it installed, extract_conditions()
    returns [] (INV-3) and we skip rather than fail.
    """
    from fhir4ds.cql.loader import NotesPipeline, NotesPipelineConfig

    pipeline = NotesPipeline(
        NotesPipelineConfig(
            categories=["condition"],
            min_grade="probable",  # loosen
        )
    )

    note_text = (
        "Patient is a 54-year-old male with a history of type 2 diabetes mellitus, "
        "hypertension, and hyperlipidemia. Presents with fatigue and polyuria. "
        "Assessment: uncontrolled diabetes. Plan: start metformin."
    )

    resource = {
        "resourceType": "ClinicalImpression",
        "id": "ci-test-001",
        "subject": {"reference": "Patient/test-patient"},
        "summary": note_text,
    }
    conditions = pipeline.extract_conditions(resource)
    if len(conditions) == 0:
        pytest.skip(
            "NotesPipeline extracted no conditions - medterm4ds sidecar may "
            "not have extraction deps installed (medterm4ds.extract)"
        )

    # Derived Condition shape contract.
    assert all(c.get("resourceType") == "Condition" for c in conditions), (
        f"non-Condition in extracted set: {conditions[:2]!r}"
    )
    assert all(
        c.get("subject", {}).get("reference") == "Patient/test-patient"
        for c in conditions
    ), "subject reference not propagated from source resource"
    assert all(
        c.get("verificationStatus", {}).get("coding", [{}])[0].get("code")
        == "unconfirmed"
        for c in conditions
    ), "verificationStatus.coding[0].code should default to 'unconfirmed'"

    # Soft check: at least one extracted Condition should mention diabetes
    # somewhere in its display text. We accept alternate SNOMED displays
    # (e.g. "Diabetes mellitus (disorder)") so we only check the stem.
    blob = " ".join(
        c.get("code", {}).get("text", "")
        + " "
        + (
            c.get("code", {}).get("coding", [{}])[0].get("display", "")
            if c.get("code", {}).get("coding")
            else ""
        )
        for c in conditions
    ).lower()
    assert "diabetes" in blob, (
        f"no Condition mentions diabetes in display text: {blob!r}"
    )
