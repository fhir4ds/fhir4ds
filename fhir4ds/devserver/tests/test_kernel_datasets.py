"""Hotfix QA-002/QA-004 regression tests (2026-10-12).

QA-002 (HIGH): mixed-data workspaces (.ndjson + .json side by side) crashed
Kernel construction — DatasetSpec rejects ndjson_paths + bundle_paths
together and the ValueError fired outside load_dataset's guard. The kernel
now groups paths by suffix into separate specs.

QA-004 (MEDIUM): multi-file dataset loads were non-transactional across
files — a later file's strict-load failure left earlier files' rows
committed. load_dataset now stages each spec inside BEGIN/COMMIT with
ROLLBACK on failure; the kernel rebuilds a clean connection on failure so
it never serves partial data.
"""

from pathlib import Path

import pytest

from fhir4ds.devserver.kernel import Kernel
from fhir4ds.operations import load_dataset
from fhir4ds.operations.envelopes import DatasetSpec


def _write_workspace(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    (data / "a.ndjson").write_text(
        '{"resourceType":"Patient","id":"a"}\n', encoding="utf-8"
    )
    (data / "b.json").write_text(
        '{"resourceType":"Bundle","type":"collection","entry":'
        '[{"resource":{"resourceType":"Patient","id":"b"}}]}',
        encoding="utf-8",
    )
    return data


class TestQa002MixedDataWorkspace:
    def test_mixed_ndjson_and_bundle_boots_and_loads_both(self, tmp_path):
        data = _write_workspace(tmp_path)
        kernel = Kernel(list(sorted(data.iterdir())), [])
        ids = {
            r[0]
            for r in kernel.conn.execute(
                "SELECT id FROM resources WHERE resourceType='Patient'"
            ).fetchall()
        }
        assert ids == {"a", "b"}
        assert kernel.load_diagnostics == []

    def test_homogeneous_suffixed_still_load(self, tmp_path):
        data = _write_workspace(tmp_path)
        k1 = Kernel([data / "a.ndjson"], [])
        k2 = Kernel([data / "b.json"], [])
        assert k1.conn.execute("SELECT COUNT(*) FROM resources").fetchone()[0] == 1
        assert k2.conn.execute("SELECT COUNT(*) FROM resources").fetchone()[0] == 1

    def test_uppercase_suffixes_route_identically(self, tmp_path):
        data = tmp_path / "data"
        data.mkdir()
        (data / "up.NDJSON").write_text(
            '{"resourceType":"Patient","id":"up"}\n', encoding="utf-8"
        )
        (data / "mix.JSOn").write_text(
            '{"resourceType":"Bundle","type":"collection","entry":'
            '[{"resource":{"resourceType":"Patient","id":"upb"}}]}',
            encoding="utf-8",
        )
        kernel = Kernel([data / "up.NDJSON", data / "mix.JSOn"], [])
        ids = {
            r[0]
            for r in kernel.conn.execute("SELECT id FROM resources").fetchall()
        }
        assert ids == {"up", "upb"}

    def test_valuesets_only_kernel_still_works(self, tmp_path):
        vs = tmp_path / "vs.json"
        vs.write_text(
            '{"resourceType":"ValueSet","id":"v1","url":"http://example.org/vs/v1","compose":{"include":'
            '[{"system":"http://loinc.org","concept":[{"code":"1"}]}]}}',
            encoding="utf-8",
        )
        kernel = Kernel([], [vs])
        assert kernel.conn.execute("SELECT 1").fetchone()[0] == 1
        assert kernel.load_diagnostics == []


class TestQa004DatasetAtomicity:
    def test_multi_file_failure_rolls_back_all_files(self, tmp_path):
        import fhir4ds

        (tmp_path / "good.ndjson").write_text(
            '{"resourceType":"Patient","id":"g1"}\n', encoding="utf-8"
        )
        (tmp_path / "zz-bad.ndjson").write_text(
            '{"resourceType":"Patient","id":"!!!invalid"}\n', encoding="utf-8"
        )
        conn = fhir4ds.create_connection()
        result = load_dataset(
            DatasetSpec(
                ndjson_paths=[
                    str(tmp_path / "good.ndjson"),
                    str(tmp_path / "zz-bad.ndjson"),
                ]
            ),
            conn,
        )
        assert not result.ok
        assert result.diagnostics
        tables = {r[0] for r in conn.execute("SHOW TABLES").fetchall()}
        n = (
            conn.execute("SELECT COUNT(*) FROM resources").fetchone()[0]
            if "resources" in tables
            else 0
        )
        # No partial state: the good file's rows did NOT survive the spec.
        assert n == 0

    def test_kernel_rebuilds_clean_connection_on_failure(self, tmp_path):
        (tmp_path / "good.ndjson").write_text(
            '{"resourceType":"Patient","id":"g1"}\n', encoding="utf-8"
        )
        (tmp_path / "zz-bad.ndjson").write_text(
            '{"resourceType":"Patient","id":"!!!invalid"}\n', encoding="utf-8"
        )
        kernel = Kernel(
            [tmp_path / "good.ndjson", tmp_path / "zz-bad.ndjson"], []
        )
        tables = {r[0] for r in kernel.conn.execute("SHOW TABLES").fetchall()}
        n = (
            kernel.conn.execute("SELECT COUNT(*) FROM resources").fetchone()[0]
            if "resources" in tables
            else 0
        )
        assert n == 0
        assert kernel.conn.execute("SELECT 1").fetchone()[0] == 1
        assert len(kernel.load_diagnostics) > 0
        # Diagnostics carry the line attribution from strict loading.
        diag_text = str(kernel.load_diagnostics[0])
        assert "ndjson" in diag_text or "Invalid FHIR" in diag_text

    def test_successful_multi_file_load_commits_all(self, tmp_path):
        import fhir4ds

        for i in range(3):
            (tmp_path / f"p{i}.ndjson").write_text(
                f'{{"resourceType":"Patient","id":"p{i}"}}\n', encoding="utf-8"
            )
        conn = fhir4ds.create_connection()
        result = load_dataset(
            DatasetSpec(
                ndjson_paths=[
                    str(tmp_path / "p0.ndjson"),
                    str(tmp_path / "p1.ndjson"),
                    str(tmp_path / "p2.ndjson"),
                ]
            ),
            conn,
        )
        assert result.ok, result.diagnostics
        assert result.total == 3
