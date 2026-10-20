"""Dev-server configuration merge tests (flags > config > convention)."""

from __future__ import annotations

import pytest

from fhir4ds.devserver.config import DevConfigError, load_config


class TestConventionOnly:
    def test_convention_dirs(self, tmp_path):
        cfg = load_config(tmp_path)
        # S22d-1: legacy shape first, FHIR-type conventions appended.
        assert [p.name for p in cfg.cql_dirs][0] == "cql"
        assert "Library" in [p.name for p in cfg.cql_dirs]
        assert [p.name for p in cfg.valueset_dirs][0] == "valuesets"
        assert "ValueSet" in [p.name for p in cfg.valueset_dirs]
        assert [p.name for p in cfg.measure_dirs][0] == "measures"
        assert "Measure" in [p.name for p in cfg.measure_dirs]
        assert [p.name for p in cfg.data_dirs][0] == "data"
        assert "Patient" in [p.name for p in cfg.data_dirs]
        assert all(str(p).startswith(str(tmp_path)) for p in cfg.all_dirs())

    def test_default_port(self, tmp_path):
        assert load_config(tmp_path).port == 8765
        assert load_config(tmp_path, port=9000).port == 9000

    def test_invalid_port(self, tmp_path):
        with pytest.raises(DevConfigError):
            load_config(tmp_path, port=0)
        with pytest.raises(DevConfigError):
            load_config(tmp_path, port=70_000)


class TestManifest:
    def test_manifest_adds_to_convention(self, tmp_path):
        (tmp_path / "fhir4ds.toml").write_text(
            '[dev]\ncql_dirs = ["shared-cql"]\ndata_dirs = ["more-data"]\n'
        )
        cfg = load_config(tmp_path)
        # Type conventions sit between legacy and manifest entries.
        names = [p.name for p in cfg.cql_dirs]
        assert names[0] == "cql" and names[-1] == "shared-cql"
        assert "Library" in names
        dnames = [p.name for p in cfg.data_dirs]
        assert dnames[0] == "data" and dnames[-1] == "more-data"
        assert "Patient" in dnames

    def test_flags_append_after_manifest(self, tmp_path):
        (tmp_path / "fhir4ds.toml").write_text('[dev]\ncql_dirs = ["from-toml"]\n')
        cfg = load_config(tmp_path, cql_dirs=["from-flag"])
        names = [p.name for p in cfg.cql_dirs]
        assert names[0] == "cql" and names[-1] == "from-flag"
        assert "from-toml" in names and "Library" in names

    def test_duplicate_dirs_deduped(self, tmp_path):
        (tmp_path / "fhir4ds.toml").write_text('[dev]\ncql_dirs = ["cql"]\n')
        cfg = load_config(tmp_path, cql_dirs=["cql"])
        assert [p.name for p in cfg.cql_dirs].count("cql") == 1

    def test_malformed_toml_exit2_class(self, tmp_path):
        (tmp_path / "fhir4ds.toml").write_text("[dev\nbroken")
        with pytest.raises(DevConfigError):
            load_config(tmp_path)

    def test_unknown_key_rejected(self, tmp_path):
        (tmp_path / "fhir4ds.toml").write_text('[dev]\nbogus = ["x"]\n')
        with pytest.raises(DevConfigError, match="unknown keys"):
            load_config(tmp_path)

    def test_non_list_rejected(self, tmp_path):
        (tmp_path / "fhir4ds.toml").write_text('[dev]\ncql_dirs = "cql"\n')
        with pytest.raises(DevConfigError, match="array"):
            load_config(tmp_path)

    def test_absolute_dir_kept_absolute(self, tmp_path):
        (tmp_path / "fhir4ds.toml").write_text('[dev]\ncql_dirs = ["/abs/cql"]\n')
        cfg = load_config(tmp_path)
        assert str(cfg.cql_dirs[-1]) == "/abs/cql"


class TestCliParser:
    def test_dev_subcommand_registered(self):
        from fhir4ds.cli.main import main

        import argparse

        parser = argparse.ArgumentParser(prog="fhir4ds")
        from fhir4ds.cli import dev

        sub = parser.add_subparsers(dest="command")
        dev.configure_parser(sub.add_parser("dev"))
        args = parser.parse_args(["dev", "/tmp/ws", "--port", "9100", "--cql-dir", "x"])
        assert args.dir == "/tmp/ws"
        assert args.port == 9100
        assert args.cql_dirs == ["x"]
        assert args.no_open is False
