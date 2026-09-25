import { useEffect, useMemo, useRef, useState } from "react";
import {
  BootOverlay,
  VersionBadge,
  useBootProgress,
  workerRequest,
} from "./components/BootOverlay";
import { EditorPane } from "./components/EditorPane";
import { NavRail } from "./components/NavRail";
import { TerminologyPane } from "./components/TerminologyPane";
import { ParametersDrawer, coerceParam, detectParams } from "./components/ParametersDrawer";
import { importMadiePackage } from "./lib/madiePackage";
import { exportMadiePackage } from "./lib/madieExport";
import {
  buildShareUrl,
  decodeShareFragment,
  type SharePayload,
} from "./lib/share";
import { ResultsPane } from "./components/ResultsPane";
import { TestsPane } from "./components/TestsPane";
import { MeasurePane } from "./components/MeasurePane";
import { ViewPane } from "./components/ViewPane";
import { DatasetPane } from "./components/DatasetPane";
import { ResourceBuilderPane } from "./components/ResourceBuilderPane";
import {
  exportBundle,
  importBundle,
  mergeDatasets,
} from "./lib/bundleIo";
import { RunCompare } from "./components/RunCompare";
import { DropdownMenu } from "./components/DropdownMenu";
import { FhirpathPane } from "./components/FhirpathPane";
import type { RunEntry } from "./state/workspace";
import { RUN_HISTORY_CAP } from "./state/workspace";
import {
  appendRun,
  artifactFromRows,
  datasetHash as computeDatasetHash,
  defaultRunName,
  libraryHash as computeLibraryHash,
  newRunId,
} from "./lib/runHistory";
import type { ResultsTab } from "./components/ResultsPane";
import { GraphPane } from "./components/GraphPane";
import type { DatasetSpec, LibraryText, FlattenViewResult } from "./lib/protocol";
import {
  clearWorkspace,
  exportWorkspaceZip,
  importWorkspaceZip,
  loadWorkspace,
  saveWorkspace,
  type WorkspaceLibrary,
} from "./state/workspace";

// e2e bridge: the app's singleton worker, request/response correlated by id
declare global {
  interface Window {
    __cleanroom?: (msg: Record<string, unknown>) => Promise<any>;
  }
}
(window as any).__cleanroom = workerRequest;

const DEFAULT_CQL = `library CleanroomDemo version '1.0.0'
using FHIR version '4.0.1'
include FHIRHelpers version '4.0.1' called FHIRHelpers

define "Initial Population":
  exists([Patient] P where P.gender = 'female')

define "Has Name":
  exists([Patient] P where P.name.first().given.first() is not null)
`;

/**
 * INV-3: population-role semantics resolve from the Measure resource
 * ONLY. The hardcoded OUTPUT_COLUMNS alias map is DELETED; the alias
 * map feeding translate/evaluate is derived from the measure via
 * output_columns_from_measure (column = population_code with the DQM
 * underscore convention).
 */
// Demo dataset (mirrors the raw-view default NDJSON): shipped so the
// workbench always has something to evaluate — auto-recalc fires on
// first paint with no clicks (U5 companion).
const DEFAULT_DATASET_RESOURCES: Array<Record<string, unknown>> = [
  { resourceType: "Patient", id: "p1", gender: "female", name: [{ given: ["Ann"] }] },
  { resourceType: "Patient", id: "p2", gender: "male", name: [{ given: ["Bob"] }] },
  { resourceType: "Patient", id: "p3", gender: "female" },
];

const DEFAULT_MEASURE: Record<string, unknown> = {
  resourceType: "Measure",
  name: "CleanroomMeasure",
  status: "draft",
  group: [
    {
      id: "group-1",
      extension: [
        {
          url: "http://hl7.org/fhir/us/cqf-measures/StructureDefinition/cqfm-populationBasis",
          valueCode: "boolean",
        },
      ],
      population: [
        {
          code: {
            coding: [
              {
                system: "http://terminology.hl7.org/CodeSystem/measure-population",
                code: "initial-population",
              },
            ],
          },
          criteria: {
            language: "text/cql-identifier",
            expression: "Initial Population",
          },
        },
        {
          code: {
            coding: [
              {
                system: "http://terminology.hl7.org/CodeSystem/measure-population",
                code: "numerator",
              },
            ],
          },
          criteria: {
            language: "text/cql-identifier",
            expression: "Has Name",
          },
        },
      ],
    },
  ],
};

function outputColumnsFromMeasure(
  measure: Record<string, unknown> | null,
): Record<string, string> | null {
  if (!measure) return null;
  const groups = (measure.group as Array<Record<string, unknown>>) ?? [];
  const out: Record<string, string> = {};
  for (const g of groups) {
    for (const pop of (g.population as Array<Record<string, unknown>>) ?? []) {
      const coding =
        (
          (pop.code as Record<string, unknown>)?.coding as
            Array<Record<string, unknown>>
        )?.[0] ?? {};
      const criteria = pop.criteria as Record<string, unknown> | undefined;
      const code = coding.code;
      const define = criteria?.expression;
      if (typeof code === "string" && typeof define === "string" && code && define) {
        out[code.replace(/-/g, "_")] = define;
      }
    }
  }
  return Object.keys(out).length ? out : null;
}

