"""T7: a WASM bundle built from an older C++ tree than ``HEAD`` fails the gate.

The manifest records the tree each bundle was built from. This check turns a
C++ merge that lands without a wasm rebuild into a red Python CI job, instead
of waiting for someone to remember the rebuild or for a Tier B/C difference to
show up in a browser.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from fhir4ds.operations.tests.wasm_parity import contract, ledger, shipped_bundles

BUNDLE_PATHS = {"cql": "public/extensions/cql.duckdb_extension.wasm", "fhirpath": "public/extensions/fhirpath.duckdb_extension.wasm"}
REBUILD = "scripts/build_wasm_extensions.py --build --extension"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _tree(repo: Path, path: str) -> str:
    return _git(repo, "rev-parse", f"HEAD:{path}")


def _commit_all(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A git repository with both extensions' sources and a matching manifest."""
    for extension, rel in BUNDLE_PATHS.items():
        (tmp_path / f"extensions/{extension}/src").mkdir(parents=True)
        (tmp_path / f"extensions/{extension}/src/lib.cpp").write_text(f"// {extension}\n")
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes(extension.encode() + b"-wasm")
    (tmp_path / "extensions/common").mkdir(parents=True)
    (tmp_path / "extensions/common/compat.hpp").write_text("// common\n")
    _git(tmp_path, "init", "-q")
    _commit_all(tmp_path, "base")
    (tmp_path / "manifest.json").write_text(json.dumps(_manifest(tmp_path)))
    _commit_all(tmp_path, "manifest")
    return tmp_path


def _frozen(repo: Path) -> dict:
    """The manifest as recorded when the bundles were built."""
    return json.loads((repo / "manifest.json").read_text())


def _manifest(repo: Path, *, source: bool = True) -> dict:
    bundles = []
    for extension, rel in BUNDLE_PATHS.items():
        path = repo / rel
        provenance = (
            {
                "commit": "0" * 40,
                f"{extension}_source": _tree(repo, f"extensions/{extension}/src"),
                "common_source": _tree(repo, "extensions/common"),
                "duckdb_tag": "v1.5.5",
                "emsdk": "emsdk-x",
                "built_at": "2026-11-25T00:00:00",
            }
            if source
            else None
        )
        bundles.append({"extension": extension, "path": rel, "sha256": shipped_bundles.sha256_of(path), "size": path.stat().st_size, "install": [], "source": provenance})
    return {"schema_version": 1, "duckdb_abi": "1.5.5", "duckdb_wasm_version": "1.33.1-dev64.0", "bundles": bundles}


class TestStaleSources:
    def test_a_tree_that_did_not_change_is_not_stale(self, repo: Path) -> None:
        assert shipped_bundles.stale_sources(_frozen(repo), repo) == {}
        assert "STALE_WASM_SOURCE" not in shipped_bundles.observe(_frozen(repo), repo)

    def test_a_changed_extension_tree_stales_only_its_bundle(self, repo: Path) -> None:
        (repo / "extensions/cql/src/lib.cpp").write_text("// cql, fixed\n")
        _commit_all(repo, "cql fix without a wasm rebuild")

        stale = shipped_bundles.stale_sources(_frozen(repo), repo)

        assert stale == {"extensions/cql/src": ["cql"]}
        assert shipped_bundles.observe(_frozen(repo), repo)["STALE_WASM_SOURCE"] == ["extensions/cql/src (cql)"]

    def test_a_changed_common_tree_stales_both_bundles(self, repo: Path) -> None:
        (repo / "extensions/common/compat.hpp").write_text("// common, changed\n")
        _commit_all(repo, "shared header change")

        assert shipped_bundles.stale_sources(_frozen(repo), repo) == {"extensions/common": ["cql", "fhirpath"]}

    def test_a_source_path_removed_at_head_is_stale(self, repo: Path) -> None:
        (repo / "extensions/fhirpath/src").rename(repo / "extensions/fhirpath/moved")
        _commit_all(repo, "sources moved away")

        assert shipped_bundles.stale_sources(_frozen(repo), repo) == {"extensions/fhirpath/src": ["fhirpath"]}

    def test_unknown_provenance_is_reported_as_unknown_not_stale(self, repo: Path) -> None:
        manifest = _frozen(repo)
        for bundle in manifest["bundles"]:
            bundle["source"] = None
        observed = shipped_bundles.observe(manifest, repo)

        assert observed == {"PROVENANCE_UNKNOWN": sorted(BUNDLE_PATHS.values())}

    def test_a_hash_that_is_not_a_tree_hash_cannot_accuse(self, repo: Path) -> None:
        manifest = _frozen(repo)
        manifest["bundles"][0]["source"]["cql_source"] = "not-a-tree-hash"

        assert shipped_bundles.stale_sources(manifest, repo) == {}

    def test_git_that_cannot_answer_does_not_accuse(self, tmp_path: Path) -> None:
        plain = tmp_path / "not-a-repo"
        plain.mkdir()
        (plain / BUNDLE_PATHS["cql"]).parent.mkdir(parents=True)
        for rel in BUNDLE_PATHS.values():
            (plain / rel).write_bytes(b"x")

        assert shipped_bundles.stale_sources(_manifest_plain(), plain) == {}


