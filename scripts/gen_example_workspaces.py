#!/usr/bin/env python3
"""S26: generate the cleanroom example WORKSPACES from repo fixtures.

Reproducible + idempotent: emits canonical-layout workspaces under
examples/ from the licensed eCQM fixtures (read-only). See
fhir4ds-private/docs/prompts/.ai_loop/state/s26_workspace_zip_contract.md
for the agreed contract (items 10/11).

Usage:
    python3 scripts/gen_example_workspaces.py            # cms125 + cms69
    python3 scripts/gen_example_workspaces.py --zip      # + MADiE-style zips
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ECQM = REPO / "tests/data/ecqm-content-qicore-2025"
DQM = REPO / "tests/data/dqm-content-qicore-2026"
VALUESETS = REPO / "tests/data/valuesets"
EXAMPLES = REPO / "examples"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return  # idempotent: byte-identical files are untouched
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, obj: dict) -> None:
    _write(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


import re


def _cql_valueset_refs(ws: Path) -> set[str]:
    """Canonical ValueSet URLs declared by `valueset` statements in the
    workspace's copied CQL. The MAT Library dataRequirements UNDERREPORT
    (e.g. CMS125 v0.4.000 omits the mastectomy 1133/1134 sets the CQL
    retrieves), so declarations are the authoritative superset."""
    refs: set[str] = set()
    pat = re.compile(r"^\s*valueset\s+\"[^\"]+\"\s*:\s*'([^']+)'", re.MULTILINE)
    for cql in sorted((ws / "Library").glob("*.cql")):
        refs.update(pat.findall(cql.read_text(encoding="utf-8")))
    return refs


def _valueset_refs(bundle: dict) -> set[str]:
    """Canonical ValueSet URLs referenced by a MAT bundle's Libraries."""
    refs: set[str] = set()
    for entry in bundle.get("entry", []):
        res = entry.get("resource", {})
        if res.get("resourceType") != "Library":
            continue
        for dr in res.get("dataRequirement", []) or []:
            for cf in dr.get("codeFilter", []) or []:
                url = cf.get("valueSet")
                if url:
                    refs.add(url)
    return refs


def _copy_valuesets(refs: set[str], ws: Path) -> list[str]:
    """Copy each referenced VS from tests/data/valuesets by URL tail."""
    by_tail: dict[str, Path] = {}
    for f in sorted(VALUESETS.glob("*.json")):
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        url = obj.get("url")
        if isinstance(url, str) and url:
            by_tail[url.rsplit("/", 1)[-1]] = f
    copied = []
    for ref in sorted(refs):
        tail = ref.rsplit("/", 1)[-1]
        src = by_tail.get(tail)
        if src is None:
            continue  # unreferenced-by-name VS: skip, translation reports it
        obj = json.loads(src.read_text(encoding="utf-8"))
        vid = obj.get("id") or tail
        _write_json(ws / "ValueSet" / f"{vid}.json", obj)
        copied.append(vid)
    return copied


def _namespace_case_resources(resources: list[dict], case_id: str) -> list[dict]:
    """MADiE cases reuse resource ids ACROSS cases (same Encounter id,
    different subject) — designed for one-case-per-kernel evaluation.
    Loading every case into ONE shared resources table would collide
    (last-write-wins drops a case's encounter). Namespacing: every
    non-Patient resource id gains a ``<case>--`` prefix and every
    Reference to it is rewritten. Patient ids stay verbatim (they are
    the case identity the expected MeasureReports + Tests drawer key
    on, and are already unique)."""

    def _rewrite_refs(node, mapping):
        if isinstance(node, dict):
            out = {}
            for k, v in node.items():
                if k == "reference" and isinstance(v, str) and v in mapping:
                    out[k] = mapping[v]
                else:
                    out[k] = _rewrite_refs(v, mapping)
            return out
        if isinstance(node, list):
            return [_rewrite_refs(x, mapping) for x in node]
        return node

    mapping: dict[str, str] = {}
    # FHIR ids cap at 64 chars; case names + uuids overflow. Use a short
    # stable digest of the case id as the namespace prefix (deterministic
    # across runs; collision odds across a measure's cases are nil).
    import hashlib

    tag = hashlib.sha1(case_id.encode()).hexdigest()[:8]
    for res in resources:
        rt = res.get("resourceType")
        rid = res.get("id")
        if not rt or not rid or rt == "Patient":
            continue
        new_id = f"{tag}-{rid}"[:64]
        mapping[f"{rt}/{rid}"] = f"{rt}/{new_id}"
        mapping[f"#{rid}"] = f"#{new_id}"  # contained/logical refs
        res["id"] = new_id
    return [_rewrite_refs(res, mapping) for res in resources]


