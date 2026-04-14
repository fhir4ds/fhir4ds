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
    parameters : dict, optional
        CQL parameter overrides (e.g. ``{"Measurement Period": (start, end)}``).

    Returns
    -------
    DuckDB relation or DataFrame with population membership per patient.
    """
    from fhir4ds.cql import evaluate_measure as _evaluate

    return _evaluate(
        library_path=library_path,
        conn=conn,
        output_columns=output_columns or {},
        parameters=parameters or {},
    )
