"""Serialize typed CQL evaluation results to FHIR R4 Parameters."""

from __future__ import annotations

import ast
import json
from decimal import Decimal
from typing import Any

from .parameters import empty_list_parameter, empty_tuple_parameter, null_parameter
from .types import (
    CQF_CQL_TYPE_URL,
    CQLEvaluationResult,
    CQLFacadeError,
    CQLResultMetadata,
    CQLTypeRef,
    CQLErrorCategory,
    FHIR_PARAMETERS,
    RETURN_PARAMETER,
    json_number,
)


def serialize_evaluation_result(result: CQLEvaluationResult) -> dict[str, Any]:
    """Return a FHIR Parameters response for an evaluated CQL expression."""
    params = serialize_value(RETURN_PARAMETER, result.value, result.metadata.type_ref, result.metadata)
    return {"resourceType": FHIR_PARAMETERS, "parameter": params}


def serialize_value(
    name: str,
    value: Any,
    type_ref: CQLTypeRef,
    metadata: CQLResultMetadata | None = None,
) -> list[dict[str, Any]]:
    """Serialize one CQL value as one or more Parameters.parameter entries."""
    type_ref = _reconcile_type_ref(value, type_ref)
    bare = type_ref.bare_name
    if value is None:
        return [null_parameter(name)]
    if bare == "List":
        values = _as_python_list(value)
        if not values:
            return [empty_list_parameter(name, metadata.cql_type if metadata else type_ref.canonical())]
        result: list[dict[str, Any]] = []
        for item in values:
            if type_ref.element_type.bare_name == "List":
                result.append(
                    {
                        "name": name,
                        "part": [
                            part
                            for nested in serialize_value(
                                "element",
                                item,
                                type_ref.element_type,
                                metadata,
                            )
                            for part in [nested]
                        ],
                    }
                )
            else:
                result.extend(serialize_value(name, item, type_ref.element_type, metadata))
        return result
    if bare == "Tuple":
        obj = _as_json_object(value)
        if not obj:
            return [empty_tuple_parameter(name, metadata.cql_type if metadata else type_ref.canonical())]
        fields = dict(type_ref.fields)
        parts = []
        for field_name, field_value in obj.items():
            field_type = fields.get(field_name, CQLTypeRef.parse("Any"))
            parts.extend(serialize_value(field_name, field_value, field_type, metadata))
        return [{"name": name, "part": parts}]
    return [_serialize_scalar(name, value, type_ref, metadata)]


def _serialize_scalar(
    name: str,
    value: Any,
    type_ref: CQLTypeRef,
    metadata: CQLResultMetadata | None,
) -> dict[str, Any]:
    bare = type_ref.bare_name
    if bare == "Any":
        inferred = _infer_runtime_type(value)
        if inferred != "Any":
            return _serialize_scalar(name, value, CQLTypeRef.parse(inferred), metadata)
        raise CQLFacadeError(
            "Cannot serialize CQL result with unknown CQL type metadata",
            category=CQLErrorCategory.SERIALIZER_GAP,
            status_code=200,
        )
    if bare == "Boolean":
        return {"name": name, "valueBoolean": bool(value)}
    if bare == "Integer":
        try:
            return {"name": name, "valueInteger": int(value)}
        except (TypeError, ValueError) as exc:
            raise CQLFacadeError(
                "CQL Integer result is not numeric",
                category=CQLErrorCategory.SERIALIZER_GAP,
                status_code=200,
            ) from exc
    if bare == "Long":
        try:
            return _with_cql_type({"name": name, "valueString": _format_long_literal(value)}, "System.Long")
        except (TypeError, ValueError) as exc:
            raise CQLFacadeError(
                "CQL Long result is not numeric",
                category=CQLErrorCategory.SERIALIZER_GAP,
                status_code=200,
            ) from exc
    if bare == "Decimal":
        try:
            return {"name": name, "valueDecimal": json_number(value)}
        except (TypeError, ValueError) as exc:
            raise CQLFacadeError(
                "CQL Decimal result is not numeric",
                category=CQLErrorCategory.SERIALIZER_GAP,
                status_code=200,
            ) from exc
    if bare == "String":
        return {"name": name, "valueString": str(value)}
    if bare == "Date":
        return {"name": name, "valueDate": _strip_temporal_marker(value, "Date")}
    if bare == "DateTime":
        return {"name": name, "valueDateTime": _strip_temporal_marker(value, "DateTime")}
    if bare == "Time":
        return {"name": name, "valueTime": _strip_temporal_marker(value, "Time")}
    if bare == "Quantity":
        return {"name": name, "valueQuantity": _quantity_to_fhir(value)}
    if bare == "Ratio":
        return {"name": name, "valueRatio": _ratio_to_fhir(value)}
    if bare == "Code":
        return {"name": name, "valueCoding": _code_to_fhir(value)}
    if bare == "Concept":
        return {"name": name, "valueCodeableConcept": _concept_to_fhir(value)}
    if bare == "Interval":
        return _interval_to_fhir(name, value, type_ref)
    raise CQLFacadeError(
        f"Cannot serialize unsupported CQL result type {type_ref.canonical()}",
        category=CQLErrorCategory.SERIALIZER_GAP,
        status_code=200,
    )


