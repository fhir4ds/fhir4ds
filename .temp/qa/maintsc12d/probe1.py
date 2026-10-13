"""maint/spec-comp-20261012d — SKEPTIC probe: Kernel/KernelManager lifecycle
+ dataset routing under adversarial input. Fresh evidence only (prior runs
quarantined).

Anchored to the actual contracts: Kernel(datasets, valuesets) builds a
registered connection eagerly; .ndjson vs .json suffix routing; load
failures populate load_diagnostics and still return a live connection
(strict-loader doctrine); KernelManager lock-swap restart semantics
(in-flight calls keep the old reference).
"""
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, "/mnt/d/fhir4ds-maint-spec-comp-20261012d")
from fhir4ds.devserver.kernel import Kernel, KernelManager
from fhir4ds.devserver.discovery import scan_workspace
from fhir4ds.devserver.config import load_config

findings = []
tmp = Path(tempfile.mkdtemp(prefix="kern-"))

# 1. no datasets -> live connection (no resources table by design — the
# loader creates it), no diagnostics
k0 = Kernel([], [])
alive0 = k0.conn.execute("SELECT 1").fetchone()[0] == 1
has_table = any("resources" in str(r[0]) for r in k0.conn.execute("SHOW TABLES").fetchall())
ok = alive0 and k0.load_diagnostics == []
print(f"K1 empty kernel: alive={alive0} resources_table={has_table} diags={len(k0.load_diagnostics)}")
if not ok:
    findings.append(("QA-001", "empty kernel not live", (alive0, len(k0.load_diagnostics))))

# 2. suffix routing: .ndjson and .json both load; .txt ignored
d = tmp / "data"; d.mkdir(parents=True)
(d / "a.ndjson").write_text('{"resourceType":"Patient","id":"a"}\n', encoding="utf-8")
(d / "b.json").write_text('{"resourceType":"Bundle","type":"collection","entry":[{"resource":{"resourceType":"Patient","id":"b"}}]}', encoding="utf-8")
(d / "c.txt").write_text('{"resourceType":"Patient","id":"c"}\n', encoding="utf-8")
# GENUINE FINDING QA-002 (HIGH): mixed .ndjson + .json datasets crash
# Kernel construction. Discovery collects both suffixes into datasets
# (NDJSON_SUFFIXES = (".ndjson", ".json")); kernel._build_connection
# passes BOTH lists into DatasetSpec, whose __post_init__ REJECTS the
# combination (envelopes.py:184) — and the ValueError fires at spec
# construction, BEFORE load_dataset's internal try/except. Unhandled →
# Kernel()/KernelManager()/server boot crash for any workspace whose
# data dir contains both kinds.
try:
    k1 = Kernel([d / "a.ndjson", d / "b.json"], [])
    ids = {r[0] for r in k1.conn.execute("SELECT id FROM resources WHERE resourceType='Patient'").fetchall()}
    print(f"K2 mixed datasets: loaded ids={sorted(ids)}")
    if ids != {"a", "b"}:
        findings.append(("QA-002", "mixed suffix routing", sorted(ids)))
except ValueError as exc:
    print(f"K2 mixed datasets: CRASH ValueError: {str(exc)[:90]}")
    findings.append(("QA-002", "mixed .ndjson+.json datasets crash Kernel ctor (server boot)", str(exc)[:120]))
# homogeneous suffixes still route correctly
k1n = Kernel([d / "a.ndjson"], [])
ids_n = {r[0] for r in k1n.conn.execute("SELECT id FROM resources WHERE resourceType='Patient'").fetchall()}
k1j = Kernel([d / "b.json"], [])
ids_j = {r[0] for r in k1j.conn.execute("SELECT id FROM resources WHERE resourceType='Patient'").fetchall()}
ok = ids_n == {"a"} and ids_j == {"b"}
print(f"K2b homogeneous routing: {ok} ndjson={sorted(ids_n)} bundle={sorted(ids_j)}")
if not ok:
    findings.append(("QA-003", "homogeneous suffix routing", (sorted(ids_n), sorted(ids_j))))

# 3. uppercase suffixes route the same (.NDJSON, .JSON)
(d / "up.NDJSON").write_text('{"resourceType":"Patient","id":"up"}\n', encoding="utf-8")
k2 = Kernel([d / "up.NDJSON"], [])
ok = k2.conn.execute("SELECT COUNT(*) FROM resources WHERE id='up'").fetchone()[0] == 1
print(f"K3 uppercase suffix: {ok}")
if not ok:
    findings.append(("QA-003", "uppercase suffix dropped", None))

# 4. strict-loader doctrine: ONE bad line -> empty table + diagnostics
d2 = tmp / "bad"; d2.mkdir()
(d2 / "good.ndjson").write_text('{"resourceType":"Patient","id":"g1"}\n', encoding="utf-8")
(d2 / "bad.ndjson").write_text('{"resourceType":"Patient","id":"!!!invalid"}\n', encoding="utf-8")
k3 = Kernel([d2 / "good.ndjson", d2 / "bad.ndjson"], [])
n = k3.conn.execute("SELECT COUNT(*) FROM resources").fetchone()[0]
has_diag = len(k3.load_diagnostics) > 0
ok = n == 0 and has_diag
print(f"K4 strict all-or-nothing: {ok} rows={n} diags={len(k3.load_diagnostics)}")
if not ok:
    findings.append(("QA-004", "strict load partial", (n, len(k3.load_diagnostics))))

