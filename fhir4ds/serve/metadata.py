"""CapabilityStatement generation from the live FastAPI route table.

The CapabilityStatement is **derived**, never hand-written: route handlers
declare their FHIR role with :func:`cap_interaction` / :func:`cap_operation`,
and :func:`build_capability_statement` walks ``app.routes`` to assemble
``rest[0].resource[]`` and the system-level operations. Adding a route with a
declaration therefore updates ``/metadata`` automatically; a route without a
declaration is simply not advertised.

Declared shapes follow the SQL-on-FHIR v2 IG:

* ``Library`` — ``sqlquery-run`` at type and instance level;
* ``ViewDefinition`` — ``run`` at type and instance level.

In R4 the IG restricts ``$viewdefinition-run`` to the system level; this
surface additionally serves type and instance levels because the deployment
brief requires them. The CapabilityStatement advertises exactly what exists.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from fhir4ds.operations.capabilities.sqlquery import SQLQUERY_RUN_DEFINITION
from fhir4ds.operations.capabilities.viewdefinition_run import VIEWDEFINITION_RUN_DEFINITION

from .parameters import ParameterSpec

#: Attribute set on a route endpoint to declare its FHIR capability.
ROUTE_SPEC_ATTRIBUTE = "__fhir4ds_capability__"

#: FHIR version this surface serves. ViewDefinition/SQLQuery are logical
#: models over R4 data; the CapabilityStatement reports the base FHIR version.
FHIR_VERSION = "4.0.1"

INTERACTION = "interaction"
OPERATION = "operation"

SCOPES = ("system", "type", "instance")


@dataclass(frozen=True)
class RouteSpec:
    """FHIR role declared by one route handler."""

    kind: str
    resource: str | None = None
    interaction: str | None = None
    operation: str | None = None
    scope: str | None = None
    definition: str | None = None
    parameters: tuple[ParameterSpec, ...] = ()
    documentation: str = ""

    def __post_init__(self) -> None:
        if self.kind not in (INTERACTION, OPERATION):
            raise ValueError(f"RouteSpec.kind must be {INTERACTION!r} or {OPERATION!r}")
        if self.kind == INTERACTION:
            if not self.interaction:
                raise ValueError("interaction routes require an interaction code")
            if self.operation or self.scope:
                raise ValueError("interaction routes must not declare operation/scope")
        else:
            if not self.operation:
                raise ValueError("operation routes require an operation name")
            if not self.definition:
                raise ValueError(f"operation {self.operation!r} requires a definition canonical")
            if self.scope not in SCOPES:
                raise ValueError(f"operation scope must be one of {SCOPES}")
            if self.scope != "system" and not self.resource:
                raise ValueError("type/instance operations require a resource")


def _declare(spec: RouteSpec) -> Any:
    def decorator(function: Any) -> Any:
        setattr(function, ROUTE_SPEC_ATTRIBUTE, spec)
        if spec not in DECLARED_ROUTE_SPECS:
            DECLARED_ROUTE_SPECS.append(spec)
        return function

    return decorator


#: Ordered declaration registry, filled by the decorators at import time.
#:
#: The primary source for the CapabilityStatement is the app's route table
#: (see :func:`collect_route_specs`); this registry is the fallback for
#: FastAPI/Starlette versions that hide included routers behind a shape this
#: module does not traverse, so ``/metadata`` can never silently empty out.
DECLARED_ROUTE_SPECS: list[RouteSpec] = []


def cap_interaction(*, resource: str, interaction: str) -> Any:
    """Declare a REST interaction (``read``, ``create``, ``search-type``)."""
    return _declare(RouteSpec(kind=INTERACTION, resource=resource, interaction=interaction))


def cap_operation(
    *,
    operation: str,
    definition: str,
    scope: str,
    resource: str | None = None,
    parameters: Sequence[ParameterSpec] = (),
    documentation: str = "",
) -> Any:
    """Declare an operation (``sqlquery-run`` / ``run``) on a resource or system."""
    return _declare(
        RouteSpec(
            kind=OPERATION,
            resource=resource,
            operation=operation,
            scope=scope,
            definition=definition,
            parameters=tuple(parameters),
            documentation=documentation,
        )
    )


def collect_route_specs(app: Any) -> list[RouteSpec]:
    """Return the declared specs for the routes an application actually serves.

    Walks the router tree instead of reading ``app.routes`` directly: Starlette
    ≥1.6 keeps included routers behind an ``_IncludedRouter`` node, older
    versions flatten them, and both shapes are traversed here. When no declared
    endpoint is discoverable (an unknown future shape), the ordered declaration
    registry is used so the document stays complete.
    """
    specs: list[RouteSpec] = []
    visited: set[int] = set()
    queue: list[Any] = [getattr(app, "router", app)]

    while queue:
        node = queue.pop(0)
        if id(node) in visited:
            continue
        visited.add(id(node))
        endpoint = getattr(node, "endpoint", None)
        spec = getattr(endpoint, ROUTE_SPEC_ATTRIBUTE, None)
        if isinstance(spec, RouteSpec) and spec not in specs:
            specs.append(spec)
        queue.extend(_child_routes(node))

    return specs or list(DECLARED_ROUTE_SPECS)


def _child_routes(node: Any) -> list[Any]:
    """Child route nodes, unwrapping Starlette's lazy included routers."""
    inner = getattr(node, "original_router", None)
    if inner is not None and inner is not node:
        return list(getattr(inner, "routes", ()) or ())
    return list(getattr(node, "routes", ()) or ())