def _manifest_plain() -> dict:
    """A manifest whose recorded trees match nothing (so only git can tell)."""
    bundles = [
        {"extension": extension, "path": rel, "sha256": "0" * 64, "size": 1, "install": [], "source": {f"{extension}_source": "1" * 40, "common_source": "2" * 40}}
        for extension, rel in BUNDLE_PATHS.items()
    ]
    return {"schema_version": 1, "duckdb_abi": "1.5.5", "duckdb_wasm_version": "1.33.1-dev64.0", "bundles": bundles}


class TestGate:
    def test_the_violation_names_the_rebuild(self) -> None:
        violations = contract.evaluate_files([], {"STALE_WASM_SOURCE": ["extensions/cql/src (cql)"]}, today=date(2026, 11, 25))

        assert [v.code for v in violations] == ["STALE_WASM_SOURCE"]
        assert REBUILD in violations[0].message
        assert "cannot be registered" in violations[0].message
        assert violations[0].proposal is None

    def test_the_kind_cannot_be_registered(self, tmp_path: Path) -> None:
        assert "STALE_WASM_SOURCE" not in ledger.FILE_KINDS
        assert "STALE_WASM_SOURCE" in contract.NON_REGISTRABLE_FILE_KINDS
        path = tmp_path / "ledger.json"
        entry = {"id": "excuse", "kind": "STALE_WASM_SOURCE", "target": "extensions/cql/src (cql)", "reason": "later", "owner": "nobody", "since": "2026-11-25", "expires": "2027-02-23"}
        path.write_text(json.dumps({"schema_version": ledger.SCHEMA_VERSION, "entries": [entry]}))

        with pytest.raises(ledger.LedgerError):
            ledger.load(path)

    def test_a_registered_excuse_does_not_cover_it(self) -> None:
        entry = ledger.Entry("excuse", "STALE_WASM_BUNDLE", ["web/x/cql.duckdb_extension.wasm"], "r", "o", date(2026, 11, 25), date(2027, 2, 23), None, None)
        observed = {"STALE_WASM_SOURCE": ["extensions/cql/src (cql)"], "STALE_WASM_BUNDLE": ["web/x/cql.duckdb_extension.wasm"]}

        violations = contract.evaluate_files([entry], observed, today=date(2026, 11, 25))

        assert [v.code for v in violations] == ["STALE_WASM_SOURCE"]

    def test_the_real_tree_is_current(self) -> None:
        """dev itself: the shipped bundles were built from the C++ at HEAD."""
        assert shipped_bundles.stale_sources(shipped_bundles.load_manifest()) == {}


def _script():
    spec = importlib.util.spec_from_file_location("build_wasm_extensions_under_test", shipped_bundles.REPO_ROOT / "scripts" / "build_wasm_extensions.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestVerifyCommand:
    def test_verify_fails_and_prints_the_rebuild(self, repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        (repo / "extensions/cql/src/lib.cpp").write_text("// cql, fixed\n")
        _commit_all(repo, "cql fix without a wasm rebuild")
        monkeypatch.setattr(shipped_bundles, "MANIFEST", repo / "manifest.json")
        script = _script()
        monkeypatch.setattr(script, "REPO", repo)

        exit_code = script.verify()

        assert exit_code == 1
        out = capsys.readouterr().out
        assert "ERROR [STALE_WASM_SOURCE] extensions/cql/src (cql)" in out
        assert "rebuild with --extension <cql>" in out

    def test_verify_passes_on_a_current_tree(self, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(shipped_bundles, "MANIFEST", repo / "manifest.json")
        script = _script()
        monkeypatch.setattr(script, "REPO", repo)

        assert script.verify() == 0
