"""Value normalization for the temporal-dedup pipeline (AMUX-142 slice 1).

The value partition key (design §9 revision): canonicalize the Quantity unit
per dimension through the ENGINE'S EXISTING UCUM machinery — the pure-Python
``quantityConvert`` in ``fhir4ds/cql/duckdb/udf/quantity.py`` (pint-backed,
called directly, never through a DuckDB connection) — round to 2 decimal
places AFTER conversion, and key ``<value>|<canonical unit>``.

Incommensurable / non-UCUM / failed conversions fall back to
``<rounded 2dp>|<raw unit lowercased>`` — a conservative miss, never a false
merge. Absent values key on a dataAbsentReason sentinel.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional

__all__ = ["normalize_value", "CANONICAL_UNITS"]

#: Per-dimension canonical UCUM target units, tried in this fixed
#: (deterministic) order. The first successful conversion wins. Temperature
#: is deliberately absent: pint refuses offset-unit conversion
#: (OffsetUnitCalculusError), so temperatures take the fallback key.
CANONICAL_UNITS: tuple[str, ...] = ("cm", "g", "mg", "mL", "s", "min", "h",
                                    "mm[Hg]", "1")

# Observation value[x] arms in fixed preference order (Quantity preferred).
_VALUE_ARMS: tuple[str, ...] = ("valueQuantity", "valueCodeableConcept",
                                "valueString", "valueBoolean")

_DAR_NULL = "DAR:null"


def _round2(value) -> Optional[Decimal]:
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return None


def _quantity_key(value, code: str) -> str:
    # Imported lazily: quantity.py pulls orjson (and guards pint); keeping
    # the import out of module scope keeps `import fhir4ds.dedup` light.
    from fhir4ds.cql.duckdb.udf.quantity import quantityConvert

    q_json = json.dumps({"value": value, "unit": code, "code": code,
                         "system": "http://unitsofmeasure.org"})
    for canonical in CANONICAL_UNITS:
        converted = quantityConvert(q_json, canonical)
        if converted is None:
            continue
        try:
            result = json.loads(converted)
            result_value = result.get("value")
        except (ValueError, AttributeError):
            continue
        if result_value is None:
            continue
        rounded = _round2(result_value)
        if rounded is None:
            continue
        return f"{rounded}|{canonical}"
    # Fallback: rounded value + raw unit lowercased (conservative miss).
    rounded = _round2(value)
    if rounded is None:
        return _DAR_NULL
    return f"{rounded}|{code.lower()}"


def _normalize_text(raw: str) -> str:
    return " ".join(raw.casefold().split())


def normalize_value(resource: dict) -> str:
    """Compute the deterministic value partition key for a resource.

    Non-Observation resources key on ``'n/a'``. Observations without a
    supported value arm key on ``'DAR:<code>'`` when a dataAbsentReason is
    present, else ``'DAR:null'``.
    """
    if not isinstance(resource, dict):
        return _DAR_NULL
    rtype = resource.get("resourceType")
    if rtype != "Observation":
        return "n/a"

    for arm in _VALUE_ARMS:
        if arm not in resource or resource[arm] is None:
            continue
        value = resource[arm]
        if arm == "valueQuantity":
            if not isinstance(value, dict):
                continue
            q_value = value.get("value")
            if isinstance(q_value, bool) or not isinstance(q_value, (int, float)):
                continue
            unit = value.get("code") or value.get("unit")
            if not isinstance(unit, str) or not unit:
                unit = "1"
            return _quantity_key(q_value, unit)
        if arm == "valueCodeableConcept":
            codings = value.get("coding") if isinstance(value, dict) else None
            if not isinstance(codings, list):
                continue
            for coding in codings:
                if isinstance(coding, dict) and isinstance(coding.get("code"), str) \
                        and coding["code"]:
                    return f"concept:{coding['code']}"
            continue
        if arm == "valueString":
            if not isinstance(value, str) or value == "":
                continue
            return f"str:{_normalize_text(value)}"
        if arm == "valueBoolean":
            if isinstance(value, bool):
                return f"bool:{'true' if value else 'false'}"

    dar = resource.get("dataAbsentReason")
    if isinstance(dar, dict) and isinstance(dar.get("coding"), list):
        for coding in dar["coding"]:
            if isinstance(coding, dict) and isinstance(coding.get("code"), str) \
                    and coding["code"]:
                return f"DAR:{coding['code']}"
    return _DAR_NULL