function populationCodesFromMeasure(
  measure: Record<string, unknown> | null,
): string[] {
  // Authority form: hyphenated FHIR measure-population codes
  // (initial-population). Consumers snake_case for column keys.
  if (!measure) return [];
  const groups = (measure.group as Array<Record<string, unknown>>) ?? [];
  const out: string[] = [];
  for (const g of groups) {
    for (const pop of (g.population as Array<Record<string, unknown>>) ?? []) {
      const coding =
        (
          (pop.code as Record<string, unknown>)?.coding as
            Array<Record<string, unknown>>
        )?.[0] ?? {};
      if (typeof coding.code === "string" && coding.code) {
        out.push(coding.code);
      }
    }
  }
  return out;
}

export default function App() {
  const boot = useBootProgress();
  const [libraries, setLibraries] = useState<WorkspaceLibrary[]>([
    { name: "CleanroomDemo", text: DEFAULT_CQL },
  ]);
  const [activeTab, setActiveTab] = useState(0);
  // PASS2 G1: entrypoint decouples evaluated root from edited tab.
  const [entrypoint, setEntrypoint] = useState(0);
  // Parameters drawer: declared names derive from the ENTRYPOINT CQL;
  // values are user-bound and flow to every evaluate/tests/explain call.
  const [paramValues, setParamValues] = useState<Record<string, string>>({});
  const [paramsOpen, setParamsOpen] = useState(false);
  // Per-library parse-error map (rail badges), fed by EditorPane
  // diagnostics for the active library. activeTabRef mirrors activeTab
  // so the callback always reads the CURRENT tab (the render-captured
  // activeTab goes stale across fast tab switches).
  const [libErrors, setLibErrors] = useState<Record<number, boolean>>({});
  const activeTabRef = useRef(activeTab);
  activeTabRef.current = activeTab;
  const [dataset, setDataset] = useState<DatasetSpec | null>({
    resources: DEFAULT_DATASET_RESOURCES,
  });
  // Measure resource: population-mapping authority (INV-3). NULL when
  // the workspace has none — evaluation falls back to raw define names.
  const [measure, setMeasure] = useState<Record<string, unknown> | null>(
    DEFAULT_MEASURE,
  );

  const [expectedValues, setExpectedValues] = useState<{
    [pid: string]: { [code: string]: boolean };
  } | null>(null);
  // MeasureReports from the last evaluation (View drawer default source).
  const [lastReports, setLastReports] = useState<
    Array<Record<string, unknown>> | null
  >(null);
  // Editor-column visual-editor drawer (default collapsed).
  const [graphOpen, setGraphOpen] = useState(false);
  const [terminologyOpen, setTerminologyOpen] = useState(false);
  // Editor-column FHIRPath scratchpad drawer (default collapsed).
  const [fhirpathOpen, setFhirpathOpen] = useState(false);
  // WORKBENCH_REORG §3.1/§3.3 — Results tab pref + local run history.
  const [resultsTab, setResultsTab] = useState<ResultsTab>("cql");
  const [runHistory, setRunHistory] = useState<RunEntry[]>([]);
  // Flatten SQL of the last View run (Show-SQL context for the View tab).
  const [viewSql, setViewSql] = useState<string | null>(null);
  const [viewResult, setViewResult] = useState<FlattenViewResult | null>(null);
  // Row-shaped memberships + hashes of the LATEST evaluation (compare
  // target + drift reference). Cleared when inputs change.
  const [currentRun, setCurrentRun] = useState<{
    artifact: RunEntry["artifact"];
    libraryHash: string;
    datasetHash: string;
  } | null>(null);
  // §3.5 View drawer config — persisted in workspace (schemaVersion 2).
  const [viewConfig, setViewConfig] = useState<{
    overrides: Record<string, { name?: string; path?: string }>;
  } | null>(null);
  // PASS2 G2: workspace terminology overrides (ValueSet resources).
  const [terminology, setTerminology] = useState<{
    valuesets: Array<Record<string, unknown>>;
  }>({ valuesets: [] });

  // G2: the dataset every evaluation/explain/tests call sees — workspace
  // terminology OVERRIDES dataset valueset_resources (url-deduped).
  const evalDataset = useMemo(() => {
    const baseVs = dataset?.valueset_resources ?? [];
    const wsVs = terminology.valuesets;
    if (!wsVs.length) return dataset;
    const wsUrls = new Set(
      wsVs
        .map((v) => (typeof v?.url === "string" ? v.url : null))
        .filter(Boolean),
    );
    const merged = [
      ...baseVs.filter((v) => {
        const url = (v as Record<string, unknown>)?.url;
        return !(typeof url === "string" && wsUrls.has(url));
      }),
      ...wsVs,
    ];
    return { ...(dataset ?? { resources: [] }), valueset_resources: merged };
  }, [dataset, terminology]);
  // C3-U3: builder prefill for dataset-row editing (nonce re-triggers).
  const [builderPrefill, setBuilderPrefill] = useState<{
    resource: Record<string, unknown>;
    nonce: number;
  } | null>(null);
  // §3.2: per-patient `+` context — subject-class pickers default to
  // Patient/<id> (builder v2 consumes; v1 ignores gracefully).
  const [builderContext, setBuilderContext] = useState<{
    patientId: string;
    nonce: number;
  } | null>(null);
  const [restored, setRestored] = useState(false);
  // Resolves once the mount-time workspace restore/share-load settles —
  // imports must wait on THIS (not the `restored` closure) so a late
  // restore can never clobber an import.
  // Initialized EAGERLY (not inside the effect) so any consumer that
  // reads it before the effect runs still awaits the same promise.
  const restoreDoneRef = useRef<Promise<void> | null>(null);
  const restoreDoneResolveRef = useRef<(() => void) | null>(null);
  if (restoreDoneRef.current === null) {
    restoreDoneRef.current = new Promise<void>((resolve) => {
      restoreDoneResolveRef.current = resolve;
    });
  }
  const [statusNote, setStatusNote] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const madieFileRef = useRef<HTMLInputElement | null>(null);

  // Built-in eCQM example (CMS69 conformance bundle: 62 patients,
  // 22 ValueSets, real CQL). Loaded from public/examples/.
  const loadExample = async (example: string) => {
    try {
      const base = `examples/${example}`;
      const [cql, measure, valuesets, ndjson] = await Promise.all([
        fetch(`${base}/main.cql`).then((r) => r.text()),
        fetch(`${base}/measure.json`).then((r) => r.json()),
        fetch(`${base}/valuesets.json`).then((r) => r.json()),
        fetch(`${base}/dataset.ndjson`).then((r) => r.text()),
      ]);
      const m = cql.match(/^\s*library\s+([A-Za-z][A-Za-z0-9_]*)/m);
      const name = m ? m[1] : example;
      // Included libraries become VIEWABLE tabs: resolve each include
      // against the bundled copies (examples/<ex>/includes/<Lib>.cql,
      // falling back to versionless bundled names served at
      // /examples/includes/<Lib>.cql).
      const includeTabs: Array<{ name: string; text: string }> = [];
      const seenIncludes = new Set<string>([name]);
      for (const inc of cql.matchAll(/include\s+([A-Za-z][A-Za-z0-9_]*)\s+version\s+'([^']+)'/g)) {
        const incName = inc[1];
        if (incName === "FHIRHelpers" || seenIncludes.has(incName)) continue;
        seenIncludes.add(incName);
        try {
          const r = await fetch(`${base}/includes/${incName}.cql`);
          if (r.ok) {
            includeTabs.push({ name: incName, text: await r.text() });
          }
        } catch {
          // optional include tab — bundled engine libraries resolve
          // server-side without a tab
        }
      }
      setLibraries([{ name, text: cql }, ...includeTabs]);
      setActiveTab(0);
      setEntrypoint(0);
      setMeasure(measure);
      setTerminology({ valuesets: Array.isArray(valuesets) ? valuesets : [] });
      const resources = ndjson
        .split("\n")
        .map((l) => l.trim())
        .filter(Boolean)
        .map((l) => JSON.parse(l));
      setDataset({ resources });
      // Pre-fill declared parameters with sensible defaults where known:
      // Measurement Period uses the eCQM reporting period the
      // conformance fixtures encode (2019 calendar year).
      const defaults: Record<string, string> = {};
      for (const pm of cql.matchAll(
        /parameter\s+"([^"]+)"(?!.*default)/g,
      )) {
        if (pm[1] === "Measurement Period") {
          // eCQM reporting period the conformance fixture encodes
          // (expected MeasureReport period 2026-01-01..2026-12-31).
          defaults[pm[1]] = "2026-01-01T00:00:00.0..2026-12-31T23:59:59.999";
        }
      }
      if (Object.keys(defaults).length) setParamValues(defaults);
      setStatusNote(`loaded example ${example}: ${resources.length} resources`);
    } catch (e) {
      setStatusNote(`example load failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  // Derived from the Measure — the ONLY alias/order source (INV-3).
  const outputColumns = useMemo(
    () => outputColumnsFromMeasure(measure),
    [measure],
  );
  const populationCodes = useMemo(
    () => populationCodesFromMeasure(measure),
    [measure],
  );

  // Restore workspace on first mount; autosave (debounced) on changes.
  // A share fragment (#s=...) takes precedence over IndexedDB state.
  useEffect(() => {
    const shared = decodeShareFragment(location.hash);
    if (shared) {
      setLibraries(
        shared.libraries.map((l) => ({ name: l.name, text: l.text })),
      );
      setActiveTab(Math.min(shared.activeIndex ?? 0, shared.libraries.length - 1));
      setRestored(true);
      return;
    }
    loadWorkspace()
      .then((ws) => {
        if (ws?.libraries?.length) {
          setLibraries(ws.libraries);
          setActiveTab(0);
          if (ws.dataset) {
            setDataset({
              resources: ws.dataset.resources as Record<string, unknown>[],
            });
          }
        }
        if (ws?.measure) {
          setMeasure(ws.measure);
        }
        if (ws?.viewConfig) {
          setViewConfig(ws.viewConfig);
        }
        if (ws && Array.isArray(ws.runHistory)) {
          setRunHistory(ws.runHistory);
        }
        if (
          ws &&
          (ws.activeTabPref === "cql" ||
            ws.activeTabPref === "measure" ||
            ws.activeTabPref === "view")
        ) {
          setResultsTab(ws.activeTabPref);
        }
        if (ws && ws.terminology?.valuesets?.length) {
          setTerminology(ws.terminology);
        }
      })
      .catch(() => undefined)
      .finally(() => {
        setRestored(true);
        restoreDoneResolveRef.current?.();
      });
  }, []);

  useEffect(() => {
    if (!restored) return;
    const t = setTimeout(() => {
      saveWorkspace({
        libraries,
        dataset: dataset?.resources?.length
          ? { resources: dataset.resources as unknown[] }
          : null,
        cases: expectedValues
          ? (Object.entries(expectedValues).flatMap(([pid, codes]) =>
              Object.entries(codes).map(([code, expect]) => ({
                patient: pid,
                population: code,
                expect,
              })),
            ) as unknown[])
          : null,
        prefs: {},
        measure,
        viewConfig,
        runHistory,
        activeTabPref: resultsTab,
        terminology,
      }).catch(() => undefined);
    }, 800);
    return () => clearTimeout(t);
  }, [
    libraries,
    dataset,
    measure,
    expectedValues,
    viewConfig,
    runHistory,
    resultsTab,
    terminology,
    restored,
  ]);

  const active = libraries[activeTab] ?? libraries[0];
  // G1 invariant: evaluation always uses the ENTRYPOINT library, never
  // merely the edited tab (multi-library include flows).
  const mainLib = libraries[entrypoint] ?? active;
  // Stable identity across re-renders (same name+text → same object):
  // ResultsPane's auto-eval effect keys on [main, [main]] — a fresh
  // object per render would re-trigger the 2s debounce forever.
  const main = useMemo<LibraryText>(
    () => ({ name: mainLib.name, text: mainLib.text }),
    [mainLib.name, mainLib.text],
  );
  const mainLibs = useMemo<LibraryText[]>(() => [main], [main]);

  // Runtime parameter bindings (drawer values, coerced): empty strings
  // are absent — a half-filled binding never reaches the engine.
  const runtimeParameters = useMemo(() => {
    const out: Record<string, unknown> = {};
    for (const [name, raw] of Object.entries(paramValues)) {
      if (raw.trim() === "") continue;
      out[name] = coerceParam(raw);
    }
    return out;
  }, [paramValues]);

  // M1 write-through: Measure.library[] mirrors the entrypoint pin —
  // primary first, then the dependency closure of that library. Keeps
  // the exported Measure self-describing without touching the mapping.
  useEffect(() => {
    if (!measure || !mainLib || !restored) return;
    setMeasure((m) => {
      if (!m) return m;
      const closure = [mainLib.name];
      // Cheap client-side closure via include declarations of each
      // library below the entrypoint (worker round-trip is overkill
      // for the common single-include case; the capability remains
      // the authority at export time).
      const byName = new Map(libraries.map((l) => [l.name, l]));
      const seen = new Set([mainLib.name]);
      const queue = [mainLib.name];
      while (queue.length) {
        const name = queue.shift()!;
        const lib = byName.get(name);
        if (!lib) continue;
        const includes = [...lib.text.matchAll(/include\s+([A-Za-z][A-Za-z0-9_]*)/g)].map(
          (mm) => mm[1],
        );
        for (const inc of includes) {
          if (byName.has(inc) && !seen.has(inc)) {
            seen.add(inc);
            closure.push(inc);
            queue.push(inc);
          }
        }
      }
      const libraryUrls = closure.map((n) => `urn:cleanroom:lib:${n}`);
      const current = Array.isArray(m.library) ? (m.library as string[]) : [];
      if (
        current.length === libraryUrls.length &&
        current.every((u, i) => u === libraryUrls[i])
      ) {
        return m; // unchanged
      }
      return { ...m, library: libraryUrls };
    });
  }, [entrypoint, libraries, mainLib, restored]);


  // G2: ValueSet declarations of the ACTIVE library (for the rail-linked
  // Terminology pane); parsed debounced through the worker.
  const [activeDeclarations, setActiveDeclarations] = useState<
    Array<Record<string, unknown>>
  >([]);
  useEffect(() => {
    const t = setTimeout(() => {
      void workerRequest({ type: "parse_cql", text: active.text })
        .then((resp) => {
          const env = JSON.parse(resp.envelope) as {
            ok: boolean;
            declarations?: Array<Record<string, unknown>>;
          };
          setActiveDeclarations(env.ok ? env.declarations ?? [] : []);
        })
        .catch(() => undefined);
    }, 600);
    return () => clearTimeout(t);
  }, [active.text]);


  const updateActiveText = (text: string) => {
    setLibraries((libs) =>
      libs.map((l, i) => (i === activeTab ? { ...l, text } : l)),
    );
  };

  const addTab = () => {
    const name = `Library${libraries.length + 1}`;
    const text = `library ${name} version '1.0.0'\nusing FHIR version '4.0.1'\n`;
    setLibraries((libs) => [...libs, { name, text }]);
    setActiveTab(libraries.length);
  };

  const closeTab = (i: number) => {
    if (libraries.length === 1) return;
    setLibraries((libs) => libs.filter((_, idx) => idx !== i));
    setActiveTab((t) => (i < t ? t - 1 : Math.min(t, libraries.length - 2)));
    setEntrypoint((e) => (i < e ? e - 1 : Math.min(e, libraries.length - 2)));
  };


  const shareLink = () => {
    const payload: SharePayload = {
      format: "cql-cleanroom-share",
      version: 1,
      libraries: libraries.map((l) => ({ name: l.name, text: l.text })),
      activeIndex: activeTab,
      outputColumns: outputColumns,
      parameters: null,
      cases: null,
    };
    try {
      const url = buildShareUrl(payload);
      location.hash = url.slice(url.indexOf("#"));
      void navigator.clipboard?.writeText(url).catch(() => undefined);
    } catch (e) {
      // REV-C2-002: surface encode failures (e.g. >100KB) via statusNote.
      setStatusNote(
        `share link failed: ${e instanceof Error ? e.message : String(e)}`,
      );
    }
  };

  const exportMadieZip = () => {
    try {
      const primaryName = libraries[entrypoint]?.name ?? libraries[0]?.name;
      if (!primaryName || !measure) {
        setStatusNote("nothing to export — need a library and a Measure");
        return;
      }
      const bytes = exportMadiePackage({
        libraries,
        primaryName,
        measure,
        valuesets: terminology.valuesets,
      });
      const blob = new Blob([bytes as unknown as BlobPart], { type: "application/zip" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${String(measure.name ?? "measure")}-package.zip`;
      a.click();
      URL.revokeObjectURL(url);
      setStatusNote("measure package exported");
    } catch (e) {
      setStatusNote(`package export failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const importMadieZip = async (file: File) => {
    // Guard: the mount-time workspace restore can clobber an import
    // that lands mid-restore. Await the restore's completion signal.
    await Promise.race([
      restoreDoneRef.current ?? Promise.resolve(),
      new Promise((r) => setTimeout(r, 10_000)),
    ]);
    try {
      const pkg = importMadiePackage(new Uint8Array(await file.arrayBuffer()));
      if (!pkg.libraries.length) {
        setStatusNote("package contained no readable CQL libraries");
        return;
      }
      setLibraries(pkg.libraries.map((l) => ({ name: l.name, text: l.text })));
      setActiveTab(0);
      setEntrypoint(0);
      if (pkg.measure) setMeasure(pkg.measure);
      if (pkg.warnings.length) {
        setStatusNote(`imported with ${pkg.warnings.length} warning(s): ${pkg.warnings[0]}`);
      } else {
        setStatusNote(`imported measure package (${pkg.libraries.length} libraries, primary ${pkg.primary})`);
      }
    } catch (e) {
      setStatusNote(`package import failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const exportZip = () => {
    const bytes = exportWorkspaceZip({
      libraries,
      dataset: dataset?.resources?.length
        ? { resources: dataset.resources as unknown[] }
        : null,
      cases: expectedValues
        ? (Object.entries(expectedValues).flatMap(([pid, codes]) =>
            Object.entries(codes).map(([code, expect]) => ({
              patient: pid,
              population: code,
              expect,
            })),
          ) as unknown[])
        : null,
      prefs: {},
      measure,
      viewConfig,
      runHistory,
      activeTabPref: resultsTab,
      terminology,
    });
    const blob = new Blob([bytes as unknown as BlobPart], {
      type: "application/zip",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "cql-cleanroom-workspace.zip";
    a.click();
    URL.revokeObjectURL(url);
  };

  // §3.4 Bundle export/import for the dataset.
  const bundleFileRef = useRef<HTMLInputElement | null>(null);
  const [bundleMode, setBundleMode] = useState<"merge" | "replace">("merge");

  const exportBundleFile = () => {
    const resources = (dataset?.resources ?? []) as Array<
      Record<string, unknown>
    >;
    if (!resources.length) {
      setStatusNote("nothing to export: dataset is empty");
      return;
    }
    const bundle = exportBundle(resources);
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(bundle, null, 2)], {
        type: "application/fhir+json",
      }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = "cleanroom-dataset-bundle.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  const importBundleFile = async (file: File) => {
    try {
      const parsed = JSON.parse(await file.text());
      const result = importBundle(parsed);
      if (result.rejected.length) {
        setStatusNote(
          `imported ${result.resources.length} resource(s); ` +
            `rejected ${result.rejected.length} entry/entries without id ` +
            `or fullUrl (indexes ${result.rejected.slice(0, 5).join(", ")})`,
        );
      } else if (result.synthesizedIds) {
        setStatusNote(
          `imported ${result.resources.length} resource(s); ` +
            `synthesized ${result.synthesizedIds} id(s) from fullUrl`,
        );
      }
      const current = (dataset?.resources ?? []) as Array<
        Record<string, unknown>
      >;
      const next =
        bundleMode === "replace"
          ? result.resources
          : mergeDatasets(current, result.resources);
      setDataset(next.length ? { resources: next } : null);
    } catch (e) {
      setStatusNote(
        `bundle import failed: ${e instanceof Error ? e.message : String(e)}`,
      );
    }
  };

  const importZip = async (file: File) => {
    try {
      const state = importWorkspaceZip(new Uint8Array(await file.arrayBuffer()));
      if (state.libraries.length) {
        setLibraries(state.libraries);
        setActiveTab(0);
      }
      if (state.dataset) {
        setDataset({
          resources: state.dataset.resources as Record<string, unknown>[],
        });
      }
      setMeasure(state.measure ?? DEFAULT_MEASURE);
      setViewConfig(state.viewConfig ?? null);
      setTerminology(state.terminology ?? { valuesets: [] });
      if (Array.isArray(state.cases)) {
        const ev: { [pid: string]: { [code: string]: boolean } } = {};
        for (const c of state.cases as Array<{ patient?: string; population?: string; expect?: boolean }>) {
          if (typeof c?.patient === "string" && typeof c?.population === "string") {
            ev[c.patient] = { ...(ev[c.patient] ?? {}), [c.population]: c.expect === true };
          }
        }
        setExpectedValues(Object.keys(ev).length ? ev : null);
      } else {
        setExpectedValues(null);
      }
    } catch (e) {
      console.error("workspace import failed", e);
    }
  };

  return (
    <div className="app">
      <header className="app-header">
        <h1>CQL Cleanroom</h1>
        <VersionBadge
          wheelVersion={boot.phase === "ready" ? boot.wheelVersion : null}
        />
        {statusNote && (
          <span
            className="status-note"
            data-testid="status-note"
            ref={(el) => {
              if (el) {
                setTimeout(() => setStatusNote(null), 6000);
              }
            }}
          >
            {statusNote}
          </span>
        )}
        <div className="workspace-actions" data-testid="workspace-actions">
          <button data-testid="share-btn" onClick={shareLink}>
            Share
          </button>
          <DropdownMenu label="Import" testId="import-menu">
            <button
              className="dropdown-item"
              data-testid="workspace-import"
              onClick={() => {
                fileRef.current?.click();
              }}
            >
              Workspace zip
            </button>
            <button
              className="dropdown-item"
              data-testid="bundle-import"
              onClick={() => bundleFileRef.current?.click()}
              title={`bundle import mode: ${bundleMode}`}
            >
              FHIR Bundle ({bundleMode})
            </button>
            <button
              className="dropdown-item"
              data-testid="madie-import"
              onClick={() => madieFileRef.current?.click()}
            >
              Measure package (MADiE)
            </button>
            <div className="dropdown-sep" />
            <div className="dropdown-header">Examples</div>
            <button
              className="dropdown-item"
              data-testid="load-example-cms69"
              onClick={() => void loadExample("cms69")}
            >
              CMS69 BMI Screening
            </button>
          </DropdownMenu>
          <DropdownMenu label="Export" testId="export-menu">
            <button
              className="dropdown-item"
              data-testid="workspace-export"
              onClick={exportZip}
            >
              Workspace zip
            </button>
            <button
              className="dropdown-item"
              data-testid="bundle-export"
              onClick={exportBundleFile}
            >
              FHIR Bundle
            </button>
            <button
              className="dropdown-item"
              data-testid="madie-export"
              onClick={exportMadieZip}
            >
              Measure package (MADiE)
            </button>
          </DropdownMenu>
          <button
            data-testid="bundle-mode"
            onClick={() =>
              setBundleMode((m) => (m === "merge" ? "replace" : "merge"))
            }
            title="bundle import mode"
          >
            mode: {bundleMode}
          </button>
          <button
            data-testid="workspace-reset"
            onClick={() => {
              // Await the clear BEFORE setting state — fire-and-forget
              // raced the debounced autosave, resurrecting stale prefs
              // (notably resultsTab) on the next reload.
              {
                // Reset state SYNCHRONOUSLY; clear IndexedDB in the
                // background. (The old order — await clearWorkspace()
                // THEN set defaults — let a slow IndexedDB clear land
                // its .then() seconds later, clobbering any state that
                // changed in between, e.g. an import.)
                setLibraries([{ name: "CleanroomDemo", text: DEFAULT_CQL }]);
                setActiveTab(0);
                setDataset({ resources: DEFAULT_DATASET_RESOURCES });
                setMeasure(DEFAULT_MEASURE);
                setExpectedValues(null);
                setLastReports(null);
                setViewConfig(null);
                setRunHistory([]);
                setResultsTab("cql");
                setCurrentRun(null);
                void clearWorkspace().catch(() => undefined);
              }
            }}
          >
            Reset
          </button>
           <input
            ref={fileRef}
            type="file"
            accept=".zip"
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void importZip(f);
              e.target.value = "";
            }}
          />
          <input
            ref={madieFileRef}
            type="file"
            accept=".zip"
            hidden
            data-testid="madie-import-input"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void importMadieZip(f);
              e.target.value = "";
            }}
          />
          <input
            ref={bundleFileRef}
            type="file"
            accept=".json,application/json"
            hidden
            data-testid="bundle-import-input"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void importBundleFile(f);
              e.target.value = "";
            }}
          />
        </div>
      </header>
      <main className="app-main" data-testid="app-main">
        <NavRail
          libraries={libraries.map((l, i) => ({
            name: l.name,
            hasError: libErrors[i] === true,
          }))}
          activeIndex={activeTab}
          entrypointIndex={entrypoint}
          onSelect={setActiveTab}
          onClose={closeTab}
          onAdd={addTab}
          onSetEntrypoint={setEntrypoint}
          onNavigateDataset={() => {
            document
              .querySelector("[data-testid=dataset-pane]")
              ?.scrollIntoView({ behavior: "smooth", block: "start" });
          }}
          onNavigateTerminology={() => {
            document
              .querySelector("[data-testid=terminology-pane]")
              ?.scrollIntoView({ behavior: "smooth", block: "start" });
          }}
          datasetActive={false}
          terminologyActive={false}
        />
        <div className="pane-col editor-col">
          <EditorPane
            text={active.text}
            onTextChange={updateActiveText}
            onDiagnostics={(diags) => {
              const idx = activeTabRef.current;
              setLibErrors((prev) => {
                const hasErr = (diags ?? []).some(
                  (d) => d.severity === "error" || d.code === "parse_error",
                );
                if ((prev[idx] ?? false) === hasErr) return prev;
                return { ...prev, [idx]: hasErr };
              });
            }}
          />
          <ParametersDrawer
            params={detectParams(mainLib.text).map((name) => ({
              name,
              value: paramValues[name] ?? "",
            }))}
            onChange={(next) => {
              const vals: Record<string, string> = {};
              for (const p of next) vals[p.name] = p.value;
              setParamValues(vals);
            }}
            open={paramsOpen}
            onToggle={() => setParamsOpen((o) => !o)}
          />
          <div className="results-drawer editor-drawer" data-testid="drawer-graph">
            <button
              className="drawer-toggle"
              data-testid="drawer-graph-toggle"
              onClick={() => setGraphOpen(!graphOpen)}
            >
              {graphOpen ? "▾" : "▸"} Visual editor
            </button>
            {graphOpen && (
              <div className="drawer-body">
                <p className="pane-hint">
                  The graph writes CQL only — Apply replaces the library
                  text after a parse round-trip. Full text→graph parsing is
                  future scope; the canvas starts from the default graph.
                </p>
                <GraphPane onApplyCql={(cql) => updateActiveText(cql)} />
              </div>
            )}
          </div>
          <div className="results-drawer editor-drawer" data-testid="drawer-fhirpath">
            <button
              className="drawer-toggle"
              data-testid="drawer-fhirpath-toggle"
              onClick={() => setFhirpathOpen(!fhirpathOpen)}
            >
              {fhirpathOpen ? "▾" : "▸"} FHIRPath scratchpad
            </button>
            {fhirpathOpen && (
              <div className="drawer-body">
                <FhirpathPane dataset={dataset} />
              </div>
            )}
          </div>
          <div className="results-drawer editor-drawer" data-testid="drawer-terminology">
            <button
              className="drawer-toggle"
              data-testid="drawer-terminology-toggle"
              onClick={() => setTerminologyOpen((o) => !o)}
            >
              {terminologyOpen ? "▾" : "▸"} Terminology (ValueSets)
            </button>
            {terminologyOpen && (
              <div className="drawer-body">
                <TerminologyPane
                  cqlDeclarations={activeDeclarations}
                  datasetValuesets={(dataset?.valueset_resources ?? []) as Array<Record<string, unknown>>}
                  workspaceValuesets={terminology.valuesets}
                  onWorkspaceChange={(valuesets) =>
                    setTerminology({ valuesets })
                  }
                />
              </div>
            )}
          </div>
        </div>
        <div className="pane-col run-col">
          <ResultsPane
            libraries={mainLibs}
            main={main}
            dataset={evalDataset}
            parameters={runtimeParameters}
            viewResult={viewResult}
            outputColumns={outputColumns}
            measure={measure}
            onReports={(reports) => {
              setLastReports(reports);
            }}
            activeTab={resultsTab}
            onTabChange={setResultsTab}
            viewSql={viewSql}
            reports={lastReports}
            onEvaluated={async (env) => {
              // §3.3: capture the run (row-shaped artifact + hashes).
              const [libHash, dsHash] = await Promise.all([
                computeLibraryHash(main.text),
                computeDatasetHash(
                  dataset?.resources?.length
                    ? { resources: dataset.resources as unknown[] }
                    : null,
                ),
              ]);
              const entry: RunEntry = {
                id: newRunId(),
                name: defaultRunName(Date.now()),
                createdAt: Date.now(),
                libraryHash: libHash,
                datasetHash: dsHash,
                artifact: artifactFromRows(env.rows, env.columns),
              };
              setRunHistory((h) => appendRun(h, entry, RUN_HISTORY_CAP));
              setCurrentRun({
                artifact: entry.artifact,
                libraryHash: libHash,
                datasetHash: dsHash,
              });
            }}
            measureSlot={
              <MeasurePane
                libraries={mainLibs}
                main={main}
                measure={measure}
                onChange={(m) => {
                  setMeasure(m);
                  setLastReports(null);
                }}
              />
            }
            viewSlot={
              <ViewPane
                measure={measure}
                measureReports={lastReports}
                viewConfig={viewConfig?.overrides ?? null}
                onViewConfigChange={(overrides) => setViewConfig({ overrides })}
                onSql={setViewSql}
                onResult={setViewResult}
              />
            }
            evidenceSlot={
              <RunCompare
                runHistory={runHistory}
                currentArtifact={currentRun?.artifact ?? null}
                currentLibraryHash={currentRun?.libraryHash ?? null}
                currentDatasetHash={currentRun?.datasetHash ?? null}
                onDeleteRun={(id) =>
                  setRunHistory((h) => h.filter((r) => r.id !== id))
                }
                onRenameRun={(id, name) =>
                  setRunHistory((h) =>
                    h.map((r) => (r.id === id ? { ...r, name } : r)),
                  )
                }
              />
            }
            testsSlot={
              <TestsPane
                libraries={mainLibs}
                main={main}
                dataset={evalDataset}
                outputColumns={outputColumns}
                populationCodes={populationCodes}
                expectedValues={expectedValues}
                onExpectedValuesChange={setExpectedValues}
                measure={measure}
              />
            }
          />
        </div>
        <div className="pane-col side-col">
          <DatasetPane
            dataset={dataset}
            onDatasetChange={setDataset}
            onEditResource={(index) => {
              const r = dataset?.resources?.[index];
              if (r && typeof r === "object") {
                setBuilderPrefill((prev) => ({
                  resource: r as Record<string, unknown>,
                  nonce: (prev?.nonce ?? 0) + 1,
                }));
              }
            }}
            onAddForPatient={(patientId) => {
              setBuilderPrefill(null);
              setBuilderContext({ patientId, nonce: Date.now() });
            }}
          />
          <ResourceBuilderPane
            onAddResource={(resource) => {
              const resources = [...(dataset?.resources ?? []), resource];
              setDataset(dataset ? { ...dataset, resources } : { resources });
              setBuilderPrefill(null);
              setBuilderContext(null);
            }}
            prefill={builderPrefill}
            context={builderContext}
            dataset={dataset}
          />
          <TerminologyPane
            cqlDeclarations={activeDeclarations}
            datasetValuesets={(dataset?.valueset_resources ?? []) as Array<Record<string, unknown>>}
            workspaceValuesets={terminology.valuesets}
            onWorkspaceChange={(valuesets) =>
              setTerminology({ valuesets })
            }
          />
        </div>
      </main>
      <BootOverlay state={boot} />
    </div>
  );
}
