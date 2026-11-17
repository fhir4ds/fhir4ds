"""Temporal normalization for the temporal-dedup pipeline (AMUX-142 slice 1).

Pure, deterministic extraction of the primary temporal field per resource
type (v1 scope: Observation, Procedure, Condition, Immunization) into a
:class:`NormalizedDate` carrying the authored-precision signature, the
authored-local partition date, and UTC instants where the authored value
determines them.

Design grounding: FEATURE_TEMPORAL_DEDUP.md §1.2 (extraction map), §2a
(authored-local partition keys; a default TZ is used ONLY where no authored
offset exists — Z-suffixed instants and naive-bound span derivation), §9
(checkpoint resolution).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

__all__ = [
    "Signature",
    "NormalizedDate",
    "DEFAULT_TZ",
    "normalize_temporal",
    "secondary_timestamp",
]


class Signature:
    """Authored-precision signature of a temporal value (plain str constants)."""

    YEAR = "YEAR"
    MONTH = "MONTH"
    DATE_ONLY = "DATE_ONLY"
    DT_NAIVE = "DT_NAIVE"
    DT_Z = "DT_Z"
    DT_OFFSET = "DT_OFFSET"


#: Default timezone used to derive ``local_date`` for Z-suffixed instants and
#: to extend date-level values to UTC spans. Explicit config surface per
#: design §2a — never a wall-clock read.
DEFAULT_TZ = "America/Chicago"

# Precision rank for "more precise bound" decisions (all DT_* share rank 3;
# the DT flavor tie-break is handled separately).
_PRECISION_RANK = {
    Signature.YEAR: 0,
    Signature.MONTH: 1,
    Signature.DATE_ONLY: 2,
    Signature.DT_NAIVE: 3,
    Signature.DT_Z: 3,
    Signature.DT_OFFSET: 3,
}

# Primary temporal choice fields per resource type, in COALESCE preference
# order (design §1.2). Non-temporal variants (performedString, onsetAge,
# onsetRange, occurrenceString) are deliberately absent: they get signature
# NULL and never escalate (v1 scope decision).
_TEMPORAL_FIELDS: dict[str, tuple[tuple[str, str], ...]] = {
    "Observation": (
        ("effectiveDateTime", "datetime"),
        ("effectivePeriod", "period"),
        ("effectiveInstant", "datetime"),
    ),
    "Procedure": (
        ("performedDateTime", "datetime"),
        ("performedPeriod", "period"),
    ),
    "Condition": (
        ("onsetDateTime", "datetime"),
        ("onsetPeriod", "period"),
    ),
    "Immunization": (("occurrenceDateTime", "datetime"),),
}

# Secondary scalar timestamps (cross-field checks arrive in a later slice).
_SECONDARY_FIELDS: dict[str, str] = {
    "Observation": "issued",
    "Condition": "recordedDate",
}

_MONTH_DAYS = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
               7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}


@dataclass(frozen=True)
class NormalizedDate:
    """Normalized temporal value.

    Attributes:
        signature: authored precision (one of the :class:`Signature` constants).
        local_date: authored-local date prefix ``YYYY[-MM[-DD]]`` — the Stage-1
            partition key. For Z-suffixed instants (no authored offset) the
            instant rendered in the configured default TZ.
        dt_utc: exact UTC instant (``...Z``) for offset-bearing datetimes;
            None otherwise (design §2a: naive values never get a partition
            instant).
        start_utc / end_utc: bounded UTC span. Precise instants collapse to a
            point span; YEAR/MONTH/DATE_ONLY extend to the full calendar span
            in the default TZ; naive datetimes stay None (Stage-2 concern).
    """

    signature: str
    local_date: str
    dt_utc: Optional[str] = None
    start_utc: Optional[str] = None
    end_utc: Optional[str] = None


def _tz(name: str) -> ZoneInfo:
    return ZoneInfo(name)


def _format_instant(dt: datetime) -> str:
    """Format an aware datetime as a deterministic UTC string with Z suffix."""
    utc = dt.astimezone(timezone.utc)
    text = utc.strftime("%Y-%m-%dT%H:%M:%S")
    ms = utc.microsecond
    if ms:
        text += f".{ms // 1000:03d}"
    return text + "Z"


def _local_midnight_utc(local_date: date, tz: ZoneInfo) -> datetime:
    # fold=0 fixed: DST-ambiguous local midnights resolve deterministically.
    return datetime(local_date.year, local_date.month, local_date.day,
                    tzinfo=tz, fold=0)


def _parse_parts(raw: str) -> Optional[tuple[int, int, int, Optional[int]]]:
    """Strictly parse the date component prefix of a FHIR date/dateTime.

    Returns (year, month, day, day_precision) where day_precision is False
    for partial dates (the tuple still carries 1/1 placeholders). None on
    any lexical or calendar violation.
    """
    date_part = raw[:10] if len(raw) > 10 else raw
    pieces = date_part.split("-")
    try:
        if len(pieces) == 1:
            if len(pieces[0]) != 4 or not pieces[0].isdigit():
                return None
            return int(pieces[0]), 1, 1, False
        if len(pieces) == 2:
            if len(pieces[0]) != 4 or len(pieces[1]) != 2:
                return None
            y, m = int(pieces[0]), int(pieces[1])
            if not 1 <= m <= 12:
                return None
            return y, m, 1, False
        if len(pieces) == 3:
            if len(pieces[0]) != 4 or len(pieces[1]) != 2 or len(pieces[2]) != 2:
                return None
            y, m, d = int(pieces[0]), int(pieces[1]), int(pieces[2])
            if not 1 <= m <= 12:
                return None
            max_d = _MONTH_DAYS[m]
            if m == 2 and (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)):
                max_d = 29
            if not 1 <= d <= max_d:
                return None
            return y, m, d, True
    except ValueError:
        return None
    return None


def _parse_time_and_offset(raw: str) -> Optional[tuple]:
    """Parse ``[T]hh[:mm[:ss[.f*]]][Z|±hh:mm]``.

    Returns (tzinfo|None-marker, hour, minute, second, microsecond, has_z,
    has_offset). The naive marker is None for tzinfo with has_offset False.
    """
    if not raw or raw[0] not in "Tt":
        return None
    body = raw[1:]
    if not body:
        return None
    # split offset
    has_z = has_offset = False
    tz = None
    if body.endswith(("Z", "z")):
        has_z = True
        tz = timezone.utc
        body = body[:-1]
    else:
        for i in range(len(body) - 1, max(len(body) - 7, -1), -1):
            c = body[i]
            if c in "+-":
                off = body[i + 1:]
                parts = off.split(":")
                if len(parts) != 2 or len(parts[0]) != 2 or len(parts[1]) != 2:
                    return None
                try:
                    oh, om = int(parts[0]), int(parts[1])
                except ValueError:
                    return None
                if om > 59 or abs(oh) > 14 or (abs(oh) == 14 and om != 0):
                    return None
                if c == "-" and oh == 0 and om == 0:
                    return None  # -00:00 is not a FHIR-authored offset
                delta = timedelta(hours=oh, minutes=om)
                if c == "-":
                    delta = -delta
                tz = timezone(delta)
                has_offset = True
                body = body[:i]
                break
            if c == ":" or c.isdigit() or c == ".":
                continue
            return None
    comps = body.split(":")
    if not 1 <= len(comps) <= 3:
        return None
    try:
        hour = int(comps[0])
        minute = int(comps[1]) if len(comps) > 1 else 0
        sec = 0
        micro = 0
        if len(comps) > 2:
            sec_part = comps[2]
            if "." in sec_part:
                sec_str, frac = sec_part.split(".", 1)
                if not frac or len(frac) > 9 or not frac.isdigit():
                    return None
                sec = int(sec_str)
                micro = int((frac + "000000")[:6])
            else:
                sec = int(sec_str := sec_part)
        else:
            sec_str = None
    except ValueError:
        return None
    if hour > 23 or minute > 59 or sec > 59:
        return None
    if len(comps) < 3 and ("." in body):
        return None
    return tz, hour, minute, sec, micro, has_z, has_offset


def _classify_datetime(raw: str) -> Optional[tuple[str, datetime, str]]:
    """Classify a dateTime/instant string.

    Returns (signature, aware-or-naive datetime, local_date_prefix) or None
    on malformed input.
    """
    if not isinstance(raw, str) or not raw:
        return None
    parsed = _parse_parts(raw)
    if parsed is None:
        return None
    y, m, d, day_prec = parsed
    time_part = raw[10:] if len(raw) > 10 else ""
    if not day_prec:
        # Partial dates cannot carry a time component.
        if time_part:
            return None
        if len(raw) == 4:
            return Signature.YEAR, datetime(y, 1, 1), raw
        return Signature.MONTH, datetime(y, m, 1), raw
    if time_part == "":
        return Signature.DATE_ONLY, datetime(y, m, d), raw
    t = _parse_time_and_offset(time_part)
    if t is None:
        return None
    tz, hour, minute, sec, micro, has_z, has_offset = t
    naive = datetime(y, m, d, hour, minute, sec, micro)
    if has_z:
        sig = Signature.DT_Z
    elif has_offset:
        sig = Signature.DT_OFFSET
    else:
        sig = Signature.DT_NAIVE
    return sig, (naive.replace(tzinfo=tz) if tz is not None else naive), raw[:10]


def _span_for_date_level(signature: str, local: date,
                         tz: ZoneInfo) -> tuple[Optional[str], Optional[str]]:
    start_local = _local_midnight_utc(local, tz)
    if signature == Signature.YEAR:
        end_local = _local_midnight_utc(date(local.year + 1, 1, 1), tz)
    elif signature == Signature.MONTH:
        if local.month == 12:
            end_local = _local_midnight_utc(date(local.year + 1, 1, 1), tz)
        else:
            end_local = _local_midnight_utc(date(local.year, local.month + 1, 1), tz)
    else:  # DATE_ONLY
        end_local = _local_midnight_utc(local + timedelta(days=1), tz)
    return _format_instant(start_local), _format_instant(end_local)


def _build(signature: str, local_date: str, dt: datetime,
           tz: ZoneInfo) -> NormalizedDate:
    if signature in (Signature.DT_Z, Signature.DT_OFFSET):
        dt_utc = _format_instant(dt)
        return NormalizedDate(signature=signature, local_date=local_date,
                              dt_utc=dt_utc, start_utc=dt_utc, end_utc=dt_utc)
    if signature == Signature.DT_NAIVE:
        # Design §2a: naive datetimes never get partition instants; the
        # default TZ applies only inside Stage-2 comparisons.
        return NormalizedDate(signature=signature, local_date=local_date)
    # Date-level: extend to the full calendar span in the default TZ.
    parts = local_date.split("-") + ["1"] * (3 - local_date.count("-") - 1)
    y, m, d = (int(p) for p in parts)
    local = date(y, m, d)
    start_utc, end_utc = _span_for_date_level(signature, local, tz)
    return NormalizedDate(signature=signature, local_date=local_date,
                          start_utc=start_utc, end_utc=end_utc)


def _local_date_for(signature: str, dt: datetime, authored_prefix: str,
                    tz: ZoneInfo) -> str:
    if signature == Signature.DT_Z:
        # No authored offset: render the instant in the configured default TZ.
        return dt.astimezone(tz).strftime("%Y-%m-%d")
    # Authored-local (offset-applied wall clock or naive wall clock).
    return authored_prefix


def _classify_bound(raw) -> Optional[tuple[str, datetime, str]]:
    if not isinstance(raw, str) or not raw:
        return None
    return _classify_datetime(raw)


def _dt_flavor(signature: str) -> int:
    # Deterministic tie-break among equally-precise DT flavors.
    return {Signature.DT_NAIVE: 0, Signature.DT_Z: 1,
            Signature.DT_OFFSET: 2}.get(signature, 0)


def _normalize_period(period: dict, tz: ZoneInfo) -> Optional[NormalizedDate]:
    start = _classify_bound(period.get("start"))
    if start is None:
        return None
    end = _classify_bound(period.get("end"))
    if "end" in period and period.get("end") not in (None, "") and end is None:
        return None  # strict: a malformed bound invalidates the period
    bounds = [b for b in (start, end) if b is not None]
    # The PAIR's signature is the more precise bound (design slice spec).
    best = max(bounds, key=lambda b: (_PRECISION_RANK[b[0]], _dt_flavor(b[0])))
    pair_sig = best[0]

    def bound_utc(bound) -> Optional[str]:
        sig, dt, _ = bound
        if sig in (Signature.DT_Z, Signature.DT_OFFSET):
            return _format_instant(dt)
        return None  # naive/date-level bounds carry no authored instant

    start_utc = bound_utc(start)
    end_utc = bound_utc(end) if end is not None else None
    local_date = _local_date_for(start[0], start[1], start[2], tz)
    return NormalizedDate(signature=pair_sig, local_date=local_date,
                          dt_utc=None, start_utc=start_utc, end_utc=end_utc)


def normalize_temporal(resource: dict, *,
                       default_tz: str = DEFAULT_TZ) -> Optional[NormalizedDate]:
    """Extract and normalize the primary temporal field of a resource.

    Returns None when the resource type has no v1 temporal mapping, the
    primary field is absent, or the authored value is malformed (strict
    parsing — never a guess, never wall-clock).
    """
    if not isinstance(resource, dict):
        return None
    rtype = resource.get("resourceType")
    fields = _TEMPORAL_FIELDS.get(rtype) if isinstance(rtype, str) else None
    if not fields:
        return None
    tz = _tz(default_tz)
    for field_name, kind in fields:
        value = resource.get(field_name)
        if value is None or value == "":
            continue
        if kind == "period":
            if not isinstance(value, dict):
                continue
            result = _normalize_period(value, tz)
            if result is not None:
                return result
            continue
        classified = _classify_bound(value)
        if classified is None:
            continue  # malformed variant — try the next choice arm
        signature, dt, prefix = classified
        local_date = _local_date_for(signature, dt, prefix, tz)
        return _build(signature, local_date, dt, tz)
    return None


def secondary_timestamp(resource: dict, *,
                        default_tz: str = DEFAULT_TZ) -> Optional[NormalizedDate]:
    """Extract the secondary scalar timestamp (Observation.issued,
    Condition.recordedDate) for later cross-field checks. Same strict
    contract as :func:`normalize_temporal`; None when absent/invalid."""
    if not isinstance(resource, dict):
        return None
    rtype = resource.get("resourceType")
    field_name = _SECONDARY_FIELDS.get(rtype) if isinstance(rtype, str) else None
    if not field_name:
        return None
    classified = _classify_bound(resource.get(field_name))
    if classified is None:
        return None
    tz = _tz(default_tz)
    signature, dt, prefix = classified
    local_date = _local_date_for(signature, dt, prefix, tz)
    return _build(signature, local_date, dt, tz)