def _emit_measurement_period_parameters(ws: Path) -> None:
    """Workspace Parameters resource supplying "Measurement Period" —
    the devserver's parameter-defaults source (_workspace_parameter_defaults).
    Calendar year 2026 matches the 2025 official CMS125 test cases, so
    connected boot/heartbeat/cell runs succeed with zero UI input."""
    _write_json(
        ws / "Patient" / "Parameters-MeasurementPeriod.json",
        {
            "resourceType": "Parameters",
            "id": "measurement-period-default",
            "parameter": [
                {
                    "name": "Measurement Period",
                    "valuePeriod": {
                        "start": "2026-01-01",
                        "end": "2026-12-31",
                    },
                }
            ],
        },
    )


def _flatten_2025_case(bundle: dict, case_id: str) -> tuple[list[dict], dict | None]:
    """One tests-*-bundle.json from the 2025 MAT measure-files set →
    (case resources, expected MeasureReport). Entries ride BOTH at the
    top level and inside a nested MADiE Bundle (duplicate Patient/
    Encounter/Condition + the trailing expected MR) — dedupe by
    (resourceType, id), nested entries win (they carry the fullUrls)."""
    mr: dict | None = None
    by_key: dict[tuple[str, str], dict] = {}
    for entry in bundle.get("entry", []):
        res = entry.get("resource", {}) if isinstance(entry, dict) else {}
        rt = res.get("resourceType")
        if not rt:
            continue
        if rt == "MeasureReport":
            mr = res
            continue
        if rt == "Bundle":
            for inner in res.get("entry", []):
                ires = inner.get("resource", {}) if isinstance(inner, dict) else {}
                irt = ires.get("resourceType")
                if not irt or irt == "MeasureReport":
                    continue
                by_key[(irt, str(ires.get("id") or ""))] = ires
            continue
        by_key.setdefault((rt, str(res.get("id") or "")), res)
    return list(by_key.values()), mr


def _reset_generated(ws: Path) -> None:
    """Idempotent regeneration: clear every GENERATED subtree so stale
    content from an earlier source cannot survive a re-run. The hand-kept
    _attic/ archive is never touched."""
    for sub in ("Library", "ValueSet", "ViewDefinition", "Patient", "MeasureReport"):
        shutil.rmtree(ws / sub, ignore_errors=True)
    shutil.rmtree(ws / "Measure" / "expected", ignore_errors=True)
    for f in (ws / "Measure").glob("*.json") if (ws / "Measure").is_dir() else []:
        f.unlink()


