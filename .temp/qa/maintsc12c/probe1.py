"""maint/spec-comp-20261012c — SKEPTIC probe: watcher diff/poll +
EventBus fan-out + ws envelope semantics under adversarial input.
Fresh evidence only (prior runs quarantined).

Anchored to the ACTUAL contracts (probe-error rule):
- EventBus.subscribe() takes NO args, returns a Queue[WorkspaceEvent];
  publish is put_nowait per sub, queue.Full silently dropped (slow-client
  contract), unsubscribe removes.
- Watcher(cfg, bus, on_rescan) — diff via rescan(); changed/data-hint
  kinds; no "removed" kind (removal lands in 'changed' via old-new);
  WorkspaceEvent carries paths[] (plural) + optional snapshot dict.
"""
import queue
import sys
import threading
import time
from pathlib import Path
import tempfile

sys.path.insert(0, "/mnt/d/fhir4ds-maint-spec-comp-20261012c")
from fhir4ds.devserver.watcher import (
    Watcher, EventBus, WorkspaceEvent, POLL_INTERVAL,
)
from fhir4ds.devserver.config import load_config

findings = []


def wait_for(q, timeout):
    out = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            out.append(q.get(timeout=0.2))
        except queue.Empty:
            if out:
                break
    return out


def drain(q):
    out = []
    while True:
        try:
            out.append(q.get_nowait())
        except queue.Empty:
            return out


# --- EventBus seams -----------------------------------------------------
bus = EventBus()
q1 = bus.subscribe()
ev = WorkspaceEvent(kind="changed", paths=["cql/a.cql"])
bus.publish(ev)
got = q1.get_nowait()
bus.unsubscribe(q1)
bus.publish(WorkspaceEvent(kind="changed", paths=["cql/b.cql"]))
leak = not q1.empty()
ok = got is ev and not leak
print(f"W1 pub/sub + unsubscribe: {ok} leak={leak}")
if not ok:
    findings.append(("QA-001", "pub/sub leak after unsubscribe", None))

# 2. fan-out: two subscribers each get one copy
bus2 = EventBus()
qa, qb = bus2.subscribe(), bus2.subscribe()
bus2.publish(WorkspaceEvent(kind="changed", paths=["x"]))
ok = qa.get_nowait().paths == ["x"] and qb.get_nowait().paths == ["x"]
print(f"W2 fan-out both copies: {ok}")
if not ok:
    findings.append(("QA-002", "fan-out missing copy", None))

# 3. slow client: bounded queue (maxsize=256) does not block publisher
bus3 = EventBus()
qs = bus3.subscribe()
for i in range(600):
    bus3.publish(WorkspaceEvent(kind="changed", paths=[f"p{i}"]))
ok = qs.qsize() == 256  # overflow dropped per contract, publisher alive
print(f"W3 slow-client drop not block: {ok} qsize={qs.qsize()}")
if not ok:
    findings.append(("QA-003", "slow client blocks publisher", qs.qsize()))

# 4. threaded publish while (un)subscribing — no deadlock/crash
bus4 = EventBus()
q4 = bus4.subscribe()
stop_flag = threading.Event()
def hammer():
    while not stop_flag.is_set():
        bus4.publish(WorkspaceEvent(kind="changed", paths=["t"]))
        time.sleep(0.001)
t = threading.Thread(target=hammer, daemon=True)
t.start()
for _ in range(200):
    qq = bus4.subscribe()
    bus4.publish(WorkspaceEvent(kind="changed", paths=["m"]))
    bus4.unsubscribe(qq)
stop_flag.set(); t.join(timeout=3)
ok = not t.is_alive()
print(f"W4 concurrent sub/pub: {ok}")
if not ok:
    findings.append(("QA-004", "concurrency deadlock", None))