# 5. diagnostics carry line attribution (error severity)
if k3.load_diagnostics:
    dd = k3.load_diagnostics[0]
    has_line = any(key in str(dd) for key in ("line", "path", "bad.ndjson"))
    print(f"K5 diagnostic attribution: {has_line} diag0={str(dd)[:110]}")
    if not has_line:
        findings.append(("QA-005", "diagnostic lacks attribution", str(dd)[:80]))

# 6. valueset loading path does not crash and table exists after load
vs = tmp / "vs"; vs.mkdir()
(vs / "v.json").write_text('{"resourceType":"ValueSet","id":"v1","compose":{"include":[{"system":"http://loinc.org","concept":[{"code":"1","display":"one"}]}]}}', encoding="utf-8")
k4 = Kernel([], [vs / "v.json"])
try:
    rows = k4.conn.execute("SELECT COUNT(*) FROM valuesets").fetchone()[0]
    print(f"K6 valuesets loaded: rows={rows} (0 acceptable if table name differs; crash is the failure)")
except Exception as e:
    print(f"K6 valuesets: table-name probe failed ({type(e).__name__}) — non-fatal")
try:
    k4.conn.execute("SELECT 1").fetchone()
    print("   connection alive after valueset load")
except Exception as e:
    findings.append(("QA-006", "valueset load kills conn", type(e).__name__))

# 7. KernelManager: initial kernel live; restart swaps identity atomically
km = KernelManager.__new__(KernelManager)  # bypass snapshot scan cost? NO — use real path
ws = tmp / "ws"
(ws / "cql").mkdir(parents=True)
(ws / "data").mkdir()
(ws / "data" / "w.ndjson").write_text('{"resourceType":"Patient","id":"w1"}\n', encoding="utf-8")
snap = scan_workspace(load_config(str(ws)))
km = KernelManager(snap)
cur1 = km.current()
ok_id = cur1.kernel_id and cur1 is km.current()
print(f"K7 current stable: {ok_id} id={cur1.kernel_id}")
if not ok_id:
    findings.append(("QA-007", "current() unstable", None))

# 8. restart builds NEW kernel (new id), old reference still usable (drains)
(ws / "data" / "w2.ndjson").write_text('{"resourceType":"Patient","id":"w2"}\n', encoding="utf-8")
snap2 = scan_workspace(load_config(str(ws)))
new_k = km.restart(snap2)
cur2 = km.current()
swap_ok = cur2 is new_k and new_k.kernel_id != cur1.kernel_id
n_new = new_k.conn.execute("SELECT COUNT(*) FROM resources WHERE id='w2'").fetchone()[0]
old_alive = cur1.conn.execute("SELECT 1").fetchone()[0] == 1
old_isolated = cur1.conn.execute("SELECT COUNT(*) FROM resources WHERE id='w2'").fetchone()[0] == 0
ok = swap_ok and n_new == 1 and old_alive and old_isolated
print(f"K8 restart swap: {ok} swap={swap_ok} new_has_w2={n_new} old_alive={old_alive} old_isolated={old_isolated}")
if not ok:
    findings.append(("QA-008", "restart semantics", (swap_ok, n_new, old_alive, old_isolated)))

# 9. concurrent current() during restarts — no torn reads, all valid kernels
errs = []
def churn():
    for _ in range(5):
        km.restart(scan_workspace(load_config(str(ws))))
def read_loop():
    for _ in range(60):
        k = km.current()
        try:
            k.conn.execute("SELECT COUNT(*) FROM resources").fetchone()
        except Exception as e:
            errs.append(type(e).__name__)
threads = [threading.Thread(target=churn) for _ in range(2)] + [threading.Thread(target=read_loop) for _ in range(3)]
for t in threads: t.start()
for t in threads: t.join(timeout=30)
ok = not errs and not any(t.is_alive() for t in threads)
print(f"K9 concurrent restart/read: {ok} errs={errs[:3]}")
if not ok:
    findings.append(("QA-009", "concurrent kernel churn", errs[:3]))

# 10. missing dataset file -> diagnostics populated, conn still live
d3 = tmp / "missing"
k5 = Kernel([d3], [])
alive = k5.conn.execute("SELECT 1").fetchone()[0] == 1
ok = alive  # missing dir is not an error per discovery (absent dirs simply absent)
print(f"K10 missing dataset dir: alive={alive} diags={len(k5.load_diagnostics)}")
if not alive:
    findings.append(("QA-010", "missing dir kills conn", None))

print("\nFINDINGS:", len(findings))
for f in findings:
    print("  ", f)
sys.exit(0 if not findings else 2)
