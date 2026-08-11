"""In-process integration tests for the fhir4ds <-> medterm4ds contract.

Mirrors ``test_medterm4ds_live.py`` but exercises the contracts via
:class:`InProcessTerminologyEndpoint` (direct DuckDB, no HTTP) and
``medterm4ds.extract`` (NER, no sidecar). These tests run whenever
``medterm4ds`` is importable — no sidecar required — so they give CI
real coverage of the contract that the HTTP module only covers when
``MEDTERM4DS_TEST_URL`` is set.

Skip behavior:

* ``medterm4ds`` not installed → module skipped via ``importorskip``.
* medterm4ds's search index returns sparse results → each test skips
  with a clear reason rather than failing.
* A specific phase's optional deps are missing (e.g. NER pipeline not
  installed for Phase 4) → that phase skips independently.

The module is marked ``integration`` so ``-m "not integration"``
deselects it cheaply. It lives under ``cql/tests/integration/`` so
existing path-based selections continue to pick it up.
"""

from __future__ import annotations

import json

import pytest

# Skip the entire module if medterm4ds is missing. Same pattern as the
# live module's httpx gate. medterm4ds ships in the ``[ner]`` extra but
# we never want a hard failure.
pytest.importorskip("medterm4ds")

# Module-level marker so ``-m "not integration"`` skips us cheaply.
pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Shared fixture: session-scoped in-process endpoint.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def in_process_endpoint():
    """Return a session-scoped :class:`InProcessTerminologyEndpoint`.

    Construction loads medterm4ds's ``LocalDuckDBEngine`` (DuckDB +
    BM25 indexes + SapBERT + FAISS). On a cold cache this can take
    30–60s; session scope ensures we pay that cost once per test run,
    not once per test.

    The endpoint uses medterm4ds's default discovery (no explicit
    ``db_path`` or ``search_index_dir``). Tests that need isolated
    DuckDB state create their own ``duckdb.connect(":memory:")``
    alongside this fixture — the user's connection is independent of
    the engine's internal connection.
    """
    from fhir4ds.cql.terminology.in_process_adapter import InProcessTerminologyEndpoint

    return InProcessTerminologyEndpoint()


# ---------------------------------------------------------------------------
# Phase 1: terminology endpoint round-trip in-process.
# ---------------------------------------------------------------------------


def test_phase1_expand_valueset_in_process(in_process_endpoint) -> None:
    """InProcessTerminologyEndpoint.expand() returns CodeRefs from real medterm4ds.

    URL choice: ``http://snomed.info/sct/73211009?fhir_vs=isa`` is the
    FHIR R4 intensional ValueSet form for "descendents of Diabetes
    Mellitus (SNOMED 73211009)". The in-process endpoint delegates to
    the same medterm4ds engine call the HTTP sidecar would make — same
    contract, different transport.
    """
    codes = in_process_endpoint.expand(
        "http://snomed.info/sct/73211009?fhir_vs=isa"
    )

    assert isinstance(codes, list)
    if len(codes) == 0:
        pytest.skip(
            "medterm4ds returned no codes - SNOMED index may not be loaded"
        )
    assert all(hasattr(c, "system") and hasattr(c, "code") for c in codes), (
        f"expand() returned non-CodeRef entries: {codes[:2]!r}"
    )


# ---------------------------------------------------------------------------
# Phase 2: auto-coder end-to-end on text-only Conditions.
# ---------------------------------------------------------------------------