def build_cms125() -> Path:
    mat = ECQM / "bundles/mat/CMS125FHIR-R2-MeasureExport"
    ws = EXAMPLES / "cms125-workspace"
    _reset_generated(ws)
    # The synthetic content moved to _attic during S22e; a re-run keeps it.
    # 1) Libraries: the MAT cql/ text files, stem = library name.
    for cql in sorted((mat / "cql").glob("*.cql")):
        _write(ws / "Library" / f"{cql.stem.split('-')[0]}.cql", cql.read_text(encoding="utf-8"))
    # 2) Valuesets: every canonical VS referenced by the bundle.
    bundle = json.loads((mat / "CMS125FHIR-v0.4.000-FHIR.json").read_text(encoding="utf-8"))
    _copy_valuesets(_valueset_refs(bundle) | _cql_valueset_refs(ws), ws)
    # 3) Measure: the MAT Measure resource.
    measure = json.loads((mat / "Measure-CMS125FHIRBreastCancerScreening.json").read_text(encoding="utf-8"))
    _write_json(ws / "Measure" / "CMS125FHIRBreastCancerScreening.json", measure)
    # 4) Patients + expected results: the 2025 official test bundles
    #    (tests-*-bundle.json — one case each, trailing expected MR),
    #    plus the S9 synthetic set (reference data from the attic).
    mfiles = ECQM / "bundles/measure/CMS125FHIRBreastCancerScreening/CMS125FHIRBreastCancerScreening-files"
    n_cases = 0
    for tb in sorted(mfiles.glob("tests-*-bundle.json")):
        b = json.loads(tb.read_text(encoding="utf-8"))
        # MAT test files are tests-<uuid>-bundle.json; the -bundle suffix
        # is a FILE artifact, not part of the case id (expected-MR subjects
        # and Patient resource ids are the bare uuid).
        case_id = tb.stem[len("tests-"):].removesuffix("-bundle")
        case_res, expected_mr = _flatten_2025_case(b, case_id)
        if expected_mr is None:
            continue  # not a test-case bundle (no expected MR)
        case_res = _namespace_case_resources(case_res, case_id)
        for res in case_res:
            rt = res.get("resourceType")
            rid = res.get("id") or f"{rt}-{case_id}"
            _write_json(ws / "Patient" / case_id / f"{rt}-{rid}.json", res)
        _write_json(
            ws / "MeasureReport" / "CMS125FHIRBreastCancerScreening" / f"{case_id}.json",
            expected_mr,
        )
        n_cases += 1
    if n_cases == 0:
        raise SystemExit("cms125: no 2025 test cases found")
    _emit_measure_report_view(ws)
    _emit_measurement_period_parameters(ws)
    return ws


def build_cms69() -> Path:
    ws = EXAMPLES / "cms69-workspace"
    _reset_generated(ws)
    files = ECQM / "bundles/measure/CMS69FHIRPCSBMIScreenAndFollowUp/CMS69FHIRPCSBMIScreenAndFollowUp-files"
    # 1) Library: the human-authored CQL from the measure bundle.
    cql = files / "CMS69FHIRPCSBMIScreenAndFollowUp.cql"
    _write(ws / "Library" / "CMS69FHIRPCSBMIScreenAndFollowUp.cql", cql.read_text(encoding="utf-8"))
    # Include closure from the repo's shared cql tree (same versions the
    # conformance fixtures use).
    shared = ECQM / "input/cql"
    for name in ("FHIRHelpers", "QICoreCommon", "Status", "Hospice",
                 "AdultOutpatientEncounters", "SupplementalDataElements",
                 "AHAOverall", "CumulativeMedicationDuration",
                 "AdvancedIllnessandFrailty"):
        src = shared / f"{name}.cql"
        if src.exists():
            _write(ws / "Library" / f"{name}.cql", src.read_text(encoding="utf-8"))
    # 2) Valuesets referenced by the measure bundle.
    bundle = json.loads(
        (files / "library-deps-CMS69FHIRPCSBMIScreenAndFollowUp-bundle.json").read_text(
            encoding="utf-8"
        )
    )
    _copy_valuesets(_valueset_refs(bundle) | _cql_valueset_refs(ws), ws)
    # 2b) The dedicated valuesets bundle carries the full expansion set —
    # but only for ids NOT already covered (two sources for one id with
    # different bytes would break idempotency; the expansion bundle wins
    # ONLY when the ref-copy didn't already place the file).
    vs_bundle = json.loads(
        (files / "valuesets-CMS69FHIRPCSBMIScreenAndFollowUp-bundle.json").read_text(
            encoding="utf-8"
        )
    )
    for entry in vs_bundle.get("entry", []):
        res = entry.get("resource", {})
        if res.get("resourceType") == "ValueSet":
            vid = res.get("id") or res.get("url", "").rsplit("/", 1)[-1]
            out = ws / "ValueSet" / f"{vid}.json"
            if out.exists():
                continue
            _write_json(out, res)
    # 3) Measure resource: the MAT MeasureExport zip carries the real
    #    Measure (the measure-bundle-files dir's <Name>.json is a
    #    LIBRARY resource — misnamed file, not a Measure).
    mat69 = zipfile.ZipFile(
        ECQM / "bundles/mat/CMS69/CMS69FHIR-R1-MeasureExport.zip"
    )
    measure = None
    for n in sorted(mat69.namelist()):
        if not n.endswith(".json"):
            continue
        try:
            d = json.loads(mat69.read(n))
        except json.JSONDecodeError:
            continue
        if d.get("resourceType") == "Measure":
            measure = d
            break
    if measure is not None:
        _write_json(ws / "Measure" / "CMS69FHIRPCSBMIScreenAndFollowUp.json", measure)
    # 4) Patients + expected results: the 60 MADiE test bundles (one
    # patient each: Patient id == bundle uuid tail; MeasureReport is
    # the fixture-official expected result). Non-Patient ids are
    # namespaced per case (same collision class as the DQM cases).
    for tb in sorted(files.glob("tests-*-bundle.json")):
        bundle = json.loads(tb.read_text(encoding="utf-8"))
        # MAT test files are tests-<uuid>-bundle.json; the -bundle suffix
        # is a FILE artifact, not part of the case id (expected-MR subjects
        # and Patient resource ids are the bare uuid).
        case_id = tb.stem[len("tests-"):].removesuffix("-bundle")
        mr = None
        case_res: list[dict] = []
        for entry in bundle.get("entry", []):
            res = entry.get("resource", {})
            rt = res.get("resourceType")
            if not rt:
                continue
            if rt == "MeasureReport":
                mr = res
                continue
            if rt == "Bundle":
                continue  # inner bundles not needed for patient-context eval
            case_res.append(res)
        case_res = _namespace_case_resources(case_res, case_id)
        for res in case_res:
            rt = res.get("resourceType")
            rid = res.get("id") or f"{rt}-{case_id}"
            _write_json(ws / "Patient" / case_id / f"{rt}-{rid}.json", res)
        if mr is not None:
            _write_json(
                ws / "MeasureReport" / "CMS69FHIRPCSBMIScreenAndFollowUp" / f"{case_id}.json",
                mr,
            )
    _emit_measure_report_view(ws)
    _emit_measurement_period_parameters(ws)
    return ws


