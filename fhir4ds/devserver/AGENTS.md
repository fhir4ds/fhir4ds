# devserver Contributor Notes

`fhir4ds dev [dir]` — single-user CQL cleanroom dev server (127.0.0.1:8765).

## Structure
- `config.py` — flags > `fhir4ds.toml [dev]` > convention merge (config ADDS to convention).
- `discovery.py` — dir scan → WorkspaceSnapshot; malformed CQL never crashes discovery.
- `watcher.py` — stdlib polling watcher (500ms) + EventBus; data-dir changes emit
  `data-hint` (never auto-reload — kernel restart is explicit; locked decision).
- `kernel.py` — Kernel(conn+datasets) + KernelManager (restart = pointer swap; in-flight
  holders keep the old conn and drain).
- `api.py` — stdlib http.server routes, THIN over fhir4ds.operations capabilities;
  serves the committed wasm product UI from static-wasm/ (c-wasm-bolton S5:
  the legacy shell in static/ and web/dev-server/src are DELETED).
- `ws.py` — stdlib RFC 6455 WebSocket helpers (101 handshake accept key,
  text/close/pong frames, masked client-frame reader). Events channel is
  WebSocket-only per conductor ruling 2026-10-03 (no SSE path, no deps).
- `static-wasm/` — committed wasm product build (rebuilt from web/wasm-demo:
  `npx vite build --base=/` then copy dist/ here minus the duplicate wheel).
- `tests/` — pytest (config/discovery/watcher/api/static/kernel-datasets).

## Rules
- All evaluation behavior comes from the operations layer as-is; no engine seams here.
- Per-define evaluation = output_columns={define: define} narrowing (documented in
  _route_evaluate); do not add a new engine path.
- The server is zero-write: dependency dirs are read-only; the edit loop is in-memory
  buffers + Apply (inline LibraryText).
- The frontend IS web/wasm-demo (the product app). web/dev-server/ exists
  only as the connected-mode playwright host (specs were consolidated into
  the wasm suite at S5; madie_fixtures.ts retained for the follow-up UI slice).
