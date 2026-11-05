---
id: autocoding
title: Auto-Coding, Live
sidebar_label: Auto-Coding
description: "Run the real fhir4ds AutoCoder in your browser against a live terminology service — watch a text-only CodeableConcept gain a coded Coding with a full audit trail."
---

import AutocodingDemo from '@site/src/components/AutocodingDemo';

# Auto-Coding, Live

Legacy EHR exports routinely carry CodeableConcepts with a free-text `text`
and no `coding[]` — `"code": {"text": "uncontrolled type 2 diabetes"}`. CQL
retrieves against `[Code: <valueset>]` cannot match those rows. The
**AutoCoder** fixes that: it searches each text-only concept against a
terminology service and attaches coded Codings carrying a full audit trail.

This page runs the **real thing**: `fhir4ds-v2` executes in your browser
(Pyodide), the `AutoCoder` is the shipped implementation, and the terminology
search is served live by the public
[medterm4ds terminology Space](https://fhir4ds-terminology-demo-server.hf.space)
in **hybrid** mode — lexical (BM25) and semantic (SapBERT) results fused, with
match grades (`certain` / `probable` / `possible` / `broader`) derived from
semantic confidence.

## How it works

1. **Detection** — the AutoCoder walks the resource for CodeableConcepts that
   have a `text` and no existing `coding[]` (never re-coding manual codes).
2. **Search** — each text goes to `CodeSystem/$search` on the terminology
   service (hybrid mode, system chosen by clinical category).
3. **Filter** — results below the configured minimum match grade are dropped;
   the top *k* survive. Re-filtering is instant — no new search.
4. **Augmentation** — each surviving result becomes a Coding with
   `userSelected: false` and the
   [`autocoding` audit extension](https://fhir4ds.org/fhir/StructureDefinition/autocoding):
   engine, engine version, search mode, score, match grade.

The same flow in Python is three lines — see the
[Auto-Coding guide](/docs/user-guide/terminology/autocoding):

```python
from fhir4ds.cql.loader import AutoCoder

coder = AutoCoder(endpoint, con)          # any terminology endpoint
coder.augment_resource(resource)          # in place, audited
```

## Try it

Edit the resource (any `code.text` works — try a colloquial phrase and watch
semantic search find the clinical concept), set the policy, and run.

:::note[Good to know]

The terminology Space **sleeps when idle** — the first search after a wake can
take up to ~2 minutes (the demo tells you when this happens; retry shortly
after). The demo allows **30 requests/minute per IP**; for anything heavier,
self-host the terminology service. Nothing you type leaves your browser except
the search query itself.

:::

<AutocodingDemo />

## Where to go next

- [Auto-Coding guide](/docs/user-guide/terminology/autocoding) — the Python
  API, batch mode, caching, and config reference.
- [Terminology service](/docs/user-guide/terminology/terminology-service) —
  endpoints: in-process medterm4ds or any FHIR R4 sidecar.
- [Notes pipeline](/docs/user-guide/terminology/notes-pipeline) — free-text
  notes to derived Condition resources (NER cascade).
- [Terminology search demo](https://terminology.fhir4ds.com/docs/examples/terminology-search) —
  the terminology operations themselves, live.
