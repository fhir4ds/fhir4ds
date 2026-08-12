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

from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from .errors import (
    SQLQueryCycleError,
    SQLQueryMaterializationError,
    SQLQueryTypeError,
)
from .types import SQLQuery, SQLView, _SQLLibraryBase
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
            resolver: A callable mapping canonical URLs to parsed resources.
                For ViewDefinition canonicals, returns either a
                :class:`ViewDefinition` or a dict (which the runner parses).
                For SQLView canonicals, returns a dict (which the runner
                parses as a Library). May raise to signal "not found".
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

        # Execute. DuckDB's prepared-statement API expects $1, $2, ... or
        # named parameters. The spec's SQLQuery profile uses named parameters
        # in the SQL body via DuckDB's $name syntax. We pass a dict to
        # con.execute which DuckDB expands safely.
        if params:
            return list(self._con.execute(sql_body, params).fetchall())
        return list(self._con.execute(sql_body).fetchall())

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

        # Determine kind: parsed ViewDefinition vs Library dict vs VD dict.
        if isinstance(resolved, ViewDefinition):
            view_sql = self._generate_view_sql(resolved)
        elif isinstance(resolved, dict):
            # ViewDefinition has no FHIR resourceType field the way Library
            # does; detect it structurally (has `select` array and `resource`).
            if "select" in resolved and "resource" in resolved:
                from ..viewdef.parser import parse_view_definition

                vd = parse_view_definition(resolved)
                view_sql = self._generate_view_sql(vd)
            elif resolved.get("resourceType") == "Library":
                from .parser import parse_library

                inner = parse_library(resolved)
                # Recursively materialize the inner SQLView's dependencies first.
                self._materialize_dependencies(inner.related_artifact, in_progress)
                content_for_view = select_best_content(inner.content)
                view_sql = content_for_view.data
            else:
                raise SQLQueryMaterializationError(
                    f"Cannot materialize canonical {canonical!r}: expected "
                    f"ViewDefinition (with `select` and `resource`) or "
                    f"Library (resourceType='Library'). Got keys: "
                    f"{sorted(resolved.keys())}"
                )
        else:
            raise SQLQueryMaterializationError(
                f"Resolver returned unsupported type {type(resolved).__name__} "
                f"for canonical {canonical!r}"
            )

        quoted_label = quote_identifier(label)
        self._con.execute(f'CREATE OR REPLACE VIEW {quoted_label} AS {view_sql}')

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
                # Tolerate extra params by ignoring them; the prepared SQL
                # would only consume the names it references.
                continue
            param = declared[name]
            # Coerce via the FHIR-type-to-DuckDB registry. The registry
            # is the authority; we do not branch on param.type here.
            try:
                duckdb_type = fhir_type_to_duckdb(param.type)
            except ValueError as exc:
                raise SQLQueryTypeError(str(exc)) from exc
            bound[name] = self._coerce(value, duckdb_type, param.name)

        return bound

    def _coerce(self, value: Any, duckdb_type: str, name: str) -> Any:
        """Light-touch type validation; DuckDB handles the actual coercion.

        DuckDB's prepared-statement binding performs canonical type coercion
        on its own. We short-circuit only the obviously-incompatible cases
        (e.g., a string passed for a BOOLEAN parameter) so callers get a
        typed :class:`SQLQueryTypeError` with parameter name context rather
        than a generic DuckDB conversion error.
        """
        if value is None:
            return None
        if duckdb_type == "BOOLEAN" and not isinstance(value, bool):
            raise SQLQueryTypeError(
                f"Parameter {name!r} declared boolean; "
                f"got {type(value).__name__}={value!r}"
            )
        if duckdb_type in {"INTEGER", "BIGINT"} and not isinstance(value, int):
            raise SQLQueryTypeError(
                f"Parameter {name!r} declared "
                f"{'integer64' if duckdb_type == 'BIGINT' else 'integer'}; "
                f"got {type(value).__name__}={value!r}"
            )
        if duckdb_type == "DOUBLE" and not isinstance(value, (int, float)):
            raise SQLQueryTypeError(
                f"Parameter {name!r} declared decimal; "
                f"got {type(value).__name__}={value!r}"
            )
        return value


__all__ = ["SQLQueryRunner", "DependencyResolver"]
