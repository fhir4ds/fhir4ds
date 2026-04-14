"""Dependency resolver for CQL libraries and FHIR resources."""

from pathlib import Path
from typing import List, Optional, Dict, Any, Set
import json
import base64
import logging
import re

_logger = logging.getLogger(__name__)

from .types import (
    DependencyType,
    ResolvedLibrary,
    ResolvedValueSet,
    ResolvedCodeSystem,
    ResolvedMeasure,
    ResolutionContext,
)
from .errors import ResolutionError
from .cache import DependencyCache


class DependencyResolver:
    """
    Unified resolver for CQL/FHIR dependencies.

    Resolves from file system:
    - .cql files (CQL libraries)
    - .json files (FHIR resources: Library, ValueSet, CodeSystem, Measure, Bundle)

    Example:
        resolver = DependencyResolver(paths=[
            Path("./cql-libraries"),
            Path("./fhir-resources"),
        ])

        # Resolve a library by name
        lib = resolver.resolve_library("FHIRHelpers")

        # Resolve a valueset by URL
        vs = resolver.resolve_valueset("http://hl7.org/fhir/ValueSet/diabetes")

        # Build context for translation
        context = resolver.build_context("http://example.org/Library/MyMeasure")
    """

    def __init__(
        self,
        paths: List[Path],
        cache_parsed: bool = True,
    ):
        self.paths = [Path(p) for p in paths]
        self.cache_parsed = cache_parsed

        # Indexes
        self._libraries: Dict[str, ResolvedLibrary] = {}
        self._valuesets: Dict[str, ResolvedValueSet] = {}
        self._codesystems: Dict[str, ResolvedCodeSystem] = {}
        self._measures: Dict[str, ResolvedMeasure] = {}

        # Cache
        self._cache = DependencyCache() if cache_parsed else None

        # Scan on init
        self._scan_all_paths()

    def _scan_all_paths(self) -> None:
        """Scan all configured paths and index resources."""
        for base_path in self.paths:
            if not base_path.exists():
                continue
            self._scan_path(base_path)

    def _scan_path(self, base_path: Path) -> None:
        """Scan a single path recursively."""
        for file_path in base_path.glob("**/*"):
            if file_path.is_file():
                self._index_file(file_path)

    def _index_file(self, file_path: Path) -> None:
        """Index a single file by type."""
        suffix = file_path.suffix.lower()

        if suffix == ".cql":
            self._index_cql_file(file_path)
        elif suffix == ".json":
            self._index_json_file(file_path)

    def _index_cql_file(self, file_path: Path) -> None:
        """Index a raw CQL file."""
        try:
            content = file_path.read_text()
            # Extract library name from CQL
            name = self._extract_library_name(content)
            if name:
                # Extract dependencies (using include/using statements)
                dependencies = self._extract_cql_dependencies(content)
                self._libraries[name] = ResolvedLibrary(
                    name=name,
                    source_path=file_path,
                    cql_text=content,
                    dependencies=dependencies,
                )
        except Exception as e:
            _logger.warning("Failed to index CQL file %s: %s", file_path, e)

    def _index_json_file(self, file_path: Path) -> None:
        """Index a FHIR resource JSON file."""
        try:
            data = json.loads(file_path.read_text())
            resource_type = data.get("resourceType")

            if resource_type == "Library":
                self._index_fhir_library(file_path, data)
            elif resource_type == "ValueSet":
                self._index_valueset(file_path, data)
            elif resource_type == "CodeSystem":
                self._index_codesystem(file_path, data)
            elif resource_type == "Measure":
                self._index_measure(file_path, data)
            elif resource_type == "Bundle":
                self._index_bundle(file_path, data)
        except Exception as e:
            _logger.warning("Failed to index JSON file %s: %s", file_path, e)

    def _index_fhir_library(self, file_path: Path, data: Dict) -> None:
        """Index a FHIR Library resource."""
        url = data.get("url")
        name = data.get("name")

        # Extract CQL from content.attachment.data
        cql_text = self._extract_cql_from_library(data)

        lib = ResolvedLibrary(
            name=name or "",
            version=data.get("version"),
            url=url,
            source_path=file_path,
            cql_text=cql_text,
            dependencies=self._extract_dependencies(data),
        )

        if url:
            self._libraries[url] = lib
        if name:
            self._libraries[name] = lib

    def _index_valueset(self, file_path: Path, data: Dict) -> None:
        """Index a FHIR ValueSet resource."""
        url = data.get("url")
        if not url:
            return

        # Extract codes from expansion
        codes = []
        expansion = data.get("expansion", {}).get("contains", [])
        for item in expansion:
            codes.append({
                "system": item.get("system"),
                "code": item.get("code"),
                "display": item.get("display"),
            })

        # Also check compose.include
        if not codes:
            for include in data.get("compose", {}).get("include", []):
                system = include.get("system")
                for concept in include.get("concept", []):
                    codes.append({
                        "system": system,
                        "code": concept.get("code"),
                        "display": concept.get("display"),
                    })

        self._valuesets[url] = ResolvedValueSet(
            url=url,
            version=data.get("version"),
            name=data.get("name"),
            source_path=file_path,
            codes=codes,
        )

    def _index_codesystem(self, file_path: Path, data: Dict) -> None:
        """Index a FHIR CodeSystem resource."""
        url = data.get("url")
        if not url:
            return

        self._codesystems[url] = ResolvedCodeSystem(
            url=url,
            version=data.get("version"),
            name=data.get("name"),
            source_path=file_path,
        )

    def _index_measure(self, file_path: Path, data: Dict) -> None:
        """Index a FHIR Measure resource."""
        url = data.get("url")
        if not url:
            return

        # Extract library references
        library_urls = data.get("library", [])

        # Extract population criteria
        populations = []
        for group in data.get("group", []):
            for pop in group.get("population", []):
                populations.append({
                    "code": pop.get("code", {}).get("coding", [{}])[0].get("code"),
                    "criteria": pop.get("criteria", {}).get("expression"),
                })

        self._measures[url] = ResolvedMeasure(
            url=url,
            version=data.get("version"),
            name=data.get("name"),
            source_path=file_path,
            library_urls=library_urls,
            population_criteria=populations,
        )

    def _index_bundle(self, file_path: Path, data: Dict) -> None:
        """Index resources within a FHIR Bundle."""
        for entry in data.get("entry", []):
            resource = entry.get("resource")
            if resource:
                self._index_resource(resource, file_path)

    def _index_resource(self, resource: Dict, source_path: Path) -> None:
        """Index a single resource from a bundle."""
        resource_type = resource.get("resourceType")

        if resource_type == "Library":
            self._index_fhir_library(source_path, resource)
        elif resource_type == "ValueSet":
            self._index_valueset(source_path, resource)
        elif resource_type == "CodeSystem":
            self._index_codesystem(source_path, resource)
        elif resource_type == "Measure":
            self._index_measure(source_path, resource)

    def _extract_library_name(self, content: str) -> Optional[str]:
        """Extract library name from CQL text."""
        # Match: library <name> version '<version>'
        # or: library <name>
        match = re.search(r'^\s*library\s+([A-Za-z_][A-Za-z0-9_]*)', content, re.MULTILINE)
        if match:
            return match.group(1)
        return None

    def _extract_cql_dependencies(self, content: str) -> List[str]:
        """Extract dependencies from CQL include/using statements."""
        dependencies = []

        # Match: include <name> version '<version>'
        # or: include <name>
        for match in re.finditer(r'^\s*include\s+([A-Za-z_][A-Za-z0-9_]*)', content, re.MULTILINE):
            dependencies.append(match.group(1))

        return dependencies

    def _extract_cql_from_library(self, data: Dict) -> Optional[str]:
        """Extract CQL from FHIR Library content.attachment.data."""
        contents = data.get("content", [])
        for content in contents:
            content_type = content.get("contentType", "")
            # Check for CQL content type
            if content_type in ("text/cql", "application/cql"):
                # CQL may be in attachment.data (base64) or directly
                attachment = content.get("attachment", {})
                raw_data = attachment.get("data")
                if raw_data:
                    try:
                        return base64.b64decode(raw_data).decode("utf-8")
                    except Exception as e:
                        _logger.warning("Failed to decode base64 attachment data: %s", e)
                # Also check for direct CQL in content
                if "data" in content:
                    try:
                        return base64.b64decode(content["data"]).decode("utf-8")
                    except Exception as e:
                        _logger.warning("Failed to decode base64 content data: %s", e)
        return None

    def _extract_dependencies(self, data: Dict) -> List[str]:
        """Extract dependencies from FHIR Library."""
        dependencies = []

        # Check relatedArtifact for dependencies
        for artifact in data.get("relatedArtifact", []):
            if artifact.get("type") == "depends-on":
                # URL reference to another library
                url = artifact.get("url")
                if url:
                    dependencies.append(url)
                # Also check resource reference
                resource = artifact.get("resource")
                if resource:
                    dependencies.append(resource)

        # Check parameter for data requirements
        for param in data.get("parameter", []):
            # ValueSet references
            if param.get("type") == "ValueSet":
                vs_url = param.get("valueSet")
                if vs_url:
                    # This is a valueset dependency, not a library one
                    pass

        return dependencies

    def resolve_library(
        self,
        name_or_url: str,
        version: Optional[str] = None
    ) -> Optional[ResolvedLibrary]:
        """Resolve a library by name or URL."""
        # Try exact match
        if name_or_url in self._libraries:
            return self._libraries[name_or_url]

        # Try with version
        if version:
            key = f"{name_or_url}|{version}"
            if key in self._libraries:
                return self._libraries[key]

        return None

    def resolve_valueset(self, url: str) -> Optional[ResolvedValueSet]:
        """Resolve a valueset by URL."""
        return self._valuesets.get(url)

    def resolve_measure(self, url: str) -> Optional[ResolvedMeasure]:
        """Resolve a measure by URL."""
        return self._measures.get(url)

    def build_context(
        self,
        library_name_or_url: str,
        recursive: bool = True
    ) -> ResolutionContext:
        """
        Build complete translation context for a library.

        Recursively resolves all dependencies (included libraries, valuesets).
        """
        context = ResolutionContext()

        # Resolve the main library
        lib = self.resolve_library(library_name_or_url)
        if not lib:
            raise ResolutionError(f"Library not found: {library_name_or_url}")

        context.libraries[lib.name] = lib

        # Recursively resolve dependencies with cycle detection
        if recursive:
            self._resolve_dependencies(lib, context, visiting=set())

        return context

    def _resolve_dependencies(
        self,
        library: ResolvedLibrary,
        context: ResolutionContext,
        visiting: Optional[Set[str]] = None
    ) -> None:
        """Recursively resolve library dependencies with cycle detection."""
        if visiting is None:
            visiting = set()

        # Track the current library in the visiting path
        # Use library name as the key for cycle detection
        current_key = library.name

        for dep_ref in library.dependencies:
            # Cycle detection - check if we're trying to visit something
            # that's already in the current resolution path
            if dep_ref in visiting:
                cycle_path = " -> ".join(sorted(visiting)) + f" -> {dep_ref}"
                raise ResolutionError(
                    f"Circular dependency detected: {cycle_path}"
                )

            # Try to resolve as library
            dep_lib = self.resolve_library(dep_ref)
            if dep_lib:
                # Check if already fully resolved (in context)
                if dep_lib.name in context.libraries:
                    continue

                # Add to context and track visiting path for cycle detection
                context.libraries[dep_lib.name] = dep_lib
                visiting.add(current_key)
                self._resolve_dependencies(dep_lib, context, visiting)
                visiting.remove(current_key)
