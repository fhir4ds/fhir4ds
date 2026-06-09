"""Tests for the CQL server CLI wiring."""

from __future__ import annotations

import pytest

from fhir4ds.cli.main import main


def test_cql_server_cli_registered_help(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["cql-server", "--help"])

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "--base-path" in captured.out
