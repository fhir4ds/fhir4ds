"""MADiE package importers (c-cleanroom-ux5 item 4).

Two importers, grounded in the §0 research (cloned sources under
``.temp/qa/ux5/madie_sources_snapshot/``):

* **Package ZIP** (``POST /api/madie/import-package``): the exported
  measure bundle ``<Title>-v<ver>-FHIR.json`` at the zip root plus
  ``cql/<Lib>-<ver>.cql`` and ``resources/*.json|.xml``. We extract the
  human-readable CQL into ``cql/<lib>.cql``, valuesets (bundle compose or
  resource entries) into ``valuesets/<id>.json``, and the Measure
  resource into ``measures/<name>.json``.

* **Test-case ZIP** (``POST /api/madie/import-tests``): MADiE lays out
  ``<patientId>/<EcqmTitle>-v<ver>[-Series]-<Title>.json`` — one Bundle
  per test case whose TRAILING entry is the expected MeasureReport
  carrying the ``cqfm-test-cases`` profile / ``isTestCases`` modifier
  extension (TestCaseBundleService sets only the modifierExtension form
  — verified against the cloned sources). The importer strips that
  trailing entry into the item-3 expected store (keyed by patient) and
  writes the patient bundle to ``data/<patientId>/<case>.json``.

Both importers write through plain files + publish a watcher 'changed'
event; discovery picks the new files up on the next rescan (data dirs are
scanned recursively, so ``data/<patientId>/*.json`` needs no manifest
change when the data root is already configured).
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any

IS_TEST_CASES_URL = (
    "http://hl7.org/fhir/us/cqf-measures/StructureDefinition/"
    "cqfm-isTestCases"
)
CQFM_TEST_CASES_PROFILE = "cqfm-test-cases"

_CQL_FILENAME_RE = re.compile(r"^(?P<lib>[A-Za-z][A-Za-z0-9_]*)[-_]v?\d")


def is_expected_measure_report(resource: Any) -> bool:
    """True when a resource is a MADiE expected-results MeasureReport.

    Matches BOTH markers MADiE/our own store may carry: the
    ``cqfm-isTestCases`` modifier extension or a ``cqfm-test-cases``
    profile in ``meta.profile``. Mirrors the defensive guard in
    ``operations/dataset_ops.py`` (keep the two in lockstep).
    """
    if not isinstance(resource, dict):
        return False
    if resource.get("resourceType") != "MeasureReport":
        return False
    for ext in resource.get("modifierExtension") or []:
        url = ext.get("url", "") if isinstance(ext, dict) else ""
        if isinstance(url, str) and url.rstrip("/").endswith("cqfm-isTestCases"):
            return True
    meta = resource.get("meta") or {}
    for profile in (meta.get("profile") or []) if isinstance(meta, dict) else []:
        if isinstance(profile, str) and CQFM_TEST_CASES_PROFILE in profile:
            return True
    return False


def _load_json_bytes(data: bytes) -> Any:
    return json.loads(data.decode("utf-8-sig"))


def _safe_stem(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.\-]", "_", name).strip("._")
    return stem or "imported"


def _write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _publish_changed(server: Any, paths: list[str]) -> None:
    publish = getattr(server.watcher, "publish_changed", None)
    if publish is not None:
        publish(paths)


# ---------------------------------------------------------------------------
# Package ZIP import
# ---------------------------------------------------------------------------


def import_package_zip(
    server: Any, zip_bytes: bytes, *, target: str = ""
) -> dict[str, Any]:
    """Import a MADiE measure package ZIP into the workspace.

    Returns a summary dict (never raises for content problems — errors
    are reported in ``diagnostics`` so the API can envelope them).
    """
    diagnostics: list[dict[str, str]] = []
    written: dict[str, list[str]] = {"cql": [], "valuesets": [], "measures": []}
    cfg = getattr(server.watcher, "_cfg", None)
    if cfg is None:
        return {"ok": False, "diagnostics": [{"code": "INPUT_ERROR",
                "message": "workspace config unavailable"}]}

    root = Path(cfg.root)
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except (zipfile.BadZipFile, OSError) as exc:
        return {"ok": False, "diagnostics": [{"code": "INPUT_ERROR",
                "message": f"not a valid zip: {exc}"}]}

    cql_texts: dict[str, str] = {}
    valuesets: dict[str, dict] = {}
    measures: list[dict] = []
    bundle_valuesets: dict[str, dict] = {}

    with zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            base = name.rsplit("/", 1)[-1]
            lower = base.lower()
            try:
                data = zf.read(name)
            except OSError as exc:
                diagnostics.append({"code": "ZIP_READ",
                                    "message": f"skipped {name}: {exc}"})
                continue

            if "/" in name and name.split("/", 1)[0].lower() == "cql" and lower.endswith(".cql"):
                m = _CQL_FILENAME_RE.match(base)
                lib = m.group("lib") if m else base[:-4]
                cql_texts[_safe_stem(lib)] = data.decode("utf-8-sig")
            elif lower.endswith(".json"):
                try:
                    payload = _load_json_bytes(data)
                except (ValueError, UnicodeDecodeError):
                    diagnostics.append({"code": "ZIP_CONTENT",
                                        "message": f"skipped non-JSON {name}"})
                    continue
                rt = payload.get("resourceType") if isinstance(payload, dict) else None
                if rt == "Bundle":
                    _harvest_bundle(payload, measures, bundle_valuesets)
                elif rt == "Measure":
                    measures.append(payload)
                elif rt == "ValueSet":
                    vid = payload.get("id") or payload.get("url") or "valueset"
                    valuesets[_safe_stem(str(vid))] = payload
            # .xml/.html entries are skipped: MADiE always ships .json twins.

    if not (cql_texts or measures or valuesets or bundle_valuesets):
        return {"ok": False, "diagnostics": diagnostics or [
            {"code": "INPUT_ERROR", "message":
             "no importable content found (expected a MADiE package zip with "
             "cql/*.cql, a *-FHIR.json bundle, or resources/*.json)"}]}

    changed: list[str] = []
    for stem, text in sorted(cql_texts.items()):
        dest = root / "cql" / f"{stem}.cql"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        written["cql"].append(str(dest.relative_to(root)))
        changed.append(str(dest))
    merged_vs = {**valuesets, **bundle_valuesets}
    for stem, payload in sorted(merged_vs.items()):
        dest = root / "valuesets" / f"{stem}.json"
        _write_json_file(dest, payload)
        written["valuesets"].append(str(dest.relative_to(root)))
        changed.append(str(dest))
    for i, measure in enumerate(measures):
        mname = measure.get("name") or measure.get("id") or f"measure-{i + 1}"
        dest = root / "measures" / f"{_safe_stem(str(mname))}.json"
        _write_json_file(dest, measure)
        written["measures"].append(str(dest.relative_to(root)))
        changed.append(str(dest))

    if changed:
        _publish_changed(server, changed)
    return {
        "ok": True,
        "written": written,
        "counts": {k: len(v) for k, v in written.items()},
        "diagnostics": diagnostics,
    }


def _harvest_bundle(
    bundle: dict,
    measures: list[dict],
    valuesets: dict[str, dict],
) -> None:
    for entry in bundle.get("entry") or []:
        res = entry.get("resource") if isinstance(entry, dict) else None
        if not isinstance(res, dict):
            continue
        rt = res.get("resourceType")
        if rt == "Measure":
            measures.append(res)
        elif rt == "ValueSet":
            vid = res.get("id") or res.get("url") or "valueset"
            valuesets[_safe_stem(str(vid))] = res


# ---------------------------------------------------------------------------
# Test-case ZIP import
# ---------------------------------------------------------------------------


def import_tests_zip(
    server: Any,
    zip_bytes: bytes,
    *,
    measure_name: str = "",
) -> dict[str, Any]:
    """Import a MADiE test-case ZIP into data/ + the expected store.

    Layout: ``<patientId>/<case>.json`` Bundle per test; the TRAILING
    entry is the expected MeasureReport (isTestCases-marked). The
    expectation lands in the item-3 store via
    ``expected_store.save_expected_report``; the remaining patient
    bundle is written to ``data/<patientId>/<case>.json``.
    """
    from .expected_store import save_expected_report

    diagnostics: list[dict[str, str]] = []
    written_cases: list[str] = []
    expected_written: list[str] = []
    cfg = getattr(server.watcher, "_cfg", None)
    if cfg is None:
        return {"ok": False, "diagnostics": [{"code": "INPUT_ERROR",
                "message": "workspace config unavailable"}]}
    root = Path(cfg.root)

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except (zipfile.BadZipFile, OSError) as exc:
        return {"ok": False, "diagnostics": [{"code": "INPUT_ERROR",
                "message": f"not a valid zip: {exc}"}]}

    changed: list[str] = []
    with zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            if not name.lower().endswith(".json"):
                continue
            try:
                bundle = _load_json_bytes(zf.read(name))
            except (ValueError, UnicodeDecodeError, OSError) as exc:
                diagnostics.append({"code": "ZIP_CONTENT",
                                    "message": f"skipped {name}: {exc}"})
                continue
            if not isinstance(bundle, dict) or bundle.get("resourceType") != "Bundle":
                diagnostics.append({"code": "ZIP_CONTENT",
                                    "message": f"skipped {name}: not a Bundle"})
                continue

            entries = [e for e in (bundle.get("entry") or []) if isinstance(e, dict)]
            trailing = entries[-1].get("resource") if entries else None
            expected: dict | None = (
                trailing if is_expected_measure_report(trailing) else None
            )
            if expected is None:
                diagnostics.append(
                    {"code": "NO_EXPECTATION", "message":
                     f"{name}: no trailing isTestCases MeasureReport — "
                     "imported as a plain patient bundle (no expectation)"}
                )
                patient_entries = entries
            else:
                patient_entries = entries[:-1]

            # Patient id: from the expected MR subject, else from the first
            # Patient resource in the bundle, else the top folder name.
            pid: str | None = None
            if expected is not None:
                subject = ((expected.get("subject") or {}).get("reference") or "")
                pid = subject.rsplit("/", 1)[-1] if "/" in subject else None
            if not pid:
                for e in patient_entries:
                    res = e.get("resource") or {}
                    if res.get("resourceType") == "Patient":
                        pid = str(res.get("id") or "") or None
                        break
            folder = name.split("/", 1)[0] if "/" in name else ""
            pid = pid or folder or "patient"

            case_stem = _safe_stem(Path(name).stem or "case")
            patient_bundle = {**bundle, "entry": patient_entries}
            dest = root / "data" / _safe_stem(pid) / f"{case_stem}.json"
            _write_json_file(dest, patient_bundle)
            written_cases.append(str(dest.relative_to(root)))
            changed.append(str(dest))

            if expected is not None:
                raw_m = str(
                    (expected.get("measure") or "").rsplit("/", 1)[-1]
                    or "ImportedMeasure"
                )
                mname = measure_name or raw_m.split("|", 1)[0] or "ImportedMeasure"
                from .expected_store import patient_from_report

                stamped = expected
                if (patient_from_report(stamped) or "") != pid:
                    stamped = {**stamped, "subject": {"reference": f"Patient/{pid}"}}
                out = save_expected_report(
                    Path(root) / "measures" / "expected", mname, stamped
                )
                expected_written.append(str(out.relative_to(root)))
                changed.append(str(out))

    if not written_cases:
        summary = {"code": "INPUT_ERROR", "message":
            "no test-case bundles found (expected <patientId>/<case>.json "
            "Bundle entries)"}
        return {"ok": False, "diagnostics": [summary] + diagnostics}
    if changed:
        _publish_changed(server, changed)
    return {
        "ok": True,
        "cases": written_cases,
        "expected": expected_written,
        "counts": {"cases": len(written_cases), "expected": len(expected_written)},
        "diagnostics": diagnostics,
    }