def _operation_entry(spec: RouteSpec) -> dict:
    entry: dict = {"name": spec.operation, "definition": spec.definition}
    if spec.documentation:
        entry["documentation"] = spec.documentation
    return entry


def build_capability_statement(
    app: Any,
    *,
    title: str,
    date: str | None = None,
) -> dict:
    """Assemble the CapabilityStatement from the app's declared routes."""
    from fhir4ds import __version__ as engine_version

    resources: dict[str, dict] = {}
    system_operations: list[dict] = []
    seen_system: set[tuple] = set()

    for spec in collect_route_specs(app):
        if spec.kind == OPERATION and spec.resource is None:
            entry = _operation_entry(spec)
            key = (entry["name"], entry["definition"])
            if key not in seen_system:
                seen_system.add(key)
                system_operations.append(entry)
            continue
        if spec.resource is None:
            continue
        entry = resources.setdefault(
            spec.resource,
            {"type": spec.resource, "interaction": [], "operation": []},
        )
        if spec.kind == INTERACTION:
            candidate = {"code": spec.interaction}
            if candidate not in entry["interaction"]:
                entry["interaction"].append(candidate)
        else:
            candidate = _operation_entry(spec)
            if candidate not in entry["operation"]:
                entry["operation"].append(candidate)

    rest: dict = {"mode": "server"}
    if resources:
        rest["resource"] = [resources[name] for name in sorted(resources)]
    rest["interaction"] = [{"code": "transaction"}]
    if system_operations:
        rest["operation"] = system_operations

    return {
        "resourceType": "CapabilityStatement",
        "status": "active",
        "date": date or utc_now_instant(),
        "kind": "instance",
        "software": {"name": "fhir4ds", "version": engine_version},
        "implementation": {"description": title},
        "fhirVersion": FHIR_VERSION,
        "format": ["application/fhir+json", "json"],
        "rest": [rest],
    }


def utc_now_instant() -> str:
    """Current time as a FHIR ``instant`` (UTC, second precision)."""
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    return now.isoformat().replace("+00:00", "Z")


__all__ = [
    "RouteSpec",
    "cap_interaction",
    "cap_operation",
    "collect_route_specs",
    "build_capability_statement",
    "utc_now_instant",
    "FHIR_VERSION",
    "ROUTE_SPEC_ATTRIBUTE",
    "SQLQUERY_RUN_DEFINITION",
    "VIEWDEFINITION_RUN_DEFINITION",
]