def _emit_measure_report_view(ws: Path) -> None:
    """S26 (slice 3): the MeasureReport ViewDefinition showcase — the
    same wide-format shape the app's buildDerivedView derives, shipped
    as a disk file so the nav Views section lists it in connected mode.

    S26 review fix: paths match the MADiE MeasureReport shape — the
    group carries NO code (each population does), and the patient rides
    contained[Parameters].parameter[name=subject] (fixture-official
    reports have no subject.reference)."""
    _write_json(
        ws / "ViewDefinition" / "MeasureReportPopulations.json",
        {
            # S26 review fix: the canonical root resourceType (the parser
            # accepts absent OR the canonical URL — the bare string
            # "ViewDefinition" is a ParseError; SOF-VD-01 doctrine).
            "resourceType": "https://sql-on-fhir.org/ig/StructureDefinition/ViewDefinition",
            "name": "MeasureReportPopulations",
            # S30: authored artifact declares its version — the nav shows
            # a version pill for ViewDefinitions like libraries/valuesets.
            "version": "1.0.0",
            "resource": "MeasureReport",
            "select": [
                {
                    "column": [
                        {
                            "name": "patient_id",
                            "path": "%resource.contained.where(resourceType='Parameters').parameter.where(name='subject').valueString",
                            "type": "string",
                        },
                        {
                            "name": "initial_population",
                            "path": "group.population.where(code.coding.code='initial-population').count",
                            "type": "integer",
                        },
                        {
                            "name": "denominator",
                            "path": "group.population.where(code.coding.code='denominator').count",
                            "type": "integer",
                        },
                        {
                            "name": "denominator_exclusion",
                            "path": "group.population.where(code.coding.code='denominator-exclusion').count",
                            "type": "integer",
                        },
                        {
                            "name": "numerator",
                            "path": "group.population.where(code.coding.code='numerator').count",
                            "type": "integer",
                        },
                    ]
                }
            ],
        },
    )


