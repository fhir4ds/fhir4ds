"""FHIR-native write surface: versioned writes, reads, history and bundles.

Every write appends one version row to the append-only log
(:mod:`fhir4ds.serve.versioning`) with a writer-assigned ``_seq``; reads go
through the latest-wins view, so a client sees its write immediately while the
row is still pending publication. ``meta.versionId`` is that ``_seq`` — the
same number the dataset's ``_seq`` column carries, which is what makes
``_history``, ``If-Match`` and the published parquet agree.

Status codes are the FHIR REST ones (``201``/``200``/``204``/``410``/``412``/
``415``) because clients depend on them. Buffering is visible, but out of band:
``X-Pending-Commits`` on every write, ``pending`` in ``/health``, ``committed``
from ``POST /admin/flush``. (The brief's ``202 {accepted, pending}`` for writes
would contradict its own FHIR surface table; see the design doc's decisions.)
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, Body, Request
from starlette.responses import Response

from . import bulk_publish, search, versioning
from .config import context_for
from .errors import Issue, ServeError, bad_request, not_found, unprocessable, unsupported
from .parameters import decode_json_body
from .resources import paging_links, search_controls, searchset_bundle

FHIR_JSON = "application/fhir+json"
JSON_CONTENT_TYPES = ("application/fhir+json", "application/json")

#: FHIR ``id`` lexical space, same rule the definition registry enforces.
ID_PATTERN = re.compile(r"^[A-Za-z0-9\-.]{1,64}$")

#: Header reporting how many rows are still waiting for a Hub commit.
PENDING_HEADER = "X-Pending-Commits"

#: Types owned by the definition registry (phase 1/2). Generic resource writes
#: would bypass the registry's canonical/url handling, so they are refused with
#: a pointer at the routes that do own them.
REGISTRY_OWNED_TYPES: tuple[str, ...] = ("Library", "ViewDefinition")

#: Write result statuses as FHIR spells them in a bundle response.
STATUS_CREATED = "201 Created"
STATUS_OK = "200 OK"
STATUS_DELETED = "204 No Content"


def etag_for(seq: int) -> str:
    """Weak ETag carrying the version id (``W/"3"``)."""
    return f'W/"{seq}"'


def parse_if_match(value: str | None) -> int | None:
    """Parse ``If-Match`` into a version id.

    ``*`` means "any existing version" and is reported as ``0``. A malformed
    value raises the FHIR ``412`` (a precondition the client asserted cannot be
    evaluated is not satisfiable either).
    """
    if value is None:
        return None
    candidate = value.strip()
    if candidate == "*":
        return 0
    if candidate.startswith("W/"):
        candidate = candidate[2:]
    candidate = candidate.strip('"')
    if not candidate.isdigit():
        raise precondition_failed(f"If-Match {value!r} is not a version id")
    return int(candidate)


def precondition_failed(message: str) -> ServeError:
    """412 — the resource does not match the asserted version."""
    return ServeError(412, [Issue(code="conflict", diagnostics=message)])


@dataclass
class WriteResult:
    """One applied write."""

    resource: dict
    seq: int
    created: bool
    deleted: bool = False
    publish_row: dict = field(default_factory=dict)

    @property
    def status(self) -> str:
        if self.deleted:
            return STATUS_DELETED
        return STATUS_CREATED if self.created else STATUS_OK


class ResourceWriter:
    """Assigns versions, persists them, and reads them back.

    All methods require the caller to hold the connection lock
    (``ServeContext.run_locked``).
    """

    def __init__(self, connection: Any, *, seq: int) -> None:
        self._connection = connection
        self._seq = max(0, int(seq))

    @property
    def seq(self) -> int:
        """Last assigned sequence (the next write takes ``seq + 1``)."""
        return self._seq

    # -- writes ----------------------------------------------------------

    def create(self, resource_type: str, resource: dict) -> WriteResult:
        """Create (or reject a duplicate) with a server-assigned id when absent."""
        _require_type(resource, resource_type)
        resource = dict(resource)
        resource_id = resource.get("id")
        if resource_id is None:
            resource_id = uuid.uuid4().hex
            resource["id"] = resource_id
        validate_id(resource_id)

        existing = versioning.latest_row(self._connection, resource_type, resource_id)
        if existing is not None and not existing["deleted"]:
            raise bad_request(
                f"{resource_type} with id {resource_id!r} already exists; use PUT to "
                "create a new version",
                expression=["id"],
                code="duplicate",
            )
        return self._append(resource_type, resource_id, resource, created=True)

    def update(
        self,
        resource_type: str,
        resource_id: str,
        resource: dict,
        *,
        if_match: int | None = None,
    ) -> WriteResult:
        """Create-or-update one resource, honouring ``If-Match``."""
        _require_type(resource, resource_type)
        validate_id(resource_id)
        body_id = resource.get("id")
        if body_id is not None and body_id != resource_id:
            raise bad_request(
                f"Resource id {body_id!r} does not match the path id {resource_id!r}",
                expression=["id"],
                code="value",
            )
        resource = dict(resource)
        resource["id"] = resource_id

        latest = versioning.latest_row(self._connection, resource_type, resource_id)
        if if_match is not None:
            if latest is None:
                raise precondition_failed(
                    f"If-Match asserted a version for {resource_type}/{resource_id}, "
                    "which does not exist"
                )
            if if_match != 0 and latest["seq"] != if_match:
                raise precondition_failed(
                    f"If-Match W/\"{if_match}\" does not match the current version "
                    f"W/\"{latest['seq']}\" of {resource_type}/{resource_id}"
                )
        created = latest is None or latest["deleted"]
        return self._append(resource_type, resource_id, resource, created=created)

    def delete(self, resource_type: str, resource_id: str) -> WriteResult:
        """Tombstone a resource: gone from reads, still in ``_history``."""
        validate_id(resource_id)
        latest = versioning.latest_row(self._connection, resource_type, resource_id)
        if latest is None or latest["deleted"]:
            raise not_found(f"{resource_type} with id {resource_id!r} not found")
        resource = dict(latest["resource"])
        return self._append(resource_type, resource_id, resource, created=False, deleted=True)

    def _append(
        self,
        resource_type: str,
        resource_id: str,
        resource: dict,
        *,
        created: bool,
        deleted: bool = False,
    ) -> WriteResult:
        self._seq += 1
        seq = self._seq
        stored = _with_meta(resource, seq)
        versioning.insert_version(
            self._connection, resource=stored, seq=seq, deleted=deleted
        )
        return WriteResult(
            resource=stored,
            seq=seq,
            created=created,
            deleted=deleted,
            publish_row={
                "id": resource_id,
                "resourceType": resource_type,
                "resource": json.dumps(stored, ensure_ascii=False, separators=(",", ":")),
                "patient_ref": versioning.extract_patient_ref(stored),
                "_seq": seq,
                "_deleted": deleted,
                "_ingested_at": bulk_publish.utc_timestamp(),
            },
        )

    # -- reads -----------------------------------------------------------

    def read(self, resource_type: str, resource_id: str) -> dict:
        """Current version, or the FHIR error the state deserves."""
        validate_id(resource_id)
        latest = versioning.latest_row(self._connection, resource_type, resource_id)
        if latest is None:
            raise not_found(f"{resource_type} with id {resource_id!r} not found")
        if latest["deleted"]:
            raise ServeError(
                410,
                [
                    Issue(
                        code="deleted",
                        diagnostics=(
                            f"{resource_type} with id {resource_id!r} was deleted "
                            f"(last version W/\"{latest['seq']}\")"
                        ),
                    )
                ],
            )
        return latest["resource"]

    def current_seq(self, resource_type: str, resource_id: str) -> int:
        latest = versioning.latest_row(self._connection, resource_type, resource_id)
        if latest is None:
            raise not_found(f"{resource_type} with id {resource_id!r} not found")
        return int(latest["seq"])

    def history(self, resource_type: str, resource_id: str) -> list[dict]:
        validate_id(resource_id)
        rows = versioning.history_rows(self._connection, resource_type, resource_id)
        if not rows:
            raise not_found(f"{resource_type} with id {resource_id!r} not found")
        return rows

    def read_version(self, resource_type: str, resource_id: str, seq: int) -> dict:
        validate_id(resource_id)
        row = versioning.version_row(self._connection, resource_type, resource_id, seq)
        if row is None:
            raise not_found(
                f"{resource_type}/{resource_id} has no version W/\"{seq}\""
            )
        return row["resource"]

    # -- bundles ---------------------------------------------------------

    def apply_bundle(self, bundle: dict) -> list[WriteResult]:
        """Apply a ``transaction``/``batch`` bundle atomically.

        A ``transaction`` is all-or-nothing: the log writes run inside one
        DuckDB transaction and a failing entry rolls everything back, so no
        publish rows are handed to the flush loop. ``batch`` stops at the first
        failure too — partial application of a batch is defensible in FHIR, but
        mixing that with a single flush boundary is not worth the ambiguity.
        """
        bundle_type = bundle.get("type")
        if bundle_type not in ("transaction", "batch"):
            raise bad_request(
                f"Bundle.type must be 'transaction' or 'batch'; got {bundle_type!r}",
                expression=["type"],
                code="value",
            )
        entries = bundle.get("entry")
        if entries is None:
            raise bad_request("Bundle.entry is required", expression=["entry"], code="required")
        if not isinstance(entries, list):
            raise bad_request("Bundle.entry must be an array", expression=["entry"])

        results: list[WriteResult] = []
        self._connection.execute("BEGIN TRANSACTION")
        try:
            for index, entry in enumerate(entries):
                results.append(self._apply_entry(index, entry))
        except Exception:
            self._connection.execute("ROLLBACK")
            raise
        self._connection.execute("COMMIT")
        return results

    def _apply_entry(self, index: int, entry: Any) -> WriteResult:
        where = ["entry", f"entry[{index}]"]
        if not isinstance(entry, dict):
            raise bad_request("Bundle.entry entries must be objects", expression=where)
        request = entry.get("request")
        if not isinstance(request, dict):
            raise bad_request("Bundle.entry.request is required", expression=where, code="required")
        method = str(request.get("method", "")).upper()
        url = request.get("url")
        if not isinstance(url, str) or not url.strip("/"):
            raise bad_request("Bundle.entry.request.url is required", expression=where, code="required")

        segments = [segment for segment in url.strip("/").split("/") if segment]
        resource_type = segments[0]
        resource_id = segments[1] if len(segments) > 1 else None

        if method == "POST":
            if len(segments) != 1:
                raise bad_request(
                    f"POST entries address a type ('{resource_type}'), not '{url}'",
                    expression=where,
                )
            resource = entry.get("resource")
            if not isinstance(resource, dict):
                raise bad_request("POST entries require a resource", expression=where, code="required")
            return self.create(resource_type, resource)

        if method == "PUT":
            if len(segments) != 2 or resource_id is None:
                raise bad_request(
                    f"PUT entries address '{resource_type}/{{id}}', not '{url}'",
                    expression=where,
                )
            resource = entry.get("resource")
            if not isinstance(resource, dict):
                raise bad_request("PUT entries require a resource", expression=where, code="required")
            raw_if_match = request.get("ifMatch")
            if_match = None
            if raw_if_match is not None:
                if not isinstance(raw_if_match, str):
                    raise bad_request(
                        "Bundle entry request.ifMatch must be a string (an ETag "
                        f"value); got {type(raw_if_match).__name__}",
                        expression=[*where, "ifMatch"],
                        code="value",
                    )
                if_match = parse_if_match(raw_if_match)
            return self.update(
                resource_type, resource_id, resource, if_match=if_match
            )

        if method == "DELETE":
            if len(segments) != 2 or resource_id is None:
                raise bad_request(
                    f"DELETE entries address '{resource_type}/{{id}}', not '{url}'",
                    expression=where,
                )
            return self.delete(resource_type, resource_id)

        raise bad_request(
            f"Unsupported bundle method {method!r}; use POST, PUT or DELETE",
            expression=where,
            code="not-supported",
        )

    # -- import ----------------------------------------------------------

    def import_rows(self, rows: Iterable[dict]) -> int:
        """Append pre-existing resources (``--resources`` preload) to the log."""
        imported = 0
        for row in rows:
            resource = row.get("resource")
            if not isinstance(resource, dict):
                continue
            resource_type = resource.get("resourceType")
            resource_id = resource.get("id")
            if not resource_type or not resource_id:
                continue
            try:
                validate_id(str(resource_id))
            except ServeError:
                continue
            self._append(
                str(resource_type), str(resource_id), resource, created=True
            )
            imported += 1
        return imported


# -- helpers -----------------------------------------------------------------


def _require_type(resource: Any, resource_type: str) -> None:
    if not isinstance(resource, dict):
        raise bad_request("Request body must be a FHIR resource", code="structure")
    body_type = resource.get("resourceType")
    if body_type != resource_type:
        raise bad_request(
            f"Request body must be a {resource_type} resource; got resourceType "
            f"{body_type!r}",
            code="structure",
        )


def validate_id(resource_id: Any) -> str:
    if not isinstance(resource_id, str) or not ID_PATTERN.match(resource_id):
        raise bad_request(
            f"Resource id {resource_id!r} is not a valid FHIR id "
            f"([A-Za-z0-9-.]{{1,64}})",
            expression=["id"],
            code="value",
        )
    return resource_id


def _with_meta(resource: dict, seq: int) -> dict:
    stored = dict(resource)
    meta = dict(stored.get("meta") or {})
    meta["versionId"] = str(seq)
    meta["lastUpdated"] = bulk_publish.utc_timestamp()
    stored["meta"] = meta
    return stored


def version_from_etag_header(request: Request) -> int | None:
    return parse_if_match(request.headers.get("if-match"))


def require_json_content_type(request: Request) -> None:
    """415 unless the request body is FHIR JSON (writes only)."""
    raw = request.headers.get("content-type") or ""
    media_type = raw.split(";", 1)[0].strip().lower()
    if media_type not in JSON_CONTENT_TYPES:
        raise ServeError(
            415,
            [
                Issue(
                    code="not-supported",
                    diagnostics=(
                        f"Unsupported content type {raw!r}; this surface accepts "
                        f"{' or '.join(JSON_CONTENT_TYPES)}"
                    ),
                )
            ],
        )


def _decode(request: Request, body: Any) -> dict:
    payload = decode_json_body(body, label="request body")
    if payload is None:
        raise bad_request("A FHIR resource body is required", code="structure")
    if not isinstance(payload, dict):
        raise bad_request(
            f"Request body must be a FHIR resource; got {type(payload).__name__}",
            code="structure",
        )
    return payload


def reject_registry_owned(resource_type: str) -> None:
    """Refuse generic writes for the types the definition registry owns."""
    if resource_type in REGISTRY_OWNED_TYPES:
        raise unsupported(
            f"{resource_type} is managed by the definition registry; use "
            f"POST /{resource_type} and GET /{resource_type}/{{id}}",
            expression=["resourceType"],
        )


def _etag_of(resource: dict) -> str:
    version = int(resource.get("meta", {}).get("versionId", 0) or 0)
    return etag_for(version)


def _conditional_query(request: Request, resource_type: str, header: str | None) -> Any:
    """A search query from an ``If-None-Exist`` header or the query string."""
    pairs = search.parse_query_string(header) if header else request.query_params
    query = search.parse_search(resource_type, pairs)
    if not query.has_filter:
        raise bad_request(
            "A conditional request needs a search filter (for example "
            "identifier=urn:mrn|A1 or _id=abc)",
            expression=["_id"],
            code="required",
        )
    return query


def _writer(request: Request) -> ResourceWriter:
    return context_for(request).writer


def _pending(request: Request) -> int:
    flusher = context_for(request).flusher
    return flusher.pending() if flusher is not None else 0


def _resource_response(
    result: WriteResult,
    *,
    pending: int,
    location: str | None = None,
    status_code: int | None = None,
) -> Response:
    headers = {"ETag": etag_for(result.seq), PENDING_HEADER: str(pending)}
    if location:
        headers["Location"] = location
    return Response(
        content=json.dumps(result.resource, ensure_ascii=False),
        media_type=FHIR_JSON,
        status_code=status_code or (201 if result.created else 200),
        headers=headers,
    )


def _enqueue(request: Request, results: Iterable[WriteResult]) -> None:
    rows = [result.publish_row for result in results if result.publish_row]
    flusher = context_for(request).flusher
    if flusher is not None and rows:
        flusher.enqueue(rows)


# -- routes ------------------------------------------------------------------

router = APIRouter(tags=["resources"])


@router.post("/Bundle", summary="Apply a transaction or batch bundle")
def apply_bundle(request: Request, body: Any | None = Body(default=None)) -> Response:
    """Apply a Bundle's entries in order, one flush, per-entry response statuses."""
    require_json_content_type(request)
    bundle = _decode(request, body)
    if bundle.get("resourceType") != "Bundle":
        raise bad_request(
            f"Request body must be a Bundle; got resourceType {bundle.get('resourceType')!r}",
            code="structure",
        )
    context = context_for(request)
    results = context.run_locked(context.writer.apply_bundle, bundle)
    _enqueue(request, results)

    response = {
        "resourceType": "Bundle",
        "type": f"{bundle['type']}-response",
        "entry": [
            {
                "response": {
                    "status": result.status,
                    "location": f"{result.resource['resourceType']}/{result.resource['id']}",
                    "etag": etag_for(result.seq),
                }
            }
            for result in results
        ],
    }
    return Response(
        content=json.dumps(response, ensure_ascii=False),
        media_type=FHIR_JSON,
        headers={PENDING_HEADER: str(_pending(request))},
    )


