"""
CQL measure evaluation via the cql-py translator.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import duckdb
    from fhir4ds.cql.terminology.endpoint import TerminologyEndpoint


def evaluate_measure(
    library_path: str | Path,
    conn: "duckdb.DuckDBPyConnection",
    *,
    output_columns: dict[str, str] | None = None,
    parameters: dict[str, Any] | None = None,
    audit_mode: str = "none",
    terminology_endpoint: "TerminologyEndpoint | None" = None,
    closure_loaded: bool = False,
    **kwargs: Any,
) -> Any:
    """
    Evaluate a CQL measure against FHIR data in a DuckDB connection.

    Parameters
    ----------
    library_path : str | Path
        Path to the CQL library file.
    conn : duckdb.DuckDBPyConnection
        DuckDB connection with FHIR data and registered UDFs.
    output_columns : dict, optional
        Mapping of output column names to CQL expression names.
        Pass ``None`` (the default) to return all CQL definitions.
    parameters : dict, optional
        CQL parameter overrides (e.g. ``{"Measurement Period": (start, end)}``).
    audit_mode : str, optional
        Controls audit granularity: ``"none"`` (default), ``"population"``
        (lightweight evidence from retrieve CTEs), or ``"full"`` (expression-
        level wrapping for maximum evidence detail).
    terminology_endpoint : TerminologyEndpoint, optional
        Phase 1 medterm4ds terminology endpoint for ValueSet expansion
        fallback. ``None`` (the default) preserves local-only resolution.
    closure_loaded : bool, optional
        Phase 3 medterm4ds subsumption flag. When ``True``, generated SQL
        routes ``~``, ``is`` and ``Descendents`` through the
        ``terminology_closure`` table (which the caller must have loaded).
        Default ``False`` preserves byte-identical SQL output.
    **kwargs
        Additional keyword arguments passed through to the underlying evaluator
        (e.g. ``verbose``, ``patient_ids``, ``include_paths``).

    Returns
    -------
    DuckDB relation or DataFrame with population membership per patient.
    """
    from fhir4ds.cql import evaluate_measure as _evaluate

    if conn is None:
        raise TypeError(
            "Expected a DuckDB connection for 'conn', got None"
        )
    if not hasattr(conn, "execute"):
        raise TypeError(
            f"Expected a DuckDB connection for 'conn', got {type(conn).__name__}"
        )

    call_kwargs: dict[str, Any] = {
        "library_path": library_path,
        "conn": conn,
        "parameters": parameters or {},
        "audit_mode": audit_mode,
        "terminology_endpoint": terminology_endpoint,
        "closure_loaded": closure_loaded,
    }
    # Preserve None semantics: None means "all definitions"
    if output_columns is not None:
        call_kwargs["output_columns"] = output_columns
    call_kwargs.update(kwargs)

    return _evaluate(**call_kwargs)
