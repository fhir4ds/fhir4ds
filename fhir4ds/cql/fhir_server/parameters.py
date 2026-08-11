"""FHIR R4 Parameters parsing and response helpers for ``$cql``."""

from __future__ import annotations

import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any

from .types import (
    CQF_CQL_TYPE_URL,
    CQF_EMPTY_LIST_URL,
    CQF_EMPTY_TUPLE_URL,
    CQLFacadeError,
    CQLErrorCategory,
    CQLRequest,
    DATA_ABSENT_REASON_URL,
    FHIR_OPERATION_OUTCOME,
    FHIR_PARAMETERS,
    InputParameter,
)

_UNSUPPORTED_TOP_LEVEL = {
    "subject",
    "library",
    "data",
    "prefetchData",
    "dataEndpoint",
    "contentEndpoint",
}


def parse_cql_request(body: Any) -> CQLRequest:
    """Parse a FHIR ``$cql`` Parameters request."""
    if not isinstance(body, dict):
        raise CQLFacadeError(
            "FHIR $cql request body must be a JSON object",
            category=CQLErrorCategory.INVALID_REQUEST,
            status_code=400,
        )
    if body.get("resourceType") != FHIR_PARAMETERS:
        raise CQLFacadeError(
            "FHIR $cql request body must be a Parameters resource",
            category=CQLErrorCategory.INVALID_REQUEST,
            status_code=400,
        )
    params = body.get("parameter", [])
    if not isinstance(params, list):
        raise CQLFacadeError(
            "Parameters.parameter must be an array",
            category=CQLErrorCategory.INVALID_REQUEST,
            status_code=422,
        )

    expressions = [p for p in params if isinstance(p, dict) and p.get("name") == "expression"]
    if len(expressions) != 1:
        raise CQLFacadeError(
            "FHIR $cql requires exactly one expression parameter",
            category=CQLErrorCategory.INVALID_REQUEST,
            status_code=422,
        )
    expression = expressions[0].get("valueString")
    if not isinstance(expression, str) or not expression.strip():
        raise CQLFacadeError(
            "FHIR $cql expression parameter must contain a non-empty valueString",
            category=CQLErrorCategory.INVALID_REQUEST,
            status_code=422,
        )

    unsupported = sorted(
        p.get("name")
        for p in params
        if isinstance(p, dict) and p.get("name") in _UNSUPPORTED_TOP_LEVEL
    )
    if unsupported:
        raise CQLFacadeError(
            "FHIR $cql parameter is not supported in the V1 facade: " + ", ".join(unsupported),
            category=CQLErrorCategory.UNSUPPORTED_FEATURE,
            status_code=422,
        )

    terminology_endpoint_url = _parse_terminology_endpoint(params)

    input_parameters = _parse_input_parameters(params)
    return CQLRequest(
        expression=expression,
        parameters=input_parameters,
        terminology_endpoint_url=terminology_endpoint_url,
    )


def _parse_terminology_endpoint(params: list[Any]) -> str | None:
    """Extract and validate the optional ``terminologyEndpoint`` parameter.

    Returns the URL string if present, ``None`` if absent. The literal
    string ``"disabled"`` is treated as ``None`` so callers can explicitly
    turn off the endpoint via the FHIR Parameters payload.
    """
    endpoints = [p for p in params if isinstance(p, dict) and p.get("name") == "terminologyEndpoint"]
    if not endpoints:
        return None
    if len(endpoints) > 1:
        raise CQLFacadeError(
            "FHIR $cql accepts at most one terminologyEndpoint parameter",
            category=CQLErrorCategory.INVALID_REQUEST,
            status_code=422,
        )
    url = endpoints[0].get("valueUrl")
    if not isinstance(url, str) or not url.strip():
        raise CQLFacadeError(
            "FHIR $cql terminologyEndpoint parameter must contain a non-empty valueUrl",
            category=CQLErrorCategory.INVALID_REQUEST,
            status_code=422,
        )
    url = url.strip()
    if url.lower() == "disabled":
        return None
    return url


def operation_outcome(
    *,
    message: str,
    category: CQLErrorCategory,
    diagnostics: str | None = None,
    severity: str = "error",
) -> dict[str, Any]:
    """Build a compact FHIR R4 OperationOutcome."""
    issue: dict[str, Any] = {
        "severity": severity,
        "code": _issue_code(category),
        "details": {"text": message},
    }
    if diagnostics:
        issue["diagnostics"] = diagnostics
    return {"resourceType": FHIR_OPERATION_OUTCOME, "issue": [issue]}