@router.get("/$bulk-publish", summary="Bulk publish manifest")
def bulk_publish_manifest(request: Request) -> Response:
    """The manifest the browser demo consumes straight off the Hub."""
    context = context_for(request)
    flusher = context.flusher
    if flusher is None:
        raise unprocessable("This server has no publish store configured")
    manifest = flusher.manifest(str(request.base_url).rstrip("/"))
    return Response(
        content=json.dumps(manifest, ensure_ascii=False),
        media_type="application/json",
    )


@router.post("/admin/flush", summary="Force a publish flush")
def force_flush(request: Request) -> Response:
    """Commit buffered writes now; returns the new revision and row count."""
    context = context_for(request)
    flusher = context.flusher
    if flusher is None:
        raise unprocessable("This server has no publish store configured")
    result = flusher.flush()
    payload = {
        "revision": result.revision,
        "committed": result.committed,
        "pending": flusher.pending(),
        "last_error": flusher.last_error,
    }
    return Response(content=json.dumps(payload), media_type="application/json")


@router.post("/{resource_type}", status_code=201, summary="Create a resource")
def create_resource(
    resource_type: str, request: Request, body: Any | None = Body(default=None)
) -> Response:
    """Create a resource; the server assigns an id when the body omits one."""
    require_json_content_type(request)
    reject_registry_owned(resource_type)
    resource = _decode(request, body)
    context = context_for(request)

    # FHIR conditional create: If-None-Exist names a search; zero matches means
    # create, one means "already there" (200, no new version), many is a 412.
    if_none_exist = request.headers.get("if-none-exist")
    if if_none_exist:
        query = _conditional_query(request, resource_type, if_none_exist)

        # The match decision and the create run in ONE locked section: with the
        # check and the act in separate acquisitions, two concurrent identical
        # conditional creates could both see "zero matches" and both create.
        def decide_and_act() -> tuple[str, Any]:
            matches = search.match_count(context.connection, query)
            if matches > 1:
                return "conflict", matches
            if matches == 1:
                return "existing", search.first_match(context.connection, query)
            return "created", context.writer.create(resource_type, resource)

        kind, payload = context.run_locked(decide_and_act)
        if kind == "conflict":
            raise precondition_failed(
                f"If-None-Exist {if_none_exist!r} matches {payload} resources; "
                "a conditional create needs zero or one"
            )
        if kind == "existing":
            existing = payload
            return Response(
                content=json.dumps(existing, ensure_ascii=False),
                media_type=FHIR_JSON,
                status_code=200,
                headers={
                    "ETag": _etag_of(existing),
                    PENDING_HEADER: str(_pending(request)),
                    "Location": f"{resource_type}/{existing['id']}",
                },
            )
        result = payload
        _enqueue(request, [result])
        return _resource_response(
            result,
            pending=_pending(request),
            location=f"{resource_type}/{result.resource['id']}",
            status_code=201,
        )

    result = context.run_locked(context.writer.create, resource_type, resource)
    _enqueue(request, [result])
    return _resource_response(
        result,
        pending=_pending(request),
        location=f"{resource_type}/{result.resource['id']}",
        status_code=201,
    )


