"""CQL evaluation contexts."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

try:
    import duckdb
except ImportError:
    duckdb = None  # type: ignore[assignment]


class EvaluationContext(ABC):
    """Abstract base class for CQL evaluation contexts."""

    @abstractmethod
    def get_patient_id(self) -> Optional[str]:
        """Get the patient ID for this context.

        Returns:
            Patient ID as string, or None for population context
        """
        pass

    @abstractmethod
    def evaluate_expression(self, expression: str) -> Any:
        """Evaluate a CQL expression.

        Args:
            expression: CQL expression to evaluate

        Returns:
            Result of the evaluation
        """
        pass

    @abstractmethod
    def get_context_type(self) -> str:
        """Get the type of context.

        Returns:
            Either "Patient" or "Population"
        """
        pass


class PatientContext(EvaluationContext):
    """CQL evaluation context for individual patient records."""

    def __init__(self, con: duckdb.DuckDBPyConnection, patient_id: str, resources_table: str = "resources"):
        """Initialize patient context.

        Args:
            con: DuckDB connection
            patient_id: ID of the patient
            resources_table: Name of the table containing FHIR resources
        """
        self.con = con
        self.patient_id = patient_id
        self.resources_table = resources_table

    def get_patient_id(self) -> str:
        """Get the patient ID for this context."""
        return self.patient_id

    def get_context_type(self) -> str:
        """Get the type of context."""
        return "Patient"

    def evaluate_expression(self, expression: str) -> Any:
        """Evaluate a CQL expression using fhirpath UDF.

        Args:
            expression: CQL expression to evaluate

        Returns:
            Result of the evaluation
        """
        # TODO: Implement fhirpath UDF evaluation
        # This will require integrating with the fhirpath extension
        raise NotImplementedError(
            f"FHIRPath evaluation not yet implemented for expression: {expression}"
        )


class PopulationContext(EvaluationContext):
    """CQL evaluation context for population-level operations."""

    def __init__(self, con: duckdb.DuckDBPyConnection, resources_table: str = "resources"):
        """Initialize population context.

        Args:
            con: DuckDB connection
            resources_table: Name of the table containing FHIR resources
        """
        self.con = con
        self.resources_table = resources_table

    def get_patient_id(self) -> None:
        """Get the patient ID for this context."""
        return None

    def get_context_type(self) -> str:
        """Get the type of context."""
        return "Population"

    def evaluate_expression(self, expression: str) -> Any:
        """Evaluate a CQL expression.

        Args:
            expression: CQL expression to evaluate

        Returns:
            Result of the evaluation
        """
        raise NotImplementedError(
            "Population-level evaluation not yet implemented"
        )