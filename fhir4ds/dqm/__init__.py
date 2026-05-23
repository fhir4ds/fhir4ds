"""dqm — Digital Quality Measure Orchestrator & Audit Engine."""

from .audit import AuditEngine
from .errors import DQMError, MeasureParseError
from .evaluator import (
    CompiledGroup,
    CompiledMeasure,
    CompiledMeasureMetrics,
    MeasureEvaluator,
)
from .models import MeasureResult
from .narrative import NarrativeGenerator
from .parser import MeasureParser
from .reactive import ReactiveEvaluator
from .types import (
    AuditMode,
    AuditOrStrategy,
    AuditPersona,
    GroupMap,
    PopulationEntry,
    PopulationMap,
    SupportingEvidenceDef,
)

__version__ = "0.0.6"

__all__ = [
    "__version__",
    "AuditEngine",
    "AuditMode",
    "AuditOrStrategy",
    "AuditPersona",
    "DQMError",
    "CompiledGroup",
    "CompiledMeasure",
    "CompiledMeasureMetrics",
    "GroupMap",
    "MeasureEvaluator",
    "MeasureParseError",
    "MeasureParser",
    "MeasureResult",
    "NarrativeGenerator",
    "PopulationEntry",
    "PopulationMap",
    "ReactiveEvaluator",
    "SupportingEvidenceDef",
]