@router.get("/{resource_type}", summary="Search resources by type")
def search_resources(resource_type: str, request: Request) -> Response:
    """Search the latest-wins view. Unsupported parameters are a 400."""
    context = context_for(request)
    query = search.parse_search(resource_type, request.query_params)
    count, offset = search_controls(request.query_params)
    capped = context.config.capped_limit(count)
    resources, total = context.run_locked(
        search.search, context.connection, query, count=capped, offset=offset
    )
    links = paging_links(
        base_url=str(request.url).split("?")[0],
        params=request.query_params,
        page=resources,
        total=total,
        count=capped,
        offset=offset,
    )
    return Response(
        content=json.dumps(searchset_bundle(resources, total, links=links), ensure_ascii=False),
        media_type=FHIR_JSON,
    )


@router.put("/{resource_type}", summary="Conditional update")
def conditional_update(
    resource_type: str, request: Request, body: Any | None = Body(default=None)
) -> Response:
    """``PUT /{type}?<filter>``: zero matches create, one updates, many are 412."""
    require_json_content_type(request)
    reject_registry_owned(resource_type)
    query = _conditional_query(request, resource_type, None)
    resource = _decode(request, body)
    context = context_for(request)
    if_match = version_from_etag_header(request)

    # One locked section for decide + act (see the conditional-create note).
    def decide_and_act() -> tuple[str, Any]:
        matches = search.match_count(context.connection, query)
        if matches > 1:
            return "conflict", matches
        if matches == 0:
            return "created", context.writer.create(resource_type, resource)
        existing = search.first_match(context.connection, query)
        result = context.writer.update(
            resource_type,
            existing["id"],
            {**resource, "id": existing["id"]},
            if_match=if_match,
        )
        return "updated", result

    kind, payload = context.run_locked(decide_and_act)
    if kind == "conflict":
        raise precondition_failed(
            f"The conditional update filter matches {payload} resources; it must "
            "match zero or one"
        )
    result = payload
    status_code = 201 if kind == "created" else 200

    _enqueue(request, [result])
    return _resource_response(
        result,
        pending=_pending(request),
        location=f"{resource_type}/{result.resource['id']}",
        status_code=status_code,
    )