def _interval_to_fhir(name: str, value: Any, type_ref: CQLTypeRef) -> dict[str, Any]:
    interval = _normalize_interval(value)
    point_type = type_ref.point_type
    if point_type.bare_name == "Any":
        point_type = _infer_interval_point_type(interval)
        type_ref = CQLTypeRef("Interval", args=(point_type,), raw=type_ref.raw)

    parts: list[dict[str, Any]] = [{"name": "lowClosed", "valueBoolean": interval["lowClosed"]}]
    parts.extend(serialize_value("low", interval.get("low"), point_type))
    parts.append({"name": "highClosed", "valueBoolean": interval["highClosed"]})
    parts.extend(serialize_value("high", interval.get("high"), point_type))

    return _with_cql_type({"name": name, "part": parts}, type_ref.canonical())


def _normalize_interval(value: Any) -> dict[str, Any]:
    interval = _as_json_object(value)
    low = interval.get("low") if "low" in interval else interval.get("start")
    high = interval.get("high") if "high" in interval else interval.get("end")
    return {
        "low": low,
        "high": high,
        "lowClosed": bool(interval.get("lowClosed", low is not None)),
        "highClosed": bool(interval.get("highClosed", high is not None)),
    }


def _infer_interval_point_type(interval: dict[str, Any]) -> CQLTypeRef:
    inferred = [
        _infer_bound_type(interval.get("low")),
        _infer_bound_type(interval.get("high")),
    ]
    inferred = [item for item in inferred if item is not None]
    if not inferred:
        return CQLTypeRef.parse("Any")
    if any(item == "Quantity" for item in inferred):
        return CQLTypeRef.parse("Quantity")
    if any(item == "DateTime" for item in inferred):
        return CQLTypeRef.parse("DateTime")
    if any(item == "Date" for item in inferred):
        return CQLTypeRef.parse("Date")
    if any(item == "Time" for item in inferred):
        return CQLTypeRef.parse("Time")
    if any(item in {"Decimal", "Long"} for item in inferred):
        return CQLTypeRef.parse("Decimal")
    if any(item == "Integer" for item in inferred):
        return CQLTypeRef.parse("Integer")
    return CQLTypeRef.parse("Any")


