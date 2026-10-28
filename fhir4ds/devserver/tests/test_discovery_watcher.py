"""Discovery + watcher tests (truncated writes, data-hint, never-crash)."""

from __future__ import annotations

import time

from fhir4ds.devserver.config import load_config
from fhir4ds.devserver.discovery import scan_workspace
from fhir4ds.devserver.watcher import EventBus, Watcher

CQL = (
    "library Demographics version '1.0.0'\n"
    "using FHIR version '4.0.1'\n\n"
    "define \"Male\": Patient.gender = 'male'\n"
)


def make_ws(tmp_path, cql_text=CQL, data=True):
    (tmp_path / "cql").mkdir(exist_ok=True)
    (tmp_path / "cql" / "Demographics.cql").write_text(cql_text)
    if data:
        (tmp_path / "data").mkdir(exist_ok=True)
        (tmp_path / "data" / "patients.ndjson").write_text(
            '{"resourceType": "Patient", "id": "p1", "gender": "male"}\n'
        )
    return load_config(tmp_path)


class TestDiscovery:
    def test_scan_finds_library_and_dataset(self, tmp_path):
        cfg = make_ws(tmp_path)
        snap = scan_workspace(cfg)
        assert len(snap.libraries) == 1
        lib = snap.libraries[0]
        assert lib.name == "Demographics"
        assert lib.parse_ok
        assert "Male" in lib.definitions
        assert [p.name for p in snap.datasets] == ["patients.ndjson"]

    def test_truncated_write_never_crashes(self, tmp_path):
        cfg = make_ws(tmp_path, cql_text="library Broken vers")
        snap = scan_workspace(cfg)
        assert len(snap.libraries) == 1
        lib = snap.libraries[0]
        assert not lib.parse_ok
        assert lib.error  # surfaced for the UI

    def test_missing_dirs_are_absent(self, tmp_path):
        cfg = load_config(tmp_path)
        snap = scan_workspace(cfg)
        assert snap.libraries == []
        assert snap.datasets == []

    def test_to_dict_shape(self, tmp_path):
        cfg = make_ws(tmp_path)
        d = scan_workspace(cfg).to_dict()
        assert set(d) >= {"libraries", "valuesets", "measures", "datasets"}
        assert d["libraries"][0]["name"] == "Demographics"


class TestWatcher:
    def test_cql_change_event(self, tmp_path):
        cfg = make_ws(tmp_path)
        bus = EventBus()
        w = Watcher(cfg, bus)
        q = bus.subscribe()
        (tmp_path / "cql" / "Demographics.cql").write_text(
            CQL + 'define "Extra": true\n'
        )
        w.rescan()
        ev = q.get(timeout=5)
        assert ev.kind == "changed"
        lib = w.snapshot.library("Demographics")
        assert "Extra" in lib.definitions

    def test_truncated_mid_save_file(self, tmp_path):
        """Conductor note: malformed CQL mid-save must not crash the watcher."""
        cfg = make_ws(tmp_path)
        bus = EventBus()
        w = Watcher(cfg, bus)
        (tmp_path / "cql" / "Broken.cql").write_text("library Broken vers")
        w.rescan()  # must not raise
        broken = w.snapshot.library("Broken")
        assert broken is not None and not broken.parse_ok

    def test_data_file_hint_no_autoreload(self, tmp_path):
        """Conductor note: locked decision 4 — new data NEVER auto-reloads."""
        cfg = make_ws(tmp_path)
        bus = EventBus()
        w = Watcher(cfg, bus)
        q = bus.subscribe()
        (tmp_path / "data" / "more.ndjson").write_text(
            '{"resourceType": "Patient", "id": "p2"}\n'
        )
        w.rescan()
        ev = q.get(timeout=5)
        assert ev.kind == "data-hint"
        # S22e: the ndjson was TRANSPORT — normalized into the canonical
        # Patient/<id>/ folder (the monolith archived); the hint names
        # the canonical file(s).
        assert any("Patient" in p and "p2" in p for p in ev.paths)
        assert not (tmp_path / "data" / "more.ndjson").exists()

    def test_removal_event(self, tmp_path):
        cfg = make_ws(tmp_path)
        bus = EventBus()
        w = Watcher(cfg, bus)
        q = bus.subscribe()
        (tmp_path / "cql" / "Demographics.cql").unlink()
        w.rescan()
        ev = q.get(timeout=5)
        assert ev.kind == "changed"
        assert w.snapshot.library("Demographics") is None


class TestSilentSwitch:
    def test_switch_rescan_publishes_no_diff_events(self, tmp_path, tmp_path_factory):
        """S25: a workspace re-root is NOT a data change.

        The switch flow re-roots the watcher onto another workspace and
        rescans SILENTLY — the old-vs-new file-set diff must not surface
        as changed/data-hint events (the spurious 'Data files changed
        on disk' banner Joel hit on every switch).
        """
        import queue

        # Workspace A (with data).
        cfg_a = make_ws(tmp_path)
        # Workspace B: a sibling with DIFFERENT data + library.
        ws_b = tmp_path_factory.mktemp("ws_b")
        (ws_b / "cql").mkdir()
        (ws_b / "cql" / "Other.cql").write_text(
            "library Other version '1.0.0'\ndefine \"X\": 1\n"
        )
        (ws_b / "data").mkdir()
        (ws_b / "data" / "p2.ndjson").write_text(
            '{"resourceType": "Patient", "id": "z9", "gender": "female"}\n'
        )

        bus = EventBus()
        w = Watcher(cfg_a, bus)
        q = bus.subscribe()
        # Re-root like _route_workspace_switch does, then silent rescan.
        w._cfg = load_config(ws_b)
        w.rescan(silent=True)
        # No changed/data-hint events; only the caller's own `switched`
        # publish (which the route does itself) is authoritative.
        assert q.empty()
        assert w.snapshot.library("Other") is not None
        assert w.snapshot.library("Demographics") is None
