"""Types for the narrow FHIR ``$cql`` facade."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any

from fhir4ds.cql.types.typeref import ANY_TYPE, CQLTypeRef, _TypeParser

__all__ = [
    "ANY_TYPE",
    "CQLTypeRef",
    "CQLResultMetadata",
    "CQLEvaluationResult",
    "InputParameter",
    "CQLRequest",
    "CQLServerConfig",
    "CQLErrorCategory",
    "CQLFacadeError",
    "json_number",
    "FHIR_PARAMETERS",
    "FHIR_OPERATION_OUTCOME",
    "RETURN_PARAMETER",
    "EVALUATION_ERROR_PARAMETER",
    "CQF_CQL_TYPE_URL",
    "DATA_ABSENT_REASON_URL",
    "CQF_EMPTY_LIST_URL",
    "CQF_EMPTY_TUPLE_URL",
]


FHIR_PARAMETERS = "Parameters"
FHIR_OPERATION_OUTCOME = "OperationOutcome"
RETURN_PARAMETER = "return"
EVALUATION_ERROR_PARAMETER = "evaluation error"
CQF_CQL_TYPE_URL = "http://hl7.org/fhir/StructureDefinition/cqf-cqlType"
DATA_ABSENT_REASON_URL = "http://hl7.org/fhir/StructureDefinition/data-absent-reason"
CQF_EMPTY_LIST_URL = "http://hl7.org/fhir/StructureDefinition/cqf-isEmptyList"
CQF_EMPTY_TUPLE_URL = "http://hl7.org/fhir/StructureDefinition/cqf-isEmptyTuple"


class CQLErrorCategory(str, Enum):
    """Classified facade errors surfaced through OperationOutcome."""

    INVALID_REQUEST = "invalid-request"
    UNSUPPORTED_FEATURE = "unsupported-feature"
    PARSE_ERROR = "parse-error"
    TRANSLATION_ERROR = "translation-error"
    EVALUATION_ERROR = "evaluation-error"
    SERIALIZER_GAP = "serializer-gap"


@dataclass(frozen=True)
class CQLResultMetadata:
    """Semantic metadata used to serialize CQL results to FHIR values."""

    cql_type: str = "Any"
    definition_name: str = RETURN_PARAMETER
    sql_result_type: str | None = None
    type_ref: CQLTypeRef = field(default=ANY_TYPE)

    @classmethod
    def from_definition_meta(cls, definition_name: str, meta: Any) -> "CQLResultMetadata":
        """Build metadata preferring the builder-attached ``cql_type_ref``.

        Fallback chain: ``cql_type_ref`` (TypeMapBuilder) -> ``cql_type``
        (legacy lowering inference) -> ``sql_result_type`` (SQL shape hint)
        -> ``Any``. The builder already consumes ``sql_result_type`` as an
        input type source, so the facade never trusts the physical hint
        blindly when a builder ref exists.
        """
        builder_ref = getattr(meta, "cql_type_ref", None)
        cql_type = getattr(meta, "cql_type", None) or "Any"
        sql_result_type = getattr(meta, "sql_result_type", None)
        if isinstance(builder_ref, CQLTypeRef):
            type_ref = builder_ref
            if cql_type == "Any":
                cql_type = type_ref.canonical()
        else:
            if cql_type == "Any" and sql_result_type:
                cql_type = sql_result_type
            type_ref = CQLTypeRef.parse(cql_type)
        return cls(
            cql_type=cql_type,
            definition_name=definition_name,
            sql_result_type=sql_result_type,
            type_ref=type_ref,
        )


@dataclass(frozen=True)
class CQLEvaluationResult:
    """Result of evaluating one runner expression."""

    value: Any
    metadata: CQLResultMetadata
    sql: str


@dataclass(frozen=True)
class InputParameter:
    """Parsed input parameter that can be declared in synthetic CQL."""

    name: str
    cql_type: str
    literal: str


@dataclass(frozen=True)
class CQLRequest:
    """Parsed FHIR ``$cql`` operation request."""

    expression: str
    parameters: tuple[InputParameter, ...] = ()
    terminology_endpoint_url: str | None = None


@dataclass(frozen=True)
class CQLServerConfig:
    """Configuration for the local FHIR ``$cql`` facade."""

    host: str = "127.0.0.1"
    port: int = 8080
    base_path: str = "/fhir"
    use_cpp_extensions: bool = True
    debug: bool = False
    fhir_version: str = "4.0.1"
    library_name: str = "FHIR4DSCqlRunner"
    max_request_bytes: int = 1_000_000
    metadata_first_serialization: bool = True

    @property
    def cql_paths(self) -> tuple[str, ...]:
        base = "/" + self.base_path.strip("/")
        if base == "/":
            return ("/$cql",)
        return ("/$cql", f"{base}/$cql")


class CQLFacadeError(Exception):
    """Base error for the FHIR ``$cql`` facade."""

    def __init__(
        self,
        message: str,
        *,
        category: CQLErrorCategory,
        status_code: int = 400,
        diagnostics: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.category = category
        self.status_code = status_code
        self.diagnostics = diagnostics


def json_number(value: Any) -> int | float:
    """Return a JSON-serializable FHIR number."""
    if isinstance(value, bool):
        raise TypeError("Boolean is not a JSON number")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, float):
        return value
    return float(value)