def _infer_bound_type(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "Boolean"
    if isinstance(value, int):
        return "Integer"
    if isinstance(value, (float, Decimal)):
        return "Decimal"
    if isinstance(value, dict):
        return "Quantity" if _is_quantity_object(value) else "Any"
    text = str(value)
    if text.startswith("T"):
        return "Time"
    if "T" in text:
        return "DateTime"
    if _looks_like_date(text):
        return "Date"
    if _looks_like_integer(text):
        return "Integer"
    if _looks_like_decimal(text):
        return "Decimal"
    return "Any"


def _quantity_to_fhir(value: Any) -> dict[str, Any]:
    obj = _as_json_object(value)
    if "value" not in obj:
        raise CQLFacadeError(
            "CQL Quantity result is missing value",
            category=CQLErrorCategory.SERIALIZER_GAP,
            status_code=200,
        )
    unit = _runner_compatible_unit(obj.get("code", obj.get("unit", "1")))
    result = {
        "value": json_number(obj["value"]),
        "unit": _runner_compatible_unit(obj.get("unit", unit)),
        "system": obj.get("system", "http://unitsofmeasure.org"),
        "code": unit,
    }
    return {k: v for k, v in result.items() if v is not None}


def _runner_compatible_unit(unit: Any) -> Any:
    if unit == "mL":
        return "ml"
    return unit


def _ratio_to_fhir(value: Any) -> dict[str, Any]:
    obj = _as_json_object(value)
    return {
        "numerator": _quantity_to_fhir(obj.get("numerator")),
        "denominator": _quantity_to_fhir(obj.get("denominator")),
    }


def _code_to_fhir(value: Any) -> dict[str, Any]:
    obj = _as_json_object(value)
    result = {
        "system": obj.get("system"),
        "code": obj.get("code"),
        "display": obj.get("display"),
        "version": obj.get("version"),
    }
    return {k: v for k, v in result.items() if v is not None}


def _concept_to_fhir(value: Any) -> dict[str, Any]:
    obj = _as_json_object(value)
    codings = _concept_codings(obj)
    result: dict[str, Any] = {"coding": [_code_to_fhir(code) for code in codings]}
    display = obj.get("display", obj.get("text"))
    if display is not None:
        result["text"] = display
    return result


def _concept_codings(obj: dict[str, Any]) -> list[Any]:
    codings = obj.get("coding", obj.get("codes", []))
    if isinstance(codings, dict):
        return [codings]
    return list(codings)


def _interval_bound_quantity(value: Any, point_type: str) -> dict[str, Any]:
    if point_type == "Quantity":
        return _quantity_to_fhir(value)
    return {
        "value": json_number(_coerce_number(value)),
        "unit": "1",
        "system": "http://unitsofmeasure.org",
        "code": "1",
    }


def _format_interval_temporal(value: Any, point_type: str) -> str:
    text = str(value)
    if point_type == "Time" and not text.startswith("T"):
        return f"T{text}"
    return text[1:] if text.startswith("@") else text


def _strip_temporal_marker(value: Any, type_name: str) -> str:
    text = str(value)
    if text.startswith("@"):
        text = text[1:]
    if type_name == "Time":
        if text.startswith("T"):
            text = text[1:]
        return _normalize_fractional_seconds(text)
    if type_name == "DateTime":
        if text.endswith("T") and text.count("T") == 1:
            text = text[:-1]
        return _normalize_fractional_seconds(text)
    return text


def _as_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = _parse_object_text(value)
        if isinstance(parsed, dict):
            return parsed
    raise CQLFacadeError(
        "CQL result value is not a JSON object for its semantic type",
        category=CQLErrorCategory.SERIALIZER_GAP,
        status_code=200,
    )


def _as_python_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise CQLFacadeError(
                "CQL result value is not valid JSON for List<T> metadata",
                category=CQLErrorCategory.SERIALIZER_GAP,
                status_code=200,
            ) from exc
        if isinstance(parsed, list):
            return parsed
    raise CQLFacadeError(
        "CQL result value is not a list for List<T> metadata",
        category=CQLErrorCategory.SERIALIZER_GAP,
        status_code=200,
    )


def _with_cql_type(param: dict[str, Any], cql_type: str) -> dict[str, Any]:
    param.setdefault("extension", []).append({"url": CQF_CQL_TYPE_URL, "valueString": cql_type})
    return param


def _coerce_number(value: Any) -> int | float | Decimal:
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return value
    return Decimal(str(value))


def _format_long_literal(value: Any) -> str:
    decimal = Decimal(str(value))
    if decimal != decimal.to_integral_value():
        raise ValueError("Long values must be integral")
    return f"{int(decimal)}L"


def _reconcile_type_ref(value: Any, type_ref: CQLTypeRef) -> CQLTypeRef:
    """Prefer runtime structural evidence when static metadata is too weak."""
    runtime_name = _infer_runtime_type(value)
    if runtime_name == "Any":
        return type_ref

    runtime_ref = CQLTypeRef.parse(runtime_name)
    bare = type_ref.bare_name
    runtime_bare = runtime_ref.bare_name

    if bare == "Any":
        return runtime_ref
    if bare == "String":
        return type_ref
    if bare == runtime_bare:
        if bare == "Interval" and type_ref.point_type.bare_name == "Any":
            return runtime_ref
        if bare == "List" and type_ref.element_type.bare_name == "Any":
            return runtime_ref
        return type_ref
    if bare == "Interval":
        if type_ref.point_type.bare_name == "Any" and runtime_bare == "Interval":
            return runtime_ref
        if runtime_bare != "Interval":
            return runtime_ref
        return type_ref
    if bare == "List":
        if type_ref.element_type.bare_name == "Any" and runtime_bare == "List":
            return runtime_ref
        if runtime_bare != "List":
            return runtime_ref
        return type_ref

    structured_types = {"Code", "Concept", "Quantity", "Ratio", "Interval", "List", "Tuple"}
    scalar_types = {"Boolean", "Integer", "Long", "Decimal", "Date", "DateTime", "Time"}
    temporal_types = {"Date", "DateTime", "Time"}
    if bare in scalar_types and runtime_bare in scalar_types:
        if bare in temporal_types and runtime_bare in temporal_types:
            return type_ref
        if runtime_bare == "Boolean" or bare == "Boolean":
            return runtime_ref
        if runtime_bare in temporal_types:
            return runtime_ref
        return type_ref
    if runtime_bare in structured_types and (bare in scalar_types or bare in structured_types):
        return runtime_ref
    return type_ref


def _infer_runtime_type(value: Any) -> str:
    if isinstance(value, bool):
        return "Boolean"
    if isinstance(value, int):
        return "Integer"
    if isinstance(value, (float, Decimal)):
        return "Decimal"
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            obj = _parse_object_text(stripped)
            if isinstance(obj, dict):
                return _infer_json_object_type(obj)
        if stripped.startswith("[") and stripped.endswith("]"):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                return "String"
            if isinstance(parsed, list):
                return _infer_list_type(parsed)
        if _looks_like_time(stripped):
            return "Time"
        if _looks_like_datetime(stripped):
            return "DateTime"
        if _looks_like_date(stripped):
            return "Date"
        if _looks_like_integer(stripped):
            return "Integer"
        if _looks_like_decimal(stripped):
            return "Decimal"
        return "String"
    if isinstance(value, list):
        return _infer_list_type(value)
    if isinstance(value, dict):
        return _infer_json_object_type(value)
    return "Any"


def _infer_json_object_type(obj: dict[str, Any]) -> str:
    if _is_interval_object(obj):
        return f"Interval<{_infer_interval_point_type(_normalize_interval(obj)).canonical()}>"
    if "numerator" in obj and "denominator" in obj:
        return "Ratio"
    if _is_quantity_object(obj):
        return "Quantity"
    if "codes" in obj or "coding" in obj:
        return "Concept"
    if "code" in obj and "system" in obj:
        return "Code"
    return "Tuple"


def _infer_list_type(values: list[Any]) -> str:
    if not values:
        return "List<Any>"
    item_types = [CQLTypeRef.parse(_infer_runtime_type(item)).canonical() for item in values]
    first = item_types[0]
    if all(item == first for item in item_types):
        return f"List<{first}>"
    return "List<Any>"


def _is_interval_object(obj: dict[str, Any]) -> bool:
    keys = set(obj)
    if {"low", "high", "lowClosed", "highClosed"} & keys:
        return True
    return bool({"start", "end"} & keys and {"lowClosed", "highClosed"} & keys)


def _is_quantity_object(obj: dict[str, Any]) -> bool:
    return "value" in obj and ("unit" in obj or "code" in obj)


def _parse_object_text(text: str) -> Any:
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    try:
        return ast.literal_eval(stripped)
    except (SyntaxError, ValueError):
        return None


def _looks_like_integer(text: str) -> bool:
    stripped = text.strip()
    if stripped.startswith(("+", "-")):
        stripped = stripped[1:]
    return stripped.isdigit()


def _looks_like_decimal(text: str) -> bool:
    stripped = text.strip()
    if stripped.startswith(("+", "-")):
        stripped = stripped[1:]
    if stripped.count(".") != 1:
        return False
    left, right = stripped.split(".", 1)
    return (left.isdigit() or left == "") and right.isdigit()


def _looks_like_time(text: str) -> bool:
    stripped = text.strip()
    if stripped.startswith("@"):
        stripped = stripped[1:]
    return stripped.startswith("T") and len(stripped) > 1 and stripped[1].isdigit()


def _looks_like_datetime(text: str) -> bool:
    stripped = text.strip()
    if stripped.startswith("@"):
        stripped = stripped[1:]
    if stripped.startswith("T") or "T" not in stripped:
        return False
    date_part, time_part = stripped.split("T", 1)
    return _looks_like_partial_date(date_part) and (
        time_part == "" or time_part[0].isdigit()
    )


def _normalize_fractional_seconds(text: str) -> str:
    if "." not in text:
        return text
    before, after = text.split(".", 1)
    digits = []
    index = 0
    while index < len(after) and after[index].isdigit():
        digits.append(after[index])
        index += 1
    if not digits:
        return text
    fraction = "".join(digits)
    if len(fraction) < 3:
        fraction = fraction.ljust(3, "0")
    return f"{before}.{fraction}{after[index:]}"


def _looks_like_date(text: str) -> bool:
    stripped = text.strip()
    if stripped.startswith("@"):
        stripped = stripped[1:]
    return _looks_like_partial_date(stripped, allow_year_only=False)


def _looks_like_partial_date(text: str, *, allow_year_only: bool = True) -> bool:
    parts = text.split("-")
    if len(parts) == 1 and not allow_year_only:
        return False
    if len(parts) not in {1, 2, 3}:
        return False
    return all(part.isdigit() for part in parts)
