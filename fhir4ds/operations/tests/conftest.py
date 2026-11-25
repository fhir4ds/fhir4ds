"""Session fixtures shared by the WASM parity gates (Step 0 and Tier A).

A missing environment input (node, a corpus, the bundled extensions, the web apps'
node_modules) skips the dependent tests with a message that names the input. Setting
``FHIR4DS_REQUIRE_WASM_PARITY=1`` turns that into a failure for CI.

The real engine (Tier B and Tier C) has its own flag, ``FHIR4DS_REQUIRE_WASM_REAL``. It is
the only one that governs those fixtures, so a job that sets the parity flag but has no
``node_modules`` or chromium (the python job) skips Tier B and Tier C instead of failing,
while the cleanroom job, which sets both, runs them.
"""

from __future__ import annotations

import pytest

from fhir4ds.operations.tests.wasm_parity import (
    contract as contract_mod,
)
from fhir4ds.operations.tests.wasm_parity import (
    ledger as ledger_mod,
)
from fhir4ds.operations.tests.wasm_parity import (
    reference_bundle as reference_mod,
)
from fhir4ds.operations.tests.wasm_parity import (
    surfaces as surfaces_mod,
)

REAL_REQUIRE_ENV = "FHIR4DS_REQUIRE_WASM_REAL"


def _skip_or_fail(exc: reference_mod.EnvironmentInputMissing, env: str | None = None):
    """Skip, or fail when the flag that governs THIS input is set (CI)."""
    if reference_mod.required(env):
        raise exc
    pytest.skip(str(exc))


@pytest.fixture(scope="session")
def wasm_reference():
    try:
        return reference_mod.load_reference_bundle()
    except reference_mod.EnvironmentInputMissing as exc:
        _skip_or_fail(exc)


def _connection(build):
    try:
        return build()
    except reference_mod.EnvironmentInputMissing as exc:
        _skip_or_fail(exc)


@pytest.fixture(scope="session")
def wasm_desktop(wasm_reference):
    con = _connection(surfaces_mod.desktop_connection)
    yield con
    con.close()


@pytest.fixture(scope="session")
def wasm_browser(wasm_reference):
    con = _connection(lambda: surfaces_mod.browser_sim_connection(wasm_reference))
    yield con
    con.close()


@pytest.fixture(scope="session")
def wasm_contract(wasm_desktop, wasm_reference):
    """The live contract between the desktop catalog and the browser simulation."""
    return _connection(lambda: contract_mod.compute(wasm_desktop, wasm_reference))


@pytest.fixture(scope="session")
def wasm_ledger():
    return ledger_mod.load()


@pytest.fixture(scope="session")
def wasm_real(wasm_reference):
    """The real engine: headless duckdb-wasm with the shipped wasm bundles (Tier B)."""
    from fhir4ds.operations.tests.wasm_parity.real_engine import real_engine

    try:
        with real_engine() as engine:
            engine.use_reference(wasm_reference)
            yield engine
    except reference_mod.EnvironmentInputMissing as exc:
        _skip_or_fail(exc, REAL_REQUIRE_ENV)
