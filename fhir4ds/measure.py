"""
CQL measure evaluation via the cql-py translator.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import duckdb


def evaluate_measure(
    library_path: str | Path,
    conn: "duckdb.DuckDBPyConnection",
    *,
    output_columns: dict[str, str] | None = None,
    parameters: dict[str, Any] | None = None,
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
    **kwargs
        Additional keyword arguments passed through to the underlying evaluator
        (e.g. ``verbose``, ``patient_ids``, ``include_paths``).

    Returns
    -------
    DuckDB relation or DataFrame with population membership per patient.
    """
    from fhir4ds.cql import evaluate_measure as _evaluate

    call_kwargs: dict[str, Any] = {
        "library_path": library_path,
        "conn": conn,
        "parameters": parameters or {},
    }
    # Preserve None semantics: None means "all definitions"
    if output_columns is not None:
        call_kwargs["output_columns"] = output_columns
    call_kwargs.update(kwargs)

    return _evaluate(**call_kwargs)
