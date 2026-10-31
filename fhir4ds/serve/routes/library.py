"""Library resource routes: CRUD plus ``$sqlquery-run``.

SQL-on-FHIR v2 defines the operation at three levels:

========  ==============================================  ===================
system    ``POST [base]/$sqlquery-run``                   queryReference|queryResource
type      ``POST [base]/Library/$sqlquery-run``           queryReference|queryResource
instance  ``POST [base]/Library/[id]/$sqlquery-run``       the Library instance
========  ==============================================  ===================

At system and type level exactly one of ``queryReference``/``queryResource``
must be supplied; at instance level neither is allowed (the path identifies the
Library), and the corresponding 400s follow the IG.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request
from starlette.responses import Response

from ..config import ServeContext, context_for
from ..errors import bad_request
from ..execution import (
    QUERY_REFERENCE_PARAMETER,
    QUERY_RESOURCE_PARAMETER,
    SQLQUERY_RUN_PARAMETERS,
    sqlquery_operation,
)
from ..metadata import SQLQUERY_RUN_DEFINITION, cap_interaction, cap_operation
from ..parameters import ParametersBag
from ..resources import (
    parse_resource_body,
    require_resource,
    resolve_reference,
    resource_response,
    search_controls,
    searchset_bundle,
)

router = APIRouter(tags=["Library"])

RESOURCE = "Library"

_OPERATION_DOC = (
    "Execute a SQLQuery Library against the ViewDefinition tables materialized "
    "on this server."
)


def _resolve_type_level_library(context: ServeContext, bag: ParametersBag) -> dict:
    """Resolve ``queryReference``/``queryResource`` for a system/type invocation."""
    chosen = bag.require_one_of(
        [QUERY_REFERENCE_PARAMETER.name, QUERY_RESOURCE_PARAMETER.name]
    )
    if chosen == QUERY_REFERENCE_PARAMETER.name:
        reference = bag.value(QUERY_REFERENCE_PARAMETER)
        return context.run_locked(
            resolve_reference,
            context.store,
            reference,
            resource_type=RESOURCE,
            parameter_name=chosen,
        )

    library = bag.value(QUERY_RESOURCE_PARAMETER)
    if not isinstance(library, dict):
        raise bad_request(
            "queryResource must be a Library resource",
            expression=["queryResource"],
            code="structure",
        )
    if library.get("resourceType") != RESOURCE:
        raise bad_request(
            "queryResource must be a Library resource; got resourceType "
            f"{library.get('resourceType')!r}",
            expression=["queryResource"],
            code="structure",
        )
    return library


# -- CRUD -------------------------------------------------------------------


@router.post("/Library", status_code=201, summary="Create or replace a Library")
@cap_interaction(resource=RESOURCE, interaction="create")
def create_library(request: Request, body: Any | None = Body(default=None)) -> Response:
    """Store a Library (create, or replace when the id already exists)."""
    context = context_for(request)
    resource = parse_resource_body(body, expected_type=RESOURCE)
    stored = context.run_locked(context.store.put, resource)
    return resource_response(stored, status_code=201)


@router.get("/Library", summary="Search Libraries")
@cap_interaction(resource=RESOURCE, interaction="search-type")
def search_libraries(request: Request) -> Response:
    """Return a ``searchset`` Bundle of stored Libraries."""
    context = context_for(request)
    count, offset = search_controls(request.query_params)
    resources, total = context.run_locked(
        context.store.search_page, RESOURCE, count=count, offset=offset
    )
    return resource_response(searchset_bundle(resources, total))


@router.get("/Library/{library_id}", summary="Read a Library")
@cap_interaction(resource=RESOURCE, interaction="read")
def read_library(library_id: str, request: Request) -> Response:
    """Read one stored Library by id."""
    context = context_for(request)
    resource = context.run_locked(require_resource, context.store, RESOURCE, library_id)
    return resource_response(resource)


# -- $sqlquery-run ----------------------------------------------------------


@router.post("/$sqlquery-run", summary="Run a SQLQuery (system level)")
@cap_operation(
    operation="sqlquery-run",
    definition=SQLQUERY_RUN_DEFINITION,
    scope="system",
    parameters=SQLQUERY_RUN_PARAMETERS,
    documentation=_OPERATION_DOC,
)
def system_sqlquery_run(
    request: Request, body: Any | None = Body(default=None)
) -> Response:
    """Execute a SQLQuery Library supplied by reference or inline."""
    context = context_for(request)
    bag = ParametersBag.from_body(body)
    bag.validate(SQLQUERY_RUN_PARAMETERS)
    library = _resolve_type_level_library(context, bag)
    return sqlquery_operation(
        context, bag, library=library, accept=request.headers.get("accept")
    )


@router.post("/Library/$sqlquery-run", summary="Run a SQLQuery (type level)")
@cap_operation(
    operation="sqlquery-run",
    definition=SQLQUERY_RUN_DEFINITION,
    scope="type",
    resource=RESOURCE,
    parameters=SQLQUERY_RUN_PARAMETERS,
    documentation=_OPERATION_DOC,
)
def type_level_sqlquery_run(
    request: Request, body: Any | None = Body(default=None)
) -> Response:
    """Execute a SQLQuery Library supplied by reference or inline."""
    context = context_for(request)
    bag = ParametersBag.from_body(body)
    bag.validate(SQLQUERY_RUN_PARAMETERS)
    library = _resolve_type_level_library(context, bag)
    return sqlquery_operation(
        context, bag, library=library, accept=request.headers.get("accept")
    )


@router.post("/Library/{library_id}/$sqlquery-run", summary="Run a stored SQLQuery")
@cap_operation(
    operation="sqlquery-run",
    definition=SQLQUERY_RUN_DEFINITION,
    scope="instance",
    resource=RESOURCE,
    parameters=SQLQUERY_RUN_PARAMETERS,
    documentation=_OPERATION_DOC,
)
def instance_sqlquery_run(
    library_id: str, request: Request, body: Any | None = Body(default=None)
) -> Response:
    """Execute the stored Library identified by the request path."""
    context = context_for(request)
    bag = ParametersBag.from_body(body)
    library = context.run_locked(require_resource, context.store, RESOURCE, library_id)
    bag.forbid([QUERY_REFERENCE_PARAMETER.name, QUERY_RESOURCE_PARAMETER.name])
    return sqlquery_operation(
        context, bag, library=library, accept=request.headers.get("accept")
    )


__all__ = ["router", "RESOURCE"]
