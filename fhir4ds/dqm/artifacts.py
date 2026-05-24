"""Artifact resolution for DQM Measure compilation.

The resolver boundary keeps Measure/CQL/ValueSet lookup separate from measure
translation. Path-based callers use ``FileArtifactResolver`` by default, while
FHIR-server backed integrations can provide an explicit resolver.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from fhir4ds.dqm.config import DQMConfigError
from fhir4ds.dqm.errors import MeasureParseError

_CQL_INCLUDE_RE = re.compile(
    r"^\s*include\s+([A-Za-z][A-Za-z0-9_.]*)\b"
    r"(?:\s+version\s+'([^']+)')?",
    re.IGNORECASE | re.MULTILINE,
)
_CQL_VALUESET_RE = re.compile(
    r"valueset\s+(?:\"[^\"]+\"|[A-Za-z_][A-Za-z0-9_]*)\s*:\s*'([^']+)'"
    r"(?:\s+version\s+'([^']+)')?",
    re.IGNORECASE,
)


@dataclass(frozen=True, order=True)
class ValueSetRef:
    """Canonical ValueSet reference declared in CQL."""

    url: str
    version: str | None = None

    @property
    def label(self) -> str:
        return f"{self.url}|{self.version}" if self.version else self.url


@dataclass(frozen=True)
class MeasureArtifact:
    """Resolved FHIR Measure resource and stable source identity."""

    resource: dict[str, Any]
    source_id: str


@dataclass(frozen=True)
class LibraryArtifact:
    """Resolved CQL library content and stable source identity."""

    text: str
    source_id: str
    name: str | None = None
    url: str | None = None
    version: str | None = None

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()


class ArtifactResolver(Protocol):
    """Resolve Measure, Library, and ValueSet artifacts for DQM compilation."""

    def resolve_measure(self, ref: str | Path | dict[str, Any]) -> MeasureArtifact:
        """Resolve a Measure reference to a FHIR Measure resource."""

    def resolve_library(
        self,
        ref: str | Path | dict[str, Any] | None = None,
        *,
        measure: dict[str, Any] | None = None,
        measure_source_id: str | None = None,
    ) -> LibraryArtifact:
        """Resolve the primary CQL library for a Measure."""

    def resolve_include(
        self,
        alias: str,
        version: str | None = None,
    ) -> LibraryArtifact | None:
        """Resolve a CQL include alias to a library artifact."""

    def resolve_valuesets_for_cql(self, cql_text: str) -> list[dict[str, Any]]:
        """Resolve ValueSet resources declared by CQL and transitive includes."""

    def fingerprint(self) -> str:
        """Return a stable fingerprint for artifacts visible to this resolver."""


@dataclass
class FileArtifactResolver:
    """Resolve Measure, CQL, and ValueSet artifacts from local files."""

    include_paths: list[str | Path] | None = None
    valueset_paths: list[str | Path] | None = None
    _default_include_paths: list[Path] = field(default_factory=list, init=False)
    _include_cache: dict[tuple[str, str | None], LibraryArtifact] = field(
        default_factory=dict,
        init=False,
    )
    _valueset_cache: dict[tuple[str, str | None], dict[str, Any]] = field(
        default_factory=dict,
        init=False,
    )
    _valueset_index_cache: dict[str, list[dict[str, Any]]] | None = field(
        default=None,
        init=False,
    )

    def resolve_measure(self, ref: str | Path | dict[str, Any]) -> MeasureArtifact:
        if isinstance(ref, dict):
            return MeasureArtifact(
                resource=ref,
                source_id=f"dict:{_json_hash(ref)}",
            )
        path = Path(ref)
        if not path.exists():
            raise FileNotFoundError(f"Measure file not found: {ref}")
        try:
            resource = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise MeasureParseError(f"Invalid JSON in measure file '{ref}': {exc}") from exc
        return MeasureArtifact(
            resource=resource,
            source_id=f"file:{path.resolve()}:{_file_hash(path)}",
        )

    def resolve_library(
        self,
        ref: str | Path | dict[str, Any] | None = None,
        *,
        measure: dict[str, Any] | None = None,
        measure_source_id: str | None = None,
    ) -> LibraryArtifact:
        if isinstance(ref, dict):
            return _library_artifact_from_resource(ref, source_id=f"dict:{_json_hash(ref)}")
        if ref is not None:
            return self._library_from_path(Path(ref), label=str(ref))

        if measure is None:
            raise FileNotFoundError("CQL library path is required when no Measure is supplied")

        measure_path = _path_from_file_source_id(measure_source_id)
        search_dirs = self._search_dirs(default_dir=measure_path.parent if measure_path else None)
        candidates = _library_candidate_names(measure)
        for directory in search_dirs:
            for candidate in candidates:
                path = directory / candidate
                if path.exists():
                    return self._library_from_path(path, label=str(path))
        raise FileNotFoundError(
            "Could not resolve CQL library for Measure. "
            "Set cql_library_path or add the library directory to include_paths."
        )

    def resolve_include(
        self,
        alias: str,
        version: str | None = None,
    ) -> LibraryArtifact | None:
        cached = self._include_cache.get((alias, version))
        if cached is not None:
            return cached
        if version is None:
            cached = self._include_cache.get((alias, None))
            if cached is not None:
                return cached

        resolved_alias = alias.rsplit(".", 1)[-1] if "." in alias else alias
        for search_alias in dict.fromkeys([alias, resolved_alias]):
            for directory in self._search_dirs():
                candidates = []
                if version:
                    candidates.append(directory / f"{search_alias}-{version}.cql")
                candidates.append(directory / f"{search_alias}.cql")
                candidates.extend(sorted(directory.glob(f"{search_alias}-*.cql")))
                for path in candidates:
                    if path.exists():
                        artifact = self._library_from_path(path, label=str(path))
                        self._include_cache[(alias, version)] = artifact
                        self._include_cache.setdefault((search_alias, version), artifact)
                        self._include_cache.setdefault((search_alias, None), artifact)
                        if artifact.name:
                            self._include_cache.setdefault((artifact.name, version), artifact)
                            self._include_cache.setdefault((artifact.name, None), artifact)
                        return artifact
        return None

    def resolve_valuesets_for_cql(self, cql_text: str) -> list[dict[str, Any]]:
        """Resolve CQL-declared ValueSets from configured files.

        If ``valueset_paths`` is omitted, file-based resolution is intentionally
        passive for backward compatibility: existing callers may have loaded
        terminology by other means.
        """
        if not self.valueset_paths:
            return []

        refs = _valueset_refs_for_cql(
            cql_text,
            resolve_include=self.resolve_include,
            seen_libraries=set(),
        )
        valuesets: list[dict[str, Any]] = []
        for ref in refs:
            valuesets.append(self._resolve_valueset_ref(ref))
        return valuesets

    def fingerprint(self) -> str:
        items: list[tuple[str, str]] = []
        for path in self._search_dirs():
            if path.is_dir():
                candidates = sorted(path.glob("*.cql"))
            else:
                candidates = [path]
            for candidate in candidates:
                try:
                    items.append((str(candidate.resolve()), _file_hash(candidate)))
                except OSError:
                    items.append((str(candidate), "missing"))
        for path in self._valueset_search_paths():
            candidates = sorted(path.rglob("*.json")) if path.is_dir() else [path]
            for candidate in candidates:
                try:
                    items.append((str(candidate.resolve()), _file_hash(candidate)))
                except OSError:
                    items.append((str(candidate), "missing"))
        return hashlib.sha256(json.dumps(items, sort_keys=True).encode()).hexdigest()

    def _library_from_path(self, path: Path, *, label: str) -> LibraryArtifact:
        if not path.exists():
            raise FileNotFoundError(f"CQL library not found: {label}")
        if not path.is_file():
            raise ValueError(f"CQL library path must be a file: {label}")
        self._add_default_include_path(path.parent)
        return LibraryArtifact(
            text=path.read_text(),
            source_id=f"file:{path.resolve()}:{_file_hash(path)}",
            name=path.stem,
        )

    def _search_dirs(self, default_dir: Path | None = None) -> list[Path]:
        raw_paths = [Path(path) for path in self.include_paths or []]
        paths = [*raw_paths, *self._default_include_paths]
        if default_dir is not None:
            paths.append(default_dir)
        deduped: list[Path] = []
        seen: set[str] = set()
        for path in paths:
            key = str(path)
            if key in seen:
                continue
            deduped.append(path)
            seen.add(key)
        return deduped

    def _add_default_include_path(self, path: Path) -> None:
        if not any(existing == path for existing in self._default_include_paths):
            self._default_include_paths.append(path)

    def _valueset_search_paths(self) -> list[Path]:
        return [Path(path) for path in self.valueset_paths or []]

    def _resolve_valueset_ref(self, ref: ValueSetRef) -> dict[str, Any]:
        cache_key = (ref.url, ref.version)
        cached = self._valueset_cache.get(cache_key)
        if cached is not None:
            return cached

        candidates = list(self._valueset_index().get(ref.url, []))
        if ref.version:
            candidates = [
                valueset
                for valueset in candidates
                if valueset.get("version") == ref.version
            ]
        if not candidates:
            raise DQMConfigError(f"ValueSet not found in files: {ref.label}")
        if len(candidates) > 1 and not ref.version:
            versions = ", ".join(
                sorted(str(valueset.get("version") or "<unversioned>") for valueset in candidates)
            )
            raise DQMConfigError(
                f"ValueSet reference is ambiguous in files: {ref.url}. "
                f"Specify a version; available versions: {versions}"
            )

        valueset = candidates[0]
        self._valueset_cache[cache_key] = valueset
        return valueset

    def _valueset_index(self) -> dict[str, list[dict[str, Any]]]:
        if self._valueset_index_cache is not None:
            return self._valueset_index_cache

        index: dict[str, list[dict[str, Any]]] = {}
        for path in self._iter_valueset_files():
            try:
                data = json.loads(path.read_text())
            except json.JSONDecodeError as exc:
                raise DQMConfigError(f"Invalid ValueSet JSON {path}: {exc}") from exc
            for resource in _valueset_resources_from_json(data):
                url = resource.get("url")
                if not isinstance(url, str) or not url:
                    raise DQMConfigError(f"ValueSet JSON is missing a canonical url: {path}")
                index.setdefault(url, []).append(resource)

        self._valueset_index_cache = index
        return index

    def _iter_valueset_files(self):
        for path in self._valueset_search_paths():
            if path.is_dir():
                yield from sorted(path.rglob("*.json"))
            elif path.is_file():
                yield path
            else:
                raise FileNotFoundError(f"ValueSet path not found: {path}")


class HapiArtifactResolver:
    """Resolve Measure, Library, and ValueSet resources through a FHIR REST API."""

    def __init__(
        self,
        base_url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout_seconds: float = 30.0,
    ):
        if not base_url:
            raise DQMConfigError("HAPI artifact resolver requires a base URL")
        if timeout_seconds <= 0:
            raise DQMConfigError("HAPI artifact resolver timeout must be positive")
        self.base_url = base_url.rstrip("/")
        self.headers = _normalize_headers(headers)
        self.timeout_seconds = float(timeout_seconds)
        self._cache: dict[tuple[str, str], dict[str, Any]] = {}
        self._library_cache: dict[str, LibraryArtifact] = {}
        self._valueset_cache: dict[tuple[str, str | None], dict[str, Any]] = {}

    def resolve_measure(self, ref: str | Path | dict[str, Any]) -> MeasureArtifact:
        if isinstance(ref, dict):
            return MeasureArtifact(resource=ref, source_id=f"dict:{_json_hash(ref)}")
        resource = self._read_resource_ref("Measure", str(ref))
        return MeasureArtifact(
            resource=resource,
            source_id=_resource_source_id("hapi", resource),
        )

    def resolve_library(
        self,
        ref: str | Path | dict[str, Any] | None = None,
        *,
        measure: dict[str, Any] | None = None,
        measure_source_id: str | None = None,
    ) -> LibraryArtifact:
        del measure_source_id
        if isinstance(ref, dict):
            return _library_artifact_from_resource(ref, source_id=f"dict:{_json_hash(ref)}")
        if ref is None:
            if measure is None:
                raise DQMConfigError("A Measure is required to resolve the primary Library")
            ref = _primary_library_ref(measure)
        if not ref:
            raise DQMConfigError("Measure does not reference a CQL Library")
        return self._resolve_library_ref(str(ref))

    def resolve_include(
        self,
        alias: str,
        version: str | None = None,
    ) -> LibraryArtifact | None:
        resolved_alias = alias.rsplit(".", 1)[-1] if "." in alias else alias
        for candidate in dict.fromkeys([alias, resolved_alias]):
            try:
                return self._resolve_library_ref(candidate, version=version)
            except FileNotFoundError:
                continue
        return None

    def fingerprint(self) -> str:
        payload = {
            "base_url": self.base_url,
            "resources": [
                _resource_source_id(key[0], resource)
                for key, resource in sorted(self._cache.items())
            ],
            "libraries": [
                (key, artifact.source_id, artifact.content_hash)
                for key, artifact in sorted(self._library_cache.items())
            ],
            "valuesets": [
                (key[0], key[1], _resource_source_id("hapi", valueset))
                for key, valueset in sorted(self._valueset_cache.items())
            ],
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def resolve_valuesets_for_cql(self, cql_text: str) -> list[dict[str, Any]]:
        """Resolve transitive ValueSet declarations in CQL through HAPI."""
        refs = _valueset_refs_for_cql(
            cql_text,
            resolve_include=self.resolve_include,
            seen_libraries=set(),
        )
        valuesets: list[dict[str, Any]] = []
        for ref in refs:
            try:
                valuesets.append(self._resolve_valueset_ref(ref))
            except FileNotFoundError as exc:
                raise DQMConfigError(
                    f"ValueSet not found in HAPI: {ref.label}"
                ) from exc
        return valuesets

    def _resolve_valueset_ref(self, ref: ValueSetRef) -> dict[str, Any]:
        cache_key = (ref.url, ref.version)
        cached = self._valueset_cache.get(cache_key)
        if cached is not None:
            return cached

        params = {"url": ref.url}
        if ref.version:
            params["version"] = ref.version
        valueset = self._search_one("ValueSet", params)
        if valueset.get("expansion"):
            self._valueset_cache[cache_key] = valueset
            return valueset

        try:
            expanded = self._expand_valueset(ref, valueset)
        except RuntimeError as exc:
            raise DQMConfigError(
                "HAPI ValueSet resolution requires an expanded ValueSet. "
                f"The ValueSet resource had no expansion and $expand failed for: {ref.label}. "
                f"{exc}"
            ) from exc
        if expanded.get("expansion"):
            if not expanded.get("url"):
                expanded = {**expanded, "url": ref.url}
            if ref.version and not expanded.get("version"):
                expanded = {**expanded, "version": ref.version}
            self._valueset_cache[cache_key] = expanded
            return expanded

        raise DQMConfigError(
            "HAPI ValueSet resolution requires an expanded ValueSet. "
            "HAPI returned the ValueSet resource, but neither the resource nor "
            f"$expand contained expansion codes for: {ref.label}"
        )

    def _resolve_library_ref(
        self,
        ref: str,
        *,
        version: str | None = None,
    ) -> LibraryArtifact:
        cache_key = f"{ref}|{version}" if version else ref
        cached = self._library_cache.get(cache_key)
        if cached is not None:
            return cached
        resource = self._read_resource_ref("Library", ref, version=version)
        artifact = _library_artifact_from_resource(
            resource,
            source_id=_resource_source_id("hapi", resource),
        )
        self._library_cache[cache_key] = artifact
        self._library_cache.setdefault(ref, artifact)
        if artifact.name:
            self._library_cache.setdefault(artifact.name, artifact)
            if artifact.version:
                self._library_cache.setdefault(f"{artifact.name}|{artifact.version}", artifact)
        if artifact.url:
            self._library_cache.setdefault(artifact.url, artifact)
            if artifact.version:
                self._library_cache.setdefault(f"{artifact.url}|{artifact.version}", artifact)
        return artifact

    def _read_resource_ref(
        self,
        resource_type: str,
        ref: str,
        *,
        version: str | None = None,
    ) -> dict[str, Any]:
        if version:
            for params in _versioned_search_params(resource_type, ref, version):
                try:
                    return self._search_one(resource_type, params)
                except FileNotFoundError:
                    continue
        if ref.startswith(f"{resource_type}/"):
            return self._get_resource(resource_type, ref.split("/", 1)[1])
        if ref.startswith("http://") or ref.startswith("https://"):
            url, canonical_version = _split_canonical(ref)
            params = {"url": url}
            effective_version = version or canonical_version
            if effective_version:
                params["version"] = effective_version
            return self._search_one(resource_type, params)
        try:
            return self._get_resource(resource_type, ref)
        except FileNotFoundError:
            pass
        if resource_type == "Library":
            for params in (
                {"name": ref},
                {"url": f"https://madie.cms.gov/Library/{ref}"},
            ):
                try:
                    return self._search_one(resource_type, params)
                except FileNotFoundError:
                    continue
        raise FileNotFoundError(f"{resource_type} not found in HAPI: {ref}")

    def _get_resource(self, resource_type: str, resource_id: str) -> dict[str, Any]:
        key = (resource_type, resource_id)
        if key in self._cache:
            return self._cache[key]
        resource = self._read_json(
            f"{self.base_url}/{resource_type}/{urllib.parse.quote(resource_id, safe='')}"
        )
        if resource.get("resourceType") != resource_type:
            raise FileNotFoundError(f"{resource_type}/{resource_id} returned no resource")
        self._cache[key] = resource
        return resource

    def _search_one(self, resource_type: str, params: dict[str, str]) -> dict[str, Any]:
        query = urllib.parse.urlencode(params)
        bundle = self._read_json(f"{self.base_url}/{resource_type}?{query}")
        for entry in bundle.get("entry", []):
            resource = entry.get("resource", {}) if isinstance(entry, dict) else {}
            if resource.get("resourceType") == resource_type:
                key = (resource_type, str(resource.get("id", "")))
                self._cache[key] = resource
                return resource
        raise FileNotFoundError(f"{resource_type} not found in HAPI for {params}")

    def _expand_valueset(
        self,
        ref: ValueSetRef,
        valueset: dict[str, Any],
    ) -> dict[str, Any]:
        params = {"url": ref.url}
        if ref.version:
            params["valueSetVersion"] = ref.version
        query = urllib.parse.urlencode(params)
        try:
            return self._read_json(f"{self.base_url}/ValueSet/$expand?{query}")
        except FileNotFoundError:
            resource_id = valueset.get("id")
            if not resource_id:
                raise
            return self._read_json(
                f"{self.base_url}/ValueSet/"
                f"{urllib.parse.quote(str(resource_id), safe='')}/$expand"
            )

    def _read_json(self, url: str) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/fhir+json",
                **self.headers,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise FileNotFoundError(url) from exc
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HAPI artifact request failed for {url}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"HAPI artifact request failed for {url}: {exc}") from exc


def _valueset_refs_from_cql(cql_text: str) -> list[ValueSetRef]:
    refs: list[ValueSetRef] = []
    for raw_url, raw_version in _CQL_VALUESET_RE.findall(cql_text):
        url, canonical_version = _split_canonical(raw_url)
        version = raw_version or canonical_version
        if raw_version and canonical_version and raw_version != canonical_version:
            raise DQMConfigError(
                "ValueSet declaration contains conflicting canonical and "
                f"version values: {raw_url} version '{raw_version}'"
            )
        refs.append(ValueSetRef(url=url, version=version or None))
    return refs


def _valueset_refs_for_cql(
    cql_text: str,
    *,
    resolve_include: Any,
    seen_libraries: set[str],
) -> list[ValueSetRef]:
    refs = set(_valueset_refs_from_cql(cql_text))
    for alias, version in _CQL_INCLUDE_RE.findall(cql_text):
        key = f"{alias}|{version}" if version else alias
        if key in seen_libraries:
            continue
        seen_libraries.add(key)
        artifact = resolve_include(alias, version=version or None)
        if artifact is not None:
            refs.update(
                _valueset_refs_for_cql(
                    artifact.text,
                    resolve_include=resolve_include,
                    seen_libraries=seen_libraries,
                )
            )
    return sorted(refs)


def _valueset_resources_from_json(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict) and data.get("resourceType") == "Bundle":
        resources: list[dict[str, Any]] = []
        for entry in data.get("entry", []):
            resource = entry.get("resource", {}) if isinstance(entry, dict) else {}
            if isinstance(resource, dict) and resource.get("resourceType") == "ValueSet":
                resources.append(resource)
        return resources
    if isinstance(data, dict) and data.get("resourceType") == "ValueSet":
        return [data]
    return []


def _versioned_search_params(
    resource_type: str,
    ref: str,
    version: str,
) -> list[dict[str, str]]:
    params: list[dict[str, str]] = []
    if ref.startswith("http://") or ref.startswith("https://"):
        url, canonical_version = _split_canonical(ref)
        params.append({"url": url, "version": canonical_version or version})
    else:
        params.append({"name": ref, "version": version})
        if resource_type == "Library":
            params.append({"url": f"https://madie.cms.gov/Library/{ref}", "version": version})
    return params


def _normalize_headers(headers: dict[str, str] | None) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in (headers or {}).items():
        if not isinstance(key, str) or not key.strip():
            raise DQMConfigError("HAPI headers must use non-empty string names")
        if not isinstance(value, str):
            raise DQMConfigError(f"HAPI header {key!r} must have a string value")
        normalized[key.strip()] = value
    return normalized


def _library_artifact_from_resource(
    resource: dict[str, Any],
    *,
    source_id: str,
) -> LibraryArtifact:
    if resource.get("resourceType") != "Library":
        raise DQMConfigError(
            f"Expected Library resource, got {resource.get('resourceType')!r}"
        )
    return LibraryArtifact(
        text=_extract_cql_from_library(resource),
        source_id=source_id,
        name=resource.get("name") or resource.get("id"),
        url=resource.get("url"),
        version=resource.get("version"),
    )


def _extract_cql_from_library(resource: dict[str, Any]) -> str:
    for content in resource.get("content", []):
        content_type = str(content.get("contentType", "")).lower()
        if content_type not in {"text/cql", "application/cql", "text/plain"}:
            continue
        if "data" in content:
            return base64.b64decode(content["data"]).decode("utf-8")
        if "url" in content:
            raise DQMConfigError(
                "Library.content.url CQL attachments are not supported yet"
            )
    raise DQMConfigError(
        f"Library {resource.get('id', '<unknown>')} does not contain text/cql content"
    )


def _library_candidate_names(measure: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    library_ref = _primary_library_ref(measure)
    if library_ref:
        library_name = library_ref.rstrip("/").split("/")[-1].split("|")[0]
        candidates.append(f"{library_name}.cql")
    measure_id = measure.get("id")
    if measure_id:
        candidates.append(f"{measure_id}.cql")
    return list(dict.fromkeys(candidates))


def _primary_library_ref(measure: dict[str, Any]) -> str | None:
    for artifact in measure.get("relatedArtifact", []):
        if (
            isinstance(artifact, dict)
            and artifact.get("type") == "depends-on"
            and "Library" in str(artifact.get("resource", ""))
        ):
            return artifact.get("resource")
    libraries = measure.get("library", [])
    if libraries:
        return libraries[0]
    return None


def _path_from_file_source_id(source_id: str | None) -> Path | None:
    if not source_id or not source_id.startswith("file:"):
        return None
    path_part = source_id[len("file:"):].rsplit(":", 1)[0]
    return Path(path_part)


def _split_canonical(value: str) -> tuple[str, str | None]:
    if "|" not in value:
        return value, None
    url, version = value.split("|", 1)
    return url, version or None


def _resource_source_id(prefix: str, resource: dict[str, Any]) -> str:
    identity = {
        "resourceType": resource.get("resourceType"),
        "id": resource.get("id"),
        "url": resource.get("url"),
        "version": resource.get("version"),
        "hash": _json_hash(resource),
    }
    return f"{prefix}:{json.dumps(identity, sort_keys=True)}"


def _json_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