@router.get("/{resource_type}/{resource_id}", summary="Read a resource version")
def read_resource(resource_type: str, resource_id: str, request: Request) -> Response:
    context = context_for(request)
    resource = context.run_locked(context.writer.read, resource_type, resource_id)
    seq = int(resource.get("meta", {}).get("versionId", 0))
    return Response(
        content=json.dumps(resource, ensure_ascii=False),
        media_type=FHIR_JSON,
        headers={"ETag": etag_for(seq)},
    )


@router.put("/{resource_type}/{resource_id}", summary="Update a resource")
def update_resource(
    resource_type: str,
    resource_id: str,
    request: Request,
    body: Any | None = Body(default=None),
) -> Response:
    """Create-or-update, honouring ``If-Match`` (a mismatch is 412)."""
    require_json_content_type(request)
    reject_registry_owned(resource_type)
    resource = _decode(request, body)
    if_match = version_from_etag_header(request)
    context = context_for(request)
    result = context.run_locked(
        context.writer.update, resource_type, resource_id, resource, if_match=if_match
    )
    _enqueue(request, [result])
    return _resource_response(
        result,
        pending=_pending(request),
        location=f"{resource_type}/{resource_id}",
        status_code=200 if result.created is False else 201,
    )


@router.delete("/{resource_type}/{resource_id}", status_code=204, summary="Delete a resource")
def delete_resource(resource_type: str, resource_id: str, request: Request) -> Response:
    """Tombstone: gone from reads, still visible in ``_history``.

    No Content-Type is required: DELETE carries no body, so a plain
    ``curl -X DELETE`` is valid.
    """
    reject_registry_owned(resource_type)
    context = context_for(request)
    result = context.run_locked(context.writer.delete, resource_type, resource_id)
    _enqueue(request, [result])
    return Response(
        status_code=204,
        headers={"ETag": etag_for(result.seq), PENDING_HEADER: str(_pending(request))},
    )


