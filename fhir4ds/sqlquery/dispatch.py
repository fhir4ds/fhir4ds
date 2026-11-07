"""Single-dispatch entry point for the SQL-on-FHIR analytics layer.

AMUX-35: before this module, callers had to know which runner world
their artifact lived in — plain SQLQuery/SQLView Libraries go through
:class:`fhir4ds.sqlquery.SQLQueryRunner`, manifest compositions (the
OMOP family) through :func:`fhir4ds.viewdef.runner.run_composition`,
and bare ViewDefinitions through :func:`fhir4ds.generate_view_sql`.
:func:`run_sql` sniffs the artifact shape once and routes.

Routing table
-------------

============================  ==========================================
artifact                      route
============================  ==========================================
:class:`SQLQuery` /           :class:`SQLQueryRunner` (returns rows)
:class:`SQLView` instance
Library dict                  parsed, then ``SQLQueryRunner`` (rows)
:class:`ViewDefinition` /     executed via ``generate_view_sql`` (rows)
ViewDefinition dict
manifest path (str/Path to    :func:`run_composition` (table -> view map)
a JSON file with ``views``)
Library/ViewDefinition JSON   sniffed by content after loading (rows)
path
============================  ==========================================

A manifest *dict* is rejected with a typed error — compositions resolve
their view stems relative to the manifest's directory on disk, so they
require a path.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from .errors import SQLError
from .lint import lint_sql_body
from .runner import DependencyResolver, SQLQueryRunner
from .types import SQLQuery, SQLView
from ..viewdef.types import ViewDefinition

_logger = logging.getLogger(__name__)

__all__ = ["run_sql"]


class SQLDispatchError(SQLError):
    """run_sql received an artifact it cannot route to a runner."""


def _fail_resolver(canonical: str) -> Any:
    raise SQLDispatchError(
        f"SQLQuery dependency {canonical!r} cannot be resolved: run_sql was "
        "called without a resolver. Pass run_sql(..., resolver=...) mapping "
        "canonical URLs to the referenced ViewDefinition/Library."
    )


def _lint_if_requested(library: Union[SQLQuery, SQLView], *, lint: bool) -> None:
    if not lint:
        return
    try:
        from .validator import select_best_content

        content = select_best_content(library.content)
        sql = content.data or content.sql_text
    except SQLError:
        # No supported content / dialect — the runner raises the typed
        # error; linting has nothing to add.
        return
    for warning in lint_sql_body(sql):
        _logger.warning("SQL body lint [%s]: %s", warning.code, warning)


def _run_library(
    con: Any,
    library: Union[SQLQuery, SQLView, Dict[str, Any]],
    *,
    parameters: Optional[Dict[str, Any]],
    resolver: Optional[DependencyResolver],
    source_table: str,
    lint: bool,
) -> List[Tuple[Any, ...]]:
    if resolver is None:
        resolver = _fail_resolver
    runner = SQLQueryRunner(con, resolver, source_table=source_table)
    parsed = library
    if isinstance(library, dict):
        from .parser import parse_library

        parsed = parse_library(library)
    _lint_if_requested(parsed, lint=lint)
    return runner.execute(parsed, parameters)


def _run_view_definition(
    con: Any,
    view_definition: Union[ViewDefinition, Dict[str, Any]],
    *,
    source_table: str,
) -> List[Tuple[Any, ...]]:
    from ..viewdef.generator import SQLGenerator

    if isinstance(view_definition, dict):
        from ..viewdef.parser import parse_view_definition

        view_definition = parse_view_definition(view_definition)
    sql = SQLGenerator(source_table=source_table).generate(view_definition)
    return [tuple(row) for row in con.execute(sql).fetchall()]


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except OSError as exc:
        raise SQLDispatchError(f"cannot read {path}: {exc}") from exc
    except ValueError as exc:
        raise SQLDispatchError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SQLDispatchError(
            f"{path} does not contain a JSON object (got {type(data).__name__})"
        )
    return data


def _is_manifest(data: Dict[str, Any]) -> bool:
    return isinstance(data.get("views"), dict)


def _is_view_definition(data: Dict[str, Any]) -> bool:
    return "select" in data and "resource" in data


def run_sql(
    con: Any,
    artifact: Union[SQLQuery, SQLView, ViewDefinition, Dict[str, Any], str, Path],
    *,
    parameters: Optional[Dict[str, Any]] = None,
    resolver: Optional[DependencyResolver] = None,
    source_table: str = "resources",
    lint: bool = True,
) -> Union[List[Tuple[Any, ...]], Dict[str, str]]:
    """Execute any SQL-on-FHIR analytics artifact against ``con``.

    One entry point across the analytics layer (AMUX-35):

    * SQLQuery / SQLView (instance, Library dict, or JSON file path) →
      executed; returns the result rows.
    * ViewDefinition (instance, dict, or JSON file path) → generated
      and executed; returns the result rows.
    * Composition manifest path (JSON file with a ``views`` map, e.g.
      the OMOP mapping) → :func:`run_composition`; returns the
      table -> materialized-view-name map.

    Args:
        con: A DuckDB connection.
        artifact: The artifact to execute (see routing table above).
        parameters: Values for a SQLQuery's declared parameters
            (SQLQuery route only).
        resolver: Canonical-URL resolver for a SQLQuery's
            ``relatedArtifact`` dependencies. Required only when the
            library declares dependencies; without one, dependency
            resolution fails with a typed, actionable error.
        source_table: Physical table that ViewDefinition SQL reads
            from (default ``"resources"``).
        lint: When True (default), statically lint hand-authored SQL
            bodies and log non-DuckDB dialect findings at WARNING.
            See :func:`fhir4ds.sqlquery.lint_sql_body`.

    Returns:
        Result rows (Library / ViewDefinition routes) or a table ->
        view-name map (manifest route).

    Raises:
        SQLDispatchError: the artifact shape is not routable (including
            manifest dicts, which need a path).
        SQLError subclasses: whatever the underlying runner raises
            (parse/validation/cycle/coercion errors propagate as-is).
    """
    # Parsed instances — direct routes.
    if isinstance(artifact, (SQLQuery, SQLView)):
        return _run_library(
            con, artifact, parameters=parameters, resolver=resolver,
            source_table=source_table, lint=lint,
        )
    if isinstance(artifact, ViewDefinition):
        return _run_view_definition(con, artifact, source_table=source_table)

    # Paths — load JSON, sniff content (manifest must keep its path).
    if isinstance(artifact, (str, Path)):
        path = Path(artifact)
        if path.suffix.lower() != ".json":
            raise SQLDispatchError(
                f"artifact path {path!r} must be a .json file (Library, "
                "ViewDefinition, or composition manifest)"
            )
        data = _load_json(path)
        if _is_manifest(data):
            from ..viewdef.runner import run_composition

            return run_composition(con, path, source_table)
        if data.get("resourceType") == "Library":
            return _run_library(
                con, data, parameters=parameters, resolver=resolver,
                source_table=source_table, lint=lint,
            )
        if _is_view_definition(data):
            return _run_view_definition(con, data, source_table=source_table)
        raise SQLDispatchError(
            f"{path} is neither a Library, a ViewDefinition, nor a "
            "composition manifest (no resourceType/select/views keys)"
        )

    # Dicts — sniff by shape.
    if isinstance(artifact, dict):
        if artifact.get("resourceType") == "Library":
            return _run_library(
                con, artifact, parameters=parameters, resolver=resolver,
                source_table=source_table, lint=lint,
            )
        if _is_manifest(artifact):
            raise SQLDispatchError(
                "composition manifests need a PATH (their view stems resolve "
                "relative to the manifest directory); pass the manifest file "
                "path, not a dict"
            )
        if _is_view_definition(artifact):
            return _run_view_definition(con, artifact, source_table=source_table)
        raise SQLDispatchError(
            "artifact dict is not routable: expected a Library "
            "(resourceType == 'Library'), a ViewDefinition (select + resource), "
            f"or pass a manifest path. Keys present: {sorted(artifact)[:8]}"
        )

    raise TypeError(
        "artifact must be a SQLQuery/SQLView/ViewDefinition, a Library or "
        "ViewDefinition dict, or a path to a Library/ViewDefinition/manifest "
        f"JSON file; got {type(artifact).__name__}"
    )
