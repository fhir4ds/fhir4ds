"""S22d-2 (§5): closure-driven MADiE export from the workspace.

``export_measure_closure_zip(root, measure_key)`` builds the measure-
scoped package: the Measure resource, its CQL include-graph closure
(from ``Library/``), the closure's referenced ValueSets, the test-case
patients, and the expected MeasureReports (MADiE trailing-entry form).

Layouts (canonical-first, legacy fallback):
* Measure: flat ``Measure/<key>.json`` (id or name == key) — canonical
  type-folder workspaces — or legacy ``Measure/<key>/Measure/*.json``.
* Expected MeasureReports: ``MeasureReport/<key>/<caseId>.json`` —
  canonical expected store — or legacy ``Measure/<key>/MeasureReport/``.
* Test-case patients: the expected store's subjects define the case set
  (one ``Patient/<caseId>/`` folder each). A legacy ``List/TestCases.json``
  registry, when present, still gates membership. With NEITHER (no
  expected store, no List), every ``Patient/`` folder ships — the
  workspace IS the test set for the demo workspaces.

Zip layout: ``docs/madie-package-layout.md`` (cql/, resources/, tests/
<caseId>/ with the expected MR as the trailing ``MeasureReport-*.json``
entry). Cleanroom extras ride under ``resources/extras/``.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from .expected_store import patient_from_report
from .workspace_types import list_patient_ids, read_resource

_CQL_INCLUDE_RE = None  # compiled lazily


def _include_names(text: str) -> list[str]:
    import re

    global _CQL_INCLUDE_RE
    if _CQL_INCLUDE_RE is None:
        _CQL_INCLUDE_RE = re.compile(r"include\s+([A-Za-z][A-Za-z0-9_]*)")
    return [m.group(1) for m in _CQL_INCLUDE_RE.finditer(text)]


def _declared_valueset_urls(texts: list[str]) -> set[str]:
    import re

    urls: set[str] = set()
    for text in texts:
        # valueset "Quoted Name With Spaces": 'url' | valueset Bare: 'url'
        for m in re.finditer(
            r"valueset\s+(?:\"[^\"]+\"|[A-Za-z0-9_]+)\s*:\s*'?([^'\"\s]+)",
            text,
        ):
            url = m.group(1).rstrip("',")
            if url.startswith(("http://", "https://", "urn:")):
                urls.add(url)
    return urls


def _resolve_measure(root: Path, measure_key: str) -> dict | None:
    """The Measure resource for ``measure_key``.

    Canonical: ``Measure/<key>.json`` (file stem, resource id, or name ==
    key). Legacy: folder-per-measure ``Measure/<key>/Measure/*.json``.
    """
    measure_root = root / "Measure"
    if not measure_root.is_dir():
        return None
    # Canonical flat files first: stem == key.
    direct = measure_root / f"{measure_key}.json"
    if direct.is_file():
        resource = read_resource(direct)
        if resource is not None:
            return resource
    for path in sorted(measure_root.glob("*.json")):
        resource = read_resource(path)
        if resource is None:
            continue
        if resource.get("id") == measure_key or resource.get("name") == measure_key:
            return resource
    # Legacy folder-per-measure.
    for child in sorted(measure_root.iterdir()):
        if not child.is_dir():
            continue
        for mf in sorted((child / "Measure").glob("*.json")):
            resource = read_resource(mf)
            if resource is None:
                continue
            name = resource.get("name") or resource.get("id")
            if child.name == measure_key or name == measure_key:
                return resource
    return None


def _expected_reports(root: Path, measure_key: str) -> list[dict]:
    """Expected MeasureReports: canonical ``MeasureReport/<key>/`` first,
    legacy ``Measure/<key>/MeasureReport/`` fallback."""
    for mr_dir in (
        root / "MeasureReport" / measure_key,
        root / "Measure" / measure_key / "MeasureReport",
    ):
        if mr_dir.is_dir():
            out = []
            for path in sorted(mr_dir.glob("*.json")):
                resource = read_resource(path)
                if resource is not None:
                    out.append(resource)
            if out:
                return out
    return []


def export_measure_closure_zip(root: Path, measure_key: str) -> bytes:
    """Build the closure-driven MADiE package zip (bytes).

    Raises LookupError when the measure is unknown.
    """
    root = Path(root)
    measure = _resolve_measure(root, measure_key)
    if measure is None:
        raise LookupError(f"unknown measure {measure_key!r}")

    # -- CQL closure from the shared Library/ layer ------------------------
    library_dir = root / "Library"
    cql_by_name: dict[str, tuple[str, str]] = {}  # name -> (version, text)
    if library_dir.is_dir():
        for path in sorted(library_dir.glob("*.cql")):
            try:
                text = path.read_text(encoding="utf-8-sig")
            except OSError:
                continue
            name = version = None
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("library "):
                    tokens = stripped.split()
                    if len(tokens) >= 2:
                        name = tokens[1]
                        if len(tokens) >= 4 and tokens[2] == "version":
                            version = tokens[3].strip("'\"")
                    break
            if name:
                cql_by_name[name] = (version or "1.0.0", text)

    # The measure names its primary library (urn or plain name).
    primary = None
    lib_refs = measure.get("library")
    if isinstance(lib_refs, list) and lib_refs:
        ref = str(lib_refs[0])
        primary = ref.rsplit(":", 1)[-1]
    elif isinstance(lib_refs, str):
        primary = lib_refs.rsplit(":", 1)[-1]

    closure: list[tuple[str, str, str]] = []  # (name, version, text)
    seen: set[str] = set()
    queue = [primary] if primary and primary in cql_by_name else []
    if not queue:
        # Fall back: a library whose name matches the measure key.
        queue = [measure_key] if measure_key in cql_by_name else []
    while queue:
        name = queue.pop(0)
        if name in seen:
            continue
        seen.add(name)
        version, text = cql_by_name[name]
        closure.append((name, version, text))
        for dep in _include_names(text):
            if dep not in seen and dep in cql_by_name:
                queue.append(dep)

    # -- ValueSets referenced by the closure -------------------------------
    referenced = _declared_valueset_urls([text for _, _, text in closure])
    valuesets: list[tuple[str, dict]] = []
    vs_dir = root / "ValueSet"
    if vs_dir.is_dir():
        for path in sorted(vs_dir.glob("*.json")):
            resource = read_resource(path)
            if resource is None:
                continue
            url = resource.get("url")
            if isinstance(url, str) and url in referenced:
                vid = resource.get("id") or path.stem
                valuesets.append((str(vid), resource))

    # -- Expected MeasureReports (canonical store first) --------------------
    expected = _expected_reports(root, measure_key)

    # -- Test-case membership ----------------------------------------------
    # A legacy List registry, when present, still gates membership.
    list_path = root / "Measure" / measure_key / "List" / "TestCases.json"
    list_resource = read_resource(list_path) if list_path.is_file() else None
    if list_resource is not None:
        test_patients = list_patient_ids(list_resource)
    elif expected:
        # The expected store names its cases: one Patient/ folder each.
        test_patients = sorted(
            {pid for pid in (patient_from_report(r) for r in expected) if pid}
        )
    else:
        # No expected store, no List: the whole Patient/ store ships.
        patient_root = root / "Patient"
        test_patients = (
            sorted(p.name for p in patient_root.iterdir() if p.is_dir())
            if patient_root.is_dir()
            else []
        )

    # Case folders may be named by case id OR by patient id (the 2025
    # MAT bundles name folders "<uuid>-bundle" while the expected MR
    # subject is the bare "<uuid>"). Resolve each subject to its folder
    # by the folder's Patient resource id — never by folder name alone.
    patient_root = root / "Patient"

    def _case_dir(pid: str) -> Path | None:
        direct = patient_root / pid
        if direct.is_dir():
            return direct
        if not patient_root.is_dir():
            return None
        for pdir in sorted(patient_root.iterdir()):
            if not pdir.is_dir():
                continue
            for pf in sorted(pdir.glob("Patient-*.json")):
                res = read_resource(pf)
                if res is not None and res.get("id") == pid:
                    return pdir
        return None

    # -- Build the zip -------------------------------------------------------
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, version, text in closure:
            zf.writestr(f"cql/{name}-{version}.cql", text)
            zf.writestr(
                f"resources/library-{name}-{version}.json",
                json.dumps(
                    {
                        "resourceType": "Library",
                        "name": name,
                        "version": version,
                        "status": "draft",
                        "type": {
                            "coding": [
                                {
                                    "system": "http://terminology.hl7.org/CodeSystem/library-type",
                                    "code": "logic-library",
                                }
                            ]
                        },
                        "content": [{"contentType": "text/cql", "data": text}],
                    },
                    indent=2,
                ),
            )
        for vid, resource in valuesets:
            zf.writestr(
                f"resources/valueset-{vid}.json", json.dumps(resource, indent=2)
            )
        measure_version = str(measure.get("version") or "1.0.0")
        measure_name = str(measure.get("name") or measure_key)
        # The Measure MUST carry library[0] = the primary (loader main-first
        # ordering key) — synthesize when the workspace Measure lacks it.
        if not isinstance(measure.get("library"), list) or not measure["library"]:
            if primary:
                measure = {**measure, "library": [primary]}
        zf.writestr(
            f"resources/measure-{measure_name}-{measure_version}.json",
            json.dumps(measure, indent=2),
        )
        # Test-case patients: resources + clinical, expected MR as the
        # MADiE trailing entry (tests/<caseId>/MeasureReport-<caseId>.json).
        patient_root = root / "Patient"
        shipped: set[str] = set()
        for case_id in test_patients:
            pdir = patient_root / case_id
            if not pdir.is_dir():
                continue
            shipped.add(case_id)
            for path in sorted(pdir.rglob("*.json")):
                resource = read_resource(path)
                if resource is None:
                    continue
                rt = resource.get("resourceType") or "Resource"
                rid = resource.get("id") or path.stem
                zf.writestr(
                    f"tests/{case_id}/{rt}-{rid}.json",
                    json.dumps(resource, indent=2),
                )
            mr = next(
                (r for r in expected if patient_from_report(r) == case_id),
                None,
            )
            if mr is not None:
                zf.writestr(
                    f"tests/{case_id}/MeasureReport-{case_id}.json",
                    json.dumps(mr, indent=2),
                )
        # Expected reports with no matching Patient folder ride as extras.
        for i, mr in enumerate(expected):
            pid = patient_from_report(mr)
            if pid and pid in shipped:
                continue
            zf.writestr(
                f"resources/extras/expected-measurereport-{i + 1}.json",
                json.dumps(mr, indent=2),
            )
    return buf.getvalue()
