"""Execute SQLQuery / SQLView resources against a DuckDB connection.

The runner:

1. **Materializes dependencies.** Each ``relatedArtifact`` entry resolves
   to a :class:`fhir4ds.viewdef.ViewDefinition` or a nested SQLView. For
   ViewDefinitions, the runner calls ``SQLGenerator().generate(vd)`` and
   emits ``CREATE OR REPLACE VIEW "<label>" AS <generated SQL>`` against
   the caller-supplied DuckDB connection. For SQLView dependencies, the
   runner recursively materializes the SQLView first, then creates a
   view from the SQLView's own SQL body. Cycle detection prevents
   infinite recursion.

2. **Selects content.** Among the ``content[]`` entries, prefers
   ``application/sql;dialect=duckdb``; falls back to ``application/sql``;
   rejects other dialects with :class:`UnsupportedDialectError`.

3. **Binds parameters.** Uses DuckDB prepared statements. Each parameter
   is coerced from its declared FHIR type to the corresponding DuckDB
   type via :func:`fhir4ds.viewdef.types.fhir_type_to_duckdb`. No string
   interpolation.

4. **Executes** and returns rows as Python tuples.
"""

from __future__ import annotations

import datetime
import re
from decimal import Decimal
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from .errors import (
    SQLQueryCycleError,
    SQLQueryMaterializationError,
    SQLQueryTypeError,
)
from .types import SQLQuery, SQLParameter, SQLView, _SQLLibraryBase
from .validator import select_best_content
from ..viewdef.types import ViewDefinition, fhir_type_to_duckdb
from ..viewdef.utils import quote_identifier


# Type alias for the caller-supplied canonical → Library resolver.
# Returns a parsed ViewDefinition dict, SQLQuery, or SQLView.
DependencyResolver = Callable[[str], Union[Dict[str, Any], ViewDefinition, SQLQuery, SQLView]]


