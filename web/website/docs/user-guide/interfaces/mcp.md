---
id: mcp
title: MCP Server
sidebar_label: MCP Server
---

# MCP Server (`fhir4ds-mcp`)

fhir4ds ships an [Model Context Protocol](https://modelcontextprotocol.io)
stdio server exposing the [operations layer](./operations) as MCP tools, so
any MCP client — Claude Desktop, opencode, Cursor — gets a closed
draft → evaluate → fix loop for CQL authoring.

## Install

The server is an optional extra; the core install adds no dependencies:

```bash
pip install fhir4ds-v2[mcp]
fhir4ds-mcp   # stdio server; the MCP client manages the process
```

## Tools

| Tool | Maps to | Purpose |
|------|---------|---------|
| `parse_cql_tool` | `parse_cql` | Parse/validate CQL text; declaration metadata |
| `translate_cql_tool` | `translate_cql` | Emit generated SQL |
| `evaluate_library_tool` | `evaluate_library` | Evaluate populations (rows + summary) |
| `run_tests_tool` | `run_tests` | Run declarative cases; verify envelope |
| `fhirpath_eval_tool` | `fhirpath_eval` | Evaluate a FHIRPath expression on one resource |
| `load_dataset_tool` | `load_dataset` | Load a dataset; returns a handle + counts |
| `explain_patient_tool` | `explain_patient` | Per-patient audit evidence drill-in |

Every tool returns the shared envelope (`schema: 1`, `ok`, `passed`,
`diagnostics`) — identical shapes to the [CLI](./cli) on the same inputs.

## Datasets

`load_dataset_tool` accepts inline `resources` (capped at 5 MB — use
`ndjson_paths`/`bundle_paths` files for larger data) or file paths, and
returns a handle. Later calls may reference `{"handle": "..."}` to reuse the
loaded data. One server process hosts one **active** dataset: loading a new
dataset explicitly replaces it, and referencing a stale handle is a typed
`not_found` error.

Libraries sent once in a session are cached, so subsequent calls can be
shorter — includes also resolve automatically from the bundled standard
libraries (`FHIRHelpers`, `QICoreCommon`, `Status`) without sending them.

## Client configuration

### Claude Desktop

```json
{
  "mcpServers": {
    "fhir4ds": {
      "command": "fhir4ds-mcp"
    }
  }
}
```

### opencode

```json
{
  "mcp": {
    "fhir4ds": {
      "type": "local",
      "command": ["fhir4ds-mcp"]
    }
  }
}
```

### Cursor

```json
{
  "mcpServers": {
    "fhir4ds": {
      "command": "fhir4ds-mcp"
    }
  }
}
```

The server runs locally with the same trust model as the CLI (local files,
local DuckDB); it is not a multi-tenant service.