def error_parameters(
    *,
    message: str,
    category: CQLErrorCategory,
    diagnostics: str | None = None,
) -> dict[str, Any]:
    """Build a runner-compatible evaluation error response."""
    return {
        "resourceType": FHIR_PARAMETERS,
        "parameter": [
            {
                "name": "evaluation error",
                "resource": operation_outcome(
                    message=message,
                    category=category,
                    diagnostics=diagnostics,
                ),
            }
        ],
    }


def null_parameter(name: str = "return") -> dict[str, Any]:
    return {
        "name": name,
        "_valueBoolean": {
            "extension": [
                {
                    "url": DATA_ABSENT_REASON_URL,
                    "valueCode": "unknown",
                }
            ]
        },
    }


def empty_list_parameter(name: str = "return", cql_type: str = "List<System.Any>") -> dict[str, Any]:
    return {
        "name": name,
        "extension": [{"url": CQF_CQL_TYPE_URL, "valueString": cql_type}],
        "_valueBoolean": {"extension": [{"url": CQF_EMPTY_LIST_URL, "valueBoolean": True}]},
    }


def empty_tuple_parameter(name: str = "return", cql_type: str = "Tuple{}") -> dict[str, Any]:
    return {
        "name": name,
        "extension": [{"url": CQF_CQL_TYPE_URL, "valueString": cql_type}],
        "_valueBoolean": {"extension": [{"url": CQF_EMPTY_TUPLE_URL, "valueBoolean": True}]},
    }


