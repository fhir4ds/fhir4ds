"""AMUX-150 chunk B — identity-resource field extractors.

Per-type extractors following the :func:`~fhir4ds.matching.normalizers.
extract_patient_fields` pattern: a FHIR resource in, a normalized
``field_name -> values`` map out, reusing the shared normalizers
(``norm_text``, ``norm_phone``, ``norm_name_parts``, nickname/suffix
machinery). The auditable raw counterpart of each extractor is the
matching ViewDefinition artifact
(``fhir4ds/matching/artifacts/<type>_match_fields.vd.json``).

Wall-clock note (FDD §9): unlike the patient extractor, these introduce
NO date normalization, so no ``as_of`` determinism surface is needed.
"""

from __future__ import annotations

import re
from typing import Optional

from .normalizers import (
    _dedup,
    norm_name_parts,
    norm_phone,
    norm_text,
    norm_text_keep_dots,
)

__all__ = [
    "extract_practitioner_fields",
    "extract_organization_fields",
    "extract_location_fields",
]

_NPI_SYSTEM_KEYS = ("us-npi", "2.16.840.1.113883.4.6")
_CLIA_SYSTEM_KEYS = ("clia", "2.16.840.1.113883.4.82")
# The TAX OID is a PREFIX of the NPI/CLIA/ITIN OIDs — substring matching
# would misclassify, so tax matching is exact-OID or keyword based.
_TAX_OID = "2.16.840.1.113883.4.2"
_TAX_KEYWORDS = ("tax", "tin", "ein")


def _norm_ident(value: str) -> Optional[str]:
    normalized = norm_text(value)
    if normalized is None:
        return None
    return normalized.replace(" ", "") or None


def _identifier_system(identifier: dict) -> str:
    system = identifier.get("system") or ""
    return system.lower() if isinstance(system, str) else ""


def _identifier_value(identifier: dict) -> Optional[str]:
    value = identifier.get("value")
    if not isinstance(value, str) or not value.strip():
        return None
    return _norm_ident(value)


def _phones(telecom) -> list[str]:
    out = []
    for entry in telecom or []:
        if not isinstance(entry, dict) or entry.get("system") != "phone":
            continue
        out.append(norm_phone(entry.get("value")))
    return out


def _emails(telecom) -> list[str]:
    out = []
    for entry in telecom or []:
        if not isinstance(entry, dict) or entry.get("system") != "email":
            continue
        value = entry.get("value")
        if isinstance(value, str) and value.strip():
            out.append(norm_text_keep_dots(value))
    return out


def _first_address_lines(address, count: int = 1) -> list[str]:
    out = []
    for address_entry in address or []:
        if not isinstance(address_entry, dict):
            continue
        lines = address_entry.get("line") or []
        if isinstance(lines, str):
            lines = [lines]
        lines = [ln for ln in lines if isinstance(ln, str)]
        if lines:
            out.append(norm_text(lines[0]))
    return out


def _addr_key(address_entry: dict) -> Optional[str]:
    lines = address_entry.get("line") or []
    if isinstance(lines, str):
        lines = [lines]
    lines = [ln for ln in lines if isinstance(ln, str)]
    if not lines:
        return None
    city = norm_text(address_entry.get("city")) or ""
    state = norm_text(address_entry.get("state")) or ""
    postal_raw = address_entry.get("postalCode")
    postal = re.sub(r"\D", "", postal_raw)[:5] \
        if isinstance(postal_raw, str) else ""
    key = "|".join([norm_text(lines[0]) or "", city, state, postal])
    return key if key.strip("|") else None


def _name_parts_to_fields(names: list, out: dict) -> None:
    """Shared HumanName extraction (patient-style): official-preferred,
    family -> last, given -> first, suffix tokens -> suffix."""
    official = [n for n in names
                if isinstance(n, dict) and n.get("use") == "official"] or \
        [n for n in names if isinstance(n, dict)]
    for name in official:
        family = name.get("family")
        given = name.get("given") or []
        if isinstance(given, str):
            given = [given]
        given = [g for g in given if isinstance(g, str)]
        if isinstance(family, str):
            parsed = norm_name_parts(family)
            if parsed is not None:
                if parsed[0]:
                    out.setdefault("last", []).append(" ".join(parsed[0]))
                for suffix in parsed[1]:
                    out.setdefault("suffix", []).append(suffix)
        for g in given:
            parsed = norm_name_parts(g)
            if parsed is not None:
                if parsed[0]:
                    out.setdefault("first", []).append(" ".join(parsed[0]))
                for suffix in parsed[1]:
                    out.setdefault("suffix", []).append(suffix)


