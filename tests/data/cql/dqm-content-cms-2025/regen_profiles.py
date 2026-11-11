#!/usr/bin/env python3
"""Regenerate uscore-usqualitycore-profiles.json from the dqm-content-cms-2025
modelinfo sources.

Sources (see README.md in this directory):
  - USQualityCore 0.1.0-cibuild modelinfo: tests/data/dqm-content-cms-2025/input/cql/
    usqualitycore-modelinfo-0.1.0-cibuild.xml (ships in the submodule)
  - USCore 6.1.0-derived modelinfo: uscore-modelinfo-6.1.0-derived.xml in this
    directory (vendored from HL7/us-cql-ig@2.0.0-ballot, commit fb23fc7bca47)

Run from the repo root:
    python3 tests/data/cql/dqm-content-cms-2025/regen_profiles.py
"""
import json
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
NS = "{urn:hl7-org:elm-modelinfo:r1}"
OUT = REPO / "fhir4ds/cql/resources/profiles/uscore-usqualitycore-profiles.json"


# Retrievable typeInfos that omit `target` but MUST still be registered so
# their retrieves get a meta.profile membership test. Keep this list tiny and
# justified: registering such a profile switches on the filter for that
# retrieve, which is only safe when the fixtures reliably declare the
# canonical. (Counter-example: registering all 42 missing-target profiles
# drops CMS177 100% -> 97.6%, because its Encounters carry no meta.profile.)
_MISSING_TARGET_ALLOWLIST = {
    ("USQualityCore", "MedicationRequest"),
}


def parse_modelinfo(path: Path) -> dict:
    """Collect retrievable typeInfos that carry an explicit ``target``.

    Profiles WITHOUT a ``target`` attribute are deliberately EXCLUDED, and this
    is load-bearing rather than incidental: 38 USQualityCore and 4 USCore
    profiles omit it (e.g. ``USQualityCore.Encounter``, ``USQualityCore.Coverage``),
    and registering them switches on a ``meta.profile`` membership test for
    those retrieves. Measured 2026-11-11: adding all 42 (base_type derived from
    the typeInfo name) drops CMS177 from 100% to 97.6%, because that measure's
    fixtures carry Encounters with no ``meta.profile`` at all — they are visible
    today precisely because these profiles stay unfiltered.

    Do not "complete" this list without re-running ``--suite cms2025`` and
    ``--suite 2025``; the filtered-profile set is an empirically tuned boundary,
    not a mechanical transform of the modelinfo.
    """
    root = ET.parse(path).getroot()
    out = {}
    for ti in root.iter(f"{NS}typeInfo"):
        if ti.get("retrievable") != "true":
            continue
        target = ti.get("target")
        name = ti.get("name")
        if not name:
            continue
        if not target:
            # Allowlisted profiles derive their base type from the typeInfo
            # name itself (the modelinfo omits `target` when it would repeat
            # the name, e.g. USQualityCore.MedicationRequest).
            if (ti.get("namespace", ""), name) not in _MISSING_TARGET_ALLOWLIST:
                continue
            target = name
        key = name
        if ti.get("target") is None:
            # Namespace-qualify allowlisted entries so the key states which
            # model declared it (e.g. USQualityCoreMedicationRequest).
            key = f"{ti.get('namespace', '')}{name}"

        out[key] = {
            "base_type": target,
            "url": ti.get("identifier") or "",
            "meta_profile_filter": True,
            "namespace": ti.get("namespace", ""),
            "label": ti.get("label") or "",
        }
    return out


def main() -> None:
    usq = parse_modelinfo(
        REPO / "tests/data/dqm-content-cms-2025/input/cql/"
        "usqualitycore-modelinfo-0.1.0-cibuild.xml"
    )
    usc = parse_modelinfo(HERE / "uscore-modelinfo-6.1.0-derived.xml")
    merged = dict(usc)
    merged.update(usq)
    doc = {
        "_comment": (
            "GENERATED from USQualityCore 0.1.0-cibuild modelinfo (dqm-content-cms-2025 "
            "submodule, input/cql/usqualitycore-modelinfo-0.1.0-cibuild.xml) and USCore "
            "6.1.0-derived modelinfo (vendored at tests/data/cql/dqm-content-cms-2025/"
            "uscore-modelinfo-6.1.0-derived.xml from HL7/us-cql-ig@2.0.0-ballot, commit "
            "fb23fc7bca47). Regenerate with tests/data/cql/dqm-content-cms-2025/"
            "regen_profiles.py."
        ),
        "named_profiles": merged,
    }
    OUT.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"USCore: {len(usc)}  USQualityCore: {len(usq)}  merged: {len(merged)} -> {OUT}")


if __name__ == "__main__":
    main()
