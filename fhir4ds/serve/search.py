"""FHIR search, deliberately small: the subset the write surface needs.

Two things use this:

* ``GET /{type}`` — a ``searchset`` Bundle over the latest-wins view;
* conditional writes — ``If-None-Exist`` (conditional create) and
  ``PUT /{type}?…`` (conditional update), which both need "does this match
  exactly zero, one, or many resources?".

Supported parameters are ``_id``, ``identifier``, ``_count`` and ``_offset``.
Anything else is a **400** ``not-supported`` naming what is supported. Silently
ignoring an unknown filter would answer a different question than the client
asked — the one failure mode a clinical API must not have. Adding a parameter
means teaching :func:`parse_search` and :func:`condition_sql`, with tests.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .errors import bad_request, unsupported
from .versioning import LATEST_VIEW

#: Resource-type lexical space (FHIR `code` for resourceType).
RESOURCE_TYPE_PATTERN = re.compile(r"^[A-Z][A-Za-z0-9]{0,63}$")

#: Parameters this surface understands.
SUPPORTED_PARAMETERS: tuple[str, ...] = ("_id", "identifier", "_count", "_offset")

#: Default page size when ``_count`` is absent.
DEFAULT_PAGE_SIZE = 100


@dataclass(frozen=True)
class SearchQuery:
    """A parsed search: a resource type plus the filters we support."""

    resource_type: str
    ids: tuple[str, ...] = ()
    identifiers: tuple[tuple[str | None, str], ...] = ()

    @property
    def has_filter(self) -> bool:
        return bool(self.ids or self.identifiers)


def parse_search(resource_type: str, query_params: Any) -> SearchQuery:
    """Parse query parameters, rejecting anything unsupported."""
    validate_resource_type(resource_type)

    ids: list[str] = []
    identifiers: list[tuple[str | None, str]] = []

    for name, values in _pairs(query_params):
        if name in ("_count", "_offset"):
            continue  # paging is read by the caller (search_controls)
        if name not in SUPPORTED_PARAMETERS:
            raise unsupported(
                f"Unsupported search parameter {name!r}. Supported: "
                f"{', '.join(sorted(SUPPORTED_PARAMETERS))}",
                expression=[name],
            )
        for value in str(values).split(","):
            entry = value.strip()
            if not entry:
                continue
            if name == "_id":
                ids.append(entry)
            else:
                identifiers.append(_parse_identifier(entry))

    return SearchQuery(
        resource_type=resource_type,
        ids=tuple(ids),
        identifiers=tuple(identifiers),
    )


def parse_query_string(value: str) -> list[tuple[str, str]]:
    """Parse an ``If-None-Exist`` header into ``(name, value)`` pairs."""
    from urllib.parse import parse_qsl

    return parse_qsl(value, keep_blank_values=True)


def _pairs(query_params: Any) -> list[tuple[str, str]]:
    """Normalize a Starlette ``QueryParams`` or a pair list."""
    if not query_params:
        return []
    if hasattr(query_params, "multi_items"):
        return list(query_params.multi_items())
    return list(query_params)


def validate_resource_type(resource_type: str) -> str:
    if not isinstance(resource_type, str) or not RESOURCE_TYPE_PATTERN.match(resource_type):
        raise bad_request(
            f"{resource_type!r} is not a FHIR resource type",
            expression=["resourceType"],
            code="value",
        )
    return resource_type


def _parse_identifier(value: str) -> tuple[str | None, str]:
    """Parse ``system|value`` / ``|value`` / ``value`` into its parts."""
    if "|" not in value:
        return None, value
    system, _, code = value.partition("|")
    return system, code


def condition_sql(query: SearchQuery) -> tuple[str, list[Any]]:
    """SQL ``WHERE`` fragment (and parameters) selecting the query's matches.

    Identifiers match entries of the resource's ``identifier`` array, which is
    how FHIR token search works on a resource we store whole; repeated
    ``identifier`` parameters are ANDed, as FHIR specifies.
    """
    clauses: list[str] = []
    parameters: list[Any] = []

    if query.ids:
        placeholders = ", ".join("?" for _ in query.ids)
        clauses.append(f"id IN ({placeholders})")
        parameters.extend(query.ids)

    for system, code in query.identifiers:
        sub = [
            "json_extract_string(entry.value, '$.value') = ?",
        ]
        parameters.append(code)
        if system is not None:
            sub.append("coalesce(json_extract_string(entry.value, '$.system'), '') = ?")
            parameters.append(system)
        clauses.append(
            "EXISTS (SELECT 1 FROM json_each(resource, '$.identifier') AS entry "
            f"WHERE {' AND '.join(sub)})"
        )

    return (" AND ".join(clauses) or "TRUE"), parameters


def search(
    connection: Any,
    query: SearchQuery,
    *,
    count: int | None = None,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Return ``(page_of_resources, total_matches)`` for one query."""
    where, parameters = condition_sql(query)
    base = f"FROM {LATEST_VIEW} WHERE resourceType = ?"
    arguments = [query.resource_type, *parameters]

    total = connection.execute(
        f"SELECT count(*) {base} AND ({where})", arguments
    ).fetchone()[0]

    limit = DEFAULT_PAGE_SIZE if count is None else max(0, count)
    rows = connection.execute(
        f"SELECT resource {base} AND ({where}) ORDER BY id LIMIT ? OFFSET ?",
        [*arguments, limit, max(0, offset)],
    ).fetchall()

    resources: list[dict] = []
    for row in rows:
        payload = row[0]
        resources.append(json.loads(payload) if isinstance(payload, str) else payload)
    return resources, int(total)


def match_count(connection: Any, query: SearchQuery) -> int:
    """How many resources a conditional request matches."""
    where, parameters = condition_sql(query)
    return int(
        connection.execute(
            f"SELECT count(*) FROM {LATEST_VIEW} WHERE resourceType = ? AND ({where})",
            [query.resource_type, *parameters],
        ).fetchone()[0]
    )


def first_match(connection: Any, query: SearchQuery) -> dict | None:
    """The single matching resource (caller has checked the count)."""
    resources, _ = search(connection, query, count=1)
    return resources[0] if resources else None


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "SUPPORTED_PARAMETERS",
    "SearchQuery",
    "condition_sql",
    "first_match",
    "match_count",
    "parse_query_string",
    "parse_search",
    "search",
    "validate_resource_type",
]
