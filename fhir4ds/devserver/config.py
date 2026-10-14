"""Dev server configuration: flags > config-file > convention merge."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on 3.10 environments
    try:
        import tomli as tomllib
    except ImportError:  # pragma: no cover - tomli ships with the dev env
        tomllib = None

CONVENTION_DIRS = {
    "cql": "cql",
    "valueset": "valuesets",
    "measure": "measures",
    "data": "data",
    "view": "views",
}

_CONFIG_KEYS = {"cql_dirs", "valueset_dirs", "measure_dirs", "data_dirs", "view_dirs"}
_LIST_FIELDS = {
    "cql_dirs": "cql",
    "valueset_dirs": "valueset",
    "measure_dirs": "measure",
    "data_dirs": "data",
    "view_dirs": "view",
}


class DevConfigError(Exception):
    """Invalid dev-server configuration (CLI exit code 2)."""


@dataclass
class DevServerConfig:
    """Effective dev-server configuration after the merge."""

    root: Path
    port: int = 8765
    host: str = "127.0.0.1"
    cql_dirs: list[Path] = field(default_factory=list)
    valueset_dirs: list[Path] = field(default_factory=list)
    measure_dirs: list[Path] = field(default_factory=list)
    data_dirs: list[Path] = field(default_factory=list)
    view_dirs: list[Path] = field(default_factory=list)

    def all_dirs(self) -> list[Path]:
        out: list[Path] = []
        for dirs in (
            self.cql_dirs,
            self.valueset_dirs,
            self.measure_dirs,
            self.data_dirs,
            self.view_dirs,
        ):
            out.extend(dirs)
        return out


def _parse_manifest(path: Path) -> dict[str, list[str]]:
    """Parse the ``[dev]`` table of ``fhir4ds.toml`` (when present)."""
    if not path.exists():
        return {}
    if tomllib is None:  # pragma: no cover
        raise DevConfigError(
            "fhir4ds.toml parsing requires Python 3.11+ (tomllib) or tomli"
        )
    try:
        with open(path, "rb") as fh:
            doc = tomllib.load(fh)
    except Exception as exc:
        raise DevConfigError(f"Invalid TOML in {path}: {exc}") from exc
    section = doc.get("dev")
    if section is None:
        section = {}
    if not isinstance(section, dict):
        raise DevConfigError("fhir4ds.toml [dev] must be a table")
    unknown = set(section) - _CONFIG_KEYS
    if unknown:
        raise DevConfigError(
            f"fhir4ds.toml [dev] has unknown keys {sorted(unknown)}; "
            f"allowed: {sorted(_CONFIG_KEYS)}"
        )
    out: dict[str, list[str]] = {}
    for key, kind in _LIST_FIELDS.items():
        if key not in section:
            continue
        value = section[key]
        if not isinstance(value, list) or not all(
            isinstance(item, str) and item.strip() for item in value
        ):
            raise DevConfigError(
                f"fhir4ds.toml [dev].{key} must be an array of non-empty strings"
            )
        out[kind] = list(value)
    return out


def load_config(
    root: Path | str,
    *,
    port: int | None = None,
    cql_dirs: list[str] | None = None,
    valueset_dirs: list[str] | None = None,
    measure_dirs: list[str] | None = None,
    data_dirs: list[str] | None = None,
    view_dirs: list[str] | None = None,
) -> DevServerConfig:
    """Merge convention dirs + ``[dev]`` manifest + CLI flags.

    Precedence (append order): convention dirs first, then manifest
    entries, then CLI flags last. The manifest ADDS to convention; it
    never replaces it. Later entries win only in the sense that they are
    appended (all dirs are searched; duplicate paths are de-duplicated
    while preserving first occurrence).
    """
    root = Path(root).expanduser().resolve()
    manifest = _parse_manifest(root / "fhir4ds.toml")

    def merged(kind: str, flags: list[str] | None) -> list[Path]:
        entries: list[str] = [CONVENTION_DIRS[kind]]
        entries.extend(manifest.get(kind, []))
        entries.extend(flags or [])
        seen: set[Path] = set()
        out: list[Path] = []
        for entry in entries:
            p = Path(entry).expanduser()
            if not p.is_absolute():
                p = root / p
            p = p.resolve()
            if p not in seen:
                seen.add(p)
                out.append(p)
        return out

    cfg = DevServerConfig(
        root=root,
        port=port if port is not None else 8765,
        cql_dirs=merged("cql", cql_dirs),
        valueset_dirs=merged("valueset", valueset_dirs),
        measure_dirs=merged("measure", measure_dirs),
        data_dirs=merged("data", data_dirs),
        view_dirs=merged("view", view_dirs),
    )
    if not (1 <= cfg.port <= 65535):
        raise DevConfigError(f"Invalid port {cfg.port}")
    return cfg


# ---------------------------------------------------------------------------
# Terminology connectivity ([terminology] table of fhir4ds.toml)
# ---------------------------------------------------------------------------

_TERMINOLOGY_KEYS = {"provider", "base_url", "timeout_seconds", "api_key_env"}

_TERMINOLOGY_PROVIDERS = {"vsac", "http", "disabled"}


@dataclass
class TerminologySettings:
    """Terminology-server connectivity for the dev server.

    The API key is NEVER stored here — only the NAME of the environment
    variable holding it (``api_key_env``, default ``UMLS_API_KEY``), per
    the never-render/never-log doctrine. Resolution happens lazily at
    endpoint-construction time.
    """

    provider: str = "disabled"
    base_url: str | None = None
    timeout_seconds: float = 5.0
    api_key_env: str = "UMLS_API_KEY"

    def api_key(self) -> str | None:
        """Lazily read the API key from the named env var (never logged)."""
        import os

        return os.environ.get(self.api_key_env) or None


def _parse_terminology_manifest(path: Path) -> dict[str, object]:
    """Parse the ``[terminology]`` table of ``fhir4ds.toml`` (when present).

    Returns {} when absent. Env vars (``FHIR4DS_TERMINOLOGY_PROVIDER``,
    ``FHIR4DS_VSAC_API_KEY``/``UMLS_API_KEY``) remain the zero-config path;
    the toml section is the workspace-persistent form.
    """
    if not path.exists():
        return {}
    if tomllib is None:  # pragma: no cover
        raise DevConfigError(
            "fhir4ds.toml parsing requires Python 3.11+ (tomllib) or tomli"
        )
    try:
        with open(path, "rb") as fh:
            doc = tomllib.load(fh)
    except Exception as exc:
        raise DevConfigError(f"Invalid TOML in {path}: {exc}") from exc
    section = doc.get("terminology")
    if section is None:
        return {}
    if not isinstance(section, dict):
        raise DevConfigError("fhir4ds.toml [terminology] must be a table")
    unknown = set(section) - _TERMINOLOGY_KEYS
    if unknown:
        raise DevConfigError(
            f"fhir4ds.toml [terminology] has unknown keys {sorted(unknown)}; "
            f"allowed: {sorted(_TERMINOLOGY_KEYS)}"
        )
    out: dict[str, object] = {}
    if "provider" in section:
        provider = section["provider"]
        if not isinstance(provider, str) or provider not in _TERMINOLOGY_PROVIDERS:
            raise DevConfigError(
                f"fhir4ds.toml [terminology].provider must be one of "
                f"{sorted(_TERMINOLOGY_PROVIDERS)}; got {provider!r}"
            )
        out["provider"] = provider
    if "base_url" in section:
        base_url = section["base_url"]
        if not isinstance(base_url, str) or not base_url.strip():
            raise DevConfigError(
                "fhir4ds.toml [terminology].base_url must be a non-empty string"
            )
        out["base_url"] = base_url.strip()
    if "timeout_seconds" in section:
        timeout = section["timeout_seconds"]
        if not isinstance(timeout, (int, float)) or not timeout > 0:
            raise DevConfigError(
                "fhir4ds.toml [terminology].timeout_seconds must be a positive number"
            )
        out["timeout_seconds"] = float(timeout)
    if "api_key_env" in section:
        api_key_env = section["api_key_env"]
        if not isinstance(api_key_env, str) or not api_key_env.strip():
            raise DevConfigError(
                "fhir4ds.toml [terminology].api_key_env must be a non-empty string"
            )
        out["api_key_env"] = api_key_env.strip()
    return out


def terminology_settings(cfg: DevServerConfig) -> TerminologySettings:
    """Resolve effective terminology settings: toml [terminology] first,
    then env-var overrides (``FHIR4DS_TERMINOLOGY_PROVIDER`` /
    ``FHIR4DS_TERMINOLOGY_URL``), matching the merge doctrine.

    The API key itself never transits this function.
    """
    import os

    manifest = _parse_terminology_manifest(cfg.root / "fhir4ds.toml")
    settings = TerminologySettings(**manifest)  # type: ignore[arg-type]
    env_provider = os.environ.get("FHIR4DS_TERMINOLOGY_PROVIDER")
    if env_provider:
        if env_provider not in _TERMINOLOGY_PROVIDERS:
            raise DevConfigError(
                f"FHIR4DS_TERMINOLOGY_PROVIDER must be one of "
                f"{sorted(_TERMINOLOGY_PROVIDERS)}; got {env_provider!r}"
            )
        settings.provider = env_provider
    env_url = os.environ.get("FHIR4DS_TERMINOLOGY_URL")
    if env_url:
        settings.base_url = env_url
    return settings
