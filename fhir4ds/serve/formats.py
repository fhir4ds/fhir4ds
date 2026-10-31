"""Output formats for SQL-on-FHIR operation results.

SQL-on-FHIR v2 ``$sqlquery-run`` / ``$viewdefinition-run`` return either a
**Binary** (flat formats: ``json``, ``ndjson``, ``csv``, ``parquet``) or a
FHIR **Parameters** resource (``_format=fhir``).

Format negotiation, per the IG:

* ``_format`` wins over the ``Accept`` header;
* if ``_format`` is omitted the server SHALL return ``ndjson``;
* the ``Accept`` header MAY be honoured when ``_format`` is absent.

The ``_format=fhir`` encoder implements the IG's ``SQL → value[x]`` table
(mirrored from :mod:`fhir4ds.operations.capabilities.tabular`) with a
``row`` parameter per result row and one ``part`` per column. SQL NULL omits
the part. A column whose SQL type has no ``value[x]`` mapping, or a duplicate
column name, is a 422 per the IG.
"""

from __future__ import annotations

import base64
import csv
import datetime
import io
import json
import re
import uuid
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from fhir4ds.operations.capabilities.tabular import (
    ResultColumn,
    TabularResult,
    normalize_sql_type,
)

from .errors import bad_request, unprocessable, unsupported

DEFAULT_FORMAT = "ndjson"

#: Supported ``_format`` values, in the order documented in /metadata.
OUTPUT_FORMATS: tuple[str, ...] = ("json", "ndjson", "csv", "parquet", "fhir")

CONTENT_TYPES: dict[str, str] = {
    "json": "application/json",
    "ndjson": "application/x-ndjson",
    "csv": "text/csv",
    "parquet": "application/octet-stream",
    "fhir": "application/fhir+json",
}

#: ``Accept`` media type → ``_format``. Unlisted types fall back to the default.
ACCEPT_FORMATS: dict[str, str] = {
    "application/json": "json",
    "application/x-ndjson": "ndjson",
    "application/ndjson": "ndjson",
    "text/csv": "csv",
    "application/octet-stream": "parquet",
    "application/fhir+json": "fhir",
}

_DECIMAL_TYPE_PATTERN = re.compile(r"^DECIMAL\(\s*(\d+)\s*,\s*(\d+)\s*\)$")


# ---------------------------------------------------------------------------
# Format negotiation
# ---------------------------------------------------------------------------


def validate_format(explicit: str | None) -> str | None:
    """Validate an explicit ``_format`` value, or ``None`` when absent."""
    if explicit is None:
        return None
    value = explicit.strip().lower()
    if value not in OUTPUT_FORMATS:
        raise bad_request(
            f"Format {explicit!r} is not supported. Supported formats: "
            f"{', '.join(OUTPUT_FORMATS)}",
            expression=["_format"],
            code="not-supported",
        )
    return value


def format_from_accept(accept: str | None) -> str | None:
    """Return the negotiated format for an ``Accept`` header, if any."""
    if not accept:
        return None
    for media_range in accept.split(","):
        media_type = media_range.split(";", 1)[0].strip().lower()
        if media_type in ACCEPT_FORMATS:
            return ACCEPT_FORMATS[media_type]
    return None


def negotiate_format(
    explicit: str | None,
    accept: str | None = None,
    *,
    default: str = DEFAULT_FORMAT,
) -> str:
    """Resolve the output format: ``_format`` first, then ``Accept``, then default."""
    resolved = validate_format(explicit)
    if resolved is not None:
        return resolved
    return format_from_accept(accept) or default


# ---------------------------------------------------------------------------
# Value encoding
# ---------------------------------------------------------------------------


