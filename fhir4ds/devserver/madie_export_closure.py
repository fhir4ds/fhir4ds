"""S22d-2 (§5): closure-driven MADiE export from the FHIR-type workspace.

``export_measure_closure_zip(root, measure_key)`` builds the measure-
scoped package: the Measure resource, its CQL include-graph closure
(from ``Library/``), the closure's referenced ValueSets, the
``List/TestCases.json``-referenced patient folders (single patient
store — patients NOT in the List are NOT exported), and the expected
MeasureReports (MADiE trailing-entry form). Cleanroom extras stay under
``resources/extras/`` (S18 layout).
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from .workspace_types import FHIR_TYPE_FOLDERS, list_patient_ids, read_resource

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
        for m in re.finditer(
            r"valueset\s+\"?([A-Za-z0-9_]+)\"?\s*:\s*'?([^'\"\s]+)", text
        ):
            url = m.group(2).rstrip("',")
            if url.startswith(("http://", "https://", "urn:")):
                urls.add(url)
    return urls


def _measure_dir(root: Path, measure_key: str) -> Path | None:
    measure_root = root / "Measure"
    if not measure_root.is_dir():
        return None
    for child in sorted(measure_root.iterdir()):
        if not child.is_dir():
            continue
        if child.name == measure_key:
            return child
        measure_files = list((child / "Measure").glob("*.json"))
        for mf in measure_files:
            resource = read_resource(mf)
            if resource is None:
                continue
            name = resource.get("name") or resource.get("id")
            if name == measure_key:
                return child
    return None


def export_measure_closure_zip(root: Path, measure_key: str) -> bytes:
    """Build the closure-driven MADiE package zip (bytes).

    Raises LookupError when the measure is unknown.
    """
    root = Path(root)
    mdir = _measure_dir(root, measure_key)
    if mdir is None:
        raise LookupError(f"unknown measure {measure_key!r}")

    measure_files = sorted((mdir / "Measure").glob("*.json"))
    measure = read_resource(measure_files[0]) if measure_files else None
    if measure is None:
        raise LookupError(f"measure {measure_key!r} has no readable Measure resource")

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

    # -- List-referenced patients (single store) ----------------------------
    list_path = mdir / "List" / "TestCases.json"
    list_resource = read_resource(list_path) if list_path.is_file() else None
    test_patients = list_patient_ids(list_resource)

    # -- Expected MeasureReports --------------------------------------------
    expected: list[dict] = []
    mr_dir = mdir / "MeasureReport"
    if mr_dir.is_dir():
        for path in sorted(mr_dir.glob("*.json")):
            resource = read_resource(path)
            if resource is not None:
                expected.append(resource)

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
        zf.writestr(
            f"resources/measure-{measure_name}-{measure_version}.json",
            json.dumps(measure, indent=2),
        )
        # Test-case patients: one bundle per patient (patient resources +
        # clinical), expected MR as the MADiE trailing entry.
        patient_root = root / "Patient"
        for pid in test_patients:
            pdir = patient_root / pid
            if not pdir.is_dir():
                continue
            entries: list[dict] = []
            for path in sorted(pdir.rglob("*.json")):
                resource = read_resource(path)
                if resource is not None:
                    entries.append({"resource": resource})
            zf.writestr(
                f"testcase/patient-{pid}/{pid}.json",
                json.dumps(
                    {
                        "resourceType": "Bundle",
                        "type": "collection",
                        "entry": entries,
                    },
                    indent=2,
                ),
            )
            mr = next(
                (r for r in expected if _mr_subject(r) == pid),
                None,
            )
            if mr is not None:
                zf.writestr(
                    f"testcase/patient-{pid}/{pid}-expected.json",
                    json.dumps(mr, indent=2),
                )
        # Unmatched expected reports still ride along (extras).
        matched = {_mr_subject(r) for r in expected}
        for i, mr in enumerate(expected):
            if _mr_subject(mr) in matched and _mr_subject(mr) in test_patients:
                continue
            zf.writestr(
                f"resources/extras/expected-measurereport-{i + 1}.json",
                json.dumps(mr, indent=2),
            )
    return buf.getvalue()


def _mr_subject(report: dict) -> str | None:
    subject = report.get("subject")
    if isinstance(subject, dict):
        ref = subject.get("reference")
        if isinstance(ref, str) and ref.startswith("Patient/"):
            return ref[len("Patient/"):]
    return None