def cql_string_literal(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def cql_identifier(name: str) -> str:
    if name.replace("_", "").isalnum() and not name[0].isdigit():
        return name
    return '"' + name.replace('"', '""') + '"'


def _parse_input_parameters(params: list[Any]) -> tuple[InputParameter, ...]:
    containers = [p for p in params if isinstance(p, dict) and p.get("name") == "parameters"]
    if not containers:
        return ()
    if len(containers) > 1:
        raise CQLFacadeError(
            "FHIR $cql accepts at most one parameters container",
            category=CQLErrorCategory.INVALID_REQUEST,
            status_code=422,
        )

    container = containers[0]
    nested = _container_parameters(container)
    grouped: dict[str, list[InputParameter]] = defaultdict(list)
    for param in nested:
        parsed = _parse_single_input_parameter(param)
        grouped[parsed.name].append(parsed)

    result: list[InputParameter] = []
    for name, values in grouped.items():
        if len(values) == 1:
            result.append(values[0])
            continue
        first_type = values[0].cql_type
        if any(v.cql_type != first_type for v in values):
            raise CQLFacadeError(
                f"Input parameter {name!r} has mixed repeated value types",
                category=CQLErrorCategory.UNSUPPORTED_FEATURE,
                status_code=422,
            )
        literal = "{" + ", ".join(v.literal for v in values) + "}"
        result.append(InputParameter(name=name, cql_type=f"List<{first_type}>", literal=literal))
    return tuple(result)


def _container_parameters(container: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(container.get("part"), list):
        nested = container["part"]
        if not all(isinstance(p, dict) for p in nested):
            raise CQLFacadeError(
                "FHIR $cql parameters input part entries must be objects",
                category=CQLErrorCategory.INVALID_REQUEST,
                status_code=422,
            )
        return nested
    resource = container.get("resource")
    if isinstance(resource, dict) and resource.get("resourceType") == FHIR_PARAMETERS:
        nested = resource.get("parameter", [])
        if isinstance(nested, list):
            if not all(isinstance(p, dict) for p in nested):
                raise CQLFacadeError(
                    "FHIR $cql nested Parameters.parameter entries must be objects",
                    category=CQLErrorCategory.INVALID_REQUEST,
                    status_code=422,
                )
            return nested
    raise CQLFacadeError(
        "FHIR $cql parameters input must use part entries or a Parameters resource",
        category=CQLErrorCategory.INVALID_REQUEST,
        status_code=422,
    )


def _parse_single_input_parameter(param: dict[str, Any]) -> InputParameter:
    name = param.get("name")
    if not isinstance(name, str) or not name:
        raise CQLFacadeError(
            "Nested input parameter must have a non-empty name",
            category=CQLErrorCategory.INVALID_REQUEST,
            status_code=422,
        )
    cql_type, literal = _parameter_value_to_cql(param)
    return InputParameter(name=name, cql_type=cql_type, literal=literal)


def _parameter_value_to_cql(param: dict[str, Any]) -> tuple[str, str]:
    if _has_extension(param, DATA_ABSENT_REASON_URL):
        return "System.Any", "null"
    if _has_extension(param, CQF_EMPTY_LIST_URL):
        return "List<System.Any>", "{}"
    if _has_extension(param, CQF_EMPTY_TUPLE_URL):
        return "Tuple{}", "Tuple {}"
    if "part" in param:
        if not isinstance(param["part"], list):
            raise CQLFacadeError(
                "Tuple input parameter part must be an array",
                category=CQLErrorCategory.INVALID_REQUEST,
                status_code=422,
            )
        parts = param["part"]
        if not all(isinstance(p, dict) for p in parts):
            raise CQLFacadeError(
                "Tuple input parameter part entries must be objects",
                category=CQLErrorCategory.INVALID_REQUEST,
                status_code=422,
            )
        fields: list[str] = []
        values: list[str] = []
        for part in parts:
            parsed = _parse_single_input_parameter(part)
            fields.append(f"{parsed.name}: {parsed.cql_type}")
            values.append(f"{parsed.name}: {parsed.literal}")
        return "Tuple{" + ", ".join(fields) + "}", "Tuple { " + ", ".join(values) + " }"
    if "valueBoolean" in param:
        if not isinstance(param["valueBoolean"], bool):
            raise CQLFacadeError(
                "valueBoolean must be a boolean",
                category=CQLErrorCategory.INVALID_REQUEST,
                status_code=422,
            )
        return "Boolean", "true" if param["valueBoolean"] else "false"
    if "valueInteger" in param:
        return "Integer", str(_require_int(param["valueInteger"], "valueInteger"))
    if "valueDecimal" in param:
        return "Decimal", _decimal_literal(param["valueDecimal"])
    if "valueString" in param:
        if not isinstance(param["valueString"], str):
            raise CQLFacadeError(
                "valueString must be a string",
                category=CQLErrorCategory.INVALID_REQUEST,
                status_code=422,
            )
        return "String", cql_string_literal(param["valueString"])
    if "valueDate" in param:
        if not isinstance(param["valueDate"], str):
            raise CQLFacadeError(
                "valueDate must be a string",
                category=CQLErrorCategory.INVALID_REQUEST,
                status_code=422,
            )
        return "Date", "@" + param["valueDate"]
    if "valueDateTime" in param:
        if not isinstance(param["valueDateTime"], str):
            raise CQLFacadeError(
                "valueDateTime must be a string",
                category=CQLErrorCategory.INVALID_REQUEST,
                status_code=422,
            )
        return "DateTime", "@" + param["valueDateTime"]
    if "valueTime" in param:
        if not isinstance(param["valueTime"], str):
            raise CQLFacadeError(
                "valueTime must be a string",
                category=CQLErrorCategory.INVALID_REQUEST,
                status_code=422,
            )
        text = param["valueTime"]
        return "Time", "@" + (text if text.startswith("T") else f"T{text}")
    if "valueQuantity" in param:
        return "Quantity", _quantity_literal(param["valueQuantity"])
    if "valueRange" in param:
        return _range_literal(param["valueRange"])
    if "valuePeriod" in param:
        period = param["valuePeriod"]
        if not isinstance(period, dict):
            raise CQLFacadeError(
                "valuePeriod must be an object",
                category=CQLErrorCategory.INVALID_REQUEST,
                status_code=422,
            )
        start = period.get("start")
        end = period.get("end")
        if start is not None and not isinstance(start, str):
            raise CQLFacadeError(
                "valuePeriod.start must be a string",
                category=CQLErrorCategory.INVALID_REQUEST,
                status_code=422,
            )
        if end is not None and not isinstance(end, str):
            raise CQLFacadeError(
                "valuePeriod.end must be a string",
                category=CQLErrorCategory.INVALID_REQUEST,
                status_code=422,
            )
        low = "@" + start if start is not None else ""
        high = "@" + end if end is not None else ""
        return "Interval<DateTime>", f"Interval[{low}, {high}]"
    if "valueCoding" in param:
        return "Code", _code_literal(param["valueCoding"])
    if "valueCodeableConcept" in param:
        return "Concept", _concept_literal(param["valueCodeableConcept"])
    if "valueRatio" in param:
        raise CQLFacadeError(
            "Ratio input parameters are not supported by the V1 synthetic CQL default path",
            category=CQLErrorCategory.UNSUPPORTED_FEATURE,
            status_code=422,
        )
    raise CQLFacadeError(
        f"Unsupported input parameter value shape for {param.get('name')!r}",
        category=CQLErrorCategory.UNSUPPORTED_FEATURE,
        status_code=422,
    )


def _has_extension(param: dict[str, Any], url: str) -> bool:
    for holder in (param, param.get("_valueBoolean", {})):
        for ext in holder.get("extension", []) if isinstance(holder, dict) else []:
            if isinstance(ext, dict) and ext.get("url") == url:
                if url == DATA_ABSENT_REASON_URL:
                    return ext.get("valueCode") == "unknown"
                return bool(ext.get("valueBoolean"))
    return False


def _require_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CQLFacadeError(
            f"{field} must be an integer",
            category=CQLErrorCategory.INVALID_REQUEST,
            status_code=422,
        )
    return value


def _decimal_literal(value: Any) -> str:
    if isinstance(value, bool):
        raise CQLFacadeError(
            "valueDecimal must be numeric",
            category=CQLErrorCategory.INVALID_REQUEST,
            status_code=422,
        )
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise CQLFacadeError(
            "valueDecimal must be numeric",
            category=CQLErrorCategory.INVALID_REQUEST,
            status_code=422,
        ) from exc
    if not decimal_value.is_finite():
        raise CQLFacadeError(
            "valueDecimal must be finite",
            category=CQLErrorCategory.INVALID_REQUEST,
            status_code=422,
        )
    return format(decimal_value, "f")


def _quantity_literal(quantity: Any) -> str:
    if not isinstance(quantity, dict) or "value" not in quantity:
        raise CQLFacadeError(
            "valueQuantity must contain value",
            category=CQLErrorCategory.INVALID_REQUEST,
            status_code=422,
        )
    unit = quantity.get("code", quantity.get("unit", "1"))
    if not isinstance(unit, str):
        raise CQLFacadeError(
            "valueQuantity unit/code must be a string",
            category=CQLErrorCategory.INVALID_REQUEST,
            status_code=422,
        )
    return f"{_decimal_literal(quantity['value'])} {cql_string_literal(str(unit))}"


def _range_literal(range_value: Any) -> tuple[str, str]:
    if not isinstance(range_value, dict):
        raise CQLFacadeError(
            "valueRange must be an object",
            category=CQLErrorCategory.INVALID_REQUEST,
            status_code=422,
        )
    low = _quantity_literal(range_value["low"]) if "low" in range_value else ""
    high = _quantity_literal(range_value["high"]) if "high" in range_value else ""
    return "Interval<Quantity>", f"Interval[{low}, {high}]"


def _code_literal(coding: Any) -> str:
    if not isinstance(coding, dict):
        raise CQLFacadeError(
            "valueCoding must be an object",
            category=CQLErrorCategory.INVALID_REQUEST,
            status_code=422,
        )
    parts = []
    for key in ("system", "code", "display", "version"):
        if key in coding and coding[key] is not None:
            if not isinstance(coding[key], str):
                raise CQLFacadeError(
                    f"valueCoding.{key} must be a string",
                    category=CQLErrorCategory.INVALID_REQUEST,
                    status_code=422,
                )
            parts.append(f"{key}: {cql_string_literal(str(coding[key]))}")
    return "Code { " + ", ".join(parts) + " }"


def _concept_literal(concept: Any) -> str:
    if not isinstance(concept, dict):
        raise CQLFacadeError(
            "valueCodeableConcept must be an object",
            category=CQLErrorCategory.INVALID_REQUEST,
            status_code=422,
        )
    codings = concept.get("coding", [])
    if not isinstance(codings, list):
        raise CQLFacadeError(
            "valueCodeableConcept.coding must be an array",
            category=CQLErrorCategory.INVALID_REQUEST,
            status_code=422,
        )
    if not all(isinstance(coding, dict) for coding in codings):
        raise CQLFacadeError(
            "valueCodeableConcept.coding entries must be objects",
            category=CQLErrorCategory.INVALID_REQUEST,
            status_code=422,
        )
    code_literals = [_code_literal(coding) for coding in codings if isinstance(coding, dict)]
    parts = [f"codes: {{{', '.join(code_literals)}}}"]
    if concept.get("text") is not None:
        if not isinstance(concept["text"], str):
            raise CQLFacadeError(
                "valueCodeableConcept.text must be a string",
                category=CQLErrorCategory.INVALID_REQUEST,
                status_code=422,
            )
        parts.append(f"display: {cql_string_literal(concept['text'])}")
    return "Concept { " + ", ".join(parts) + " }"


def _issue_code(category: CQLErrorCategory) -> str:
    return {
        CQLErrorCategory.INVALID_REQUEST: "invalid",
        CQLErrorCategory.UNSUPPORTED_FEATURE: "not-supported",
        CQLErrorCategory.PARSE_ERROR: "invalid",
        CQLErrorCategory.TRANSLATION_ERROR: "processing",
        CQLErrorCategory.EVALUATION_ERROR: "exception",
        CQLErrorCategory.SERIALIZER_GAP: "not-supported",
    }[category]


def dumps_fhir_json(body: dict[str, Any]) -> bytes:
    """Serialize a FHIR response body."""
    return json.dumps(body, separators=(",", ":"), default=str).encode("utf-8")
