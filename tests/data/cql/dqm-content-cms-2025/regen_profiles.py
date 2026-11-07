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


def parse_modelinfo(path: Path) -> dict:
    root = ET.parse(path).getroot()
    out = {}
    for ti in root.iter(f"{NS}typeInfo"):
        if ti.get("retrievable") != "true":
            continue
        target = ti.get("target")
        name = ti.get("name")
        if not target or not name:
            continue
        out[name] = {
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
