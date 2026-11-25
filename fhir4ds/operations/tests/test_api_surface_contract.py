"""Domain 11 — public API surface contract freeze.

Pins, as executable contract:
1. every public package's ``__all__`` names are importable (``from pkg import *``
   never breaks) — including the v0.0.26 packages ``fhir4ds.piqi`` and
   ``fhir4ds.realism`` (QA-D11S-001: they were missing from the freeze, the
   same guard class that caught the shipped LOCATION_APPROVAL_THRESHOLD bug);
2. ``__version__`` is uniform across the public packages;
3. the cross-package import graph stays one-way (viewdef/fhirpath never import
   the layers above them);
4. PEP 562 lazy packages (serve, dqm) surface their lazy names in ``dir()``.
"""
import ast
import importlib
import importlib.util
from pathlib import Path

import pytest


def _not_installed(*modules: str) -> list[str]:
    """Modules of an optional extra that this environment does not have."""
    return [name for name in modules if importlib.util.find_spec(name) is None]


# Two public packages resolve their names through an optional extra:
# ``fhir4ds.serve`` needs ``[serve]`` (``fhir4ds/serve/app.py`` guards the same
# imports) and ``fhir4ds.dqm`` needs ``[measures]`` (pandas). CI installs both
# extras, so the contract is enforced there; a local run without one skips with
# the reason instead of failing on the environment.
_SERVE_MISSING = _not_installed("fastapi", "uvicorn")
_MEASURES_MISSING = _not_installed("pandas")


def _needs(extra: str, missing: list[str]):
    return pytest.mark.skipif(
        bool(missing), reason=f"optional extra {extra!r} is not installed here"
    )


# package -> mark for the packages resolved through an optional extra
_OPTIONAL_EXTRA_MARKS = {
    "fhir4ds.dqm": _needs("measures", _MEASURES_MISSING),
    "fhir4ds.serve": _needs("serve", _SERVE_MISSING),
}

PUBLIC_PACKAGES = [
    "fhir4ds",
    "fhir4ds.cql",
    "fhir4ds.dqm",
    "fhir4ds.serve",
    "fhir4ds.sqlquery",
    "fhir4ds.operations",
    "fhir4ds.matching",
    "fhir4ds.dedup",
    "fhir4ds.piqi",
    "fhir4ds.realism",
    "fhir4ds.viewdef",
    "fhir4ds.fhirpath",
]

# (subpackage dir, modules it must never import)
ONE_WAY_RULES = [
    ("viewdef", ["fhir4ds.sqlquery", "fhir4ds.cql", "fhir4ds.dqm", "fhir4ds.serve"]),
    ("fhirpath", ["fhir4ds.cql", "fhir4ds.dqm", "fhir4ds.serve", "fhir4ds.viewdef"]),
    ("sqlquery", ["fhir4ds.dqm", "fhir4ds.serve"]),
    ("operations", ["fhir4ds.serve"]),
]


@pytest.mark.parametrize(
    "pkg",
    [
        pytest.param(p, marks=_OPTIONAL_EXTRA_MARKS[p]) if p in _OPTIONAL_EXTRA_MARKS else p
        for p in PUBLIC_PACKAGES
    ],
)
def test_all_names_importable(pkg):
    m = importlib.import_module(pkg)
    names = getattr(m, "__all__", None)
    assert names, f"{pkg} has no __all__"
    missing = [n for n in names if not hasattr(m, n)]
    assert not missing, f"{pkg}.__all__ has unimportable names: {missing}"


def test_version_uniform_across_public_packages():
    versions = {
        pkg: getattr(importlib.import_module(pkg), "__version__", None)
        for pkg in PUBLIC_PACKAGES
    }
    assert len(set(versions.values())) == 1, versions


def _module_imports(path: Path):
    tree = ast.parse(path.read_text())
    mods = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            mods.append(node.module)
        elif isinstance(node, ast.Import):
            mods.extend(a.name for a in node.names)
    return mods


def test_import_graph_one_way():
    import fhir4ds

    root = Path(fhir4ds.__file__).parent
    violations = []
    for subdir, forbidden in ONE_WAY_RULES:
        for path in (root / subdir).rglob("*.py"):
            mods = _module_imports(path)
            for forb in forbidden:
                if any(m == forb or m.startswith(forb + ".") for m in mods):
                    violations.append((path.relative_to(root), forb))
    assert not violations, f"one-way import rules broken: {violations}"


@pytest.mark.parametrize("pkg", ["fhir4ds.serve", "fhir4ds.dqm"])
def test_lazy_dir_surfaces_all(pkg):
    m = importlib.import_module(pkg)
    d = dir(m)
    missing = [n for n in getattr(m, "__all__", []) if n not in d]
    assert not missing, f"dir({pkg}) is missing lazy names: {missing}"
