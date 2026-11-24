"""Session fixtures shared by the WASM parity gates (Step 0 and Tier A).

A missing environment input (node, a corpus, the bundled extensions) skips the
dependent tests with a message that names the input. Setting
``FHIR4DS_REQUIRE_WASM_PARITY=1`` turns that into a failure for CI.
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


def _skip_or_fail(exc: reference_mod.EnvironmentInputMissing):
    if reference_mod.required():
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
