"""Types for the narrow FHIR ``$cql`` facade."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any


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
class CQLTypeRef:
    """Small structural representation of a CQL type name."""

    name: str
    args: tuple["CQLTypeRef", ...] = ()
    fields: tuple[tuple[str, "CQLTypeRef"], ...] = ()
    raw: str | None = None

    @property
    def bare_name(self) -> str:
        name = self.name.split(".")[-1]
        if name.startswith("System."):
            name = name.split(".")[-1]
        return name

    @property
    def element_type(self) -> "CQLTypeRef":
        if self.bare_name == "List" and self.args:
            return self.args[0]
        return ANY_TYPE

    @property
    def point_type(self) -> "CQLTypeRef":
        if self.bare_name == "Interval" and self.args:
            return self.args[0]
        return ANY_TYPE

    def canonical(self) -> str:
        if self.bare_name == "Tuple":
            inner = ", ".join(f"{name}: {field.canonical()}" for name, field in self.fields)
            return f"Tuple{{{inner}}}"
        if self.args:
            return f"{self.bare_name}<{', '.join(arg.canonical() for arg in self.args)}>"
        return self.bare_name

    @classmethod
    def parse(cls, value: str | None) -> "CQLTypeRef":
        text = (value or "Any").strip()
        if not text:
            return ANY_TYPE
        parser = _TypeParser(text)
        parsed = parser.parse()
        return parsed


ANY_TYPE = CQLTypeRef("Any", raw="Any")


@dataclass(frozen=True)
class CQLResultMetadata:
    """Semantic metadata used to serialize CQL results to FHIR values."""

    cql_type: str = "Any"
    definition_name: str = RETURN_PARAMETER
    sql_result_type: str | None = None
    type_ref: CQLTypeRef = field(default=ANY_TYPE)

    @classmethod
    def from_definition_meta(cls, definition_name: str, meta: Any) -> "CQLResultMetadata":
        cql_type = getattr(meta, "cql_type", None) or "Any"
        sql_result_type = getattr(meta, "sql_result_type", None)
        if cql_type == "Any" and sql_result_type:
            cql_type = sql_result_type
        return cls(
            cql_type=cql_type,
            definition_name=definition_name,
            sql_result_type=sql_result_type,
            type_ref=CQLTypeRef.parse(cql_type),
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


class _TypeParser:
    """Tiny parser for CQL type names such as ``List<Tuple{a: Integer}>``."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0

    def parse(self) -> CQLTypeRef:
        result = self._parse_type()
        self._skip_ws()
        if self.pos != len(self.text):
            return CQLTypeRef(self.text, raw=self.text)
        return result

    def _parse_type(self) -> CQLTypeRef:
        self._skip_ws()
        name = self._parse_name()
        bare = name.split(".")[-1]
        self._skip_ws()
        if bare == "Tuple" and self._peek() == "{":
            self.pos += 1
            fields: list[tuple[str, CQLTypeRef]] = []
            while True:
                self._skip_ws()
                if self._peek() == "}":
                    self.pos += 1
                    break
                field_name = self._parse_name()
                self._skip_ws()
                if self._peek() == ":":
                    self.pos += 1
                self._skip_ws()
                fields.append((field_name, self._parse_type()))
                self._skip_ws()
                if self._peek() == ",":
                    self.pos += 1
                    continue
                if self._peek() == "}":
                    self.pos += 1
                    break
                break
            return CQLTypeRef("Tuple", fields=tuple(fields), raw=self.text)
        if self._peek() == "<":
            self.pos += 1
            args: list[CQLTypeRef] = []
            while True:
                args.append(self._parse_type())
                self._skip_ws()
                if self._peek() == ",":
                    self.pos += 1
                    continue
                if self._peek() == ">":
                    self.pos += 1
                    break
                break
            return CQLTypeRef(bare, args=tuple(args), raw=self.text)
        return CQLTypeRef(bare, raw=self.text)

    def _parse_name(self) -> str:
        self._skip_ws()
        start = self.pos
        while self.pos < len(self.text):
            char = self.text[self.pos]
            if char.isalnum() or char in "._":
                self.pos += 1
                continue
            break
        return self.text[start:self.pos] or "Any"

    def _skip_ws(self) -> None:
        while self.pos < len(self.text) and self.text[self.pos].isspace():
            self.pos += 1

    def _peek(self) -> str:
        return self.text[self.pos] if self.pos < len(self.text) else ""