def _json_default(value: Any) -> Any:
    """JSON encoder fallback for the native Python types DuckDB returns."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, datetime.timedelta):
        # DuckDB INTERVAL (no value[x] mapping, but flat formats still encode it).
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return base64.b64encode(bytes(value)).decode("ascii")
    if isinstance(value, uuid.UUID):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _json_text(value: Any) -> str:
    return json.dumps(value, default=_json_default, ensure_ascii=False)


def row_mapping(result: TabularResult, row: Sequence[Any]) -> dict[str, Any]:
    """One row as an ordered dict keyed by column name."""
    return {column.name: value for column, value in zip(result.columns, row, strict=False)}


def csv_cell(value: Any) -> str:
    """Render one value for CSV output."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return base64.b64encode(bytes(value)).decode("ascii")
    if isinstance(value, (dict, list, tuple)):
        return _json_text(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    return str(value)


def _text(value: Any) -> str:
    """Render one value as plain text (parquet fallback for exotic types)."""
    return csv_cell(value)


# ---------------------------------------------------------------------------
# Flat formats
# ---------------------------------------------------------------------------


def to_ndjson(result: TabularResult) -> bytes:
    """One JSON object per line; zero rows serialize to an empty body."""
    names = result.column_names
    lines = []
    for row in result.rows:
        lines.append(_json_text(dict(zip(names, row, strict=False))))
    if not lines:
        return b""
    return ("\n".join(lines) + "\n").encode("utf-8")


def to_json(result: TabularResult) -> bytes:
    """A JSON array of row objects (the IG's ``_format=json`` shape)."""
    return _json_text(result.row_dicts()).encode("utf-8")


def to_csv(result: TabularResult, *, header: bool = True) -> bytes:
    """RFC 4180 CSV with an optional header row."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    if header:
        writer.writerow(list(result.column_names))
    for row in result.rows:
        writer.writerow([csv_cell(value) for value in row])
    return buffer.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------
# Parquet
# ---------------------------------------------------------------------------


def _arrow_type(column: ResultColumn) -> Any:
    """Map a DuckDB/ISO SQL type to a pyarrow type (``None`` → string fallback)."""
    import pyarrow as pa

    base = normalize_sql_type(column.sql_type)
    match = _DECIMAL_TYPE_PATTERN.match(column.sql_type.strip().upper())
    if base == "DECIMAL" or base == "NUMERIC":
        if match:
            precision, scale = int(match.group(1)), int(match.group(2))
            if 1 <= precision <= 38:
                return pa.decimal128(precision, scale)
        return pa.float64()
    mapping = {
        "BOOLEAN": pa.bool_(),
        "TINYINT": pa.int8(),
        "SMALLINT": pa.int16(),
        "INT": pa.int32(),
        "INTEGER": pa.int32(),
        "BIGINT": pa.int64(),
        "REAL": pa.float32(),
        "FLOAT": pa.float32(),
        "DOUBLE": pa.float64(),
        "DOUBLE PRECISION": pa.float64(),
        "CHAR": pa.string(),
        "CHARACTER": pa.string(),
        "VARCHAR": pa.string(),
        "CHARACTER VARYING": pa.string(),
        "TEXT": pa.string(),
        "CLOB": pa.string(),
        "BINARY": pa.binary(),
        "VARBINARY": pa.binary(),
        "BLOB": pa.binary(),
        "DATE": pa.date32(),
        "TIME": pa.time64("us"),
        "TIMESTAMP": pa.timestamp("us"),
        "DATETIME": pa.timestamp("us"),
        "TIMESTAMP WITH TIME ZONE": pa.timestamp("us", tz="UTC"),
    }
    return mapping.get(base)


def _arrow_values(column: ResultColumn, values: Sequence[Any], arrow_type: Any) -> list[Any]:
    """Normalize values so pyarrow can build the declared column type."""
    import pyarrow as pa

    if arrow_type is None:
        return [None if value is None else _text(value) for value in values]
    if pa.types.is_timestamp(arrow_type) and arrow_type.tz is not None:
        converted = []
        for value in values:
            if isinstance(value, datetime.datetime):
                if value.tzinfo is None:
                    converted.append(value.replace(tzinfo=datetime.timezone.utc))
                else:
                    converted.append(value.astimezone(datetime.timezone.utc))
            else:
                converted.append(value)
        return converted
    if pa.types.is_string(arrow_type):
        return [None if value is None else _text(value) for value in values]
    return list(values)


def to_parquet(result: TabularResult) -> bytes:
    """Write the result set as an Apache Parquet file."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - pyarrow is a base dependency
        raise unsupported(
            f"parquet output requires pyarrow, which is not installed: {exc}",
            expression=["_format"],
        ) from exc

    names = list(result.column_names)
    if len(set(names)) != len(names):
        duplicates = sorted({name for name in names if names.count(name) > 1})
        raise unprocessable(
            f"Cannot write parquet: duplicate result column names {duplicates}. "
            f"Alias the columns in the SQL query.",
            expression=duplicates,
            code="invalid",
        )

    arrays = []
    for index, column in enumerate(result.columns):
        arrow_type = _arrow_type(column)
        values = [row[index] for row in result.rows]
        normalized = _arrow_values(column, values, arrow_type)
        arrays.append(pa.array(normalized, type=arrow_type if arrow_type is not None else pa.string()))

    table = pa.Table.from_arrays(arrays, names=names)
    sink = io.BytesIO()
    pq.write_table(table, sink)
    return sink.getvalue()


# ---------------------------------------------------------------------------
# _format=fhir: Parameters row/part encoding
# ---------------------------------------------------------------------------


def _round_to_millis(value: datetime.datetime) -> datetime.datetime:
    """Round (not truncate) to millisecond precision, per the IG's SHOULD."""
    milliseconds = (value.microsecond + 500) // 1000
    return value.replace(microsecond=0) + datetime.timedelta(milliseconds=milliseconds)


def _trim_fraction(text: str) -> str:
    """Drop trailing zeros in a fractional-seconds component."""
    if "." not in text:
        return text
    head, _, fraction = text.partition(".")
    fraction = fraction.rstrip("0")
    return f"{head}.{fraction}" if fraction else head


def _date_text(value: Any) -> str:
    if isinstance(value, datetime.datetime):
        return value.date().isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    return str(value)


def _time_text(value: Any) -> str:
    if isinstance(value, datetime.datetime):
        return value.time().isoformat()
    if isinstance(value, datetime.time):
        return value.isoformat()
    return str(value)


def _datetime_text(value: Any) -> str:
    if isinstance(value, datetime.datetime):
        return _trim_fraction(value.isoformat())
    if isinstance(value, datetime.date):
        return value.isoformat()
    return str(value)


def _instant_text(value: Any) -> str:
    if isinstance(value, datetime.datetime):
        rounded = _round_to_millis(value)
        text = rounded.isoformat(timespec="milliseconds")
        if text.endswith("+00:00"):
            text = text[: -len("+00:00")] + "Z"
        return text
    return str(value)


def fhir_value(value_type: str, value: Any) -> Any:
    """Encode one SQL value into the IG's ``value[x]`` representation."""
    if value_type == "valueBoolean":
        return bool(value)
    if value_type == "valueInteger":
        return int(value)
    if value_type == "valueInteger64":
        # FHIR integer64 is a JSON string in FHIR JSON, not a JSON number.
        return str(int(value))
    if value_type == "valueDecimal":
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        if isinstance(value, (int, float)):
            return float(value)
        return float(value)
    if value_type == "valueString":
        return str(value)
    if value_type == "valueBase64Binary":
        if isinstance(value, (bytes, bytearray, memoryview)):
            return base64.b64encode(bytes(value)).decode("ascii")
        return str(value)
    if value_type == "valueDate":
        return _date_text(value)
    if value_type == "valueTime":
        return _time_text(value)
    if value_type == "valueDateTime":
        return _datetime_text(value)
    if value_type == "valueInstant":
        return _instant_text(value)
    raise unprocessable(  # pragma: no cover - guarded by to_parameters
        f"Unsupported FHIR value type {value_type!r}", code="not-supported"
    )


def to_parameters(result: TabularResult) -> dict:
    """Encode the result as a FHIR ``Parameters`` resource (``_format=fhir``)."""
    unmapped = [
        f"{column.name} ({column.sql_type})"
        for column in result.columns
        if column.fhir_type is None
    ]
    if unmapped:
        raise unprocessable(
            "Cannot encode result as FHIR Parameters: these columns have SQL types "
            f"with no value[x] mapping per the SQL-on-FHIR type table: {', '.join(unmapped)}. "
            "Cast them to a supported type in the query.",
            expression=[column.name for column in result.columns if column.fhir_type is None],
            code="not-supported",
        )

    outcome: dict = {"resourceType": "Parameters"}
    parameters = []
    for row in result.rows:
        parts = []
        for column, value in zip(result.columns, row, strict=False):
            if value is None:
                # SQL NULL: the IG requires omitting the part entirely.
                continue
            parts.append({"name": column.name, column.fhir_type: fhir_value(column.fhir_type, value)})
        parameters.append({"name": "row", "part": parts})
    if parameters:
        outcome["parameter"] = parameters
    return outcome


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def serialize(
    result: TabularResult,
    output_format: str,
    *,
    header: bool = True,
) -> tuple[bytes, str]:
    """Serialize a result set for ``output_format``.

    Returns ``(body_bytes, content_type)``. ``_format=fhir`` returns the JSON
    encoding of a ``Parameters`` resource with the FHIR media type.
    """
    if output_format == "ndjson":
        return to_ndjson(result), CONTENT_TYPES["ndjson"]
    if output_format == "json":
        return to_json(result), CONTENT_TYPES["json"]
    if output_format == "csv":
        return to_csv(result, header=header), CONTENT_TYPES["csv"]
    if output_format == "parquet":
        return to_parquet(result), CONTENT_TYPES["parquet"]
    if output_format == "fhir":
        body = json.dumps(to_parameters(result), default=_json_default, ensure_ascii=False)
        return body.encode("utf-8"), CONTENT_TYPES["fhir"]
    raise bad_request(
        f"Format {output_format!r} is not supported. Supported formats: "
        f"{', '.join(OUTPUT_FORMATS)}",
        expression=["_format"],
        code="not-supported",
    )


__all__ = [
    "DEFAULT_FORMAT",
    "OUTPUT_FORMATS",
    "CONTENT_TYPES",
    "ACCEPT_FORMATS",
    "negotiate_format",
    "validate_format",
    "format_from_accept",
    "row_mapping",
    "csv_cell",
    "to_ndjson",
    "to_json",
    "to_csv",
    "to_parquet",
    "to_parameters",
    "fhir_value",
    "serialize",
]
