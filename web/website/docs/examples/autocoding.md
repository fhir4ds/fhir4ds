---
id: autocoding
title: NLP
sidebar_label: NLP
description: "Run the real fhir4ds AutoCoder and the medterm4ds NER pipeline in your browser against a live terminology service — auto-code text-only concepts and turn clinical notes into derived Condition resources."
---

import AutocodingDemo from '@site/src/components/AutocodingDemo';
import NotesDemo from '@site/src/components/AutocodingDemo/NotesDemo';

# NLP

Clinical text is everywhere and structure isn't. Legacy EHR exports carry
CodeableConcepts with a free-text `text` and no `coding[]` — CQL retrieves
against `[Code: <valueset>]` can't match them. Progress notes hold the
richest clinical detail in the record, as prose. This page runs the real
NLP machinery against both: the **AutoCoder** turns text-only concepts
into coded Codings with a full audit trail, and the **annotations**
engine reads clinical notes by meaning and derives structured Condition
resources from them.

Both run the **real thing**: `fhir4ds-v2` executes in your browser
(Pyodide), the `AutoCoder` is the shipped implementation, and the
terminology work — hybrid search (lexical BM25 + semantic SapBERT, fused,
with match grades `certain` / `probable` / `possible` / `broader`) and the
NER cascade — is served live by the public
[medterm4ds terminology Space](https://fhir4ds-terminology-demo-server.hf.space).

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

## Auto-Coding

<AutocodingDemo />

## Annotations

The same terminology service also reads free text. The example below runs
the NER cascade (`CodeSystem/$extract`) on a clinical note — live, against
the public Space — and wraps every affirmed concept as a derived FHIR
Condition resource: coded, audit-trailed, and queryable.

<NotesDemo />

## Where to go next

- [Auto-Coding guide](/docs/user-guide/terminology/autocoding) — the Python
  API, batch mode, caching, and config reference.
- [Terminology service](/docs/user-guide/terminology/terminology-service) —
  endpoints: in-process medterm4ds or any FHIR R4 sidecar.
- [Notes pipeline](/docs/user-guide/terminology/notes-pipeline) — free-text
  notes to derived Condition resources (NER cascade).
- [Terminology search demo](https://terminology.fhir4ds.com/docs/examples/terminology-search) —
  the terminology operations themselves, live.
