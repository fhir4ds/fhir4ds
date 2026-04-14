# src/cql_py/dependency/types.py

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum
from pathlib import Path


class DependencyType(Enum):
    CQL_LIBRARY = "cql_library"
    FHIR_LIBRARY = "fhir_library"
    VALUESET = "valueset"
    CODESYSTEM = "codesystem"
    MEASURE = "measure"
    BUNDLE = "bundle"


@dataclass
class ResolvedLibrary:
    """A resolved CQL library (from .cql or FHIR Library resource)."""
    name: str
    source_path: Path
    version: Optional[str] = None
    url: Optional[str] = None           # FHIR Library URL
    cql_text: Optional[str] = None      # Extracted CQL
    dependencies: List[str] = field(default_factory=list)


@dataclass
class ResolvedValueSet:
    """A resolved ValueSet with expansion."""
    url: str
    source_path: Path
    version: Optional[str] = None
    name: Optional[str] = None
    codes: List[Dict[str, str]] = field(default_factory=list)
    # Each code: {"system": "...", "code": "...", "display": "..."}


@dataclass
class ResolvedCodeSystem:
    """A resolved CodeSystem."""
    url: str
    source_path: Path
    version: Optional[str] = None
    name: Optional[str] = None


@dataclass
class ResolvedMeasure:
    """A resolved Measure resource."""
    url: str
    source_path: Path
    version: Optional[str] = None
    name: Optional[str] = None
    library_urls: List[str] = field(default_factory=list)
    population_criteria: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ResolutionContext:
    """
    Pre-translation dependency graph.

    NOTE: Renamed from TranslationContext to avoid collision with
    translator/translator.py:TranslationContext (which tracks translation-time state).
    """
    libraries: Dict[str, ResolvedLibrary] = field(default_factory=dict)
    valuesets: Dict[str, ResolvedValueSet] = field(default_factory=dict)
    codesystems: Dict[str, ResolvedCodeSystem] = field(default_factory=dict)
    measures: Dict[str, ResolvedMeasure] = field(default_factory=dict)

    # ValueSet codes loaded into database (for fhirpath_in_valueset UDF)
    valueset_codes_loaded: bool = False