@router.get("/{resource_type}/{resource_id}/_history", summary="Resource version history")
def resource_history(resource_type: str, resource_id: str, request: Request) -> Response:
    """A ``history`` Bundle over every version, newest first."""
    context = context_for(request)
    rows = context.run_locked(context.writer.history, resource_type, resource_id)
    entries = [
        {
            "resource": row["resource"],
            "request": {
                "method": "DELETE" if row["deleted"] else "PUT",
                "url": f"{resource_type}/{resource_id}",
            },
            "response": {
                "status": "204 No Content" if row["deleted"] else "200 OK",
                "etag": etag_for(row["seq"]),
            },
        }
        for row in rows
    ]
    bundle = {
        "resourceType": "Bundle",
        "type": "history",
        "total": len(entries),
        "entry": entries,
    }
    return Response(content=json.dumps(bundle, ensure_ascii=False), media_type=FHIR_JSON)


@router.get("/{resource_type}/{resource_id}/_history/{version_id}", summary="Read one version")
def read_version(
    resource_type: str, resource_id: str, version_id: str, request: Request
) -> Response:
    """vread: one specific version of a resource."""
    if not version_id.isdigit():
        raise bad_request(
            f"Version id {version_id!r} must be an integer", expression=["version_id"]
        )
    context = context_for(request)
    resource = context.run_locked(
        context.writer.read_version, resource_type, resource_id, int(version_id)
    )
    return Response(
        content=json.dumps(resource, ensure_ascii=False),
        media_type=FHIR_JSON,
        headers={"ETag": etag_for(int(version_id))},
    )


__all__ = [
    "ResourceWriter",
    "WriteResult",
    "router",
    "etag_for",
    "parse_if_match",
    "precondition_failed",
    "require_json_content_type",
    "validate_id",
    "FHIR_JSON",
    "PENDING_HEADER",
    "REGISTRY_OWNED_TYPES",
    "reject_registry_owned",
]
