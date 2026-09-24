"""fhir4ds.operations — capabilities defined once, adapters are thin.

Public surface (v1, schema: 1): parse_cql, translate_cql,
evaluate_library, run_tests, fhirpath_eval, load_dataset,
explain_patient. See docs/architecture/plans/FEATURE_OPERATIONS_LAYER.md.
"""

from .capabilities.dataset_ops import DatasetResult, load_dataset
from .capabilities.evaluate import (
    EvaluateResult,
    EvidenceResult,
    VerifyEnvelope,
    evaluate_library,
    explain_patient,
    run_tests,
)
from .capabilities.fhirpath import FhirpathResult, fhirpath_eval
from .capabilities.parse import ParseResult, parse_cql
from .capabilities.schema import ResourceSchemaResult, resource_schema
from .capabilities.schema_tree import (
    SchemaTreeResult,
    resource_schema_tree,
)
from .capabilities.translate import TranslateResult, translate_cql
from .capabilities.compare import (
    CompareEvidenceResult,
    compare_evidence,
    evidence_payload_from_dict,
)
from .capabilities.validate import ValidateResourceResult, validate_resource
from .capabilities.measure import (
    DEFAULT_MEASURE_REPORT_VIEW,
    POPULATION_ORDER,
    FlattenViewResult,
    MeasureReportResult,
    MeasureResult,
    MeasureRowsResult,
    flatten_view,
    measure_from_definitions,
    measure_population_map,
    measure_report_from_rows,
    output_columns_from_measure,
    rows_from_measure_reports,
)
from .envelopes import (
    DatasetSpec,
    DiagnosticCode,
    Diagnostics,
    ErrorLocation,
    LibraryText,
    TestCase,
    TestsInput,
    dataset_spec_from_dict,
    tests_input_from_dict,
)
from .errors import OperationError, diagnostic_from_exception
from .library_sources import LibraryResolver, bundled_library_names

__all__ = [
    "CompareEvidenceResult",
    "DatasetResult",
    "DatasetSpec",
    "DiagnosticCode",
    "Diagnostics",
    "ErrorLocation",
    "EvaluateResult",
    "EvidenceResult",
    "FlattenViewResult",
    "FhirpathResult",
    "LibraryResolver",
    "LibraryText",
    "MeasureReportResult",
    "MeasureResult",
    "MeasureRowsResult",
    "OperationError",
    "POPULATION_ORDER",
    "ParseResult",
    "ResourceSchemaResult",
    "TestCase",
    "TestsInput",
    "TranslateResult",
    "ValidateResourceResult",
    "VerifyEnvelope",
    "bundled_library_names",
    "compare_evidence",
    "dataset_spec_from_dict",
    "diagnostic_from_exception",
    "evaluate_library",
    "evidence_payload_from_dict",
    "explain_patient",
    "fhirpath_eval",
    "flatten_view",
    "load_dataset",
    "measure_from_definitions",
    "measure_population_map",
    "measure_report_from_rows",
    "output_columns_from_measure",
    "parse_cql",
    "resource_schema",
    "resource_schema_tree",
    "rows_from_measure_reports",
    "run_tests",
    "tests_input_from_dict",
    "translate_cql",
    "validate_resource",
]