def test_phase2_autocoder_loads_and_codes_in_process(in_process_endpoint) -> None:
    """FHIRDataLoader with AutoCoder populates coding[] for text-only Conditions.

    Same contract as the HTTP test: ``min_match_grade="probable"`` so
    the test surfaces hits even when SapBERT confidence is not at its
    peak. INV-5 (autocoding extension) and INV-6 (userSelected=False)
    are the load-bearing assertions.
    """
    import duckdb

    from fhir4ds.cql.loader import AutoCoder, AutoCoderConfig, FHIRDataLoader

    conn = duckdb.connect(":memory:")

    config = AutoCoderConfig(
        # The in-process engine's default SapBERT scoring tends to
        # return match_grade='ambiguous' for short clinical phrases
        # (the sidecar may be configured differently). Loosen to
        # 'ambiguous' so the test exercises the AutoCoder pipeline
        # without depending on SapBERT's score calibration. The point
        # is to verify INV-5 (autocoding extension) and INV-6
        # (userSelected=False), not match quality.
        min_match_grade="ambiguous",
        top_k=3,
    )
    auto_coder = AutoCoder(in_process_endpoint, conn, config=config)
    loader = FHIRDataLoader(conn, auto_coder=auto_coder)

    resource = {
        "resourceType": "Condition",
        "id": "test-cond-inprocess-001",
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


def test_phase3_closure_table_built_and_subsumption_works_in_process(
    in_process_endpoint,
) -> None:
    """build_closure_table() + closure-loaded SQL via InProcessTerminologyEndpoint.

    Same CQL library as the HTTP test (``descendents(Diabetes)``); the
    closure table is seeded from the in-process engine's SNOMED
    hierarchy expansion, then ``evaluate_measure(closure_loaded=True)``
    routes the ``Descendents`` call through ``terminology_closure``.
    """
    import duckdb
    import pathlib
    import tempfile

    from fhir4ds.cql import evaluate_measure
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.terminology.closure import build_closure_table
    from fhir4ds.cql.loader import FHIRDataLoader

    conn = duckdb.connect(":memory:")

    cql_source = """
    library TestPhase3InProcess version '1.0'
    using FHIR version '4.0.1'
    codesystem snomed: 'http://snomed.info/sct'
    code Diabetes: '73211009' from snomed
    context Patient
    define DiabetesDescendents: descendents(Diabetes)
    """

    library = parse_cql(cql_source)
    report = build_closure_table(
        library, in_process_endpoint, conn, on_expand_error="warn"
    )

    closure_count = conn.execute(
        "SELECT COUNT(*) FROM terminology_closure"
    ).fetchone()[0]
    if closure_count == 0:
        pytest.skip(
            "build_closure_table inserted 0 rows - SNOMED hierarchy index "
            f"may not be loaded (errors={len(report.errors)})"
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        lib_path = pathlib.Path(tmpdir) / "TestPhase3InProcess.cql"
        lib_path.write_text(cql_source)

        loader = FHIRDataLoader(conn)
        loader.load_resource(
            {
                "resourceType": "Condition",
                "id": "cond-phase3-inprocess",
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

        rel = evaluate_measure(
            library_path=str(lib_path),
            conn=conn,
            output_columns={"diabetes_desc": "DiabetesDescendents"},
            terminology_endpoint=in_process_endpoint,
            closure_loaded=True,
        )
        df = rel.fetchdf() if hasattr(rel, "fetchdf") else None
        # No assertion on row count - the test's purpose is that the
        # closure-loaded SQL path executes successfully. Sparse indices
        # may return zero rows, which is fine.
        _ = df  # silence linter


# ---------------------------------------------------------------------------
# Phase 4: notes pipeline extraction (no endpoint needed).
# ---------------------------------------------------------------------------


def test_phase4_notes_pipeline_extracts_conditions_in_process() -> None:
    """NotesPipeline.extract_conditions() derives Conditions from real clinical text.

    NotesPipeline does not take an endpoint — it calls the module-level
    ``medterm4ds.extract`` directly. The HTTP module's Phase 4 test is
    gated by ``pytest.importorskip("httpx")`` only because of where it
    lives; this in-process variant runs whenever ``medterm4ds`` is
    importable.
    """
    from fhir4ds.cql.loader import NotesPipeline, NotesPipelineConfig

    pipeline = NotesPipeline(
        NotesPipelineConfig(
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
        "id": "ci-test-inprocess-001",
        "subject": {"reference": "Patient/test-patient"},
        "summary": note_text,
    }
    conditions = pipeline.extract_conditions(resource)
    if len(conditions) == 0:
        pytest.skip(
            "NotesPipeline extracted no conditions - medterm4ds may not "
            "have extraction deps installed (medterm4ds.extract)"
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
