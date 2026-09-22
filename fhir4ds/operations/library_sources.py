"""Library resolution chain (FDD §3.3.1).

Includes resolve: inline ``libraries[]`` → bundled standards via
``importlib.resources`` → adapter extras → typed NOT_FOUND. Explicit
beats implicit: an inline LibraryText always wins over a bundled
library of the same name.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib import resources as importlib_resources

from fhir4ds.cql.parser import parse_cql

from .envelopes import LibraryText
from .errors import not_found

_BUNDLED_ANCHOR = "fhir4ds.cql.resources.cql"

# Parse cache keyed by resource name (process lifetime).
_BUNDLED_CACHE: dict[str, object] = {}
# Names available in the wheel's resources/cql directory (verified via
# importlib.resources iterdir; kept static so the bundled tier never
# depends on filesystem listing at runtime).
_BUNDLED_NAMES: list[str] = ["FHIRHelpers", "QICoreCommon", "Status"]


def bundled_library_names() -> list[str]:
    """Standard libraries shipped in the wheel (FHIRHelpers et al.)."""
    return list(_BUNDLED_NAMES)


def _load_bundled(name: str) -> object | None:
    if name in _BUNDLED_CACHE:
        return _BUNDLED_CACHE[name]
    try:
        text = (
            importlib_resources.files(_BUNDLED_ANCHOR)
            .joinpath(f"{name}.cql")
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        return None
    library = parse_cql(text)
    _BUNDLED_CACHE[name] = library
    return library


class LibraryResolver:
    """Resolve a library alias through the §3.3.1 chain.

    ``extra_loaders`` are adapter-specific sources (CLI --include-dir,
    MCP session cache) consulted AFTER the bundled tier.
    """

    def __init__(
        self,
        inline: list[LibraryText] | None = None,
        extra_loaders: list[Callable[[str], object | None]] | None = None,
    ) -> None:
        self._inline: dict[str, LibraryText] = {lib.name: lib for lib in (inline or [])}
        self._inline_cache: dict[str, object] = {}
        self._extra_loaders = list(extra_loaders or [])
        self.consulted: list[str] = []

    def resolve(self, alias: str) -> object | None:
        """Return a parsed Library for ``alias`` or None (caller emits NOT_FOUND)."""
        self.consulted = []
        # Tier 1: inline (explicit beats implicit).
        lib = self._inline.get(alias)
        if lib is not None:
            self.consulted.append(f"inline:{alias}")
            if alias not in self._inline_cache:
                self._inline_cache[alias] = parse_cql(lib.text)
            return self._inline_cache[alias]
        # Tier 2: bundled standards.
        if alias in _BUNDLED_NAMES:
            library = _load_bundled(alias)
            if library is not None:
                self.consulted.append(f"bundled:{alias}")
                return library
        # Tier 3: adapter extras.
        for loader in self._extra_loaders:
            library = loader(alias)
            if library is not None:
                self.consulted.append(f"adapter:{alias}")
                return library
        return None

    def unresolved_diagnostic(self, alias: str, path: str | None = None):
        tiers = ["inline libraries[]", "bundled standards ("
                 + ", ".join(_BUNDLED_NAMES) + ")", "adapter sources"]
        name = f"{path or alias}" + (f" (alias '{alias}')" if path and path != alias else "")
        return not_found(
            f"Could not resolve included library '{name}'.",
            detail=f"tiers consulted: {'; '.join(tiers)}",
        )
