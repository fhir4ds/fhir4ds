"""Reference-bundle export parity.

The macro-sync contract itself moved to ``test_wasm_parity_step0.py`` (Step 0:
the reference bundle is compared with the LIVE desktop catalog, bodies included,
and every gap is registered in ``wasm_parity/known_gaps.json``). This module
keeps the one check that only node can do: the TS module's
``REGISTERED_MACRO_NAMES`` export must equal the names of the statements the
module actually registers (``CQL_MACRO_SQL``).
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
TS_MACRO_FILE = REPO_ROOT / "web" / "cql-cleanroom" / "src" / "lib" / "cql-macros.ts"


class TestMacroSync:
    def test_registered_name_export_matches_ts_source(self):
        """REGISTERED_MACRO_NAMES runtime export parity with the TS source.

        Runs the TS module in node (experimental type stripping) and
        diffs the exported list against names extracted from the raw TS
        source, so the export cannot drift from the registered SQL.
        Skips when node is unavailable (environment availability).
        """
        from fhir4ds.operations.tests.wasm_parity import reference_bundle

        try:
            bundle = reference_bundle.load_reference_bundle()
        except reference_bundle.EnvironmentInputMissing as exc:
            import pytest

            pytest.skip(str(exc))
        registered = set(bundle.registered_names)
        unregistered = {"resolve"}  # exported for the apps, not registered by the module
        assert registered - unregistered == set(bundle.names), (
            "REGISTERED_MACRO_NAMES export drift vs CQL_MACRO_SQL: "
            f"missing={sorted(set(bundle.names) - registered)} "
            f"extra={sorted((registered - unregistered) - set(bundle.names))}"
        )
