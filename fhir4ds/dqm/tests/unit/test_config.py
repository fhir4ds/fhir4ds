"""Unit tests for DQM run configuration parsing."""

from __future__ import annotations

import pytest

from fhir4ds.dqm.config import DQMConfigError, load_run_config, parse_run_config


def _valid_config() -> dict:
    return {
        "measures": ["measure.json"],
        "source": {"type": "directory", "path": "fhir"},
        "outputs": {"directory": "out"},
    }


def test_load_run_config_wraps_invalid_json(tmp_path):
    config_path = tmp_path / "run.json"
    config_path.write_text("{")

    with pytest.raises(DQMConfigError, match="Invalid JSON DQM config"):
        load_run_config(config_path)


def test_parse_run_config_resolves_library_paths(tmp_path):
    raw = _valid_config()
    raw["libraries"] = {"paths": ["lib"]}

    config = parse_run_config(raw, base_dir=tmp_path)

    assert config.libraries == [tmp_path / "lib"]


def test_parse_run_config_rejects_non_object_libraries():
    raw = _valid_config()
    raw["libraries"] = []

    with pytest.raises(DQMConfigError, match="'libraries' must be an object"):
        parse_run_config(raw)


def test_parse_run_config_rejects_invalid_library_paths():
    raw = _valid_config()
    raw["libraries"] = {"paths": [1]}

    with pytest.raises(DQMConfigError, match="Expected a path string"):
        parse_run_config(raw)


def test_parse_run_config_rejects_non_object_terminology():
    raw = _valid_config()
    raw["terminology"] = []

    with pytest.raises(DQMConfigError, match="'terminology' must be an object"):
        parse_run_config(raw)
