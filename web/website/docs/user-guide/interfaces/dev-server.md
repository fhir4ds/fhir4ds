---
id: dev-server
title: Dev Server
sidebar_label: Dev Server
description: fhir4ds dev — the local cleanroom server. One wasm product UI, standalone or connected to your workspace.
---

# Dev Server (`fhir4ds dev`)

`fhir4ds dev [dir]` starts a local cleanroom server (default
`127.0.0.1:8765`) serving the **wasm product UI** — the same app that runs
on the website, now wired to your local workspace.

```bash
pip install -e ".[dev]"     # from a checkout
fhir4ds dev ~/my-workspace --port 8765
# → http://127.0.0.1:8765
```

## One app, three modes

| Mode | How entered | Engine | Data |
|------|-------------|--------|------|
| **standalone** | Static hosting (website / `wasm-app/`) | In-browser (Pyodide translate + DuckDB-WASM) | Uploaded / inline only |
| **connected** | Served by `fhir4ds dev` | Python server (native DuckDB, full CQL/DQM stack) | Your local workspace files |
| **embed** | `<fhir4ds-demo>` web component; add `server-url="http://127.0.0.1:8765"` for embed-connected | Per mode | Per mode |

The app resolves its mode via the `/api/mode` handshake (four states:
connecting → connected / standalone / degraded) — never a boolean. The
status-bar engine badge (`⚙ wasm` / `🖧 server vX.Y`) is clickable: retry
the connection or switch to the in-browser engine explicitly.

## The UI

- **Rail** (left): CQL · Data · SQL · Viewer always active; the cleanroom
  section (Libraries · Valuesets · Measures · Terminology · History) is
  capability-gated — in standalone the entries are visible but locked with
  a "requires a connected server" remedy, never hidden.
- **Slide-outs**: Libraries/Valuesets list your workspace files (with
  watcher change badges and per-file dots); Terminology hosts VSAC/FHIR
  import + UMLS lookup (key configured via the `UMLS_API_KEY` env var —
  displayed, never written from the browser); History shows the persistent
  run log.
- **Cells**: the CQL editor has a per-buffer cell mode (`// # %%`
  markers). Run a cell, its dependency closure (`cell + deps`), or
  everything up to it (`to here`) — identical semantics in both engines;
  standalone results carry a "computed locally" badge.
- **Builder tab**: the FHIR resource builder playground (offline schema
  trees, validation).

## Workspace layout

```
my-workspace/
  fhir4ds.toml      # [dev] config (dirs, ui mode)
  cql/              # CQL libraries (include dir)
  valuesets/        # ValueSet JSON
  measures/         # Measure resources + expected/ results
  data/             # *.ndjson and Bundle *.json — mixed is fine
```

File changes reload automatically (watcher); **data changes never
auto-reload** — you get a banner with an explicit *Restart kernel* button.

## CLI

```
fhir4ds dev [dir] [--port PORT] [--ui {wasm,legacy}]
            [--cql-dir DIR] [--valueset-dir DIR]
            [--measure-dir DIR] [--data-dir DIR] [--no-open]
```

`--ui legacy` is accepted but unreachable (the pre-bolton shell was
retired); `[dev] ui = "wasm"` in `fhir4ds.toml` is the default.

## Installing the dev server UI (wheel users)

The PyPI wheel stays lean: the 61MB committed wasm UI build
(`fhir4ds/devserver/static-wasm/`) ships in the **sdist** and in git
checkouts, not the wheel. Wheel installs that need the UI should install
from the sdist or a checkout (`pip install fhir4ds-v2 --no-binary :all:`),
or serve any static build of `web/wasm-demo` at the same paths.

## Terminology keys

```
export UMLS_API_KEY=...        # UMLS lookup
export VSAC_API_KEY=...        # VSAC import (or [terminology] api_key_env)
fhir4ds dev .
```

Keys are resolved server-side at call time and never logged; the UI only
ever displays *configured / not configured*.
