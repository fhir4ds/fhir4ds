"""Domain 11 EXPLORER regression battery (v0.0.26 loop, iter 35).

Adversarial API-fuzz findings from .temp/qa/d11_explorer_v0026:

- QA-D11E-001: ``create_http_server`` / top-level ``create_cql_http_server``
  accepted wrong-typed ``config`` values (dict/str/int — the realistic config
  shapes users pass) and leaked a raw ``AttributeError: 'X' object has no
  attribute 'host'``. Same class as the serve ``create_app`` fix
  (QA-D8H-003). Must raise ``TypeError`` naming ``CQLServerConfig``.
- QA-D11E-002: the public conn-taking registration surfaces
  ``fhir4ds.cql.register_udfs`` and ``fhir4ds.cql.duckdb.register`` (+
  its ``register_cql`` alias) leaked raw errors for non-connection inputs
  (``AttributeError: 'NoneType' object has no attribute 'execute'``) and raw
  ``ConnectionException`` for closed connections, while ``fhir4ds.register``
  already implements the INV-8 typed wrap (QA-D8S-002 doctrine).
- QA-D11E-003: ``fhir4ds cql-server --port=99999`` crashed with a raw
  ``OverflowError`` traceback from ``socket.bind`` instead of the graceful
  CLI error every other hostile argv form produces.
"""

from __future__ import annotations

import argparse
import duckdb
import pytest

import fhir4ds
from fhir4ds.cql import register_udfs
from fhir4ds.cql.duckdb import register as duckdb_register
from fhir4ds.cql.fhir_server import create_http_server
from fhir4ds.cli import cql_server as cql_server_cli


# ---------------------------------------------------------------- QA-D11E-001


@pytest.mark.parametrize("bad_config", [{"host": "x"}, "localhost:8000", 42, object()])
def test_create_http_server_wrong_typed_config_raises_typeerror(bad_config):
    with pytest.raises(TypeError, match="CQLServerConfig"):
        create_http_server(config=bad_config)


def test_top_level_create_cql_http_server_wrong_typed_config_raises_typeerror():
    with pytest.raises(TypeError, match="CQLServerConfig"):
        fhir4ds.create_cql_http_server(config={"host": "x"})


def test_create_http_server_none_config_still_default():
    # None keeps the documented default-config behavior. Binding the default
    # port may legitimately fail with OSError on a busy host; the contract
    # under test is that None passes the type guard (no TypeError).
    try:
        server = create_http_server()
    except OSError:
        return  # default port busy on this host — acceptable
    try:
        assert server.config.port == 8080
    finally:
        server.server_close()


# ---------------------------------------------------------------- QA-D11E-002


@pytest.mark.parametrize(
    "register_fn", [register_udfs, duckdb_register], ids=["cql.register_udfs", "cql.duckdb.register"]
)
@pytest.mark.parametrize("bad_conn", [None, object(), "x"])
def test_register_surfaces_reject_non_connections_typed(register_fn, bad_conn):
    with pytest.raises(TypeError, match="Expected a DuckDB connection"):
        register_fn(bad_conn)


@pytest.mark.parametrize(
    "register_fn", [register_udfs, duckdb_register], ids=["cql.register_udfs", "cql.duckdb.register"]
)
def test_register_surfaces_wrap_closed_connections(register_fn):
    conn = duckdb.connect()
    conn.close()
    with pytest.raises(duckdb.ConnectionException, match="closed"):
        register_fn(conn)


# ---------------------------------------------------------------- QA-D11E-003


def test_cql_server_cli_rejects_out_of_range_port_gracefully(capsys):
    args = argparse.Namespace(port=99999, host="127.0.0.1", base_path="/fhir",
                              python_udfs=False, debug=False)
    rc = cql_server_cli.run(args)
    assert rc == 2
    err = capsys.readouterr().err
    assert "port" in err.lower()
    assert "0-65535" in err


def test_cql_server_cli_rejects_negative_port_graceful(capsys):
    args = argparse.Namespace(port=-1, host="127.0.0.1", base_path="/fhir",
                              python_udfs=False, debug=False)
    rc = cql_server_cli.run(args)
    assert rc == 2
    assert "port" in capsys.readouterr().err.lower()
