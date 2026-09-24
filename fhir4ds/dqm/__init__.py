"""dqm — Digital Quality Measure Orchestrator & Audit Engine.

Import-time surface is deliberately pandas-free so that
``fhir4ds.dqm.parser`` / ``fhir4ds.dqm.types`` can be imported in
browser (Pyodide) workers: the pandas-bound evaluator/reactive re-exports
are resolved lazily via PEP 562 ``__getattr__`` (SO-1,
FEATURE_CLEANROOM_MEASURE_REPORTS.md).
"""

from .artifacts import (
    ArtifactResolver,
    FileArtifactResolver,
    HapiArtifactResolver,
    LibraryArtifact,
    MeasureArtifact,
    ValueSetRef,
    create_artifact_resolver,
)
from .audit import AuditEngine
from .errors import DQMError, MeasureParseError
from .models import MeasureResult
from .narrative import NarrativeGenerator
from .parser import MeasureParser
from .types import (
    AuditMode,
    AuditOrStrategy,
    AuditPersona,
    GroupMap,
    PopulationEntry,
    PopulationMap,
    SupportingEvidenceDef,
)

__version__ = "0.0.17"

# Lazy re-exports (PEP 562): these modules import pandas/numpy at module
# top and must not execute when the parser/types surface is imported in
# environments without them (Pyodide workers).
_LAZY_EXPORTS = {
    "CompiledGroup": (".evaluator", "CompiledGroup"),
    "CompiledMeasure": (".evaluator", "CompiledMeasure"),
    "CompiledMeasureMetrics": (".evaluator", "CompiledMeasureMetrics"),
    "MeasureEvaluator": (".evaluator", "MeasureEvaluator"),
    "ReactiveEvaluator": (".reactive", "ReactiveEvaluator"),
}


def __getattr__(name: str):
    entry = _LAZY_EXPORTS.get(name)
    if entry is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = entry
    from importlib import import_module

    module = import_module(module_name, __package__)
    return getattr(module, attr)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))


__all__ = [
    "__version__",
    "AuditEngine",
    "AuditMode",
    "AuditOrStrategy",
    "AuditPersona",
    "ArtifactResolver",
    "DQMError",
    "CompiledGroup",
    "CompiledMeasure",
    "CompiledMeasureMetrics",
    "FileArtifactResolver",
    "GroupMap",
    "HapiArtifactResolver",
    "LibraryArtifact",
    "MeasureEvaluator",
    "MeasureArtifact",
    "MeasureParseError",
    "MeasureParser",
    "MeasureResult",
    "NarrativeGenerator",
    "PopulationEntry",
    "PopulationMap",
    "ReactiveEvaluator",
    "SupportingEvidenceDef",
    "ValueSetRef",
    "create_artifact_resolver",
]
