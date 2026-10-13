"""maint/spec-comp-20261012b — SKEPTIC probe: discovery/scan_workspace +
config loading under adversarial input. Fresh evidence only (prior runs
quarantined).

Focus: scan_workspace resilience (unreadable CQL, BOM, huge files, name
extraction edge cases) and DevServerConfig parse boundary (unknown keys,
malformed lists, path normalization).
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/mnt/d/fhir4ds-maint-spec-comp-20261012b")
from fhir4ds.devserver.discovery import scan_workspace, _library_name
from fhir4ds.devserver.config import DevServerConfig, load_config

findings = []
tmp = Path(tempfile.mkdtemp(prefix="disc-"))


def scan(ws):
    return scan_workspace(load_config(str(ws)))


# 1. library-name extraction edge cases
cases = [
    ("library MyLib version '1.0'\ndefine X: 1\n", "MyLib"),
    ("// lead comment\nlibrary C2\n", "C2"),
    ("/* block */\nlibrary C3\n", "C3"),
    ("libraryname NotLib\n", "stem-only"),  # no 'library ' prefix -> stem path
]
for text, want in cases:
    p = tmp / "probe_cql" / "x"
    p.mkdir(parents=True, exist_ok=True)
    f = p / f"{want.replace('-', '_')}.cql"
    f.write_text(text, encoding="utf-8")
    got = _library_name(text, f)
    print(f"D1 {want!r}: got={got!r}")
    if want != "stem-only" and got != want:
        findings.append(("QA-001", f"name extract {want}", got))

# 2. BOM-prefixed CQL file parses (utf-8-sig doctrine)
p = tmp / "bom" / "cql"
p.mkdir(parents=True, exist_ok=True)
(p / "BomLib.cql").write_text("library BomLib\ndefine X: 1\n", encoding="utf-8-sig")
snap = scan(tmp / "bom")
lib = next((l for l in snap.libraries if l.name == "BomLib"), None)
ok = lib is not None and lib.parse_ok
print(f"D2 BOM cql: parsed={ok}")
if not ok:
    findings.append(("QA-002", "BOM cql failed", lib.error if lib else "missing"))

# 3. unreadable CQL file -> parse_ok False with error, never crash
p = tmp / "unreadable" / "cql"
p.mkdir(parents=True, exist_ok=True)
(p / "Bad.cql").write_bytes(b"\xff\xfe\x00bad\x00")
try:
    snap = scan(tmp / "unreadable")
    lib = next((l for l in snap.libraries if l.name == "Bad"), None)
    ok = lib is not None and not lib.parse_ok and lib.error
    print(f"D3 unreadable: degraded_ok={ok}")
    if not ok:
        findings.append(("QA-003", "unreadable cql crash/no-error", None))
except Exception as e:
    print(f"D3 unreadable: CRASH {type(e).__name__}")
    findings.append(("QA-003", "unreadable cql crash", type(e).__name__))

# 4. deeply nested cql dirs (rglob) discovered
p = tmp / "deep" / "cql" / "a" / "b" / "c"
p.mkdir(parents=True, exist_ok=True)
(p / "DeepLib.cql").write_text("library DeepLib\ndefine X: 1\n", encoding="utf-8")
snap = scan(tmp / "deep")
ok = any(l.name == "DeepLib" for l in snap.libraries)
print(f"D4 nested discovery: {ok}")
if not ok:
    findings.append(("QA-004", "nested cql not found", None))

# 5. config: default workspace (no toml) loads with defaults
cfg = load_config(str(tmp / "empty"))
ok = cfg is not None and cfg.root == Path(str(tmp / "empty")).resolve()
print(f"D5 default config: {ok}")
if not ok:
    findings.append(("QA-005", "default config", None))

# 6. config: [dev] manifest add-path round-trips via the _LIST_FIELDS keys
wtoml = tmp / "wpaths"
(wtoml / "cql").mkdir(parents=True, exist_ok=True)
(wtoml / "fhir4ds.toml").write_text(
    "[dev]\nmanifest = [\"cql\"]\n[dev.manifest_map]\ncql_dirs = [\"cql\"]\n",
    encoding="utf-8") if False else (wtoml / "fhir4ds.toml").write_text(
    "[dev]\ncql_dirs = [\"cql\"]\n", encoding="utf-8")
cfg = load_config(str(wtoml))
ok = "cql" in [str(d) for d in cfg.cql_dirs] or any("cql" in str(d) for d in cfg.cql_dirs)
print(f"D6 toml list field: {ok} dirs={[str(d) for d in cfg.cql_dirs]}")
if not ok:
    findings.append(("QA-006", "cql_dirs from toml", [str(d) for d in cfg.cql_dirs]))

# 7. discovery sandbox: scan does NOT follow into sibling dirs
sib = tmp / "sibling"
(sib / "cql").mkdir(parents=True, exist_ok=True)
(sib / "outside.cql").write_text("library Outside\ndefine X: 1\n", encoding="utf-8")
(sib / "inner").mkdir(exist_ok=True)
(sib / "inner" / "In.cql").write_text("library In\ndefine X: 1\n", encoding="utf-8")
snap = scan(sib)  # default cql_dirs=["cql"]: ONLY cql/ subtree is scanned
names = {l.name for l in snap.libraries}
ok = "In" not in names and "Outside" not in names  # unconfigured dirs absent
print(f"D7 sandbox: unconfigured dirs absent={ok} names={sorted(names)}")
if not ok:
    findings.append(("QA-009", "sandbox escape", sorted(names)))

# 8. case-insensitive suffix matching (2026-10 doctrine)
p = tmp / "case" / "cql"
p.mkdir(parents=True, exist_ok=True)
(p / "UpLib.CQL").write_text("library UpLib\ndefine X: 1\n", encoding="utf-8")
snap = scan(tmp / "case")
ok = any(l.name == "UpLib" for l in snap.libraries)
print(f"D8 uppercase .CQL: {ok}")
if not ok:
    findings.append(("QA-007", "uppercase suffix missed", None))

# 9. valueset/measure/view json discovery excludes expected/ subtree (S3b doctrine)
p = tmp / "exp" / "measures" / "expected" / "patients" / "M"
p.mkdir(parents=True, exist_ok=True)
(p / "p1.json").write_text('{"resourceType": "MeasureReport"}', encoding="utf-8")
(tmp / "exp" / "measures" / "real.json").write_text('{"resourceType": "Measure"}', encoding="utf-8")
snap = scan(tmp / "exp")
measures = [str(m) for m in snap.measures]
ok = any(m.endswith("real.json") for m in measures) and not any("expected" in m for m in measures)
print(f"D9 expected/ excluded: {ok} measures={measures}")
if not ok:
    findings.append(("QA-008", "expected/ leaked into measures", measures))

print("\nFINDINGS:", len(findings))
for f in findings:
    print("  ", f)
sys.exit(0 if not findings else 2)
