"""ViewDefinition resource routes: CRUD plus ``$run``.

``$run`` is the synchronous ViewDefinition evaluator (SQL-on-FHIR v2
OperationDefinition ``$viewdefinition-run``). This surface serves it at type
and instance level:

* ``POST [base]/ViewDefinition/$run`` — ``viewReference`` or ``viewResource``;
* ``POST [base]/ViewDefinition/[id]/$run`` — the ViewDefinition at the path.

The IG's R4 compatibility mode restricts the operation to the system level;
type/instance are served here because the deployment requires them, and
``/metadata`` advertises exactly what is available.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request
from starlette.responses import Response

from ..config import ServeContext, context_for
from ..errors import bad_request
from ..execution import (
    VIEW_REFERENCE_PARAMETER,
    VIEW_RESOURCE_PARAMETER,
    VIEWDEFINITION_RUN_PARAMETERS,
    viewdefinition_operation,
)
from ..metadata import VIEWDEFINITION_RUN_DEFINITION, cap_interaction, cap_operation
from ..parameters import ParametersBag
from ..resources import (
    parse_resource_body,
    require_resource,
    resolve_reference,
    resource_response,
    search_controls,
    searchset_bundle,
)

router = APIRouter(tags=["ViewDefinition"])

RESOURCE = "ViewDefinition"

_OPERATION_DOC = (
    "Transform FHIR resources into a tabular row set using one ViewDefinition."
)


def _resolve_type_level_view(context: ServeContext, bag: ParametersBag) -> dict:
    """Resolve ``viewReference``/``viewResource`` for a type-level invocation."""
    chosen = bag.require_one_of(
        [VIEW_REFERENCE_PARAMETER.name, VIEW_RESOURCE_PARAMETER.name]
    )
    if chosen == VIEW_REFERENCE_PARAMETER.name:
        reference = bag.value(VIEW_REFERENCE_PARAMETER)
        return context.run_locked(
            resolve_reference,
            context.store,
            reference,
            resource_type=RESOURCE,
            parameter_name=chosen,
        )

    view = bag.value(VIEW_RESOURCE_PARAMETER)
    if not isinstance(view, dict):
        raise bad_request(
            "viewResource must be a ViewDefinition resource",
            expression=["viewResource"],
            code="structure",
        )
    resource_type = view.get("resourceType")
    # The IG publishes ViewDefinition instances with resourceType
    # "ViewDefinition"; the engine also accepts the logical model's canonical
    # URL. Both are accepted here.
    if resource_type != RESOURCE:
        raise bad_request(
            "viewResource must be a ViewDefinition resource; got resourceType "
            f"{resource_type!r}",
            expression=["viewResource"],
            code="structure",
        )
    return view


# -- CRUD -------------------------------------------------------------------


@router.post(
    "/ViewDefinition", status_code=201, summary="Create or replace a ViewDefinition"
)
@cap_interaction(resource=RESOURCE, interaction="create")
def create_view_definition(
    request: Request, body: Any | None = Body(default=None)
) -> Response:
    """Store a ViewDefinition (create, or replace when the id already exists)."""
    context = context_for(request)
    resource = parse_resource_body(body, expected_type=RESOURCE)
    stored = context.run_locked(context.store.put, resource)
    return resource_response(stored, status_code=201)


@router.get("/ViewDefinition", summary="Search ViewDefinitions")
@cap_interaction(resource=RESOURCE, interaction="search-type")
def search_view_definitions(request: Request) -> Response:
    """Return a ``searchset`` Bundle of stored ViewDefinitions."""
    context = context_for(request)
    count, offset = search_controls(request.query_params)
    resources, total = context.run_locked(
        context.store.search_page, RESOURCE, count=count, offset=offset
    )
    return resource_response(searchset_bundle(resources, total))


@router.get("/ViewDefinition/{view_id}", summary="Read a ViewDefinition")
@cap_interaction(resource=RESOURCE, interaction="read")
def read_view_definition(view_id: str, request: Request) -> Response:
    """Read one stored ViewDefinition by id."""
    context = context_for(request)
    resource = context.run_locked(require_resource, context.store, RESOURCE, view_id)
    return resource_response(resource)


# -- $run -------------------------------------------------------------------


@router.post("/ViewDefinition/$run", summary="Run an inline or referenced view")
@cap_operation(
    operation="run",
    definition=VIEWDEFINITION_RUN_DEFINITION,
    scope="type",
    resource=RESOURCE,
    parameters=VIEWDEFINITION_RUN_PARAMETERS,
    documentation=_OPERATION_DOC,
)
def type_level_view_run(
    request: Request, body: Any | None = Body(default=None)
) -> Response:
    """Evaluate a ViewDefinition supplied by reference or inline."""
    context = context_for(request)
    bag = ParametersBag.from_body(body)
    bag.validate(VIEWDEFINITION_RUN_PARAMETERS)
    view = _resolve_type_level_view(context, bag)
    return viewdefinition_operation(
        context, bag, view_definition=view, accept=request.headers.get("accept")
    )


@router.post("/ViewDefinition/{view_id}/$run", summary="Run a stored ViewDefinition")
@cap_operation(
    operation="run",
    definition=VIEWDEFINITION_RUN_DEFINITION,
    scope="instance",
    resource=RESOURCE,
    parameters=VIEWDEFINITION_RUN_PARAMETERS,
    documentation=_OPERATION_DOC,
)
def instance_view_run(
    view_id: str, request: Request, body: Any | None = Body(default=None)
) -> Response:
    """Evaluate the ViewDefinition identified by the request path."""
    context = context_for(request)
    bag = ParametersBag.from_body(body)
    view = context.run_locked(require_resource, context.store, RESOURCE, view_id)
    bag.forbid([VIEW_REFERENCE_PARAMETER.name, VIEW_RESOURCE_PARAMETER.name])
    return viewdefinition_operation(
        context, bag, view_definition=view, accept=request.headers.get("accept")
    )


__all__ = ["router", "RESOURCE"]