def build_zips() -> None:
    """MADiE-layout zips from each workspace — loadable by the EXISTING
    cleanroom MADiE loader (cql/, resources/measure-*, resources/
    library-*, resources/valueset-*, tests/<case>/)."""
    import base64

    def _lib_name(text: str) -> str | None:
        import re

        m = re.match(r"\s*library\s+([A-Za-z][A-Za-z0-9_]*)", text, re.M)
        return m.group(1) if m else None

    def _lib_version(text: str) -> str:
        import re

        m = re.match(
            r"\s*library\s+[A-Za-z][A-Za-z0-9_]*\s+version\s+'([^']+)'", text, re.M
        )
        return m.group(1) if m else "1.0.0"

    for ws in sorted(EXAMPLES.glob("*-workspace")):
        if ws.name == "demo-workspace":
            continue  # demo ships in-repo only (zip adds nothing)
        zpath = REPO / "web/cql-cleanroom/public/examples" / f"{ws.stem}.zip"
        zpath.parent.mkdir(parents=True, exist_ok=True)
        files: dict[str, str] = {}
        main_lib = None
        for cql in sorted((ws / "Library").glob("*.cql")):
            text = cql.read_text(encoding="utf-8")
            name = _lib_name(text) or cql.stem
            if main_lib is None and "cms" in name.lower():
                main_lib = name
            files[f"cql/{name}-{_lib_version(text)}.cql"] = text
            files[f"resources/library-{name}-{_lib_version(text)}.json"] = (
                json.dumps(
                    {
                        "resourceType": "Library",
                        "name": name,
                        "version": _lib_version(text),
                        "status": "draft",
                        "type": {
                            "coding": [
                                {
                                    "system": "http://terminology.hl7.org/CodeSystem/library-type",
                                    "code": "logic-library",
                                }
                            ]
                        },
                        "content": [
                            {"contentType": "text/cql", "data": base64.b64encode(text.encode()).decode()}
                        ],
                    },
                    indent=2,
                )
            )
        for vs in sorted((ws / "ValueSet").glob("*.json")):
            obj = json.loads(vs.read_text(encoding="utf-8"))
            vid = obj.get("id") or vs.stem
            files[f"resources/valueset-{vid}.json"] = json.dumps(obj, indent=2)
        for msr in sorted((ws / "Measure").glob("*.json")):
            obj = json.loads(msr.read_text(encoding="utf-8"))
            mname = obj.get("id") or msr.stem
            # The autozip's Measure MUST carry library[0] = the primary
            # library (the loader's main-first ordering key). CMS69's
            # MAT Measure lacks library[] (relatedArtifact-only) —
            # synthesize primary-first from the workspace's CMS* lib.
            if not isinstance(obj.get("library"), list) or not obj["library"]:
                if main_lib:
                    obj["library"] = [main_lib]
            files[f"resources/measure-{mname}-{obj.get('version', '1.0.0')}.json"] = (
                json.dumps(obj, indent=2)
            )
        # S32: ship the workspace ViewDefinitions as cleanroom extras so
        # a WASM package load shows the SAME views as the dev server
        # (resources/extras/view-*.json — docs/madie-package-layout.md).
        for vd in sorted((ws / "ViewDefinition").glob("*.json")):
            files[f"resources/extras/view-{vd.stem}.json"] = vd.read_text(
                encoding="utf-8"
            )
        # S32: expected MeasureReports too (resources/extras/
        # expected-measurereport-*.json) — without them the standalone
        # Expected compare has no authored expectations.
        for mr in sorted((ws / "MeasureReport").glob("*/*.json")):
            files[f"resources/extras/expected-measurereport-{mr.stem}.json"] = (
                mr.read_text(encoding="utf-8")
            )
        for case in sorted((ws / "Patient").iterdir() if (ws / "Patient").is_dir() else []):
            if not case.is_dir():
                continue
            for f in sorted(case.glob("*.json")):
                rel = f"tests/{case.name}/{f.name}"
                files[rel] = f.read_text(encoding="utf-8")
            # MADiE trailing entry: the case's EXPECTED MeasureReport
            # (workspace MeasureReport/<measure>/<case>.json) rides in the
            # same test folder — docs/madie-package-layout.md rule 4.
            for mr_file in sorted((ws / "MeasureReport").glob(f"*/{case.name}.json")):
                files[f"tests/{case.name}/MeasureReport-{case.name}.json"] = (
                    mr_file.read_text(encoding="utf-8")
                )
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in sorted(files):
                zf.writestr(name, files[name])
        print(f"zip: {zpath}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", action="store_true", help="also emit MADiE-style zips")
    args = ap.parse_args()
    for name, fn in (("cms125", build_cms125), ("cms69", build_cms69)):
        ws = fn()
        print(f"built {name}: {ws}")
    if args.zip:
        build_zips()
        print("zips built")
    return 0


if __name__ == "__main__":
    sys.exit(main())
