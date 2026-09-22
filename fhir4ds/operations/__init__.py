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
from .capabilities.translate import TranslateResult, translate_cql
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
    "DatasetResult",
    "DatasetSpec",
    "DiagnosticCode",
    "Diagnostics",
    "ErrorLocation",
    "EvaluateResult",
    "EvidenceResult",
    "FhirpathResult",
    "LibraryResolver",
    "LibraryText",
    "OperationError",
    "ParseResult",
    "TestCase",
    "TestsInput",
    "TranslateResult",
    "VerifyEnvelope",
    "bundled_library_names",
    "dataset_spec_from_dict",
    "diagnostic_from_exception",
    "evaluate_library",
    "explain_patient",
    "fhirpath_eval",
    "load_dataset",
    "parse_cql",
    "run_tests",
    "tests_input_from_dict",
    "translate_cql",
]
