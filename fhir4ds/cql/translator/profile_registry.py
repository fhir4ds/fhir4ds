"""
Profile registry for FHIR profile resolution.

Consolidates profile knowledge from JSON config, replacing former hardcoded dicts
in retrieve.py and cte_builder.py.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

from ..paths import get_resource_path

logger = logging.getLogger(__name__)

# Default JSON config path (relative to this file's package)
_DEFAULT_CONFIG = get_resource_path("profiles", "qicore-profiles.json")


@dataclass
class ExtensionInfo:
    """Metadata for a QICore property extension."""
    url: str
    value_type: str  # e.g. "DateTime", "Boolean", "CodeableConcept"


class ProfileRegistry:
    """Registry for FHIR profile resolution.

    Loads profile data from a JSON config file and provides lookup methods
    that replace the 4 hardcoded profile dicts.
    """

    # Configurable profile-name prefixes to strip during fallback resolution.
    # Loaded from JSON config key "profile_name_prefixes" (default: QICore patterns).
    _FALLBACK_PREFIXES: tuple = ("QICore-", "QICore")

    def __init__(
        self,
        generic_profiles: Dict[str, str],
        named_profiles: Dict[str, dict],
        url_to_type: Dict[str, str],
        profiles_requiring_suffix: Dict[str, str],
        property_extensions: Optional[Dict[str, dict]] = None,
    ):
        self._generic_profiles = generic_profiles
        self._named_profiles = named_profiles
        self._url_to_type = url_to_type
        self._profiles_requiring_suffix = profiles_requiring_suffix
        self._property_extensions: Dict[str, dict] = property_extensions or {}
        self._model_config = None  # set by from_model_config
        self._extension_paths: Optional[dict] = None
        self._raw_component_profile_keywords: Optional[list] = None
        self._component_profile_keywords: Optional[list] = None
        self._raw_component_resource_types: Optional[list] = None
        self._component_resource_types_set: Optional[set] = None
        self._fallback_prefixes: tuple = self._FALLBACK_PREFIXES

    @classmethod
    def from_json(cls, path: Optional[str] = None) -> ProfileRegistry:
        """Load a ProfileRegistry from a JSON config file.

        Args:
            path: Path to JSON config. Uses bundled default if None.
        """
        config_path = Path(path) if path else _DEFAULT_CONFIG
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        registry = cls(
            generic_profiles=data.get("generic_profiles", {}),
            named_profiles=data.get("named_profiles", {}),
            url_to_type=data.get("url_to_type", {}),
            profiles_requiring_suffix=data.get("profiles_requiring_suffix", {}),
            property_extensions=data.get("property_extensions", {}),
        )
        registry._raw_component_profile_keywords = (
            data.get("component_profile_keywords", {}).get("keywords", [])
        )
        registry._raw_component_resource_types = (
            data.get("component_resource_types", {}).get("types", [])
        )
        raw_prefixes = data.get("profile_name_prefixes")
        if raw_prefixes:
            registry._fallback_prefixes = tuple(raw_prefixes)
        return registry

    @classmethod
    def from_model_config(cls, config: "ModelConfig") -> ProfileRegistry:
        """Load ProfileRegistry from the versioned QI Core directory.

        Falls back to the legacy profiles/ path if versioned file not found.
        """
        versioned = config.qicore_dir / "qicore-profiles.json"
        legacy = _DEFAULT_CONFIG
        path = versioned if versioned.exists() else legacy
        registry = cls.from_json(str(path))
        registry._model_config = config
        return registry

    # --- Lazy properties for versioned config loading ---

    @property
    def extension_paths(self) -> dict:
        """QI Core virtual property → US Core extension URL mappings."""
        if self._extension_paths is None:
            if self._model_config is not None:
                versioned = self._model_config.us_core_dir / "extension_paths.json"
                if versioned.exists():
                    with open(versioned, encoding="utf-8") as f:
                        data = json.load(f)
                    data.pop("_comment", None)
                    data.pop("_version", None)
                    self._extension_paths = data
                    return self._extension_paths
            # Fallback to legacy profiles/ dir
            legacy = get_resource_path("profiles", "extension_paths.json")
            if legacy.exists():
                with open(legacy, encoding="utf-8") as f:
                    data = json.load(f)
                data.pop("_comment", None)
                self._extension_paths = data
            else:
                self._extension_paths = {}
        return self._extension_paths

    @property
    def component_profile_keywords(self) -> list:
        """Profile URL keywords indicating BP-like composite observations."""
        if self._component_profile_keywords is None:
            self._component_profile_keywords = self._raw_component_profile_keywords or []
        return self._component_profile_keywords

    @property
    def component_resource_types(self) -> set:
        """Resource types that support component elements for composite observations."""
        if self._component_resource_types_set is None:
            self._component_resource_types_set = set(self._raw_component_resource_types or [])
        return self._component_resource_types_set

    # --- Lookups replacing QICORE_PROFILE_PATTERNS ---

    def get_generic_profile_url(self, resource_type: str) -> Optional[str]:
        """Get the generic QICore profile URL for a FHIR resource type.

        Replaces: ``QICORE_PROFILE_PATTERNS[resource_type]``
        """
        return self._generic_profiles.get(resource_type)

    # --- Lookups replacing QICORE_TO_FHIR_TYPE ---

    def resolve_named_profile(self, profile_name: str) -> Optional[Tuple[str, Optional[str]]]:
        """Resolve a named profile to (base_type, profile_url).

        Replaces: ``QICORE_TO_FHIR_TYPE[profile_name]``

        Falls back to stripping common QICore prefixes (e.g., "QICoreCondition"
        -> "Condition") when the profile name is not explicitly registered.

        Returns:
            Tuple of (base_type, profile_url) or None if unknown.
        """
        info = self._named_profiles.get(profile_name)
        if info is not None:
            return (info["base_type"], info.get("url"))
        # Fallback: strip known profile-name prefixes (configurable via JSON)
        for prefix in self._fallback_prefixes:
            if profile_name.startswith(prefix):
                return (profile_name[len(prefix):], None)
        return None

    # --- Lookups replacing USCORE_PROFILE_TO_FHIR_TYPE ---

    def resolve_url_to_type(self, url: str) -> Optional[str]:
        """Resolve a profile URL to its FHIR base resource type.

        Replaces: ``USCORE_PROFILE_TO_FHIR_TYPE[url]``
        """
        return self._url_to_type.get(url)

    def get_type_alias(self, profile_url: str) -> Optional[str]:
        """Reverse lookup: profile URL → CQL type alias.

        Returns the registered named-profile alias for a given profile URL,
        e.g. ``"http://...qicore-condition-encounter-diagnosis"`` →
        ``"ConditionEncounterDiagnosis"``.
        """
        for alias, info in self._named_profiles.items():
            if info.get("url") == profile_url:
                return alias
        return None

    # --- Profile suffix lookups ---

    def get_all_profile_urls(self, type_name: str) -> list:
        """Return the profile URL(s) for a given type/profile name.

        For named profiles (e.g. ``MedicationNotRequested``), returns only
        the specific profile URL so that ``is`` type-checks distinguish
        between profiles of the same base type.  Falls back to the generic
        profile URL only when no named-profile entry exists.
        """
        # Named profile entry — return specific URL only
        info = self._named_profiles.get(type_name)
        if info is not None and info.get("url"):
            return [info["url"]]
        # Fallback: generic profile for the base type
        base_type = info["base_type"] if info else type_name
        generic = self._generic_profiles.get(base_type)
        return [generic] if generic else []

    def get_negation_info(self, profile_name: str) -> Optional[Tuple[str, str]]:
        """Return (base_type, negation_field) for negation profiles.

        Negation profiles like ``MedicationNotRequested`` share a FHIR base
        type with a positive profile (``MedicationRequest``) and are
        distinguished by a boolean field (``doNotPerform``) or status value.

        Returns:
            Tuple of (base_type, negation_filter) or None if not a negation
            profile.
        """
        info = self._named_profiles.get(profile_name)
        if info is not None and info.get("negation_filter"):
            return (info["base_type"], info["negation_filter"])
        return None

    def get_suffix(self, url: str) -> Optional[str]:
        """Get the distinguishing suffix for a profile URL, if any.

        Returns a suffix for:
        1. Profiles explicitly registered in profiles_requiring_suffix (e.g., vital signs)
        2. Named profiles marked with ``meta_profile_filter`` — these need separate
           CTEs so that meta.profile WHERE-clause filtering can be applied.
        3. Negation profiles (profiles with ``negation_filter``) — these need
           separate CTEs from their positive counterparts.
        """
        # Check explicit suffix registration first
        explicit = self._profiles_requiring_suffix.get(url)
        if explicit is not None:
            return explicit

        # Check named profiles for meta_profile_filter or negation_filter
        for _name, info in self._named_profiles.items():
            if info.get("url") == url:
                if info.get("meta_profile_filter") or info.get("negation_filter"):
                    last_segment = url.rsplit("/", 1)[-1]
                    # Strip common implementation-guide prefixes for readability
                    for prefix in self._fallback_prefixes:
                        p = prefix.lower().rstrip("-") + "-"
                        if last_segment.startswith(p):
                            last_segment = last_segment[len(p):]
                            break
                    return last_segment

        return None

    def needs_profile_filter(self, resource_type: str, profile_url: str) -> bool:
        """Check if a retrieve with this profile_url needs meta.profile filtering.

        Returns True only when the profile is explicitly marked with
        ``"meta_profile_filter": true`` in the configuration.  This flag is set
        for profiles whose test data reliably declares the specific profile URL
        in ``meta.profile`` (e.g., QI-Core Condition sub-profiles).
        """
        if not profile_url:
            return False
        for _name, info in self._named_profiles.items():
            if info.get("url") == profile_url:
                return bool(info.get("meta_profile_filter"))
        return False

    # --- Compatibility helpers ---

    @property
    def qicore_profile_patterns(self) -> Dict[str, str]:
        """Backward-compatible access to generic_profiles dict."""
        return dict(self._generic_profiles)

    @property
    def qicore_to_fhir_type(self) -> Dict[str, Tuple[str, Optional[str]]]:
        """Backward-compatible access matching QICORE_TO_FHIR_TYPE format."""
        result = {}
        for name, info in self._named_profiles.items():
            result[name] = (info["base_type"], info.get("url"))
        return result

    @property
    def uscore_profile_to_fhir_type(self) -> Dict[str, str]:
        """Backward-compatible access to url_to_type dict."""
        return dict(self._url_to_type)

    @property
    def profiles_requiring_suffix(self) -> Dict[str, str]:
        """Backward-compatible access to profiles_requiring_suffix dict."""
        return dict(self._profiles_requiring_suffix)

    def get_extension_info(self, resource_type: str, property_name: str) -> Optional["ExtensionInfo"]:
        """Return extension metadata for a QICore property extension, or None for standard FHIR elements.

        Args:
            resource_type: FHIR resource type (e.g. "ServiceRequest").
            property_name: CQL/FHIR property name (e.g. "recorded").

        Returns:
            ExtensionInfo with url and value_type, or None if not an extension property.
        """
        key = f"{resource_type}.{property_name}"
        entry = self._property_extensions.get(key)
        if entry is None:
            return None
        return ExtensionInfo(url=entry["url"], value_type=entry["value_type"])


# Lazily-initialized default instance (thread-safe via lock)
import threading
_default_registry: Optional[ProfileRegistry] = None
_default_registry_lock = threading.Lock()


def get_default_profile_registry() -> ProfileRegistry:
    """Get the default ProfileRegistry using the default ModelConfig (versioned paths).

    Thread-safe: uses a lock to prevent duplicate initialization in concurrent
    contexts (e.g., DuckDB vectorized UDF threads).
    """
    global _default_registry
    if _default_registry is None:
        with _default_registry_lock:
            if _default_registry is None:
                from ..translator.model_config import DEFAULT_MODEL_CONFIG
                _default_registry = ProfileRegistry.from_model_config(DEFAULT_MODEL_CONFIG)
    return _default_registry
