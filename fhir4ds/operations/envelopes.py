"""Operations layer: typed, versioned envelopes and diagnostics.

Every user-facing capability returns an envelope carrying ``schema``,
``ok``/``passed`` status, and typed :class:`Diagnostics`. Codes are the
agent/UI contract (stable strings); messages are for humans.

Spec: docs/architecture/plans/FEATURE_OPERATIONS_LAYER.md §3.2.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal


class DiagnosticCode(str, Enum):
    """Stable machine-readable failure classification."""

    PARSE_ERROR = "parse_error"
    TRANSLATION_ERROR = "translation_error"
    EVALUATION_ERROR = "evaluation_error"
    INPUT_ERROR = "input_error"
    DATASET_ERROR = "dataset_error"
    NOT_FOUND = "not_found"
    UNSUPPORTED_FEATURE = "unsupported_feature"
    TIMEOUT = "timeout"  # reserved: never emitted by operations core (v1)


Severity = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class ErrorLocation:
    """Structured source location for editor surfaces (Monico squiggles).

    1-based line/column; ``end_*`` when the engine supplies a range.
    """

    start_line: int
    start_column: int
    end_line: int | None = None
    end_column: int | None = None
    library: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "start_line": self.start_line,
            "start_column": self.start_column,
        }
        if self.end_line is not None:
            out["end_line"] = self.end_line
        if self.end_column is not None:
            out["end_column"] = self.end_column
        if self.library is not None:
            out["library"] = self.library
        return out


@dataclass(frozen=True)
class Diagnostics:
    """One diagnostic event attached to an envelope.

    ``data`` carries structured engine fields verbatim (e.g.
    ``expected``/``found`` from ParseError, ``symbol``/``expected_type``
    from SemanticError) so consumers never parse message strings.
    """

    code: DiagnosticCode
    message: str
    detail: str | None = None
    severity: Severity = "error"
    location: ErrorLocation | None = None
    data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "code": self.code.value,
            "severity": self.severity,
            "message": self.message,
        }
        if self.detail is not None:
            out["detail"] = self.detail
        if self.location is not None:
            out["location"] = self.location.to_dict()
        if self.data:
            out["data"] = dict(self.data)
        return out


def _diag_tuple(value: tuple[Diagnostics, ...]) -> tuple[Diagnostics, ...]:
    return tuple(value)


class _EnvelopeFields:
    """Mixin: shared envelope fields (composition, not dataclass inheritance).

    Capability result dataclasses declare these same fields via this mixin
    so every serialized envelope carries them with stable key order.
    """

    schema: int = 1
    ok: bool = True
    passed: bool | None = None
    diagnostics: tuple[Diagnostics, ...] = ()

    def base_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"schema": self.schema, "ok": self.ok}
        if self.passed is not None:
            out["passed"] = self.passed
        if self.diagnostics:
            out["diagnostics"] = [d.to_dict() for d in self.diagnostics]
        return out

    @property
    def severity_cap(self) -> str | None:
        """Highest diagnostic severity present (None when no diagnostics)."""
        order = {"info": 0, "warning": 1, "error": 2}
        if not self.diagnostics:
            return None
        return max((d.severity for d in self.diagnostics), key=order.__getitem__)


@dataclass(frozen=True)
class LibraryText:
    """One inline CQL library source (main or include)."""

    name: str
    text: str
    version: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("LibraryText.name must be a non-empty string")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError(f"LibraryText({self.name!r}).text must be a non-empty string")


def _library_text_from_dict(value: Any) -> LibraryText:
    if isinstance(value, LibraryText):
        return value
    if isinstance(value, dict):
        keys = set(value.keys())
        allowed = {"name", "text", "version"}
        if not keys <= allowed:
            raise ValueError(
                f"library entry has unknown keys {sorted(keys - allowed)}; allowed: {sorted(allowed)}"
            )
        if "name" not in value or "text" not in value:
            raise ValueError("library entry requires 'name' and 'text'")
        return LibraryText(
            name=value["name"], text=value["text"], version=value.get("version")
        )
    raise TypeError(
        f"library entry must be a LibraryText or dict, got {type(value).__name__}"
    )


@dataclass(frozen=True)
class DatasetSpec:
    """Dataset inputs: inline resources/ValueSets and/or file paths.

    Browser workers use the inline forms (no filesystem); local agents
    use paths. Validated before any loader call.
    """

    resources: list[dict[str, Any]] | None = None
    ndjson_paths: list[str] | None = None
    bundle_paths: list[str] | None = None
    valueset_resources: list[dict[str, Any]] | None = None
    valueset_paths: list[str] | None = None

    def __post_init__(self) -> None:
        provided = [
            label
            for label, value in (
                ("resources", self.resources),
                ("ndjson_paths", self.ndjson_paths),
                ("bundle_paths", self.bundle_paths),
            )
            if value
        ]
        if len(provided) > 1:
            raise ValueError(
                "DatasetSpec accepts only one of resources, ndjson_paths, "
                f"bundle_paths; got {provided}"
            )
        for label, value in (
            ("resources", self.resources),
            ("valueset_resources", self.valueset_resources),
        ):
            if value is None:
                continue
            if not isinstance(value, list) or not all(isinstance(r, dict) for r in value):
                raise ValueError(f"DatasetSpec.{label} must be a list of JSON objects")
        from pathlib import Path

        for label in ("ndjson_paths", "bundle_paths", "valueset_paths"):
            value = getattr(self, label)
            if value is None:
                continue
            if not isinstance(value, list) or not all(isinstance(p, str) for p in value):
                raise ValueError(f"DatasetSpec.{label} must be a list of path strings")
            for p in value:
                if not Path(p).exists():
                    raise FileNotFoundError(f"DatasetSpec.{label} path does not exist: {p}")

    @property
    def is_empty(self) -> bool:
        return not (
            self.resources
            or self.ndjson_paths
            or self.bundle_paths
            or self.valueset_resources
            or self.valueset_paths
        )

    def describe(self) -> str:
        if self.resources is not None:
            return f"{len(self.resources)} inline resources"
        if self.ndjson_paths:
            return f"ndjson:{','.join(self.ndjson_paths)}"
        if self.bundle_paths:
            return f"bundle:{','.join(self.bundle_paths)}"
        return "valuesets-only"


def dataset_spec_from_dict(value: Any) -> DatasetSpec:
    """Build a DatasetSpec from an adapter-supplied dict, validating shape."""
    if isinstance(value, DatasetSpec):
        return value
    if value is None:
        raise ValueError("dataset must not be None; omit the field or pass a spec")
    if not isinstance(value, dict):
        raise TypeError(f"dataset must be a dict or DatasetSpec, got {type(value).__name__}")
    allowed = {
        "resources",
        "ndjson_paths",
        "bundle_paths",
        "valueset_resources",
        "valueset_paths",
    }
    unknown = set(value.keys()) - allowed
    if unknown:
        raise ValueError(
            f"dataset has unknown keys {sorted(unknown)}; allowed: {sorted(allowed)}"
        )
    return DatasetSpec(
        resources=value.get("resources"),
        ndjson_paths=value.get("ndjson_paths"),
        bundle_paths=value.get("bundle_paths"),
        valueset_resources=value.get("valueset_resources"),
        valueset_paths=value.get("valueset_paths"),
    )


@dataclass(frozen=True)
class TestCase:
    """One declarative expectation (spec §7)."""

    patient: str
    expect: bool
    population: str | None = None
    define: str | None = None
    comment: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.patient, str) or not self.patient:
            raise ValueError("case.patient must be a non-empty string")
        if not isinstance(self.expect, bool):
            raise ValueError("case.expect must be a boolean")
        if (self.population is None) == (self.define is None):
            raise ValueError("case requires exactly one of 'population' or 'define'")
        if self.population is not None and not isinstance(self.population, str):
            raise ValueError("case.population must be a string")

    @property
    def target(self) -> str:
        return self.population if self.population is not None else self.define  # type: ignore[return-value]


@dataclass(frozen=True)
class TestsInput:
    """Parsed cases file (schema 1)."""

    cases: tuple[TestCase, ...]
    schema: int = 1

    def __post_init__(self) -> None:
        if self.schema != 1:
            raise ValueError(f"unsupported tests schema: {self.schema!r} (expected 1)")


def tests_input_from_dict(value: Any) -> TestsInput:
    """Parse the §7 cases JSON with strict shape validation."""
    if isinstance(value, TestsInput):
        return value
    if not isinstance(value, dict):
        raise TypeError(f"tests must be a dict, got {type(value).__name__}")
    allowed = {"schema", "cases"}
    unknown = set(value.keys()) - allowed
    if unknown:
        raise ValueError(f"tests has unknown keys {sorted(unknown)}; allowed: {sorted(allowed)}")
    schema = value.get("schema", 1)
    if not isinstance(schema, int) or isinstance(schema, bool):
        raise ValueError("tests.schema must be an integer")
    raw_cases = value.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError("tests.cases must be a list")
    if not raw_cases:
        raise ValueError("tests.cases must contain at least one case")
    cases: list[TestCase] = []
    for i, raw in enumerate(raw_cases):
        if not isinstance(raw, dict):
            raise TypeError(f"cases[{i}] must be an object")
        case_keys = set(raw.keys())
        allowed_case = {"patient", "population", "define", "expect", "comment"}
        unknown = case_keys - allowed_case
        if unknown:
            raise ValueError(
                f"cases[{i}] has unknown keys {sorted(unknown)}; allowed: {sorted(allowed_case)}"
            )
        missing = {"patient", "expect"} - case_keys
        if missing:
            raise ValueError(f"cases[{i}] is missing required keys {sorted(missing)}")
        cases.append(
            TestCase(
                patient=raw["patient"],
                expect=raw["expect"],
                population=raw.get("population"),
                define=raw.get("define"),
                comment=raw.get("comment"),
            )
        )
    return TestsInput(cases=tuple(cases), schema=schema)


def envelope_dict(payload: Any, base: _EnvelopeFields, extra: dict[str, Any]) -> dict[str, Any]:
    """Serialize a capability result: base fields first, payload fields after."""
    out = base.base_dict()
    out.update(extra)
    return out
