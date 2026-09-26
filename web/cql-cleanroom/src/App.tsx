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
import { coerceParam, detectParams } from "./lib/params";
import { importMadiePackage } from "./lib/madiePackage";
import { exportMadiePackage } from "./lib/madieExport";
import {
  buildShareUrl,
  decodeShareFragment,
  type SharePayload,
} from "./lib/share";
import {
  ResultsConsole,
  type ConsoleTab,
  type ConsoleContext,
  type ConsolePlacement,
} from "./components/ResultsConsole";
import { MrOutput, useRunDiff } from "./components/MeasureReportOutput";
import { ViewOutputPanel } from "./components/ViewOutput";
import { TestsPane } from "./components/TestsPane";
import { DatasetPane } from "./components/DatasetPane";
import { ResourceBuilderPane } from "./components/ResourceBuilderPane";
import {
  exportBundle,
  importBundle,
  mergeDatasets,
} from "./lib/bundleIo";
import { DropdownMenu } from "./components/DropdownMenu";
import { ResourceContextMenu } from "./components/nav/ResourceContextMenu";
import type { ContextMenuState } from "./components/nav/ResourceContextMenu";
import {
  expectedItems,
  filterItems,
  libraryItems,
  measureItems,
  parameterItems,
  valuesetItems,
  viewItems,
} from "./lib/navSections";
import type { NavItem, NavSectionId } from "./lib/navSections";
import { buildDerivedView } from "./lib/viewDerivation";
import type { RunEntry } from "./state/workspace";
import { RUN_HISTORY_CAP } from "./state/workspace";
import {
  casesFromReports,
  expectedMapFromReports,
  reportsFromExpectedMap,
} from "./lib/expectedReports";
import {
  appendRun,
  artifactFromRows,
  datasetHash as computeDatasetHash,
  defaultRunName,
  libraryHash as computeLibraryHash,
  newRunId,
} from "./lib/runHistory";
import { GraphPane } from "./components/GraphPane";
import { Splitter } from "./components/Splitter";
import { EditorTabs } from "./components/tabs/EditorTabs";
import { TabHost } from "./components/tabs/hosts";
import {
  closeTab as closeEditorTabIn,
  neighborTabId,
  openTab as openTabIn,
  parseTabId,
  tabId,
  type EditorTab,
  type TabId,
  type TabKind,
} from "./lib/editorTabs";
import { renameLibrary } from "./lib/renameLibrary";
import type {
  DatasetSpec,
  LibraryText,
  FlattenViewResult,
  EvaluateResult,
  Diagnostics,
} from "./lib/protocol";
import {
  clearWorkspace,
  exportWorkspaceZip,
  importWorkspaceZip,
  loadWorkspace,
  newLibraryId,
  newMeasureId,
  saveWorkspace,
  withLibraryIds,
  type WorkspaceLibrary,
  type WorkspaceMeasureEntry,
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

// Stable empty bindings — ResultsPane's auto-eval effect keys on the
// parameters object; a fresh {} per render would re-arm the 2s debounce
// forever (each auto-run then clobbers the run-diff baseline).
const EMPTY_PARAM_VALUES: Record<string, string> = {};

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
  // WORKBENCH_V6: collections + active-measure selectors. Panes keep
  // their singleton-shaped props via the derived values below
  // (measure / paramValues / expectedValues / entrypoint index).
  const [libraries, setLibraries] = useState<WorkspaceLibrary[]>([
    { id: "lib_0", name: "CleanroomDemo", text: DEFAULT_CQL },
  ]);
  const [measures, setMeasures] = useState<WorkspaceMeasureEntry[]>([
    { id: "msr_0", mainLibraryId: "lib_0", resource: DEFAULT_MEASURE },
  ]);
  const [activeMeasureId, setActiveMeasureId] = useState<string | null>("msr_0");
  const [expectedReports, setExpectedReports] = useState<
    Record<string, Array<Record<string, unknown>>>
  >({});
  const [viewDefs, setViewDefs] = useState<
    Array<{ id: string; name: string; resource: Record<string, unknown> }>
  >([]);
  const [paramBindings, setParamBindings] = useState<
    Record<string, Record<string, string>>
  >({});
  const [activeTab, setActiveTab] = useState(0);
  // Per-library parse-error map (rail badges), fed by EditorPane
  // diagnostics for the active library. activeTabRef mirrors activeTab
  // so the callback always reads the CURRENT tab (the render-captured
  // activeTab goes stale across fast tab switches).
  const [libErrors, setLibErrors] = useState<Record<number, boolean>>({});
  // REORG phase 6d — maps-style nav: one section panel open at a time
  // (null = collapsed icon rail). Tests defaults open: dataset-loaded
  // is the e2e boot signal and must be visible.
  const [navPanel, setNavPanel] = useState<NavSectionId | null>("tests");
  const [navFilters, setNavFilters] = useState<
    Record<NavSectionId, string>
  >({
    measures: "",
    libraries: "",
    valuesets: "",
    parameters: "",
    tests: "",
    expected: "",
    views: "",
  });
  const [ctxMenu, setCtxMenu] = useState<ContextMenuState | null>(null);
  const [renaming, setRenaming] = useState<{ id: string; value: string } | null>(
    null,
  );
  // WORKBENCH_REORG phase 3 — editor tabs: one open resource per tab;
  // the tab's host replaces the library editor while it is active.
  const [editorTabs, setEditorTabs] = useState<EditorTab[]>([]);
  const [activeEditorTabId, setActiveEditorTabId] = useState<TabId | null>(null);
  // The library editor stays mounted while other tabs are active; this
  // pins which library model it keeps showing when it is hidden.
  const lastLibTabKeyRef = useRef<string>("library:solo");
  const activeTabRef = useRef(activeTab);
  activeTabRef.current = activeTab;
  const [dataset, setDataset] = useState<DatasetSpec | null>({
    resources: DEFAULT_DATASET_RESOURCES,
  });

  // --- v6 selectors: singleton-facing views over the collections ------
  const activeMeasureEntry =
    measures.find((m) => m.id === activeMeasureId) ?? measures[0] ?? null;
  const measure = activeMeasureEntry?.resource ?? null;
  // entrypoint index = position of the active measure's main library
  // (drives eval + the rail dot; falls back to the first library).
  const entrypoint = Math.max(
    0,
    libraries.findIndex((l) => l.id === activeMeasureEntry?.mainLibraryId),
  );
  const paramValues = useMemo(
    () => paramBindings[activeMeasureEntry?.id ?? ""] ?? EMPTY_PARAM_VALUES,
    [paramBindings, activeMeasureEntry?.id],
  );
  const expectedValues = useMemo(
    () => expectedMapFromReports(expectedReports[activeMeasureEntry?.id ?? ""]),
    [expectedReports, activeMeasureEntry?.id],
  );
  const updateParamValues = (next: Record<string, string>) => {
    if (!activeMeasureEntry) return;
    setParamBindings((pb) => ({ ...pb, [activeMeasureEntry.id]: next }));
  };
  const updateExpectedValues = (
    next: { [pid: string]: { [code: string]: boolean } } | null,
  ) => {
    if (!activeMeasureEntry) return;
    setExpectedReports((er) => ({
      ...er,
      [activeMeasureEntry.id]: reportsFromExpectedMap(next),
    }));
  };
  /** Replace the active measure's FHIR resource (identity keys kept). */
  const updateActiveMeasure = (
    resource: Record<string, unknown> | null,
  ) => {
    if (!activeMeasureEntry) return;
    // resource === null clears the populations (MeasurePane bootstrap
    // mode) but keeps the entry — it still pins the entrypoint library.
    setMeasures((ms) =>
      ms.map((m) =>
        m.id === activeMeasureEntry.id ? { ...m, resource } : m,
      ),
    );
  };
  /** Point the active measure's entry library at libraries[i]. */
  const setEntrypoint = (i: number) => {
    const lib = libraries[i];
    if (!lib || !activeMeasureEntry) return;
    setMeasures((ms) =>
      ms.map((m) =>
        m.id === activeMeasureEntry.id ? { ...m, mainLibraryId: lib.id } : m,
      ),
    );
  };
  // MeasureReports from the last evaluation (View drawer default source).
  const [lastReports, setLastReports] = useState<
    Array<Record<string, unknown>> | null
  >(null);
  // Editor-column visual-editor drawer (default collapsed).
  const [graphOpen, setGraphOpen] = useState(false);
  const [terminologyOpen, setTerminologyOpen] = useState(false);
  // Editor-column FHIRPath scratchpad retired (phase 4): the CQL
  // console's Run-Selection replaces it.
  const [consoleSelection, setConsoleSelection] = useState<string>("");
  // WORKBENCH_REORG phase 5 — console sub-tab pref + local run history.
  const [consoleTab, setConsoleTab] = useState<ConsoleTab>("results");
  const [runHistory, setRunHistory] = useState<RunEntry[]>([]);
  // Live auto-evaluation of the entrypoint library (app heartbeat):
  // the console Results/SQL/Diagnostics sub-tabs and the col2 panes
  // all render from this single run.
  const [evalResult, setEvalResult] = useState<EvaluateResult | null>(null);
  const [evalDiags, setEvalDiags] = useState<Diagnostics[] | null>(null);
  const [evalBusy, setEvalBusy] = useState(false);
  const evalBusyRef = useRef(false);
  const evalSeqRef = useRef(0);
  const [viewResult, setViewResult] = useState<FlattenViewResult | null>(null);
  // Row-shaped memberships + hashes of the LATEST evaluation (compare
  // target + drift reference). Cleared when inputs change. The read side
  // rides baselineArtifact via runHistory; currentRun itself is the
  // write-side holder (set by onEvaluated).
  const [, setCurrentRun] = useState<{
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
    sourceIndex?: number;
  } | null>(null);
  // WORKBENCH_REORG phase 5: editor/report column split (fr units),
  // persisted in prefs.layout so reloads keep the user's proportions.
  // REORG phase 6b: the console docks bottom (col1) or right (col2).
  const [col1Fr, setCol1Fr] = useState(1.1);
  const [consolePlacement, setConsolePlacement] =
    useState<ConsolePlacement>("bottom");
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
      const nextLibs = withLibraryIds([{ name, text: cql }, ...includeTabs]);
      setLibraries(nextLibs);
      setActiveTab(0);
      const msrId = newMeasureId([]);
      setMeasures([
        { id: msrId, mainLibraryId: nextLibs[0].id, resource: measure },
      ]);
      setActiveMeasureId(msrId);
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
      if (Object.keys(defaults).length && msrId) {
        setParamBindings((pb) => ({ ...pb, [msrId]: defaults }));
      }
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
      const sharedLibs = withLibraryIds(
        shared.libraries.map((l) => ({ name: l.name, text: l.text })),
      );
      setLibraries(sharedLibs);
      const activeIdx = Math.min(
        shared.activeIndex ?? 0,
        shared.libraries.length - 1,
      );
      setActiveTab(activeIdx);
      if (shared.measure) {
        const msrId = newMeasureId([]);
        setMeasures([
          {
            id: msrId,
            mainLibraryId: sharedLibs[activeIdx]?.id ?? sharedLibs[0].id,
            resource: shared.measure,
          },
        ]);
        setActiveMeasureId(msrId);
      }
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
        if (ws?.measures?.length) {
          setMeasures(ws.measures);
          setActiveMeasureId(ws.activeMeasureId ?? ws.measures[0].id);
        }
        if (ws?.expectedReports) {
          setExpectedReports(ws.expectedReports);
        }
        if (ws?.viewDefs?.length) {
          setViewDefs(ws.viewDefs);
        }
        if (ws?.paramBindings) {
          setParamBindings(ws.paramBindings);
        }
        if (ws?.viewConfig) {
          setViewConfig(ws.viewConfig);
        }
        if (ws && Array.isArray(ws.runHistory)) {
          setRunHistory(ws.runHistory);
        }
        if (
          ws &&
          (ws.activeTabPref === "results" ||
            ws.activeTabPref === "sql" ||
            ws.activeTabPref === "ast" ||
            ws.activeTabPref === "diags" ||
            ws.activeTabPref === "mr" ||
            ws.activeTabPref === "view")
        ) {
          setConsoleTab(ws.activeTabPref);
        }
        if (ws && ws.terminology?.valuesets?.length) {
          setTerminology(ws.terminology);
        }
        const layout = (
          ws?.prefs as {
            layout?: {
              col1Fr?: unknown;
              consolePlacement?: unknown;
            };
          } | null
        )?.layout;
        if (typeof layout?.col1Fr === "number" && layout.col1Fr >= 0.3) {
          setCol1Fr(Math.min(2.5, layout.col1Fr));
        }
        if (layout?.consolePlacement === "right") {
          setConsolePlacement("right");
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
        // Legacy cases stay in sync with authored expectedReports
        // (v5 zip interop); the reports themselves are first-class.
        cases: expectedReports[activeMeasureEntry?.id ?? ""]?.length
          ? (casesFromReports(
              expectedReports[activeMeasureEntry?.id ?? ""],
            ) as unknown[])
          : null,
        prefs: {
          layout: { col1Fr, consolePlacement },
        },
        measures,
        activeMeasureId,
        expectedReports,
        viewDefs,
        paramBindings,
        viewConfig,
        runHistory,
        activeTabPref: consoleTab,
        terminology,
      }).catch(() => undefined);
    }, 800);
    return () => clearTimeout(t);
  }, [
    libraries,
    dataset,
    measures,
    activeMeasureId,
    expectedReports,
    viewDefs,
    paramBindings,
    viewConfig,
    runHistory,
    consoleTab,
    terminology,
    restored,
    col1Fr,
    consolePlacement,
  ]);

  const active = libraries[activeTab] ?? libraries[0];
  // G1 invariant: evaluation always uses the ENTRYPOINT library, never
  // merely the edited tab (multi-library include flows).
  const mainLib = libraries[entrypoint] ?? active;
  // Stable identity across re-renders (same name+text → same object):
  // the auto-eval effect keys on [main, [main]] — a fresh object per
  // render would re-trigger the 2s debounce forever.
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

  // WORKBENCH_REORG phase 5 — the evaluation heartbeat lives in App so
  // the console sub-tabs AND the col2 panes render from one run.
  const canAutoEval = !!evalDataset && !!main?.text;
  const runEvaluation = async () => {
    if (!canAutoEval) return;
    const seq = ++evalSeqRef.current;
    evalBusyRef.current = true;
    setEvalBusy(true);
    setEvalDiags(null);
    try {
      const resp = await workerRequest({
        type: "evaluate_library",
        libraries: mainLibs,
        main,
        dataset: evalDataset,
        parameters: runtimeParameters,
        output_columns: outputColumns,
        emit_sql: true,
      });
      const env: EvaluateResult = JSON.parse(resp.envelope);
      if (seq !== evalSeqRef.current) return; // superseded by a newer run
      if (env.ok) {
        env.evaluated_at = Date.now();
        setEvalResult(env);
        // §3.3: capture the run (row-shaped artifact + hashes). The
        // artifact append is SYNCHRONOUS (the diff baseline must exist
        // before any follow-up run evaluates); hashes are patched in
        // afterwards (Web Crypto is async).
        const entry: RunEntry = {
          id: newRunId(),
          name: defaultRunName(Date.now()),
          createdAt: Date.now(),
          libraryHash: "",
          datasetHash: "",
          artifact: artifactFromRows(env.rows, env.columns),
        };
        setRunHistory((h) => appendRun(h, entry, RUN_HISTORY_CAP));
        setCurrentRun({
          artifact: entry.artifact,
          libraryHash: "",
          datasetHash: "",
        });
        const libText = main.text;
        const dsRes = dataset?.resources?.length
          ? { resources: dataset.resources as unknown[] }
          : null;
        void Promise.all([
          computeLibraryHash(libText),
          computeDatasetHash(dsRes),
        ]).then(([libHash, dsHash]) => {
          setRunHistory((h) =>
            h.map((r) =>
              r.id === entry.id
                ? { ...r, libraryHash: libHash, datasetHash: dsHash }
                : r,
            ),
          );
          setCurrentRun((c) =>
            c ? { ...c, libraryHash: libHash, datasetHash: dsHash } : c,
          );
        });
        // Materialize per-patient MeasureReports from the evaluation
        // rows — the MR pane's render source and the view's default.
        if (measure) {
          try {
            const repResp = await workerRequest({
              type: "measure_report_from_rows",
              measure,
              rows: env.rows,
              columns: env.columns,
            });
            const repEnv = JSON.parse(
              (repResp as { envelope: string }).envelope,
            ) as {
              ok: boolean;
              reports?: Array<Record<string, unknown>>;
            };
            setLastReports(repEnv.ok ? repEnv.reports ?? [] : null);
          } catch {
            setLastReports(null);
          }
        } else {
          setLastReports(null);
        }
      } else {
        setEvalDiags(env.diagnostics ?? []);
        setLastReports(null);
      }
    } finally {
      evalBusyRef.current = false;
      setEvalBusy(false);
    }
  };

  // AUTO-EVALUATE: recompute 2s after any input settles. U5: no manual
  // Evaluate — a first run that fails on a missing parameter still arms
  // (the effect re-fires when the parameter fills) so results auto-heal.
  useEffect(() => {
    if (!canAutoEval) return;
    const t = setTimeout(() => {
      if (evalBusyRef.current) return;
      void runEvaluation();
    }, 2000);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mainLibs, main, evalDataset, outputColumns, measure, runtimeParameters, canAutoEval]);

  // M1 write-through: Measure.library[] mirrors the entrypoint pin —
  // primary first, then the dependency closure of that library. Keeps
  // the exported Measure self-describing without touching the mapping.
  useEffect(() => {
    if (!measure || !mainLib || !restored || !activeMeasureEntry) return;
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
    const current = Array.isArray(measure.library)
      ? (measure.library as string[])
      : [];
    if (
      current.length === libraryUrls.length &&
      current.every((u, i) => u === libraryUrls[i])
    ) {
      return; // unchanged
    }
    setMeasures((ms) =>
      ms.map((m) =>
        m.id === activeMeasureEntry.id
          ? { ...m, resource: { ...m.resource, library: libraryUrls } }
          : m,
      ),
    );
  }, [entrypoint, libraries, mainLib, restored, measure, activeMeasureEntry]);


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
    const id = newLibraryId(libraries);
    setLibraries((libs) => [...libs, { id, name, text }]);
    setActiveTab(libraries.length);
  };

  const closeTab = (i: number) => {
    if (libraries.length === 1) return;
    const closed = libraries[i];
    setLibraries((libs) => libs.filter((_, idx) => idx !== i));
    setActiveTab((t) => (i < t ? t - 1 : Math.min(t, libraries.length - 2)));
    // Library ids are stable — only deleting the MAIN library re-pins
    // the active measure (nearest neighbor keeps eval defined).
    if (activeMeasureEntry && closed.id === activeMeasureEntry.mainLibraryId) {
      const neighbor = libraries[i + 1] ?? libraries[i - 1];
      if (neighbor) {
        setMeasures((ms) =>
          ms.map((m) =>
            m.id === activeMeasureEntry.id
              ? { ...m, mainLibraryId: neighbor.id }
              : m,
          ),
        );
      }
    }
  };


  const shareLink = () => {
    const payload: SharePayload = {
      format: "cql-cleanroom-share",
      version: 2,
      libraries: libraries.map((l) => ({ name: l.name, text: l.text })),
      activeIndex: activeTab,
      outputColumns: outputColumns,
      parameters: null,
      cases: null,
      measure,
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
      const nextLibs = withLibraryIds(
        pkg.libraries.map((l) => ({ name: l.name, text: l.text })),
      );
      setLibraries(nextLibs);
      setActiveTab(0);
      const msrId = newMeasureId([]);
      setMeasures([
        {
          id: msrId,
          mainLibraryId: nextLibs[0].id,
          resource: pkg.measure ?? DEFAULT_MEASURE,
        },
      ]);
      setActiveMeasureId(msrId);
      setExpectedReports((er) => ({ ...er, [msrId]: [] }));
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
      cases: expectedReports[activeMeasureEntry?.id ?? ""]?.length
        ? (casesFromReports(
            expectedReports[activeMeasureEntry?.id ?? ""],
          ) as unknown[])
        : null,
      prefs: {},
      measures,
      activeMeasureId,
      expectedReports,
      viewDefs,
      paramBindings,
      viewConfig,
      runHistory,
      activeTabPref: consoleTab,
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
      if (state.measures.length) {
        setMeasures(state.measures);
        setActiveMeasureId(state.activeMeasureId ?? state.measures[0].id);
      } else {
        // No measure in the zip — keep a default entry so the mapping
        // pane stays functional (v5 zips always carried one).
        const msrId = newMeasureId([]);
        setMeasures([
          { id: msrId, mainLibraryId: state.libraries[0]?.id ?? "lib_0", resource: DEFAULT_MEASURE },
        ]);
        setActiveMeasureId(msrId);
      }
      setExpectedReports(state.expectedReports ?? {});
      setViewDefs(state.viewDefs ?? []);
      setParamBindings(state.paramBindings ?? {});
      setViewConfig(state.viewConfig ?? null);
      setTerminology(state.terminology ?? { valuesets: [] });
    } catch (e) {
      console.error("workspace import failed", e);
    }
  };

  const libErrorById: Record<string, boolean> = {};
  libraries.forEach((l, i) => {
    if (libErrors[i]) libErrorById[l.id] = true;
  });

  const navLibItems = libraryItems(
    libraries,
    activeMeasureEntry?.mainLibraryId ?? null,
    libErrorById,
  );
  const navMeasureItems = measureItems(measures, activeMeasureId);
  const navValuesetItems = valuesetItems(
    terminology.valuesets,
    (dataset?.valueset_resources ?? []) as Array<Record<string, unknown>>,
  );
  const navParameterItems = parameterItems(
    detectParams(mainLib.text).map((name) => ({
      name,
      value: paramValues[name] ?? "",
    })),
  );
  const navExpectedItems = expectedItems(
    expectedReports[activeMeasureEntry?.id ?? ""] ?? [],
  );
  const navViewItems = viewItems(viewDefs);

  const navSectionModels: Record<
    NavSectionId,
    { title: string; items: NavItem[]; count: number }
  > = {
    measures: {
      title: "Measures",
      items: filterItems(navMeasureItems, navFilters.measures),
      count: navMeasureItems.length,
    },
    libraries: {
      title: "Libraries",
      items: filterItems(navLibItems, navFilters.libraries),
      count: navLibItems.length,
    },
    valuesets: {
      title: "Valuesets",
      items: filterItems(navValuesetItems, navFilters.valuesets),
      count: navValuesetItems.length,
    },
    parameters: {
      title: "Parameters",
      items: filterItems(navParameterItems, navFilters.parameters),
      count: navParameterItems.length,
    },
    tests: {
      title: "Tests",
      items: [],
      count: dataset?.resources?.length ?? 0,
    },
    expected: {
      title: "Expected Results",
      items: filterItems(navExpectedItems, navFilters.expected),
      count: navExpectedItems.length,
    },
    views: {
      title: "Views",
      items: filterItems(navViewItems, navFilters.views),
      count: navViewItems.length,
    },
  };

  const deleteMeasureEntry = (measureId: string) => {
    if (!window.confirm("Delete this measure (and its expectations/bindings)?"))
      return;
    setMeasures((ms) => ms.filter((m) => m.id !== measureId));
    setExpectedReports((er) => {
      if (!(measureId in er)) return er;
      const { [measureId]: _drop, ...rest } = er;
      return rest;
    });
    setParamBindings((pb) => {
      if (!(measureId in pb)) return pb;
      const { [measureId]: _drop, ...rest } = pb;
      return rest;
    });
    if (activeMeasureId === measureId) {
      setActiveMeasureId(measures.find((m) => m.id !== measureId)?.id ?? null);
    }
  };

  const deleteExpectedReport = (index: number) => {
    const msrId = activeMeasureEntry?.id;
    if (!msrId) return;
    setExpectedReports((er) => ({
      ...er,
      [msrId]: (er[msrId] ?? []).filter((_, i) => i !== index),
    }));
    // Keep the legacy bool-map carrier in sync (evaluated diff view).
    const reports = (expectedReports[msrId] ?? []).filter(
      (_, i) => i !== index,
    );
    updateExpectedValues(expectedMapFromReports(reports));
  };

  const openEditorTab = (kind: TabKind, resourceId: string) => {
    const id = tabId(kind, resourceId);
    setEditorTabs((ts) => openTabIn(ts, { id, kind, resourceId }));
    setActiveEditorTabId(id);
  };

  const closeEditorTabById = (id: TabId) => {
    setEditorTabs((ts) => closeEditorTabIn(ts, id));
    if (activeEditorTabId === id) {
      setActiveEditorTabId(neighborTabId(editorTabs, id));
    }
  };

  // Seed one library tab once the workspace is known (fresh sessions
  // open on the active measure's entrypoint library).
  useEffect(() => {
    if (!restored || editorTabs.length > 0 || libraries.length === 0) return;
    const libId = activeMeasureEntry?.mainLibraryId ?? libraries[0].id;
    const id = tabId("library", libId);
    setEditorTabs([{ id, kind: "library", resourceId: libId }]);
    setActiveEditorTabId(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [restored, editorTabs.length, libraries, activeMeasureEntry]);

  const commitRename = () => {
    if (!renaming) return;
    const { id, value } = renaming;
    const name = value.trim();
    setRenaming(null);
    if (!name) return;
    const sep = id.indexOf(":");
    const kind = id.slice(0, sep);
    const resId = id.slice(sep + 1);
    if (kind === "measure") {
      setMeasures((ms) =>
        ms.map((m) =>
          m.id === resId && m.resource
            ? { ...m, resource: { ...m.resource, name } }
            : m,
        ),
      );
    } else if (kind === "view") {
      setViewDefs((vs) =>
        vs.map((v) => (v.id === resId ? { ...v, name } : v)),
      );
    } else if (kind === "library") {
      // Rewrites the CQL header + sibling includes; ids (and hence
      // measure.mainLibraryId links and open tabs) are unaffected.
      const next = renameLibrary(libraries, resId, name);
      if (next) {
        setLibraries(next);
      } else {
        setStatusNote(`invalid library name: ${name}`);
      }
    }
  };

  const selectNavItem = (item: NavItem) => {
    // Every nav item id is `${kind}:${resourceId}` — nav clicks open (or
    // focus) the matching editor tab. Library tabs also select the
    // underlying Monaco-adjacent library index.
    const { kind, resourceId } = parseTabId(item.id);
    if (kind === "library") {
      const idx = libraries.findIndex((l) => l.id === resourceId);
      if (idx >= 0) setActiveTab(idx);
    }
    if (kind === "measure") {
      setActiveMeasureId(item.meta?.measureId as string);
    }
    // REORG phase 6: all Expected Results items author the SAME grid
    // (one authored MeasureReport set per measure) — converge on one tab.
    openEditorTab(kind as TabKind, kind === "expected" ? "grid" : resourceId);
  };

  const openNavContext = (item: NavItem, x: number, y: number) => {
    const items: ContextMenuState["items"] = [];
    if (item.kind === "library") {
      items.push({
        label: "Set as entrypoint",
        onSelect: () => setEntrypoint(item.meta?.index as number),
      });
      items.push({
        label: "Rename library",
        onSelect: () => setRenaming({ id: item.id, value: item.label }),
      });
      if (libraries.length > 1) {
        items.push({
          label: "Delete library",
          danger: true,
          onSelect: () => closeTab(item.meta?.index as number),
        });
      }
    } else if (item.kind === "measure") {
      items.push({
        label: "Rename",
        onSelect: () =>
          setRenaming({
            id: item.id,
            value: item.label === "(unauthored)" ? "" : item.label,
          }),
      });
      items.push({
        label: "Delete measure",
        danger: true,
        onSelect: () => deleteMeasureEntry(item.meta?.measureId as string),
      });
    } else if (item.kind === "valueset" && item.meta?.source === "workspace") {
      items.push({
        label: "Delete valueset",
        danger: true,
        onSelect: () =>
          setTerminology({
            valuesets: terminology.valuesets.filter(
              (_, i) => i !== item.meta?.index,
            ),
          }),
      });
    } else if (item.kind === "expected") {
      items.push({
        label: "Delete expectation",
        danger: true,
        onSelect: () => deleteExpectedReport(item.meta?.index as number),
      });
    } else if (item.kind === "view") {
      items.push({
        label: "Rename",
        onSelect: () => setRenaming({ id: item.id, value: item.label }),
      });
      items.push({
        label: "Delete view",
        danger: true,
        onSelect: () =>
          setViewDefs((vs) => vs.filter((_, i) => i !== item.meta?.index)),
      });
    } else if (item.kind === "parameter") {
      items.push({
        label: "Open parameter tab",
        onSelect: () => openEditorTab("parameter", item.meta?.name as string),
      });
    }
    if (items.length) setCtxMenu({ x, y, title: item.label, items });
  };

  // Editor tab bookkeeping (labels + active kind) for the strip + host.
  const tabLabels: Record<string, string> = {};
  for (const t of editorTabs) {
    switch (t.kind) {
      case "library":
        tabLabels[t.id] =
          libraries.find((l) => l.id === t.resourceId)?.name ?? t.resourceId;
        break;
      case "measure": {
        const m = measures.find((x) => x.id === t.resourceId);
        const name = (m?.resource as { name?: unknown } | null)?.name;
        tabLabels[t.id] =
          typeof name === "string" && name ? name : t.resourceId;
        break;
      }
      case "valueset":
        tabLabels[t.id] = t.resourceId.replace(/^(ws|ds):/, "");
        break;
      case "expected":
        tabLabels[t.id] =
          t.resourceId === "grid"
            ? "Expected Results"
            : t.resourceId.replace(/^Patient\//, "");
        break;
      case "view":
        tabLabels[t.id] =
          viewDefs.find((v) => v.id === t.resourceId)?.name || t.resourceId;
        break;
      case "test": {
        const m = /^row-(\d+)$/.exec(t.resourceId);
        if (m) {
          const idx = Number(m[1]);
          const rt = (
            dataset?.resources?.[idx] as { resourceType?: unknown } | undefined
          )?.resourceType;
          tabLabels[t.id] = `${typeof rt === "string" ? rt : "resource"} #${idx + 1}`;
        } else {
          tabLabels[t.id] = "New resource";
        }
        break;
      }
      default:
        tabLabels[t.id] = t.resourceId;
    }
  }
  const activeTabIsLibrary =
    !activeEditorTabId || parseTabId(activeEditorTabId).kind === "library";
  // Prior run = second-to-last history entry; falls back to the
  // in-flight currentRun artifact when history is pruned short.
  const baselineArtifact: import("./lib/runDiff").Artifact | null =
    runHistory.length >= 2
      ? runHistory[runHistory.length - 2].artifact.patients != null
        ? Object.fromEntries(
            Object.entries(
              runHistory[runHistory.length - 2].artifact.patients,
            ).map(([pid, p]) => [
              pid,
              (p as { populations: Record<string, boolean | null> })
                .populations,
            ]),
          )
        : null
      : null;
  const appRunDiff = useRunDiff(evalResult, baselineArtifact);
  // Latest-value mirror (same pattern as activeTabRef): which library
  // model the (possibly hidden) editor keeps showing.
  if (activeEditorTabId?.startsWith("library:")) {
    lastLibTabKeyRef.current = activeEditorTabId;
  }
  const activeLibTabKey = activeTabIsLibrary
    ? (activeEditorTabId ?? lastLibTabKeyRef.current)
    : lastLibTabKeyRef.current;

  // Resolve the non-library tab hosts' data from workspace state.
  const hostTab: EditorTab | null =
    activeEditorTabId && !activeTabIsLibrary
      ? (() => {
          const { kind, resourceId } = parseTabId(activeEditorTabId);
          return { id: activeEditorTabId, kind, resourceId };
        })()
      : null;
  const hostValueset = (() => {
    if (hostTab?.kind !== "valueset") return null;
    const m = /^([a-z]+):(.*)$/.exec(hostTab.resourceId);
    const src = m?.[1] ?? "ws";
    const url = m?.[2] ?? hostTab.resourceId;
    if (src === "ds") {
      return (
        ((dataset?.valueset_resources ?? []) as Array<Record<string, unknown>>).find(
          (v) => (v as { url?: string }).url === url,
        ) ?? null
      );
    }
    return (
      terminology.valuesets.find(
        (v) => (v as { url?: string }).url === url,
      ) ?? null
    );
  })();
  /** REORG phase 6: "+" on Views — create a default ViewDefinition
   *  (derived from the active measure) and open it as an editor tab. */
  const addStoredView = () => {
    const n = viewDefs.length + 1;
    const id = `vd_${Date.now().toString(36)}`;
    const entry = {
      id,
      name: `View ${n}`,
      resource: buildDerivedView(activeMeasureEntry?.resource ?? null, null),
    };
    setViewDefs((vs) => [...vs, entry]);
    openEditorTab("view", id);
  };
  /** "+" on Expected Results — open the authoring editor. Patients are
   *  added to the authored MeasureReports from inside the editor (6c):
   *  one individual MR per added patient, so no skeleton is needed. */
  const openExpectedEditor = () => {
    openEditorTab("expected", "grid");
  };

  // REORG phase 6b: the console's sub-tab set follows the ACTIVE editor
  // tab's kind — measure editors surface the Measure Report output,
  // view editors the ViewDefinition flatten, everything else the CQL
  // run pipeline (Results/SQL/AST/Diagnostics).
  const consoleContext: ConsoleContext =
    hostTab?.kind === "measure"
      ? "measure"
      : hostTab?.kind === "view"
        ? "view"
        : "library";
  const consoleNode = (
    <ResultsConsole
      libraries={mainLibs}
      main={main}
      dataset={evalDataset}
      parameters={runtimeParameters}
      outputColumns={outputColumns}
      selection={consoleSelection}
      result={evalResult}
      evalDiags={evalDiags}
      busy={evalBusy}
      baselineArtifact={baselineArtifact}
      context={consoleContext}
      mrOutput={
        <MrOutput
          result={evalResult}
          reports={lastReports}
          measure={measure}
          runDiff={appRunDiff}
        />
      }
      viewOutput={
        <ViewOutputPanel viewResult={viewResult} runDiff={appRunDiff} />
      }
      placement={consolePlacement}
      onPlacementChange={setConsolePlacement}
      activeTab={consoleTab}
      onTabChange={setConsoleTab}
    />
  );

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
            onClick={() => {              // Await the clear BEFORE setting state — fire-and-forget
              // raced the debounced autosave, resurrecting stale prefs
              // (notably resultsTab) on the next reload.
              {
                // Reset state SYNCHRONOUSLY; clear IndexedDB in the
                // background. (The old order — await clearWorkspace()
                // THEN set defaults — let a slow IndexedDB clear land
                // its .then() seconds later, clobbering any state that
                // changed in between, e.g. an import.)
                setLibraries([{ id: "lib_0", name: "CleanroomDemo", text: DEFAULT_CQL }]);
                setActiveTab(0);
                setDataset({ resources: DEFAULT_DATASET_RESOURCES });
                setMeasures([
                  { id: "msr_0", mainLibraryId: "lib_0", resource: DEFAULT_MEASURE },
                ]);
                setActiveMeasureId("msr_0");
                setExpectedReports({});
                setViewDefs([]);
                setLastReports(null);
                setViewConfig(null);
                setRunHistory([]);
                setEvalResult(null);
                setEvalDiags(null);
                setConsoleTab("results");
                setCurrentRun(null);
                setParamBindings({});
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
      <main
        className={`app-main ${consolePlacement === "right" ? "dock-right" : "dock-bottom"}`}
        data-testid="app-main"
        style={
          {
            "--nav-w": navPanel ? "264px" : "52px",
            "--col1-fr": `${col1Fr}fr`,
          } as React.CSSProperties
        }
      >
        <NavRail
          sections={{
            measures: { ...navSectionModels.measures, filter: navFilters.measures },
            libraries: { ...navSectionModels.libraries, filter: navFilters.libraries },
            valuesets: { ...navSectionModels.valuesets, filter: navFilters.valuesets },
            parameters: { ...navSectionModels.parameters, filter: navFilters.parameters },
            tests: {
              ...navSectionModels.tests,
              filter: navFilters.tests,
              showFilter: false,
            },
            expected: { ...navSectionModels.expected, filter: navFilters.expected },
            views: { ...navSectionModels.views, filter: navFilters.views },
          }}
          navPanel={navPanel}
          onNavPanelChange={setNavPanel}
          onFilterSection={(id, v) =>
            setNavFilters((f) => ({ ...f, [id]: v }))
          }
          onItemSelect={selectNavItem}
          onItemDoubleClick={(item) => {
            if (item.kind === "library") setEntrypoint(item.meta?.index as number);
          }}
          onItemContextMenu={openNavContext}
          renaming={renaming?.id ?? null}
          renameValue={renaming?.value ?? ""}
          onRenameChange={(v) =>
            setRenaming((r) => (r ? { ...r, value: v } : r))
          }
          onRenameCommit={commitRename}
          onRenameCancel={() => setRenaming(null)}
          onAddLibrary={addTab}
          onAddView={addStoredView}
          onAddExpected={openExpectedEditor}
          testsSlot={
            <DatasetPane
              dataset={dataset}
              onDatasetChange={setDataset}
              onEditResource={(index) => {
                const r = dataset?.resources?.[index];
                if (r && typeof r === "object") {
                  setBuilderPrefill((prev) => ({
                    resource: r as Record<string, unknown>,
                    nonce: (prev?.nonce ?? 0) + 1,
                    sourceIndex: index,
                  }));
                  openEditorTab("test", `row-${index}`);
                }
              }}
              onAddForPatient={(patientId) => {
                setBuilderPrefill(null);
                const nonce = Date.now();
                setBuilderContext({ patientId, nonce });
                openEditorTab("test", `new-${nonce}`);
              }}
              onAddNew={() => {
                setBuilderPrefill(null);
                setBuilderContext(null);
                openEditorTab("test", `new-${Date.now()}`);
              }}
            />
          }
        />
        <div
          className={`pane-col editor-col ${activeTabIsLibrary ? "" : "hosting-tab"}`}
        >
          <EditorTabs
            tabs={editorTabs}
            activeId={activeEditorTabId}
            labels={tabLabels}
            onSelect={(id) => setActiveEditorTabId(id as TabId)}
            onClose={(id) => closeEditorTabById(id as TabId)}
          />
          <EditorPane
            text={active.text}
            tabKey={activeLibTabKey}
            knownTabKeys={editorTabs
              .filter((t) => t.kind === "library")
              .map((t) => t.id)}
            onTextChange={updateActiveText}
            onSelectionChange={setConsoleSelection}
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
          {consolePlacement === "bottom" && consoleNode}
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
          {hostTab && (
            <TabHost
              tab={hostTab}
              measure={measure}
              onMeasureChange={updateActiveMeasure}
              measureLibs={mainLibs}
              measureMain={main}
              valueset={hostValueset}
              valuesetProvenance={
                hostTab.kind === "valueset" && hostValueset
                  ? hostTab.resourceId.startsWith("ds:")
                    ? "imported"
                    : "edited"
                  : undefined
              }
              onValuesetChange={(vs) => {
                const url = String(vs.url ?? "");
                setTerminology({
                  valuesets: [
                    ...terminology.valuesets.filter(
                      (v) => String((v as { url?: string }).url ?? "") !== url,
                    ),
                    vs,
                  ],
                });
              }}
              params={detectParams(mainLib.text).map((name) => ({
                name,
                value: paramValues[name] ?? "",
              }))}
              onParamsChange={(next) => {
                const vals: Record<string, string> = {};
                for (const p of next) vals[p.name] = p.value;
                updateParamValues(vals);
              }}
              builder={
                <ResourceBuilderPane
                  onAddResource={(resource) => {
                    const resources = [
                      ...(dataset?.resources ?? []),
                      resource,
                    ];
                    setDataset(
                      dataset ? { ...dataset, resources } : { resources },
                    );
                    setBuilderPrefill(null);
                    setBuilderContext(null);
                  }}
                  onReplaceResource={(index, resource) => {
                    const resources = [...(dataset?.resources ?? [])];
                    resources[index] = resource;
                    setDataset(
                      dataset ? { ...dataset, resources } : { resources },
                    );
                  }}
                  prefill={builderPrefill}
                  context={builderContext}
                  dataset={dataset}
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
                  onExpectedValuesChange={updateExpectedValues}
                  measure={measure}
                />
              }
              measureReports={lastReports}
              viewConfig={viewConfig?.overrides ?? null}
              onViewConfigChange={(overrides) => setViewConfig({ overrides })}
              onResult={setViewResult}
            />
          )}
        </div>
        {consolePlacement === "right" && (
          <Splitter value={col1Fr} onChange={setCol1Fr} />
        )}
        {consolePlacement === "right" && (
          <div className="pane-col run-col console-dock">{consoleNode}</div>
        )}
      </main>
      <ResourceContextMenu menu={ctxMenu} onClose={() => setCtxMenu(null)} />
      <BootOverlay state={boot} />
    </div>
  );
}