def extract_practitioner_fields(resource: dict) -> dict[str, list[str]]:
    """Practitioner match fields: ``last``, ``first``, ``suffix``,
    ``npi``, ``street_line``, ``phone``, ``email`` (FDD §3.2)."""
    if not isinstance(resource, dict):
        raise TypeError(
            f"resource must be a dict (a FHIR Practitioner resource), "
            f"got {type(resource).__name__}")
    out: dict[str, list[str]] = {}

    _name_parts_to_fields(resource.get("name") or [], out)

    for identifier in resource.get("identifier") or []:
        if not isinstance(identifier, dict):
            continue
        system = _identifier_system(identifier)
        if not system:
            continue
        if any(key in system for key in _NPI_SYSTEM_KEYS):
            value = _identifier_value(identifier)
            if value:
                out.setdefault("npi", []).append(value)

    for street in _first_address_lines(resource.get("address")):
        out.setdefault("street_line", []).append(street)
    for phone in _phones(resource.get("telecom")):
        out.setdefault("phone", []).append(phone)
    for email in _emails(resource.get("telecom")):
        out.setdefault("email", []).append(email)

    return {k: _dedup(v) for k, v in out.items() if _dedup(v)}


def extract_organization_fields(resource: dict) -> dict[str, list[str]]:
    """Organization match fields: ``org_name`` (name ∪ alias), ``npi``,
    ``clia``, ``tax_id``, ``street_line``, ``addr_key``, ``phone``
    (FDD §3.2; addr_key additionally feeds rule O4)."""
    if not isinstance(resource, dict):
        raise TypeError(
            f"resource must be a dict (a FHIR Organization resource), "
            f"got {type(resource).__name__}")
    out: dict[str, list[str]] = {}

    name = resource.get("name")
    if isinstance(name, str):
        normalized = norm_text(name)
        if normalized:
            out.setdefault("org_name", []).append(normalized)
    for alias in resource.get("alias") or []:
        if isinstance(alias, str):
            normalized = norm_text(alias)
            if normalized:
                out.setdefault("org_name", []).append(normalized)

    for identifier in resource.get("identifier") or []:
        if not isinstance(identifier, dict):
            continue
        system = _identifier_system(identifier)
        if not system:
            continue
        value = _identifier_value(identifier)
        if not value:
            continue
        oid = system.removeprefix("urn:oid:")
        if any(key in system for key in _NPI_SYSTEM_KEYS):
            out.setdefault("npi", []).append(value)
        elif any(key in system for key in _CLIA_SYSTEM_KEYS):
            out.setdefault("clia", []).append(value)
        elif oid == _TAX_OID or any(k in system for k in _TAX_KEYWORDS):
            out.setdefault("tax_id", []).append(value)

    for address_entry in resource.get("address") or []:
        if not isinstance(address_entry, dict):
            continue
        key = _addr_key(address_entry)
        if key:
            out.setdefault("addr_key", []).append(key)
    for street in _first_address_lines(resource.get("address")):
        out.setdefault("street_line", []).append(street)
    for phone in _phones(resource.get("telecom")):
        out.setdefault("phone", []).append(phone)

    return {k: _dedup(v) for k, v in out.items() if _dedup(v)}


def extract_location_fields(resource: dict) -> dict[str, list[str]]:
    """Location match fields: ``loc_name``, ``addr_key``, ``phone``,
    ``geo_key`` (FDD §3.2; geo_key rounded to ~1 km, absent unless BOTH
    position components are present)."""
    if not isinstance(resource, dict):
        raise TypeError(
            f"resource must be a dict (a FHIR Location resource), "
            f"got {type(resource).__name__}")
    out: dict[str, list[str]] = {}

    name = resource.get("name")
    if isinstance(name, str):
        normalized = norm_text(name)
        if normalized:
            out.setdefault("loc_name", []).append(normalized)

    for address_entry in resource.get("address") or []:
        if not isinstance(address_entry, dict):
            continue
        key = _addr_key(address_entry)
        if key:
            out.setdefault("addr_key", []).append(key)
    for phone in _phones(resource.get("telecom")):
        out.setdefault("phone", []).append(phone)

    position = resource.get("position")
    if isinstance(position, dict):
        latitude = position.get("latitude")
        longitude = position.get("longitude")
        if isinstance(latitude, (int, float)) and not isinstance(
                latitude, bool) \
                and isinstance(longitude, (int, float)) and not isinstance(
                longitude, bool):
            out.setdefault("geo_key", []).append(
                f"{latitude:.2f},{longitude:.2f}")

    return {k: _dedup(v) for k, v in out.items() if _dedup(v)}