class SQLQueryRunner:
    """Execute SQLQuery / SQLView resources against a DuckDB connection.

    The runner is stateless across executions except for views materialized
    on the caller's connection (each materialization uses
    ``CREATE OR REPLACE VIEW`` so re-running the same SQLQuery is
    idempotent). Callers sharing a connection across many SQLQuery runs
    may accumulate views; ``DROP VIEW "<label>"`` cleans them up.
    """

    def __init__(
        self,
        connection: Any,
        resolver: DependencyResolver,
        *,
        source_table: str = "resources",
    ) -> None:
        """Initialize the runner.

        Args:
            connection: A DuckDB connection. Caller-supplied so tests can
                share fixtures and production can attach to a pooled conn.
            resolver: A callable mapping canonical URLs to the referenced
                resource, per :data:`DependencyResolver`. Accepted returns
                for any canonical: a parsed :class:`ViewDefinition`, a
                parsed :class:`SQLQuery` / :class:`SQLView`, a
                ViewDefinition dict (detected structurally via ``select`` +
                ``resource`` keys), or a Library dict (``resourceType ==
                'Library'``, which the runner parses). May raise to signal
                "not found".
            source_table: The physical DuckDB table the generated
                ViewDefinition SQL reads from (default ``"resources"``).
        """
        self._con = connection
        self._resolver = resolver
        self._source_table = source_table

    def execute(
        self,
        library: Union[SQLQuery, SQLView, Dict[str, Any]],
        parameters: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[Any, ...]]:
        """Execute a SQLQuery or SQLView against the connection.

        Args:
            library: A parsed :class:`SQLQuery` / :class:`SQLView` or a
                Library dict (which the runner parses).
            parameters: Parameter values keyed by name. Required when the
                SQLQuery declares parameters; ignored for SQLView.

        Returns:
            A list of row tuples.

        Raises:
            SQLQueryMaterializationError: when a relatedArtifact cannot
                be resolved.
            SQLQueryCycleError: when dependency resolution detects a
                cycle.
            SQLQueryTypeError: when a parameter value cannot be coerced
                to its declared FHIR type.
            UnsupportedDialectError: when no supported DuckDB content
                type is present.
        """
        from .parser import parse_library

        if isinstance(library, dict):
            library = parse_library(library)
        if not isinstance(library, (SQLQuery, SQLView)):
            raise SQLQueryMaterializationError(
                f"Expected SQLQuery or SQLView, got {type(library).__name__}"
            )

        # Materialize all relatedArtifact dependencies.
        self._materialize_dependencies(library.related_artifact, in_progress=set())

        # Select best-supported content.
        content = select_best_content(library.content)
        sql_body = content.data

        # Bind parameters (SQLQuery only; SQLView has parameter 0..0).
        if isinstance(library, SQLQuery):
            params = self._bind_parameters(library, parameters or {})
        else:
            params = {}

        # Execute. DuckDB's prepared-statement API accepts named parameters
        # via the $name syntax; the spec's own SQLQuery examples and the
        # SQL-annotation tooling convention (sql-on-fhir-v2
        # sql-query-examples.fsh, StructureDefinition-SQLQuery-notes.md
        # "SQL Annotations") author bodies with :name placeholders. Rewrite
        # declared :name placeholders to $name so spec-example bodies
        # execute. Only placeholder *tokens* are rewritten — values are
        # still bound via the prepared-statement dict, never interpolated.
        sql_body = self._rewrite_named_placeholders(sql_body, params)
        if params:
            return list(self._con.execute(sql_body, params).fetchall())
        return list(self._con.execute(sql_body).fetchall())

    @staticmethod
    def _rewrite_named_placeholders(sql_body: str, params: Dict[str, Any]) -> str:
        """Rewrite ``:name`` placeholders to DuckDB's ``$name`` form.

        Scans the SQL body character-wise, skipping regions where a colon
        is not a placeholder: single-quoted string literals (with ``
        '' `` escaping), double-quoted identifiers, ``--`` line comments,
        ``/* */`` block comments, and the ``::`` cast operator. Only
        placeholders whose name matches a *declared and supplied*
        parameter are rewritten; other colons are left verbatim so the
        engine surfaces the original syntax error.
        """
        if not params or ":" not in sql_body:
            return sql_body
        out: list[str] = []
        i, n = 0, len(sql_body)
        while i < n:
            ch = sql_body[i]
            if ch == "'" or ch == '"':
                quote = ch
                out.append(ch)
                i += 1
                while i < n:
                    out.append(sql_body[i])
                    if sql_body[i] == quote:
                        if i + 1 < n and sql_body[i + 1] == quote:
                            out.append(sql_body[i + 1])
                            i += 2
                            continue
                        i += 1
                        break
                    i += 1
                continue
            if ch == "-" and sql_body.startswith("--", i):
                end = sql_body.find("\n", i)
                end = n if end == -1 else end
                out.append(sql_body[i:end])
                i = end
                continue
            if ch == "/" and sql_body.startswith("/*", i):
                end = sql_body.find("*/", i + 2)
                end = n if end == -1 else end + 2
                out.append(sql_body[i:end])
                i = end
                continue
            if ch == ":":
                # `::` is the SQL cast operator, never a placeholder.
                if sql_body.startswith("::", i):
                    out.append("::")
                    i += 2
                    continue
                j = i + 1
                while j < n and (sql_body[j].isalnum() or sql_body[j] == "_"):
                    j += 1
                name = sql_body[i + 1 : j]
                if name and name in params:
                    out.append("$" + name)
                    i = j
                    continue
            out.append(ch)
            i += 1
        return "".join(out)

    def _materialize_dependencies(
        self,
        related_artifacts: Sequence[Any],
        in_progress: set,
    ) -> None:
        for ra in related_artifacts:
            label = ra.label
            resource = ra.resource
            if resource in in_progress:
                raise SQLQueryCycleError(
                    f"Cycle detected in relatedArtifact resolution: "
                    f"label {label!r} -> {resource!r} (already being resolved)"
                )
            self._materialize_one(label, resource, in_progress | {resource})

    def _materialize_one(
        self,
        label: str,
        canonical: str,
        in_progress: set,
    ) -> None:
        try:
            resolved = self._resolver(canonical)
        except Exception as exc:
            raise SQLQueryMaterializationError(
                f"Resolver failed for relatedArtifact.label={label!r} "
                f"resource={canonical!r}: {exc}"
            ) from exc

        # Every failure path below (kind detection, parsing, dialect
        # selection, SQL generation, view creation) is part of materializing
        # the dependency for this label+canonical, so all of it is
        # translated to SQLQueryMaterializationError with that context.
        # Cycle errors from nested dependency resolution must surface as
        # themselves, and nested materialization errors already carry
        # their own context — both re-raise untouched.
        try:
            view_sql = self._resolve_view_sql(resolved, canonical, in_progress)
            quoted_label = quote_identifier(label)
            self._con.execute(f'CREATE OR REPLACE VIEW {quoted_label} AS {view_sql}')
        except (SQLQueryCycleError, SQLQueryMaterializationError):
            raise
        except Exception as exc:
            raise SQLQueryMaterializationError(
                f"Failed to materialize relatedArtifact.label={label!r} "
                f"resource={canonical!r}: {exc}"
            ) from exc

    def _resolve_view_sql(
        self,
        resolved: Any,
        canonical: str,
        in_progress: set,
    ) -> str:
        """Turn a resolver result into the SQL body for a dependency view.

        Accepted shapes: parsed :class:`ViewDefinition`, parsed
        :class:`SQLQuery`/:class:`SQLView`, a ViewDefinition dict (detected
        structurally via ``select`` + ``resource``), or a Library dict
        (``resourceType == 'Library'``). A dict carrying *both* the Library
        marker and ViewDefinition structure is ambiguous and rejected with a
        typed error rather than silently misparsed as either.
        """
        if isinstance(resolved, ViewDefinition):
            return self._generate_view_sql(resolved)
        if isinstance(resolved, (SQLQuery, SQLView)):
            # Recursively materialize the inner library's dependencies
            # first, then use its best-supported SQL body as the view.
            self._materialize_dependencies(resolved.related_artifact, in_progress)
            return select_best_content(resolved.content).data
        if isinstance(resolved, dict):
            is_library = resolved.get("resourceType") == "Library"
            is_structural_vd = "select" in resolved and "resource" in resolved
            if is_library and is_structural_vd:
                raise SQLQueryMaterializationError(
                    f"Cannot materialize canonical {canonical!r}: dict is "
                    f"ambiguous — carries resourceType='Library' plus "
                    f"ViewDefinition structure ('select' and 'resource')"
                )
            if is_structural_vd:
                from ..viewdef.parser import parse_view_definition

                vd = parse_view_definition(resolved)
                return self._generate_view_sql(vd)
            if is_library:
                from .parser import parse_library

                inner = parse_library(resolved)
                # Recursively materialize the inner SQLView's dependencies first.
                self._materialize_dependencies(inner.related_artifact, in_progress)
                return select_best_content(inner.content).data
            raise SQLQueryMaterializationError(
                f"Cannot materialize canonical {canonical!r}: expected "
                f"ViewDefinition (with `select` and `resource`) or "
                f"Library (resourceType='Library'). Got keys: "
                f"{sorted(resolved.keys())}"
            )
        raise SQLQueryMaterializationError(
            f"Resolver returned unsupported type {type(resolved).__name__} "
            f"for canonical {canonical!r}"
        )

    def _generate_view_sql(self, view_definition: ViewDefinition) -> str:
        from ..viewdef.generator import SQLGenerator

        gen = SQLGenerator(source_table=self._source_table)
        return gen.generate(view_definition)

    def _bind_parameters(
        self,
        library: SQLQuery,
        values: Dict[str, Any],
    ) -> Dict[str, Any]:
        bound: Dict[str, Any] = {}
        declared = {p.name: p for p in library.parameter}

        # All declared parameters must be supplied (DuckDB prepared
        # statements raise on missing params, but we surface a clearer
        # error here).
        for name, param in declared.items():
            if name not in values:
                raise SQLQueryTypeError(
                    f"Missing required parameter {name!r} "
                    f"(declared type {param.type!r})"
                )

        for name, value in values.items():
            if name not in declared:
                # Tolerate caller-supplied extras by ignoring them. Note the
                # converse does NOT hold: DuckDB rejects a bound parameter
                # the SQL body never references ("excess parameters"), so a
                # Library that declares a parameter unused in its SQL body
                # fails at execution with DuckDB's InvalidInputException.
                continue
            param = declared[name]
            # Coerce via the FHIR-type-to-DuckDB registry. The registry
            # is the authority; we do not branch on param.type here.
            try:
                duckdb_type = fhir_type_to_duckdb(param.type)
            except ValueError as exc:
                raise SQLQueryTypeError(str(exc)) from exc
            bound[name] = self._coerce(value, duckdb_type, param)

        return bound

    # FHIR integer bounds per declared DuckDB type (from the registry).
    _INTEGER_RANGES: Dict[str, Tuple[int, int]] = {
        "INTEGER": (-(2 ** 31), 2 ** 31 - 1),   # FHIR integer: signed 32-bit
        "BIGINT": (-(2 ** 63), 2 ** 63 - 1),    # FHIR integer64: signed 64-bit
    }

    # DuckDB types whose values must be coerced through an explicit CAST so
    # the bound parameter actually carries the declared type (and malformed
    # strings fail loudly instead of comparing as VARCHAR).
    _TEMPORAL_DUCKDB_TYPES = frozenset({"DATE", "TIMESTAMP", "TIME"})

    # Acceptable Python value kinds per temporal DuckDB type. Every accepted
    # value is routed through the registry CAST so the declared type always
    # reaches DuckDB. ``datetime.datetime`` is excluded for DATE (a dateTime
    # value is higher precision than the declared date — callers must honour
    # the declared type per SQL-on-FHIR v2 "Parameter Types"); a plain
    # ``datetime.date`` is accepted for TIMESTAMP because date precision is
    # a valid less-precise dateTime (normalized to midnight, consistent with
    # the earliest-instant partial-date doctrine).
    _TEMPORAL_KINDS: Dict[str, Tuple[type, ...]] = {
        "DATE": (datetime.date,),
        "TIMESTAMP": (datetime.datetime, datetime.date),
        "TIME": (datetime.time,),
    }

    def _coerce(self, value: Any, duckdb_type: str, param: SQLParameter) -> Any:
        """Validate and coerce a parameter value to its declared type.

        The registry-derived ``duckdb_type`` is the authority. Numeric and
        boolean incompatibilities fail fast in Python; temporal values are
        coerced through a DuckDB ``CAST`` (prepared statement — the value is
        bound, never interpolated) so callers get a typed
        :class:`SQLQueryTypeError` with parameter name and declared-vs-got
        detail rather than a generic DuckDB error or a silent VARCHAR bind.
        """
        name = param.name
        if value is None:
            return None
        # bool is an int subclass; it must not pass as a numeric parameter.
        if duckdb_type == "BOOLEAN" and not isinstance(value, bool):
            raise SQLQueryTypeError(
                f"Parameter {name!r} declared {param.type!r} (boolean); "
                f"got {type(value).__name__}={value!r}"
            )
        if duckdb_type in self._INTEGER_RANGES:
            if isinstance(value, bool) or not isinstance(value, int):
                raise SQLQueryTypeError(
                    f"Parameter {name!r} declared {param.type!r} "
                    f"({'integer64' if duckdb_type == 'BIGINT' else 'integer'}); "
                    f"got {type(value).__name__}={value!r}"
                )
            low, high = self._INTEGER_RANGES[duckdb_type]
            if not low <= value <= high:
                raise SQLQueryTypeError(
                    f"Parameter {name!r} declared {param.type!r} "
                    f"({'integer64' if duckdb_type == 'BIGINT' else 'integer'}, "
                    f"range {low}..{high}); got {value!r} out of range"
                )
            return value
        if duckdb_type == "DOUBLE":
            if isinstance(value, bool):
                raise SQLQueryTypeError(
                    f"Parameter {name!r} declared {param.type!r} (decimal); "
                    f"got bool={value!r}"
                )
            if isinstance(value, Decimal):
                return float(value)
            if not isinstance(value, (int, float)):
                raise SQLQueryTypeError(
                    f"Parameter {name!r} declared {param.type!r} (decimal); "
                    f"got {type(value).__name__}={value!r}"
                )
            return value
        if duckdb_type in self._TEMPORAL_DUCKDB_TYPES:
            kinds = self._TEMPORAL_KINDS[duckdb_type]
            if (
                isinstance(value, bool)
                or not isinstance(value, (str, *kinds))
                or (
                    duckdb_type == "DATE"
                    and isinstance(value, datetime.datetime)
                )
            ):
                raise SQLQueryTypeError(
                    f"Parameter {name!r} declared {param.type!r} ({duckdb_type}); "
                    f"got {type(value).__name__}={value!r}"
                )
            if isinstance(value, str):
                value = self._expand_partial_temporal(value, duckdb_type)
            elif (
                isinstance(value, datetime.datetime)
                and value.tzinfo is not None
            ):
                # DuckDB's CAST of a tz-aware native datetime to TIMESTAMP
                # converts through the *host* timezone, while the string
                # form of the same FHIR dateTime casts to its wall-clock
                # time. Normalize aware datetimes to naive wall time so the
                # same value binds identically regardless of spelling or
                # host timezone (matches the string path deterministically).
                value = value.replace(tzinfo=None)
            # Coerce every accepted value (string or native) through
            # DuckDB's CAST semantics using a prepared statement so the
            # declared registry type always reaches DuckDB; duckdb_type
            # comes from the internal registry, never from caller input.
            try:
                coerced = self._con.execute(
                    f"SELECT CAST(? AS {duckdb_type})", [value]
                ).fetchone()[0]
            except Exception as exc:
                raise SQLQueryTypeError(
                    f"Parameter {name!r} declared {param.type!r} ({duckdb_type}); "
                    f"got {type(value).__name__}={value!r}: {exc}"
                ) from exc
            return coerced
        return value

    @staticmethod
    def _expand_partial_temporal(value: str, duckdb_type: str) -> str:
        """Expand a valid FHIR partial date/dateTime to full precision.

        FHIR ``date``/``dateTime`` allow year (``2020``) and year-month
        (``2020-06``) precision; DuckDB's CAST requires full precision.
        Partial values are normalized to the earliest instant of the
        stated period (the conventional SQL-on-FHIR normalization, e.g.
        ``birthDate`` handling). ``time`` has no partial forms and strings
        that do not match a strict partial grammar fall through to the
        DuckDB cast, which rejects them with a typed error.
        """
        if duckdb_type == "DATE":
            if re.fullmatch(r"\d{4}", value):
                return value + "-01-01"
            if re.fullmatch(r"\d{4}-\d{2}", value):
                return value + "-01"
        elif duckdb_type == "TIMESTAMP":
            if re.fullmatch(r"\d{4}", value):
                return value + "-01-01T00:00:00"
            if re.fullmatch(r"\d{4}-\d{2}", value):
                return value + "-01T00:00:00"
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                return value + "T00:00:00"
        return value


__all__ = ["SQLQueryRunner", "DependencyResolver"]