# --- Watcher diff semantics (poll loop) --------------------------------
tmp = Path(tempfile.mkdtemp(prefix="watch-"))
(tmp / "cql").mkdir()
(tmp / "cql" / "a.cql").write_text("library A\ndefine X: 1\n", encoding="utf-8")
busw = EventBus()
qw = busw.subscribe()
rescans = []
w = Watcher(load_config(str(tmp)), busw, on_rescan=lambda s: rescans.append(1))
w.start()
try:
    # 5. modify -> one 'changed' event with the path, debounced coalescing:
    #    two writes inside one poll window surface as ONE event
    time.sleep(POLL_INTERVAL + 0.3)  # initial quiet window (no spurious event)
    initial_spurious = [e for e in drain(qw) if e.kind == "changed"]
    (tmp / "cql" / "a.cql").write_text("library A\ndefine X: 2\n", encoding="utf-8")
    time.sleep(0.1)
    (tmp / "cql" / "a.cql").write_text("library A\ndefine X: 3\n", encoding="utf-8")
    evs = wait_for(qw, timeout=POLL_INTERVAL * 4 + 4)
    time.sleep(POLL_INTERVAL + 0.4)  # stragglers
    evs += drain(qw)
    changed = [e for e in evs if "a.cql" in str(e.paths)]
    ok = len(changed) == 1
    print(f"W5 coalesced change: {ok} n={len(changed)}")
    if not ok:
        findings.append(("QA-005", "change event count", len(changed)))
    if initial_spurious:
        print(f"   (initial-scan spurious events observed: {len(initial_spurious)})")
finally:
    w.stop()

# 6. delete lands in changed set (old - new), kind stays 'changed'
events2 = []
busd = EventBus()
qd = busd.subscribe()
(tmp / "cql" / "b.cql").write_text("library B\n", encoding="utf-8")
wd = Watcher(load_config(str(tmp)), busd)
wd.start()
try:
    time.sleep(POLL_INTERVAL + 0.3)
    drain(qd)
    (tmp / "cql" / "b.cql").unlink()
    evs = wait_for(qd, timeout=POLL_INTERVAL * 4 + 4)
    time.sleep(POLL_INTERVAL + 0.4)
    evs += drain(qd)
    hit = [e for e in evs if any("b.cql" in p for p in e.paths)]
    ok = bool(hit)
    print(f"W6 delete surfaces: {ok} kinds={[e.kind for e in hit]}")
    if not ok:
        findings.append(("QA-006", "delete invisible", None))
finally:
    wd.stop()

# 7. data-hint vs changed routing (locked decision 4)
tmpd = Path(tempfile.mkdtemp(prefix="watchd-"))
(tmpd / "cql").mkdir(); (tmpd / "data").mkdir()
(tmpd / "cql" / "a.cql").write_text("library A\n", encoding="utf-8")
(tmpd / "data" / "p.ndjson").write_text('{"resourceType":"Patient","id":"p1"}\n', encoding="utf-8")
cfgd = load_config(str(tmpd))
busx = EventBus(); qx = busx.subscribe()
wx = Watcher(cfgd, busx)
wx.start()
try:
    time.sleep(POLL_INTERVAL + 0.3)
    drain(qx)
    (tmpd / "data" / "p.ndjson").write_text('{"resourceType":"Patient","id":"p2"}\n', encoding="utf-8")
    evs = wait_for(qx, timeout=POLL_INTERVAL * 4 + 4)
    time.sleep(POLL_INTERVAL + 0.4)
    evs += drain(qx)
    kinds = sorted({e.kind for e in evs if any("p.ndjson" in p for p in e.paths)})
    ok = kinds == ["data-hint"]
    print(f"W7 data change routes to data-hint: {ok} kinds={kinds}")
    if not ok:
        findings.append(("QA-007", "data change routing", kinds))
finally:
    wx.stop()

# 8. stop() idempotent, thread reaped
wx.stop(); wd.stop()
ok = wx._thread is None and wd._thread is None
print(f"W8 stop idempotent: {ok}")
if not ok:
    findings.append(("QA-008", "stop leaves thread", None))

print("\nFINDINGS:", len(findings))
for f in findings:
    print("  ", f)
sys.exit(0 if not findings else 2)
