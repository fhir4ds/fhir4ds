"""FHIR ``Parameters`` request parsing for the operation endpoints.

SQL-on-FHIR v2 operations take their input as a ``Parameters`` resource in the
request body (``Content-Type: application/fhir+json``), with parameter values
in the ``value[x]`` element matching each parameter's declared type. This
module turns that body into a typed bag and validates it against a per-
operation parameter table.

Design rules:

* FHIR resources stay plain dicts — no pydantic FHIR models.
* Only the parameters an operation declares are accepted. Unknown names and
  known-but-unsupported names are rejected with the IG's 400 forms.
* Type checking is structural against the declared ``value[x]``; a value in
  the wrong ``value[x]`` element is a 400 ``value``/``invalid`` error naming
  what was supplied.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .errors import bad_request, missing, unsupported

#: ``value[x]`` element(s) accepted for each declared parameter type.
#: ``reference`` accepts the reference-ish primitives because servers commonly
#: receive a bare URL where a Reference is declared; ``resource``/``parameters``
#: carry the nested resource in ``Parameters.parameter.resource``.
VALUE_FIELDS_BY_TYPE: dict[str, tuple[str, ...]] = {
    "code": ("valueCode",),
    "boolean": ("valueBoolean",),
    "integer": ("valueInteger",),
    "string": ("valueString",),
    "instant": ("valueInstant",),
    "reference": ("valueReference", "valueCanonical", "valueUri", "valueString"),
    "resource": (),
    "parameters": (),
}

RESOURCE_VALUED_TYPES = frozenset({"resource", "parameters"})


def _coerce_query_value(raw: Any, spec: ParameterSpec) -> Any:
    """Coerce one query-string scalar to its declared FHIR value type."""
    text = raw if isinstance(raw, str) else str(raw)
    if spec.value_type == "integer":
        try:
            return int(text)
        except ValueError:
            raise bad_request(
                f"query parameter {spec.name!r} must be an integer; got {text!r}",
                expression=[spec.name],
            ) from None
    if spec.value_type == "boolean":
        lowered = text.lower()
        if lowered in ("true", "false"):
            return lowered == "true"
        raise bad_request(
            f"query parameter {spec.name!r} must be true/false; got {text!r}",
            expression=[spec.name],
        )
    return text


@dataclass(frozen=True)
class ParameterSpec:
    """One declared operation parameter."""

    name: str
    value_type: str
    supported: bool = True
    documentation: str = ""

    def __post_init__(self) -> None:
        if self.value_type not in VALUE_FIELDS_BY_TYPE:
            raise ValueError(
                f"Unsupported parameter type {self.value_type!r} for {self.name!r}; "
                f"expected one of {sorted(VALUE_FIELDS_BY_TYPE)}"
            )


class ParametersBag:
    """Parsed, validated access to a request ``Parameters`` resource."""

    def __init__(self, entries: Mapping[str, dict]) -> None:
        self._entries: dict[str, dict] = dict(entries)

    # -- construction ----------------------------------------------------

    @classmethod
    def from_body(cls, body: Any, *, label: str = "request body") -> ParametersBag:
        """Parse a request body into a bag.

        Accepts ``None``/empty (no parameters), raw bytes (any content type),
        a JSON string, or an already-decoded dict (FastAPI decodes
        ``application/json`` / ``application/fhir+json`` bodies itself).
        """
        payload = decode_json_body(body, label=label)
        if payload is None:
            return cls({})
        if not isinstance(payload, dict):
            raise bad_request(
                f"{label} must be a FHIR Parameters resource; got {type(payload).__name__}",
                code="structure",
            )
        resource_type = payload.get("resourceType")
        if resource_type != "Parameters":
            raise bad_request(
                f"{label} must be a FHIR Parameters resource; got resourceType "
                f"{resource_type!r}",
                code="structure",
            )
        raw_parameters = payload.get("parameter")
        if raw_parameters is None:
            return cls({})
        if not isinstance(raw_parameters, list):
            raise bad_request(
                "Parameters.parameter must be an array", expression=["parameter"], code="structure"
            )
        entries: dict[str, dict] = {}
        for index, entry in enumerate(raw_parameters):
            where = [f"parameter[{index}]"]
            if not isinstance(entry, dict):
                raise bad_request(
                    f"{label} parameter[{index}] must be an object",
                    expression=where,
                    code="structure",
                )
            name = entry.get("name")
            if not isinstance(name, str) or not name:
                raise bad_request(
                    f"{label} parameter[{index}].name must be a non-empty string",
                    expression=where + ["name"],
                    code="structure",
                )
            if name in entries:
                raise bad_request(
                    f"parameter {name!r} appears more than once in {label}",
                    expression=where,
                    code="invalid",
                )
            entries[name] = entry
        return cls(entries)

    def merge_query(
        self, query: Any, specs: tuple[ParameterSpec, ...]
    ) -> ParametersBag:
        """Overlay query-string operation parameters onto this bag.

        FHIR convention: operation parameters may arrive in the query string
        (``?_format=csv&_limit=2&status=free``). A name present in both the
        body and the query string is an ambiguity and a 400 — the body does
        not silently win. Values are strings, coerced to the parameter's
        declared type; resource-valued parameters (``queryResource`` etc.)
        cannot arrive by query string and are rejected. Unknown and
        known-but-unsupported query names are rejected exactly like their
        body-path counterparts — a typo'd name (``?limitt=``) must surface as
        a 400 naming the mistake, never silently change the result set.
        """
        spec_by_name = {spec.name: spec for spec in specs}
        additions: dict[str, dict] = {}
        for raw_name, raw_value in query.multi_items() if hasattr(query, "multi_items") else query.items():
            name = str(raw_name)
            if name in additions:
                continue
            if name in self._entries:
                raise bad_request(
                    f"parameter {name!r} appears in both the body and the "
                    "query string; specify it once",
                    expression=[name],
                )
            spec = spec_by_name.get(name)
            if spec is None:
                raise bad_request(
                    f"Unknown parameter {name!r}. Supported parameters: "
                    f"{', '.join(sorted(spec_by_name))}",
                    expression=[name],
                )
            if not spec.supported:
                raise unsupported(
                    f"The server does not support the {name} parameter", expression=[name]
                )
            if not VALUE_FIELDS_BY_TYPE[spec.value_type]:
                raise bad_request(
                    f"parameter {name!r} carries a resource and cannot be "
                    "passed in the query string",
                    expression=[name],
                )
            value_field = VALUE_FIELDS_BY_TYPE[spec.value_type][0]
            additions[name] = {value_field: _coerce_query_value(raw_value, spec)}
        return ParametersBag({**self._entries, **additions})

    @classmethod
    def _from_body_impl(cls, body: Any, label: str) -> ParametersBag:
        payload = decode_json_body(body, label=label)
        if payload is None:
            return cls({})
        if not isinstance(payload, dict):
            raise bad_request(
                f"{label} must be a FHIR Parameters resource; got {type(payload).__name__}",
                code="structure",
            )
        resource_type = payload.get("resourceType")
        if resource_type != "Parameters":
            raise bad_request(
                f"{label} must be a FHIR Parameters resource; got resourceType "
                f"{resource_type!r}",
                code="structure",
            )
        raw_parameters = payload.get("parameter")
        if raw_parameters is None:
            return cls({})
        if not isinstance(raw_parameters, list):
            raise bad_request(
                "Parameters.parameter must be an array", expression=["parameter"], code="structure"
            )
        entries: dict[str, dict] = {}
        for index, entry in enumerate(raw_parameters):
            where = [f"parameter[{index}]"]
            if not isinstance(entry, dict):
                raise bad_request(
                    "Parameters.parameter entries must be objects",
                    expression=where,
                    code="structure",
                )
            name = entry.get("name")
            if not isinstance(name, str) or not name:
                raise bad_request(
                    "Parameters.parameter entries require a non-empty string name",
                    expression=where,
                    code="structure",
                )
            if name in entries:
                raise bad_request(
                    f"Parameter {name!r} appears more than once; "
                    f"operation parameters are single-valued",
                    expression=[name],
                    code="structure",
                )
            entries[name] = entry
        return cls(entries)

    # -- validation ------------------------------------------------------

    def names(self) -> frozenset[str]:
        return frozenset(self._entries)

    def has(self, name: str) -> bool:
        return name in self._entries

    def validate(self, specs: Sequence[ParameterSpec]) -> None:
        """Reject unknown and known-but-unsupported parameter names."""
        known = {spec.name: spec for spec in specs}
        for name in self._entries:
            spec = known.get(name)
            if spec is None:
                raise bad_request(
                    f"Unknown parameter {name!r}. Supported parameters: "
                    f"{', '.join(sorted(known))}",
                    expression=[name],
                )
            if not spec.supported:
                raise unsupported(
                    f"The server does not support the {name} parameter", expression=[name]
                )

    def require_one_of(self, names: Sequence[str]) -> str:
        """Return the single supplied name from ``names``.

        Raises the IG's 400 ``required`` error when none is supplied and a 400
        ``invalid`` when more than one is.
        """
        supplied = [name for name in names if name in self._entries]
        if not supplied:
            joined = " or ".join(names)
            raise missing(
                f"Either {joined} parameter is required when invoking this operation "
                f"at type or system level",
                expression=list(names),
            )
        if len(supplied) > 1:
            raise bad_request(
                f"Parameters {' and '.join(supplied)} are mutually exclusive; supply exactly one",
                expression=supplied,
            )
        return supplied[0]

    def forbid(self, names: Sequence[str]) -> None:
        """Reject parameters the instance level must not accept."""
        supplied = [name for name in names if name in self._entries]
        if supplied:
            raise bad_request(
                f"Parameter {supplied[0]!r} is not allowed when invoking this operation "
                f"at instance level; the resource is identified by the request path",
                expression=supplied,
            )

    # -- typed accessors -------------------------------------------------

    def _raw(self, name: str) -> dict | None:
        return self._entries.get(name)

    def _entry(self, spec: ParameterSpec) -> dict | None:
        return self._entries.get(spec.name)

    def value(self, spec: ParameterSpec) -> Any:
        """Return the typed value for ``spec``, or ``None`` when not supplied."""
        entry = self._entry(spec)
        if entry is None:
            return None
        if spec.value_type in RESOURCE_VALUED_TYPES:
            resource = entry.get("resource")
            if not isinstance(resource, dict):
                raise bad_request(
                    f"Parameter {spec.name!r} must supply a nested resource in "
                    f"Parameters.parameter.resource",
                    expression=[spec.name],
                    code="structure",
                )
            return resource
        accepted = VALUE_FIELDS_BY_TYPE[spec.value_type]
        for field in accepted:
            if field in entry:
                return _coerce_value(spec, field, entry[field])
        supplied = sorted(key for key in entry if key.startswith("value"))
        raise bad_request(
            f"Parameter {spec.name!r} expects a {spec.value_type} value "
            f"({accepted[0]}); got {', '.join(supplied) or 'no value element'}",
            expression=[spec.name],
            code="value",
        )

    def code(self, spec: ParameterSpec) -> str | None:
        value = self.value(spec)
        return None if value is None else str(value)

    def boolean(self, spec: ParameterSpec) -> bool | None:
        return self.value(spec)

    def integer(self, spec: ParameterSpec) -> int | None:
        return self.value(spec)

    def text(self, spec: ParameterSpec) -> str | None:
        value = self.value(spec)
        return None if value is None else str(value)


def _coerce_value(spec: ParameterSpec, field: str, raw: Any) -> Any:
    """Validate one ``value[x]`` payload against the declared type."""
    name = spec.name
    if spec.value_type == "boolean":
        if not isinstance(raw, bool):
            raise _type_error(name, spec, field, raw, "a JSON boolean")
        return raw
    if spec.value_type == "integer":
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise _type_error(name, spec, field, raw, "a JSON integer")
        return raw
    if spec.value_type in ("code", "string", "instant"):
        if not isinstance(raw, str):
            raise _type_error(name, spec, field, raw, "a JSON string")
        return raw
    if spec.value_type == "reference":
        if field == "valueReference":
            if not isinstance(raw, dict):
                raise _type_error(name, spec, field, raw, "a Reference object")
            reference = raw.get("reference")
            if not isinstance(reference, str) or not reference:
                raise bad_request(
                    f"Parameter {name!r} valueReference requires a non-empty reference",
                    expression=[name],
                    code="value",
                )
            return reference
        if not isinstance(raw, str):
            raise _type_error(name, spec, field, raw, "a reference string")
        return raw
    raise bad_request(  # pragma: no cover - ParameterSpec blocks this
        f"Parameter {name!r} has unsupported type {spec.value_type!r}",
        expression=[name],
        code="structure",
    )


def _type_error(
    name: str, spec: ParameterSpec, field: str, raw: Any, expected: str
) -> Exception:
    return bad_request(
        f"Parameter {name!r} expects {expected} in {field}; "
        f"got {type(raw).__name__}",
        expression=[name],
        code="value",
    )


def decode_json_body(body: Any, *, label: str = "request body") -> Any:
    """Normalize the request body to a decoded JSON value (or ``None``)."""
    if body is None:
        return None
    if isinstance(body, (bytes, bytearray, memoryview)):
        raw = bytes(body)
        if not raw.strip():
            return None
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise bad_request(f"{label} is not valid UTF-8", code="structure") from None
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise bad_request(
                f"{label} is not valid JSON: {exc.msg} at line {exc.lineno} column {exc.colno}",
                code="structure",
            ) from None
    if isinstance(body, str):
        if not body.strip():
            return None
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise bad_request(
                f"{label} is not valid JSON: {exc.msg} at line {exc.lineno} column {exc.colno}",
                code="structure",
            ) from None
    return body


__all__ = [
    "ParameterSpec",
    "ParametersBag",
    "VALUE_FIELDS_BY_TYPE",
    "RESOURCE_VALUED_TYPES",
    "decode_json_body",
]
