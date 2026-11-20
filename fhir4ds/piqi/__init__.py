"""PIQI — Patient Information Quality Improvement framework on
ViewDefinition + SQLQuery (card AMUX-148).

SAMs, rubrics and scorecards are authored as plain FHIR resources
(ViewDefinitions + SQLQuery Libraries) and composed through the
EXISTING ``fhir4ds.sqlquery`` runner — no runner or viewdef core
changes. See ``fhir4ds-private/docs/architecture/plans/
FEATURE_PIQI_FRAMEWORK.md`` for the approved design.
"""

from .authoring import (
    CANONICAL_BASE,
    build_parameterized_sam,
    build_rubric,
    build_sam_catalog,
    build_view,
)
from .registry import all_views, get_rubric, get_sam, get_view, piqi_resolver
from .scorecard import (
    PIQIIssue,
    PIQIScorecard,
    evaluate_rubric,
    load_piqi_views,
    run_parameterized_sam,
    run_sam,
)
from .terminology import COULD_NOT_ASSESS, run_terminology_sam
from .taxonomy import PIQIDimension, dimension_for_sam, resolve_dimension

__version__ = "0.0.25"

__all__ = [
    "__version__",
    # authoring
    "CANONICAL_BASE",
    "build_rubric",
    "build_parameterized_sam",
    "build_sam_catalog",
    "build_view",
    # registry
    "all_views",
    "get_rubric",
    "get_sam",
    "get_view",
    "piqi_resolver",
    # scorecard facade
    "PIQIIssue",
    "PIQIScorecard",
    "evaluate_rubric",
    "load_piqi_views",
    "run_sam",
    "run_parameterized_sam",
    # terminology SAMs
    "COULD_NOT_ASSESS",
    "run_terminology_sam",
    # taxonomy
    "PIQIDimension",
    "dimension_for_sam",
    "resolve_dimension",
]
