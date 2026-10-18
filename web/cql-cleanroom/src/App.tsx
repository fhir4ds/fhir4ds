import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { groupDataset } from "./lib/datasetGroup";
import { buildCellGraph } from "./lib/cell-deps";
import { mergeDiskLibraries, mergeDiskValuesets, mergeDiskViews } from "./lib/navSections";
import { useWorkspaceFiles } from "./lib/useWorkspaceFiles";
import { composeCellClosure, splitCells } from "./lib/cells";
import { PatientDetailPanel } from "./components/nav/PatientDetailPanel";
import {
  BootOverlay,
  VersionBadge,
  useBootProgress,
  workerRequest,
} from "./components/BootOverlay";
import { EditorPane } from "./components/EditorPane";
import {
  setCqlCompletionContext,
  setCqlHoverContext,
} from "./lib/monaco-cql-language";
import { EvidencePopover } from "./components/EvidencePopover";
import { NavRail } from "./components/NavRail";
import { coerceParam, detectParams, joinInterval } from "./lib/params";
import { extractCqlSymbols } from "./lib/cqlSymbols";
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
import { MrPivot, MrFunnel, useRunDiff } from "./components/MeasureReportOutput";
import { ViewOutputPanel } from "./components/ViewOutput";
import { TestsPane } from "./components/TestsPane";
import { DatasetPane } from "./components/DatasetPane";
import { ResourceBuilderPane } from "./components/ResourceBuilderPane";
import {
  importBundle,
  mergeDatasets,
} from "./lib/bundleIo";
import { DropdownMenu, DropdownSubmenu } from "./components/DropdownMenu";
import { detectServer, terminologyStatus, type ServerMode } from "./lib/serverConnection";
import {
  loadTerminologySettings,
  saveTerminologySettings,
  clearTerminologyCache,
  resolveRuntimeValuesets,
  DEFAULT_TERMINOLOGY_SETTINGS,
  type TerminologySettings,
} from "./lib/terminologyRuntime";
import { NativeClickButton } from "./components/NativeClickButton";
import { ResourceContextMenu } from "./components/nav/ResourceContextMenu";
import type { ContextMenuState } from "./components/nav/ResourceContextMenu";
import {
  expectedItems,
  filterItems,
  libraryItems,
  measureItems,
  parameterItems,
  valuesetItems,
  valuesetLabel,
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
import { libraryClosure } from "./lib/libraryGraph";
import {
  appendRun,
  artifactFromRows,
  datasetHash as computeDatasetHash,
  defaultRunName,
  libraryHash as computeLibraryHash,
  newRunId,
} from "./lib/runHistory";
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
import {
  exampleAssetUrl,
  takePendingDefaultExample,
  urlDefaultExample,
} from "./lib/defaultExample";
import type {
  DatasetSpec,
  LibraryText,
  FlattenViewResult,
  EvaluateResult,
  Diagnostics,
  MeasureRowsResult,
} from "./lib/protocol";
import { deriveCompare } from "./lib/verifyCompare";
import {
  clearWorkspace,
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

/** S12: compact cell-table text for a value (JSON for objects, trimmed). */
function fmtCell(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "object") {
    try {
      return JSON.stringify(v);
    } catch {
      return String(v);
    }
  }
  return String(v);
}

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

/**
 * A workspace is PRISTINE when it still holds the untouched
 * CleanroomDemo scratch state a fresh install auto-saves (single
 * default library text, default measure, default 3-patient dataset,
 * no user-authored extras). Pristine workspaces may be replaced by a
 * host-declared default example; edited ones are never touched.
 */
function isPristineWorkspace(ws: {
  libraries?: Array<{ name?: string; text?: string }>;
  measures?: unknown[];
  viewDefs?: Array<{ id?: string; resource?: Record<string, unknown> }>;
  expectedReports?: Record<string, unknown>;
  dataset?: { resources?: unknown[] } | null;
  cases?: unknown[] | null;
}): boolean {
  const checks: Array<[string, boolean]> = [
    [
      "exactly one library",
      !!ws.libraries && ws.libraries.length === 1,
    ],
    [
      "library is untouched CleanroomDemo",
      ws.libraries?.length === 1 &&
        ws.libraries[0].name === "CleanroomDemo" &&
        ws.libraries[0].text === DEFAULT_CQL,
    ],
    ["at most one measure", !ws.measures || ws.measures.length <= 1],
    // The app AUTO-SEEDS two artifacts for the demo measure on every
    // restore (REORG 6d): one derived default ViewDefinition
    // ("vd_default", built by buildDerivedView from the untouched demo
    // measure) and an empty expected-reports slot keyed by "msr_0".
    // Auto-save persists them, so on the NEXT visit these checks would
    // fail even though the user never authored anything — permanently
    // blocking the host default example (CMS69). Tolerate exactly the
    // seeded shapes; any authored view/report content still fails.
    [
      "no user view definitions",
      !ws.viewDefs ||
        ws.viewDefs.length === 0 ||
        (ws.viewDefs.length === 1 &&
          ws.viewDefs[0]?.id === "vd_default" &&
          JSON.stringify(ws.viewDefs[0]?.resource) ===
            JSON.stringify(buildDerivedView(DEFAULT_MEASURE, null))),
    ],
    [
      "no user expected reports",
      !ws.expectedReports ||
        Object.keys(ws.expectedReports).length === 0 ||
        (Object.keys(ws.expectedReports).length === 1 &&
          ws.expectedReports["msr_0"] != null &&
          Array.isArray(ws.expectedReports["msr_0"]) &&
          (ws.expectedReports["msr_0"] as unknown[]).length === 0),
    ],
    ["no test cases", !ws.cases || ws.cases.length === 0],
    [
      "dataset is the default 3-patient set",
      (() => {
        const res = ws.dataset?.resources;
        if (
          !Array.isArray(res) ||
          res.length !== DEFAULT_DATASET_RESOURCES.length
        ) {
          return false;
        }
        return res.every(
          (r, i) =>
            JSON.stringify(r) === JSON.stringify(DEFAULT_DATASET_RESOURCES[i]),
        );
      })(),
    ],
  ];
  const failed = checks.filter(([, ok]) => !ok).map(([name]) => name);
  if (failed.length > 0) {
    // Diagnose why a host-declared default example (e.g. CMS69) did not
    // auto-load: an edited saved workspace is intentionally preserved.
    console.info(
      "[cql-cleanroom] saved workspace is not pristine; keeping it " +
        "(failed: " + failed.join(", ") + "). Use File > Open > Examples " +
        "to load an example manually.",
    );
    return false;
  }
  return true;
}

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
  // Parameter values are GLOBAL (v7): keyed by CQL parameter name, not
  // by measure — the declarations belong to the primary library.
  const [paramValues, setParamValues] = useState<Record<string, string>>({});
  const [activeTab, setActiveTab] = useState(0);
  // Per-library parse-error map (rail badges), fed by EditorPane
  // diagnostics for the active library. activeTabRef mirrors activeTab
  // so the callback always reads the CURRENT tab (the render-captured
  // activeTab goes stale across fast tab switches).
  const [libErrors, setLibErrors] = useState<Record<number, boolean>>({});
  // REORG phase 6d — maps-style nav: one section panel open at a time
  // (null = collapsed icon rail). Tests defaults open: the dataset tree
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
  // 6f: canonical URN authored onto expected MeasureReports (explicit
  // url wins; otherwise the cleanroom urn convention).
  const measureUrn = useMemo(
    () =>
      String(
        (measure?.url as string | undefined) ??
          `urn:cleanroom:measure:${String(measure?.name ?? "CleanroomMeasure")}`,
      ),
    [measure],
  );
  // entrypoint index = position of the active measure's main library
  // (drives eval + the rail dot; falls back to the first library).
  const entrypoint = Math.max(
    0,
    libraries.findIndex((l) => l.id === activeMeasureEntry?.mainLibraryId),
  );
  const expectedValues = useMemo(
    () => expectedMapFromReports(expectedReports[activeMeasureEntry?.id ?? ""]),
    [expectedReports, activeMeasureEntry?.id],
  );
  const updateExpectedValues = (
    next: { [pid: string]: { [code: string]: boolean } } | null,
  ) => {
    if (!activeMeasureEntry) return;
    setExpectedReports((er) => ({
      ...er,
      [activeMeasureEntry.id]: reportsFromExpectedMap(next, measureUrn),
    }));
  };
  /** 6f: one-click "capture current run as expected" — the console's
   *  Measure Report tab writes the last run's populations into the
   *  authored expected reports for the active measure. */
  const captureExpectedFromRun = () => {
    if (!activeMeasureEntry || !lastReports?.length) return;
    const map = expectedMapFromReports(lastReports);
    if (!map) return;
    setExpectedReports((er) => ({
      ...er,
      [activeMeasureEntry.id]: reportsFromExpectedMap(map, measureUrn),
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
  /** Point the active measure's primary library at a library id (6f).
   *  The single write path — the nav double-click, context menu and the
   *  MeasurePane picker all land here. */
  const setMainLibrary = (libId: string) => {
    if (!activeMeasureEntry) return;
    setMeasures((ms) =>
      ms.map((m) =>
        m.id === activeMeasureEntry.id ? { ...m, mainLibraryId: libId } : m,
      ),
    );
  };
  const setEntrypoint = (i: number) => {
    const lib = libraries[i];
    if (lib) setMainLibrary(lib.id);
  };
  // MeasureReports from the last evaluation (View drawer default source).
  const [lastReports, setLastReports] = useState<
    Array<Record<string, unknown>> | null
  >(null);
  // Editor-column visual-editor drawer (default collapsed).
  const [graphOpen, setGraphOpen] = useState(false);
  // Editor-column FHIRPath scratchpad retired (phase 4): the CQL
  // console's Run-Selection replaces it.
  const [consoleSelection, setConsoleSelection] = useState<string>("");
  // WORKBENCH_REORG phase 5 — console sub-tab pref + local run history.
  const [consoleTab, setConsoleTab] = useState<ConsoleTab>("results");
  const [runHistory, setRunHistory] = useState<RunEntry[]>([]);
  // REORG 6g: which run the console displays. null = follow latest;
  // picking an older run pins it until a new MANUAL run overrides.
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  // Live auto-evaluation of the entrypoint library (app heartbeat):
  // the console Results/SQL/Diagnostics sub-tabs and the col2 panes
  // all render from this single run.
  const [evalResult, setEvalResult] = useState<EvaluateResult | null>(null);
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
  // S2: workspace-file openers into native editor tabs.
  const openWorkspaceCql = (name: string, text: string) => {
    const idx = libraries.findIndex((l) => l.name === name);
    if (idx >= 0) {
      setLibraries((libs) => {
        const next = [...libs];
        next[idx] = { ...next[idx], text };
        return next;
      });
    } else {
      setLibraries((libs) => [
        ...libs,
        { id: name.toLowerCase(), name, text },
      ]);
    }
    // Editor tabs are the modern surface — open/select the library tab.
    openEditorTab("library", name);
    setStatusNote(`opened workspace library ${name}`);
  };
  const openWorkspaceValueset = (name: string, jsonText: string) => {
    try {
      const vs = JSON.parse(jsonText) as Record<string, unknown>;
      const url = typeof vs.url === "string" ? vs.url : `ws:${name}`;
      setTerminology((t) => ({
        valuesets: [
          ...t.valuesets.filter((v) => String((v as { url?: string }).url ?? "") !== url),
          vs,
        ],
      }));
      openEditorTab("valueset", `ws:${url}`);
      setStatusNote(`opened workspace valueset ${name}`);
    } catch {
      setStatusNote(`valueset ${name} is not valid JSON`);
    }
  };

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
  // REORG 6e: pinned editor/console rows (dock-bottom) — editor top
  // ~2/3, console bottom ~1/3, adjustable; persisted in prefs.layout.
  const [editorFr, setEditorFr] = useState(2);
  // Seconds between auto-recalcs (0 = off → manual Run only).
  const [recalcSeconds, setRecalcSeconds] = useState(2);
  // REORG 6e: Tests L3 drill-in — which patient's detail panel is slid
  // out over the Tests list (null = L2).
  const [focusedPid, setFocusedPid] = useState<string | null>(null);
  // REORG 6h: resizable L2 panel / L3 detail widths (px), persisted in
  // localStorage — chrome, not workspace data.
  const [navWidths, setNavWidths] = useState<{ panel: number; detail: number }>(
    () => {
      try {
        const raw = localStorage.getItem("cleanroom:nav-widths");
        if (raw) {
          const p = JSON.parse(raw) as { panel?: number; detail?: number };
          return {
            panel: typeof p.panel === "number" ? p.panel : 198,
            detail: typeof p.detail === "number" ? p.detail : 284,
          };
        }
      } catch {
        /* fresh start */
      }
      return { panel: 198, detail: 284 };
    },
  );
  const updateNavWidths = (w: { panel: number; detail: number }) => {
    setNavWidths(w);
    try {
      localStorage.setItem("cleanroom:nav-widths", JSON.stringify(w));
    } catch {
      /* private mode */
    }
  };
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
  // c-cleanroom-redo S1: connected mode (additive; standalone = zero server
  // calls — automated e2e guards this). Server is terminology provider only.
  const [serverMode, setServerMode] = useState<ServerMode>({ kind: "standalone" });
  const [umlsReady, setUmlsReady] = useState(false);
  // Rider #2: per-field env-present flags from /health (booleans only).
  const [envFieldSet, setEnvFieldSet] = useState<{
    vsac: boolean;
    umls: boolean;
    fhirBase: boolean;
  }>({ vsac: false, umls: false, fhirBase: false });
  const [termSettings, setTermSettings] = useState<TerminologySettings>(DEFAULT_TERMINOLOGY_SETTINGS);
  const [termDiagnostics, setTermDiagnostics] = useState<string[]>([]); // surfaced via statusNote; kept for the editor strip + diagnostics pane
  const [termSettingsOpen, setTermSettingsOpen] = useState(false);
  // S2: workspace files + watcher (connected-only; data-hint NEVER
  // auto-reloads — locked decision 4: banner with explicit restart).
  const [wsChanged, setWsChanged] = useState<Set<string>>(new Set());
  const [wsDataHint, setWsDataHint] = useState(false);
  // S16 item 3: evidence popover for clicked cell-table rows.
  const [cellEvidence, setCellEvidence] = useState<{
    patientId: string;
    define: string;
    evidence: import("./lib/protocol").EvidenceResult | null;
  } | null>(null);
  // S6: disk trees feed the TYPE drawers (Workspace rail dissolves).
  const wsFiles = useWorkspaceFiles(serverMode.kind === "connected");
  // Watcher reload hook-up (the WS effect's closure would go stale —
  // keep the latest reload on a ref).
  const wsFilesReloadRef = useRef<(() => void) | null>(null);
  wsFilesReloadRef.current = wsFiles.reload;
  useEffect(() => {
    if (serverMode.kind !== "connected") return;
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    let ws: WebSocket | null = null;
    try {
      ws = new WebSocket(`${proto}//${location.host}/api/events`);
    } catch {
      return;
    }
    ws.onmessage = (msg) => {
      try {
        const ev = JSON.parse(msg.data as string) as { kind?: string; paths?: string[] };
        if (ev.kind === "changed" && Array.isArray(ev.paths)) {
          setWsChanged((prev) => new Set([...prev, ...ev.paths!]));
          // S6 Muse: new/renamed/deleted files must appear without a page
          // reload — watcher events re-list the disk trees.
          wsFilesReloadRef.current?.();
        } else if (ev.kind === "data-hint") {
          setWsDataHint(true);
        }
      } catch {
        /* ignore malformed frames */
      }
    };
    return () => { try { ws?.close(); } catch { /* noop */ } };
  }, [serverMode.kind]);
  useEffect(() => {
    let cancelled = false;
    void detectServer().then((m) => {
      if (cancelled) return;
      setServerMode(m);
      if (m.kind === "connected") {
        void terminologyStatus().then((s) => {
          if (cancelled) return;
          setUmlsReady(s?.api_key_set === true);
          setEnvFieldSet({
            vsac: s?.vsac_api_key_set === true,
            umls: s?.umls_api_key_set === true,
            fhirBase: s?.fhir_base_url_set === true,
          });
        });
        void loadTerminologySettings().then((s) => {
          if (!cancelled) setTermSettings(s);
        });
      }
    });
    return () => { cancelled = true; };
  }, []);

  // S1R P2 (user refinement): pre-run valueset resolution — declared urls
  // missing from the workspace retrieve (Settings-configured source, cache
  // beneath) and MATERIALIZE as editable workspace files (IndexedDB, Q2).
  // Workspace valuesets keep precedence; unresolved urls surface as typed
  // diagnostics. Runs for BOTH engines (dataset-merge layer = mode-uniform).
  const termResolveKey = `${serverMode.kind}:${terminology.valuesets.length}:${libraries.map((l) => l.text.length).join(",")}`;
  useEffect(() => {
    if (serverMode.kind !== "connected") return;
    let cancelled = false;
    const wsUrls = new Set(
      terminology.valuesets
        .map((v) => (typeof v?.url === "string" ? v.url : null))
        .filter(Boolean) as string[],
    );
    // Compose the library text from open libraries (declared urls scan).
    const libText = libraries.map((l) => l.text).join("\n");
    void resolveRuntimeValuesets(libText, wsUrls, termSettings, serverMode).then((r) => {
      if (cancelled) return;
      setTermDiagnostics(r.unresolved);
      if (r.hydrated.length) {
        setTerminology((t) => {
          const have = new Set(
            t.valuesets
              .map((v) => (typeof v?.url === "string" ? v.url : null))
              .filter(Boolean) as string[],
          );
          const add = r.hydrated.filter((v) => !have.has(String(v.url)));
          if (!add.length) return t;
          return { valuesets: [...t.valuesets, ...add] };
        });
        setStatusNote(
          `retrieved ${r.hydrated.length} valueset${r.hydrated.length === 1 ? "" : "s"} into the workspace`,
        );
      } else if (r.unresolved.length) {
        setStatusNote(
          `valueset not retrievable: ${r.unresolved[0]} — check Settings terminology source`,
        );
      }
    });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [termResolveKey, termSettings, serverMode.kind]);

  const fileRef = useRef<HTMLInputElement | null>(null);
  const madieFileRef = useRef<HTMLInputElement | null>(null);
  // S18 rider: MADiE TEST-CASE zip import (File > Open). Connected mode
  // posts to /api/madie/import-tests (workspace data/ + expected store);
  // standalone reports a typed pointer to connect a server.
  const madieTestsFileRef = useRef<HTMLInputElement | null>(null);
  const importMadieTestsZip = async (file: File) => {
    if (serverMode.kind !== "connected") {
      setStatusNote("MADiE test-case import needs a connected server workspace (File > Open works once a devserver serves this page)");
      return;
    }
    try {
      const b64 = await new Promise<string>((resolve, reject) => {
        const fr = new FileReader();
        fr.onload = () => {
          const s = String(fr.result);
          resolve(s.slice(s.indexOf(",") + 1));
        };
        fr.onerror = () => reject(fr.error);
        fr.readAsDataURL(file);
      });
      const res = await fetch("/api/madie/import-tests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ zip_base64: b64 }),
      });
      const j = (await res.json()) as {
        data?: { ok?: boolean; cases?: string[]; expected?: string[]; diagnostics?: { message?: string }[] };
        ok?: boolean;
        diagnostics?: { message?: string }[];
      };
      const d = (j?.data ?? j) as {
        ok?: boolean;
        cases?: string[];
        expected?: string[];
        diagnostics?: { message?: string }[];
      } | undefined;
      if (d?.ok === false) {
        setStatusNote(`test-case import failed: ${d?.diagnostics?.[0]?.message ?? "unknown"}`);
        return;
      }
      setStatusNote(`imported test cases: ${d?.cases?.length ?? 0} cases, ${d?.expected?.length ?? 0} expectations (restart kernel to load data)`);
    } catch (e) {
      setStatusNote(`test-case import failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  // Built-in eCQM example (CMS69 conformance bundle: 62 patients,
  // 22 ValueSets, real CQL). Loaded from public/examples/.
  const loadExample = async (example: string) => {
    try {
      // Resolve against the BUNDLE's asset base, not the document: inside
      // the website embed the document is a docs page and relative
      // fetches 404 into the SPA HTML fallback (r.json() then dies on
      // the DOCTYPE). See exampleAssetUrl in lib/defaultExample.ts.
      const base = exampleAssetUrl(`examples/${example}`);
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
      if (Object.keys(defaults).length) {
        setParamValues(defaults);
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
        // Host-declared default example (web component sets "cms69";
        // standalone app honors ?example=). Fires when the workspace is
        // absent OR still pristine (the untouched CleanroomDemo scratch
        // state a fresh install auto-saves) — so returning embed
        // visitors who never edited anything still get the featured
        // example, while real work is never clobbered. Share fragments
        // returned early above.
        if (!ws || !ws.libraries?.length || isPristineWorkspace(ws)) {
          const defaultExample =
            takePendingDefaultExample() ?? urlDefaultExample();
          if (defaultExample) {
            void loadExample(defaultExample);
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
        if (ws?.paramValues) {
          setParamValues(ws.paramValues);
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
            ws.activeTabPref === "mr" ||
            ws.activeTabPref === "funnel" ||
            ws.activeTabPref === "view")
        ) {
          // legacy "diags" prefs aren't restored — Results owns errors
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
              editorFr?: unknown;
              recalcSeconds?: unknown;
            };
          } | null
        )?.layout;
        if (typeof layout?.col1Fr === "number" && layout.col1Fr >= 0.3) {
          setCol1Fr(Math.min(2.5, layout.col1Fr));
        }
        if (layout?.consolePlacement === "right") {
          setConsolePlacement("right");
        }
        if (typeof layout?.editorFr === "number" && layout.editorFr >= 0.3) {
          setEditorFr(Math.min(2.5, layout.editorFr));
        }
        if (typeof layout?.recalcSeconds === "number") {
          setRecalcSeconds(
            layout.recalcSeconds > 0
              ? Math.min(10, Math.max(0.5, layout.recalcSeconds))
              : 0,
          );
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
          layout: { col1Fr, consolePlacement, editorFr, recalcSeconds },
        },
        measures,
        activeMeasureId,
        expectedReports,
        viewDefs,
        paramValues,
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
    paramValues,
    viewConfig,
    runHistory,
    consoleTab,
    terminology,
    restored,
    col1Fr,
    consolePlacement,
    editorFr,
    recalcSeconds,
  ]);

  const active = libraries[activeTab] ?? libraries[0];
  // G1 invariant: measure surfaces (MR/funnel/expected) always pin to
  // the ENTRYPOINT library, never merely the edited tab.
  const mainLib = libraries[entrypoint] ?? active;

  // S19: the measure mapping may reference defines from ANOTHER library
  // (stale import, default measure vs CMS125 demo, etc.) — filter to
  // expressions the CURRENT main library actually defines so evidence
  // and population runs never request unknown output columns.
  const effectiveOutputColumns = useMemo(() => {
    const cols = outputColumnsFromMeasure(measure);
    if (!cols) return null;
    const declared = new Set(
      extractCqlSymbols(mainLib?.text ?? "").defines.map((d) => d.name),
    );
    const filtered: Record<string, string> = {};
    for (const [code, define] of Object.entries(cols)) {
      if (declared.has(define)) filtered[code] = define;
    }
    return Object.keys(filtered).length ? filtered : null;
  }, [measure, mainLib?.text]);
  // REORG 6j — runs follow the ACTIVE library tab: opening/executing a
  // specific library evaluates and displays THAT library's output.
  // Host tabs (measure/params/valuesets/…) and the hidden editor fall
  // back to the entrypoint so the measure heartbeat stays truthful.
  const activeTabIsLibrary =
    !activeEditorTabId || parseTabId(activeEditorTabId).kind === "library";
  const runLib = activeTabIsLibrary ? active : mainLib;
  const runIsEntrypoint = runLib === mainLib;
  // Stable identity across re-renders (same name+text → same object):
  // the auto-eval effect keys on [main, [main]] — a fresh object per
  // render would re-trigger the 2s debounce forever.
  const main = useMemo<LibraryText>(
    () => ({ name: runLib.name, text: runLib.text }),
    [runLib.name, runLib.text],
  );
  const mainLibs = useMemo<LibraryText[]>(() => [main], [main]);
  // 6f: the primary library's include closure + valueset declarations,
  // surfaced as read-only chips in the Measure editor.
  const measureClosure = useMemo(
    () =>
      mainLib
        ? libraryClosure(libraries, mainLib.name)
        : { libraryNames: [], valuesetDecls: [] },
    [libraries, mainLib],
  );
  // Visual editor step 2 — feed the ACTIVE library's world to the CQL
  // completion provider (defines/params/valuesets of the edited
  // library, include aliases → their texts, dataset resource types for
  // retrieves). Pushed on every edit; the provider extracts symbols
  // per keystroke locally.
  useEffect(() => {
    const name = active?.name ?? "";
    const closure = name ? libraryClosure(libraries, name).libraryNames : [];
    setCqlCompletionContext({
      text: active?.text ?? "",
      resourceTypes: [
        ...new Set(
          (dataset?.resources ?? [])
            .map((r) => String((r as Record<string, unknown>)?.resourceType ?? ""))
            .filter(Boolean),
        ),
      ],
      includedLibraries: Object.fromEntries(
        closure
          .map((n) => [n, libraries.find((l) => l.name === n)?.text ?? ""])
          .filter(([, t]) => t !== ""),
      ),
    });
  }, [active, dataset, libraries]);
  // Workspace terminology OVERRIDES dataset valueset_resources
  // (url-deduped — same precedence as evalDataset).
  const measureValuesetSources = useMemo(() => {
    const map: Record<string, "workspace" | "dataset"> = {};
    for (const v of dataset?.valueset_resources ?? []) {
      const url = (v as Record<string, unknown>)?.url;
      if (typeof url === "string") map[url] = "dataset";
    }
    for (const v of terminology.valuesets) {
      const url = (v as Record<string, unknown>)?.url;
      if (typeof url === "string") map[url] = "workspace";
    }
    return map;
  }, [dataset, terminology]);

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

  // Visual editor step 3 — hover evaluation: one cached all-defines
  // eval per (library, text, dataset, params); hovers after the first
  // are instant until an input changes.
  const hoverEvalRef = useRef<Promise<{
    columns: string[];
    rows: Array<Record<string, unknown>>;
  } | null> | null>(null);
  const hoverEvalKey = `${main.name}|${main.text}|${evalDataset?.resources?.length ?? 0}|${JSON.stringify(runtimeParameters)}`;
  useEffect(() => {
    hoverEvalRef.current = null;
  }, [hoverEvalKey]);
  useEffect(() => {
    const evaluateAll = () => {
      if (!evalDataset || !main.text) return Promise.resolve(null);
      if (hoverEvalRef.current) return hoverEvalRef.current;
      const p = workerRequest({
        type: "evaluate_library",
        libraries: mainLibs,
        main,
        dataset: evalDataset,
        parameters: runtimeParameters,
        emit_sql: false,
      })
        .then((resp) => JSON.parse((resp as { envelope: string }).envelope))
        .then((env) =>
          env.ok
            ? { columns: env.columns as string[], rows: env.rows }
            : null,
        )
        .catch(() => null);
      hoverEvalRef.current = p;
      return p;
    };
    setCqlHoverContext({ evaluateAll });
    return () => setCqlHoverContext(null);
  }, [main, mainLibs, evalDataset, runtimeParameters, hoverEvalKey]);

  // WORKBENCH_REORG phase 5 — the evaluation heartbeat lives in App so
  // the console sub-tabs AND the col2 panes render from one run.
  const canAutoEval = !!evalDataset && !!main?.text;

  /**
   * S5 cell execution — automatic target doctrine applies:
   * connected → server per-define via /api/evaluate (output_columns
   * narrowing, one evaluation per cell set; envelope→lines rendering);
   * standalone → in-browser worker evaluate_library on the composed
   * header+cells library. S8: RunMode removed upstream — every call runs
   * the closure; the _mode param is legacy-unused (kept for the shared
   * signature).
   */
  const runCells = useCallback(
    async (
      names: string[],
      _mode: "cell" | "cell_deps" | "to_here",
    ): Promise<Record<string, { ok: boolean; lines: string[] }>> => {
      const out: Record<
        string,
        { ok: boolean; lines: string[]; columns?: string[]; rows?: Array<Array<string>> }
      > = {};
      if (!main) return out;
      const graph = buildCellGraph(main.text);
      const cells = splitCells(main.text).cells;
      const composed = composeCellClosure(graph.header, cells, names);
      const libs: LibraryText[] = [{ name: main.name, text: composed }];
      // S8 bug fix: NEVER ship synthetic fallback names (cell-N) to
      // output_columns. Only cells whose text carries a real define are
      // nameable; raw-expression cells run WITHOUT narrowing (full
      // projection; the composed library defines the columns).
      const nameable = new Set(
        cells
          .filter((c) => c.text.match(/^\s*define\s/i))
          .map((c) => c.name),
      );
      if (serverMode.kind === "connected") {
        // Server: one evaluation per cell; narrowing ONLY for nameable
        // defines. Raw-expression cells evaluate the composed library
        // (all columns) — no synthetic column names ever requested.
        for (const n of names) {
          try {
            const res = await fetch("/api/evaluate", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                libraries: libs,
                library: main.name,
                ...(nameable.has(n) ? { output_columns: { [n]: n } } : {}),
                // S16: cell runs pass the SAME runtime parameters the
                // console run uses (UI-entered values override workspace
                // Parameters-resource defaults server-side).
                parameters: runtimeParameters,
              }),
            });
            const data = (await res.json()) as any;
            if (data?.ok === false) {
              out[n] = {
                ok: false,
                lines: [data?.diagnostics?.[0]?.message ?? "evaluation failed"],
              };
            } else {
              const cols: string[] = data?.columns ?? [];
              const rows: Record<string, unknown>[] = data?.rows ?? [];
              out[n] = {
                ok: true,
                lines: [
                  cols.join(" | "),
                  ...rows
                    .slice(0, 10)
                    .map((r) => cols.map((c) => String(r[c])).join(" | ")),
                ],
                // S12: structured result — the cell renders a real table.
                columns: cols,
                rows: rows.map((r) => cols.map((c) => fmtCell(r[c]))),
              };
            }
          } catch (err) {
            out[n] = {
              ok: false,
              lines: [
                `server run failed: ${err instanceof Error ? err.message : String(err)}`,
              ],
            };
          }
        }
        return out;
      }
      // Standalone: one worker evaluation of the composed library; each
      // cell's define columns slice per row. Dataset required — same
      // precondition as the heartbeat (typed note, not a crash).
      if (!evalDataset) {
        for (const n of names)
          out[n] = { ok: false, lines: ["no dataset loaded — load data to run cells"] };
        return out;
      }
      try {
        const resp = await workerRequest({
          type: "evaluate_library",
          libraries: libs,
          main: { name: main.name, text: composed },
          dataset: evalDataset,
          parameters: runtimeParameters,
        });
        const env: EvaluateResult | null = resp.envelope
          ? (JSON.parse(resp.envelope) as EvaluateResult)
          : null;
        if (!env || !env.ok) {
          const msg =
            env?.diagnostics?.[0]?.message ??
            (resp as { error?: string }).error ??
            "evaluation failed";
          for (const n of names) out[n] = { ok: false, lines: [msg] };
          return out;
        }
        const cols: string[] = env.columns ?? [];
        const rows = (env.rows ?? []) as Array<Record<string, unknown>>;
        for (const n of names) {
          const own = nameable.has(n) ? cols.filter((c) => c === n) : [];
          const useCols = own.length ? own : cols;
          out[n] = {
            ok: true,
            lines: [
              useCols.join(" | "),
              ...rows
                .slice(0, 10)
                .map((r) =>
                  useCols
                    .map((c) => String((r as Record<string, unknown>)[c] ?? ""))
                    .join(" | "),
                ),
            ],
            // S12: structured result — the cell renders a real table.
            columns: useCols,
            rows: rows.map((r) =>
              useCols.map((c) => fmtCell((r as Record<string, unknown>)[c])),
            ),
          };
        }
      } catch (err) {
        for (const n of names)
          out[n] = { ok: false, lines: [String(err)] };
      }
      return out;
    },
    [main, serverMode.kind, evalDataset, runtimeParameters],
  );

  const runEvaluation = async (manualServer = false) => {
    if (!manualServer && !canAutoEval) return;
    const seq = ++evalSeqRef.current;
    evalBusyRef.current = true;
    // Checkpoint ruling: automatic target — manual whole-library runs on
    // a connected server evaluate SERVER-side (no picker); the auto-recalc
    // heartbeat stays BROWSER; unreachable server → typed error (below).
    if (manualServer) {
      try {
        const res = await fetch("/api/evaluate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            libraries: mainLibs,
            library: main.name,
          }),
        });
        const b = (await res.json()) as EvaluateResult & {
          ok?: boolean;
          diagnostics?: { message: string }[];
        };
        if (seq !== evalSeqRef.current) return;
        if (b?.ok === false) {
          setStatusNote(
            `server run failed: ${b?.diagnostics?.[0]?.message ?? "unknown error"}`,
          );
          return;
        }
        b.evaluated_at = Date.now();
        setEvalResult(b);
        setStatusNote(
          `server run — ${b.patient_count} patients (${main.name})`,
        );
        // S18: the server run appends its OWN history entry (rows from
        // the SERVER dataset) so replay + evidence drill-in use the
        // correct origin seam.
        const serverEntry: RunEntry = {
          id: newRunId(),
          name: defaultRunName(Date.now()),
          createdAt: Date.now(),
          libraryHash: "",
          datasetHash: "",
          artifact: artifactFromRows(b.rows ?? [], b.columns ?? []),
          payload: {
            mode: "library",
            origin: "server",
            library: main.name,
            cql: main.text,
            rows: b.rows ?? [],
            columns: b.columns ?? [],
            column_types: b.column_types,
            ms: b.timing_ms?.evaluate ?? null,
          },
        };
        setRunHistory((h) => appendRun(h, serverEntry, RUN_HISTORY_CAP));
        setSelectedRunId(serverEntry.id);
      } catch (err) {
        if (seq === evalSeqRef.current) {
          setStatusNote(
            `server run failed: ${err instanceof Error ? err.message : String(err)}`,
          );
        }
      } finally {
        evalBusyRef.current = false;
      }
      return;
    }
    try {
      const resp = await workerRequest({
        type: "evaluate_library",
        libraries: mainLibs,
        main,
        dataset: evalDataset,
        parameters: runtimeParameters,
        // 6j: non-entrypoint targets have no population defines — the
        // engine returns ALL of that library's defines instead.
        output_columns: runIsEntrypoint ? effectiveOutputColumns : undefined,
        emit_sql: true,
      });
      const env: EvaluateResult = resp.envelope
        ? (JSON.parse(resp.envelope) as EvaluateResult)
        : // Worker hard-failure (no envelope): surface as an engine
          // diagnostic row instead of crashing auto-eval with
          // JSON.parse(undefined).
          ({
            ok: false,
            diagnostics: [
              {
                code: "worker_error",
                severity: "error",
                message:
                  (resp as { error?: string }).error ??
                  "engine worker failed without an envelope",
              },
            ],
          } as unknown as EvaluateResult);
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
          // REORG 6g: replay payload — Results/SQL/AST/CQL tabs all
          // render from the run's own snapshot, not live state.
          payload: {
            mode: "library",
            origin: "browser", // this entry IS the worker run
            library: runLib.name,
            cql: main.text,
            sql: env.sql,
            rows: env.rows,
            columns: env.columns,
            column_types: env.column_types,
            ms: env.timing_ms?.evaluate ?? null,
          },
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
        // 6j: only entrypoint runs carry population shape.
        if (measure && runIsEntrypoint) {
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
        setLastReports(null);
        // REORG 6g: failures are results too — replayable from the ring
        // (CQL + diagnostics). No artifact, so the diff baseline's
        // patients!=null guard skips them.
        setRunHistory((h) =>
          appendRun(
            h,
            {
              id: newRunId(),
              name: defaultRunName(Date.now()),
              createdAt: Date.now(),
              libraryHash: "",
              datasetHash: "",
              artifact: null,
              payload: {
                mode: "library",
                origin: "browser", // worker-failure entry IS browser-origin
                library: runLib.name,
                cql: main.text,
                diags: env.diagnostics ?? [],
              },
            },
            RUN_HISTORY_CAP,
          ),
        );
      }
    } finally {
      evalBusyRef.current = false;
    }
  };

  // AUTO-EVALUATE: recompute after any input settles (delay = the
  // settings' recalc delay; 0 = off → manual Run only). U5: no manual
  // Evaluate — a first run that fails on a missing parameter still arms
  // (the effect re-fires when the parameter fills) so results auto-heal.
  useEffect(() => {
    if (!canAutoEval || recalcSeconds <= 0) return;
    let t: ReturnType<typeof setTimeout>;
    const fire = () => {
      t = setTimeout(() => {
        // 6j: tab switches fire this effect while the PREVIOUS target's
        // run may still be in flight — reschedule instead of dropping,
        // or the display goes stale until the next input change.
        if (evalBusyRef.current) {
          fire();
          return;
        }
        void runEvaluation();
      }, recalcSeconds * 1000);
    };
    fire();
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mainLibs, main, evalDataset, effectiveOutputColumns, measure, runtimeParameters, canAutoEval, recalcSeconds]);

  // M1 write-through: Measure.library[] mirrors the entrypoint pin —
  // primary first, then the dependency closure of that library (6f: the
  // BFS lives in lib/libraryGraph). Keeps the exported Measure
  // self-describing without touching the mapping.
  useEffect(() => {
    if (!measure || !mainLib || !restored || !activeMeasureEntry) return;
    const libraryUrls = libraryClosure(libraries, mainLib.name).libraryNames.map(
      (n) => `urn:cleanroom:lib:${n}`,
    );
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
        // S18 rider-2: full-workspace carrier — extras ride along.
        views: viewDefs.map((v) => v.resource ?? { resourceType: "ViewDefinition", id: v.id, name: v.name }),
        expectedReports: (expectedReports[activeMeasureEntry?.id ?? ""] ?? []) as Array<Record<string, unknown>>,
        parameters: paramValues,
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
        // S18 rider: typed rejection with the File > Add pointer.
        setStatusNote(
          "not a MADiE measure package (no cql/*.cql entries) — for bundles or individual resources use File > Add (merge)",
        );
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
      // S18 Muse: full-workspace round-trip — restore the extras.
      if (pkg.extras.views.length) setViewDefs(pkg.extras.views.map((v, i) => ({ id: String(v.id ?? `view_${i}`), name: String(v.name ?? v.id ?? `View ${i + 1}`), resource: v })));
      if (pkg.extras.expectedReports.length) {
        setExpectedReports((er) => ({ ...er, [msrId]: pkg.extras.expectedReports }));
      }
      if (pkg.extras.parameters) {
        const restored: Record<string, string> = {};
        for (const [k, v] of Object.entries(pkg.extras.parameters)) {
          restored[k] = v == null ? "" : String(v);
        }
        setParamValues((pv) => ({ ...pv, ...restored }));
      }
      if (pkg.warnings.length) {
        setStatusNote(`imported with ${pkg.warnings.length} warning(s): ${pkg.warnings[0]}`);
      } else {
        setStatusNote(`imported measure package (${pkg.libraries.length} libraries, primary ${pkg.primary})`);
      }
    } catch (e) {
      setStatusNote(`package import failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  };



  // §3.4 Bundle export/import for the dataset.
  const bundleFileRef = useRef<HTMLInputElement | null>(null);


  // 6i.1: bundle import mode is a property of the ACTION (File > Open =
  // replace, File > Add / nav imports = merge), not a Settings toggle —
  // the menu item records its mode here before the file chooser opens.
  const bundleModeRef = useRef<"merge" | "replace">("merge");
  const importBundleFile = async (
    file: File,
    mode: "merge" | "replace",
  ) => {
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
        mode === "replace"
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
      setParamValues(state.paramValues ?? {});
      setViewConfig(state.viewConfig ?? null);
      setTerminology(state.terminology ?? { valuesets: [] });
    } catch (e) {
      console.error("workspace import failed", e);
    }
  };

  // #64: per-section ▾ imports — one hidden input re-armed per pick.
  const sectionImportInputRef = useRef<HTMLInputElement | null>(null);
  const sectionImportPickRef = useRef<{
    accept: string;
    cb: (f: File) => void;
  } | null>(null);
  const pickSectionImport = (accept: string, cb: (f: File) => void) => {
    sectionImportPickRef.current = { accept, cb };
    const input = sectionImportInputRef.current;
    if (input) {
      input.accept = accept;
      input.click();
    }
  };

  /** Single JSON object off disk, validated by the caller. */
  const readJsonObject = async (
    file: File,
  ): Promise<Record<string, unknown>> => {
    const parsed: unknown = JSON.parse(await file.text());
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      throw new Error("expected a JSON object");
    }
    return parsed as Record<string, unknown>;
  };

  const upsertLibraryText = (name: string, text: string) => {
    const i = libraries.findIndex((l) => l.name === name);
    if (i >= 0) {
      const next = [...libraries];
      next[i] = { ...next[i], text };
      setLibraries(next);
      setActiveTab(i);
    } else {
      setLibraries((libs) => [
        ...libs,
        { id: newLibraryId(libs), name, text },
      ]);
      setActiveTab(libraries.length);
    }
    setStatusNote(`imported library ${name}`);
  };

  const decodeBase64Text = (b64: string) =>
    new TextDecoder().decode(
      Uint8Array.from(atob(b64.replace(/\s+/g, "")), (c) => c.charCodeAt(0)),
    );

  // Expected ▾: authored MeasureReports (.json — single resource,
  // bare array, or Bundle) → the active measure's expected grid (same
  // rows_from_measure_reports path the editor used).
  const importExpectedBundle = async (file: File) => {
    if (!measure || populationCodes.length === 0) {
      setStatusNote(
        "expected import needs a Measure mapping with populations",
      );
      return;
    }
    try {
      const parsed: unknown = JSON.parse(await file.text());
      let reports: Array<Record<string, unknown>> = [];
      if (Array.isArray(parsed)) {
        reports = parsed.filter(
          (r) => (r as { resourceType?: string })?.resourceType === "MeasureReport",
        );
      } else if (
        parsed &&
        typeof parsed === "object" &&
        (parsed as { resourceType?: string }).resourceType === "Bundle"
      ) {
        const entries =
          ((parsed as { entry?: Array<{ resource?: Record<string, unknown> }> })
            .entry ?? []);
        reports = entries
          .map((e) => e.resource)
          .filter(
            (r): r is Record<string, unknown> =>
              !!r && r.resourceType === "MeasureReport",
          );
      } else if (
        parsed &&
        typeof parsed === "object" &&
        (parsed as { resourceType?: string }).resourceType === "MeasureReport"
      ) {
        reports = [parsed as Record<string, unknown>];
      }
      if (!reports.length) {
        setStatusNote("no MeasureReport resources found in file");
        return;
      }
      const resp = await workerRequest({
        type: "rows_from_measure_reports",
        reports,
        population_codes: populationCodes,
      });
      const env: MeasureRowsResult = JSON.parse(
        (resp as { envelope: string }).envelope,
      );
      if (!env.ok && !env.rows.length) {
        setStatusNote(
          env.diagnostics?.map((d) => d.message).join("; ") ??
            "expected import failed",
        );
        return;
      }
      const colToCode = new Map(
        populationCodes.map((c) => [c.replace(/-/g, "_"), c]),
      );
      const next: { [pid: string]: { [code: string]: boolean } } = {};
      for (const row of env.rows) {
        const pid = String(row.patient_id ?? "");
        if (!pid) continue;
        const codes: { [code: string]: boolean } = {};
        for (const [col, value] of Object.entries(row)) {
          const code = colToCode.get(col);
          if (code) codes[code] = value === true;
        }
        next[pid] = codes;
      }
      updateExpectedValues(Object.keys(next).length ? next : null);
      setStatusNote(`imported expected results for ${Object.keys(next).length} patient(s)`);
    } catch (e) {
      setStatusNote(
        `expected import failed: ${e instanceof Error ? e.message : String(e)}`,
      );
    }
  };

  const importParametersResource = async (file: File) => {
    try {
      const res = await readJsonObject(file);
      if (res.resourceType !== "Parameters") {
        setStatusNote("not a Parameters resource");
        return;
      }
      const declTypes = new Map(
        detectParams(mainLib.text).map((d) => [d.name, d.type]),
      );
      const values: Record<string, string> = {};
      let firstName: string | null = null;
      for (const p of (res.parameter as Array<Record<string, unknown>>) ?? []) {
        const name = typeof p?.name === "string" ? p.name : "";
        if (!name) continue;
        firstName ??= name;
        const period = p.valuePeriod as
          | { start?: unknown; end?: unknown }
          | undefined;
        if (period && typeof period.start === "string" && typeof period.end === "string") {
          // Restore the engine's interval text — DateTime params get the
          // inclusive end-day boundaries joinInterval writes on export.
          values[name] = joinInterval(
            declTypes.get(name),
            period.start,
            period.end,
          );
          continue;
        }
        for (const key of ["valueString", "valueCode"] as const) {
          const v = p[key];
          if (typeof v === "string") values[name] = v;
        }
        for (const key of ["valueInteger", "valueDecimal"] as const) {
          const v = p[key];
          if (typeof v === "number") values[name] = String(v);
        }
        if (typeof p.valueBoolean === "boolean") {
          values[name] = p.valueBoolean ? "true" : "false";
        }
      }
      if (!firstName) {
        setStatusNote("Parameters resource has no parameter entries");
        return;
      }
      setParamValues((pv) => ({ ...pv, ...values }));
      setStatusNote(`imported ${Object.keys(values).length} parameter value(s)`);
      if (detectParams(mainLib.text).some((d) => d.name === firstName)) {
        openEditorTab("parameter", firstName);
      }
    } catch (e) {
      setStatusNote(
        `Parameters import failed: ${e instanceof Error ? e.message : String(e)}`,
      );
    }
  };

  const handleNavImport = (section: NavSectionId, item: string) => {
    const json = ".json,application/json";
    switch (`${section}:${item}`) {
      case "libraries:library-cql":
        pickSectionImport(".cql,.txt,text/plain,text/cql", async (f) => {
          const base = f.name.replace(/\.[^.]*$/, "").replace(/[^A-Za-z0-9_ -]/g, "").trim();
          upsertLibraryText(base || "Imported", await f.text());
        });
        break;
      case "libraries:library-json":
        pickSectionImport(json, async (f) => {
          try {
            const lib = await readJsonObject(f);
            if (lib.resourceType !== "Library") {
              setStatusNote("not a FHIR Library resource");
              return;
            }
            const data = (
              (lib.content as Array<{ data?: unknown }> | undefined) ?? []
            ).find((a) => typeof a?.data === "string" && a.data.length > 0)
              ?.data as string | undefined;
            if (!data) {
              setStatusNote("Library has no base64 CQL content attachment");
              return;
            }
            const name =
              (typeof lib.name === "string" && lib.name) ||
              (typeof lib.title === "string" && lib.title) ||
              (typeof lib.id === "string" && lib.id) ||
              "Imported";
            upsertLibraryText(name, decodeBase64Text(data));
          } catch (e) {
            setStatusNote(
              `Library import failed: ${e instanceof Error ? e.message : String(e)}`,
            );
          }
        });
        break;
      case "measures:measure-json":
        pickSectionImport(json, async (f) => {
          try {
            const resource = await readJsonObject(f);
            if (resource.resourceType !== "Measure") {
              setStatusNote("not a Measure resource");
              return;
            }
            const id = newMeasureId(measures);
            setMeasures((ms) => [...ms, { id, mainLibraryId: active?.id ?? "lib_0", resource }]);
            setActiveMeasureId(id);
            openEditorTab("measure", id);
            setStatusNote(`imported Measure ${String(resource.name ?? resource.id ?? id)}`);
          } catch (e) {
            setStatusNote(
              `Measure import failed: ${e instanceof Error ? e.message : String(e)}`,
            );
          }
        });
        break;
      case "valuesets:valueset-json":
        pickSectionImport(json, async (f) => {
          try {
            const vs = await readJsonObject(f);
            if (vs.resourceType !== "ValueSet") {
              setStatusNote("not a ValueSet resource");
              return;
            }
            const url = typeof vs.url === "string" ? vs.url : "";
            if (!url) {
              setStatusNote("ValueSet needs a url");
              return;
            }
            setTerminology((t) => ({
              valuesets: [
                ...t.valuesets.filter(
                  (v) => String((v as { url?: string }).url ?? "") !== url,
                ),
                vs,
              ],
            }));
            openEditorTab("valueset", `ws:${url}`);
            setStatusNote(`imported ValueSet ${url}`);
          } catch (e) {
            setStatusNote(
              `ValueSet import failed: ${e instanceof Error ? e.message : String(e)}`,
            );
          }
        });
        break;
      case "parameters:parameters-json":
        pickSectionImport(json, (f) => void importParametersResource(f));
        break;
      case "views:view-json":
        pickSectionImport(json, async (f) => {
          try {
            const resource = await readJsonObject(f);
            if (resource.resourceType !== "ViewDefinition") {
              setStatusNote("not a ViewDefinition resource");
              return;
            }
            const id =
              typeof resource.id === "string" && resource.id
                ? resource.id
                : `vd_${Date.now().toString(36)}`;
            const name =
              (typeof resource.name === "string" && resource.name) ||
              (typeof resource.title === "string" && resource.title) ||
              `View ${viewDefs.length + 1}`;
            setViewDefs((vs) => [
              ...vs.filter((v) => v.id !== id),
              { id, name, resource },
            ]);
            openEditorTab("view", id);
            setStatusNote(`imported ViewDefinition ${name}`);
          } catch (e) {
            setStatusNote(
              `View import failed: ${e instanceof Error ? e.message : String(e)}`,
            );
          }
        });
        break;
      case "tests:resource-json":
        pickSectionImport(json, async (f) => {
          try {
            const resource = await readJsonObject(f);
            if (
              typeof resource.resourceType !== "string" ||
              typeof resource.id !== "string" ||
              !resource.id
            ) {
              setStatusNote("resource needs resourceType and id");
              return;
            }
            const current = (dataset?.resources ?? []) as Array<
              Record<string, unknown>
            >;
            const next = mergeDatasets(current, [resource]);
            setDataset(next.length ? { resources: next } : null);
            setStatusNote(`imported ${resource.resourceType}/${resource.id}`);
          } catch (e) {
            setStatusNote(
              `resource import failed: ${e instanceof Error ? e.message : String(e)}`,
            );
          }
        });
        break;
      case "tests:bundle-json":
        pickSectionImport(json, (f) => void importBundleFile(f, "merge"));
        break;
      case "expected:expected-json":
        pickSectionImport(json, (f) => void importExpectedBundle(f));
        break;
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
    detectParams(mainLib.text).map((d) => ({
      name: d.name,
      value: paramValues[d.name] ?? "",
    })),
  );
  const navExpectedItems = expectedItems(measures, expectedReports);
  const navViewItems = viewItems(viewDefs);

  // S6: disk-provenance merge — one row per resource; disk wins on
  // provenance display. Watcher paths map onto the merged rows.
  const diskRefs = (dir: string) =>
    (wsFiles.files[dir] ?? []).map((f) => ({
      name: f.name,
      changed: wsChanged.has(`${dir}/${f.name}`),
    }));
  // S17 Muse: canonical header names per file stem (one /api/workspace
  // read when connected) so disk rows display library names, not stems.
  const [diskHeaderNames, setDiskHeaderNames] = useState<Record<string, string>>({});
  useEffect(() => {
    if (serverMode.kind !== "connected") return;
    let cancelled = false;
    void fetch("/api/workspace")
      .then((r) => r.json())
      .then((b: { workspace?: { libraries?: { name: string; path?: string }[] }; data?: { libraries?: { name: string; path?: string }[] } }) => {
        if (cancelled) return;
        const libs = (b?.workspace ?? b?.data)?.libraries ?? [];
        const out: Record<string, string> = {};
        for (const l of libs) {
          const file = (l.path ?? "").split("/").pop() ?? "";
          const stem = file.replace(/\.cql$/i, "");
          if (stem) out[stem] = l.name;
        }
        setDiskHeaderNames(out);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [serverMode.kind, wsFiles.loading, wsChanged.size]);
  const navLibDiskItems = mergeDiskLibraries(navLibItems, diskRefs("cql"), diskHeaderNames);
  const navVsDiskItems = mergeDiskValuesets(navValuesetItems, diskRefs("valuesets"));
  const navViewDiskItems = mergeDiskViews(
    navViewItems,
    diskRefs("views"),
    diskRefs("data"),
  );

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
      items: filterItems(navLibDiskItems, navFilters.libraries),
      count: navLibDiskItems.length,
    },
    valuesets: {
      title: "Valuesets",
      items: filterItems(navVsDiskItems, navFilters.valuesets),
      count: navVsDiskItems.length,
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
      items: filterItems(navViewDiskItems, navFilters.views),
      count: navViewDiskItems.length,
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
    if (activeMeasureId === measureId) {
      setActiveMeasureId(measures.find((m) => m.id !== measureId)?.id ?? null);
    }
  };

  // REORG 6d: expectations are per-measure now (the nav lists one item
  // per measure), so the context menu clears the measure's whole set.
  const clearExpectedReports = (measureId: string) => {
    setExpectedReports((er) => ({ ...er, [measureId]: [] }));
    // Keep the legacy bool-map carrier in sync (evaluated diff view).
    updateExpectedValues(expectedMapFromReports([]));
  };

  const openEditorTab = (kind: TabKind, resourceId: string) => {
    const id = tabId(kind, resourceId);
    setEditorTabs((ts) => openTabIn(ts, { id, kind, resourceId }));
    setActiveEditorTabId(id);
    // S5 fix: library tabs selected programmatically (e.g. a workspace
    // CQL file click) must ALSO select the underlying library index —
    // the editor pane renders libraries[activeTab]; without this the
    // tab highlights while the pane keeps showing the previous library.
    if (kind === "library") {
      setLibraries((libs) => {
        const idx = libs.findIndex((l) => l.id === resourceId || l.name === resourceId);
        if (idx >= 0) setActiveTab(idx);
        return libs;
      });
    }
  };

  const closeEditorTabById = (id: TabId) => {
    setEditorTabs((ts) => closeEditorTabIn(ts, id));
    if (activeEditorTabId === id) {
      setActiveEditorTabId(neighborTabId(editorTabs, id));
    }
  };

  // 6h: the terminology chrome is gone — the Valuesets nav section's "+"
  // creates a fresh workspace ValueSet and opens its editor tab.
  const addWorkspaceValueset = () => {
    const url = `urn:cleanroom:vs:${Date.now().toString(36)}`;
    setTerminology({
      valuesets: [
        ...terminology.valuesets.filter(
          (v) => String((v as { url?: string }).url ?? "") !== url,
        ),
        { resourceType: "ValueSet", url, compose: { include: [] } },
      ],
    });
    openEditorTab("valueset", `ws:${url}`);
  };

  // REORG 6e: Ctrl/Cmd+Enter — run the current selection (or the whole
  // library when nothing is selected) through the console's runner.
  const [runRequest, setRunRequest] = useState<{
    mode: "library" | "selection";
    nonce: number;
  } | null>(null);
  const runViaConsole = () => {
    // Checkpoint ruling: target is AUTOMATIC — connected to a server →
    // whole-library runs go to the SERVER; standalone → in-browser WASM.
    // Selection runs stay in-browser (evaluate-only server contract).
    if (serverMode.kind === "connected" && !consoleSelection.trim()) {
      void runEvaluation(true);
      return;
    }
    setRunRequest({
      mode: consoleSelection.trim() ? "selection" : "library",
      nonce: Date.now(),
    });
  };

  // REORG 6g: manual runs (editor Run button / Ctrl+Enter) append to the
  // ring and OVERRIDE the displayed result. Same sync-artifact +
  // async-hash-patch flow as the heartbeat.
  const appendManualRun = (p: {
    mode: "library" | "selection";
    origin?: "server" | "browser";
    library: string;
    cql: string;
    ok: boolean;
    sql?: string;
    rows?: Array<Record<string, unknown>>;
    columns?: string[];
    column_types?: Record<string, string>;
    ms?: number | null;
    diags?: Diagnostics[];
  }) => {
    const entry: RunEntry = {
      id: newRunId(),
      name: defaultRunName(Date.now()),
      createdAt: Date.now(),
      libraryHash: "",
      datasetHash: "",
      artifact: p.ok
        ? artifactFromRows(p.rows ?? [], p.columns ?? [])
        : null,
      payload: {
        mode: p.mode,
        origin: p.origin ?? "browser",
        library: p.library,
        cql: p.cql,
        sql: p.sql,
        rows: p.rows,
        columns: p.columns,
        column_types: p.column_types,
        ms: p.ms ?? null,
        diags: p.diags,
      },
    };
    setRunHistory((h) => appendRun(h, entry, RUN_HISTORY_CAP));
    setSelectedRunId(entry.id);
    const dsRes = dataset?.resources?.length
      ? { resources: dataset.resources as unknown[] }
      : null;
    void Promise.all([
      computeLibraryHash(main?.text ?? p.cql),
      computeDatasetHash(dsRes),
    ]).then(([libHash, dsHash]) => {
      setRunHistory((h) =>
        h.map((r) =>
          r.id === entry.id
            ? { ...r, libraryHash: libHash, datasetHash: dsHash }
            : r,
        ),
      );
    });
  };

  // The run the console renders: pinned selection, else the latest.
  const displayRun =
    (selectedRunId
      ? runHistory.find((r) => r.id === selectedRunId)
      : undefined) ??
    runHistory[runHistory.length - 1] ??
    null;

  // 6h #62: the expected-vs-actual compare is DERIVED from the latest
  // library run (heartbeat rows) + authored expectations — no second
  // evaluation, recalc is automatic. Snippet runs don't carry population
  // columns, so only the newest run with mode "library" counts; a failed
  // run has no rows and the console explains instead of comparing.
  const latestLibraryRun = useMemo(() => {
    for (let i = runHistory.length - 1; i >= 0; i--) {
      if (runHistory[i].payload?.mode === "library") return runHistory[i];
    }
    return null;
  }, [runHistory]);
  // 6j: expected values belong to the MEASURE (entrypoint library) — a
  // non-entrypoint run (active-tab targeting) can't feed the compare.
  const latestRunIsEntrypoint =
    !latestLibraryRun?.payload?.library ||
    latestLibraryRun.payload.library === mainLib.name;
  const verifyCompare = useMemo(
    () =>
      latestRunIsEntrypoint
        ? deriveCompare(
            latestLibraryRun?.payload?.rows,
            expectedValues ?? {},
            populationCodes,
          )
        : null,
    [latestRunIsEntrypoint, latestLibraryRun, expectedValues, populationCodes],
  );
  const compareStale =
    (!!latestLibraryRun && !latestLibraryRun.payload?.rows) ||
    !latestRunIsEntrypoint;

  // A pinned run that fell off the 20-ring reverts to following latest.
  useEffect(() => {
    if (selectedRunId && !runHistory.some((r) => r.id === selectedRunId)) {
      setSelectedRunId(null);
    }
  }, [runHistory, selectedRunId]);

  // REORG 6e: Tests L2/L3 — patient groups live here so BOTH the list
  // and the detail panel can consume them, and so a focused patient
  // that vanishes (row delete / raw-edit wipe / workspace reset) can
  // fall back to the L2 list automatically.
  const patientGroups = useMemo(
    () => groupDataset(dataset?.resources ?? []),
    [dataset],
  );
  const focusedGroup = focusedPid
    ? patientGroups.find((g) => g.key === focusedPid)
    : undefined;
  useEffect(() => {
    if (focusedPid && !patientGroups.some((g) => g.key === focusedPid)) {
      setFocusedPid(null);
    }
  }, [focusedPid, patientGroups]);

  // Dataset callbacks shared by the L2 list and the L3 detail panel.
  const editDatasetResource = (index: number) => {
    const r = dataset?.resources?.[index];
    if (r && typeof r === "object") {
      setBuilderPrefill((prev) => ({
        resource: r as Record<string, unknown>,
        nonce: (prev?.nonce ?? 0) + 1,
        sourceIndex: index,
      }));
      openEditorTab("test", `row-${index}`);
    }
  };
  const addResourceForPatient = (patientId: string) => {
    setBuilderPrefill(null);
    const nonce = Date.now();
    setBuilderContext({ patientId, nonce });
    openEditorTab("test", `new-${nonce}`);
  };
  const addNewDatasetResource = () => {
    setBuilderPrefill(null);
    setBuilderContext(null);
    openEditorTab("test", `new-${Date.now()}`);
  };
  // INV-C3-3: immutable replace — never mutate the dataset in place.
  const deleteDatasetResource = (index: number) => {
    if (!dataset) return;
    setDataset({
      ...dataset,
      resources: (dataset.resources ?? []).filter((_, j) => j !== index),
    });
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
    } else if (kind === "valueset") {
      // Nav ids are url-keyed (`valueset:ws:<url>`) — the rename writes
      // `name` onto the workspace copy; dataset valuesets aren't renamable.
      if (!resId.startsWith("ws:")) return;
      const url = resId.slice(3);
      setTerminology({
        valuesets: terminology.valuesets.map((v) =>
          String((v as { url?: string }).url ?? "") === url
            ? { ...v, name }
            : v,
        ),
      });
    }
  };

  const selectNavItem = (item: NavItem) => {
    // S6 disk rows: fetch + open through the workspace loaders (same
    // behavior as the dissolved Workspace panel).
    const src = item.meta?.source as string | undefined;
    if (src === "disk" && item.kind === "library") {
      void (async () => {
        const name = String(item.meta?.name ?? `${item.label}.cql`);
        setStatusNote(`loading ${name}…`);
        const canonical = String(item.meta?.libName ?? '');
        try {
          // S17: the disk row shows the FILE stem, but /api/libraries/<n>
          // resolves by the CQL header library name — try the stem, then
          // fall back to the workspace listing that matches this row's
          // file (MADiE zips name files <Lib>-v<ver>.cql, so the stem
          // rarely equals the library name).
          const tryFetch = async (libName: string) => {
            const res = await fetch(`/api/libraries/${encodeURIComponent(libName)}`);
            const b = (await res.json()) as {
              data?: { text?: string; ok?: boolean };
              text?: string;
              ok?: boolean;
            };
            const text = b?.data?.text ?? b?.text;
            return typeof text === "string" && text ? { text, name: libName } : null;
          };
          let hit = canonical ? await tryFetch(canonical) : null;
          if (!hit) hit = await tryFetch(item.label);
          if (!hit) {
            const wsRes = await fetch("/api/workspace");
            const wsB = (await wsRes.json()) as {
              workspace?: { libraries?: { name: string; path?: string }[] };
              data?: { libraries?: { name: string; path?: string }[] };
            };
            const libs = (wsB?.workspace ?? wsB?.data)?.libraries ?? [];
            const fileSuffix = `${item.label}.cql`;
            const match = libs.find((l) => (l.path ?? "").endsWith(`/${fileSuffix}`) || (l.path ?? "").endsWith(fileSuffix));
            if (match) hit = await tryFetch(match.name);
          }
          if (hit) openWorkspaceCql(hit.name, hit.text);
          else setStatusNote(`could not load ${name}`);
        } catch {
          setStatusNote(`could not load ${name}`);
        }
      })();
      return;
    }
    if (src === "disk" && item.kind === "valueset") {
      void (async () => {
        const name = String(item.meta?.name ?? `${item.label}.json`);
        setStatusNote(`loading ${name}…`);
        try {
          const wsRes = await fetch("/api/workspace");
          const wsB = (await wsRes.json()) as { workspace?: { valuesets?: string[] }; data?: { valuesets?: string[] } };
          const d = wsB?.workspace ?? wsB?.data;
          const vsPath = (d?.valuesets ?? []).find((p) => String(p).split("/").pop() === name);
          if (!vsPath) {
            setStatusNote(`could not load ${name}`);
            return;
          }
          const res2 = await fetch(`/api/valueset?path=${encodeURIComponent(vsPath)}`);
          const b2 = (await res2.json()) as { data?: { ok?: boolean; url?: string; concepts?: unknown[] } } & { ok?: boolean; url?: string; concepts?: unknown[] };
          const d2 = b2?.data ?? b2;
          if (d2?.ok !== false && Array.isArray(d2?.concepts)) {
            openWorkspaceValueset(
              item.label,
              JSON.stringify(
                { resourceType: "ValueSet", url: d2.url ?? `ws:${item.label}`, compose: { include: [{ system: "", concept: d2.concepts }] } },
                null,
                2,
              ),
            );
          } else setStatusNote(`could not load ${name}`);
        } catch {
          setStatusNote(`could not load ${name}`);
        }
      })();
      return;
    }
    if (src === "disk-view" && item.kind === "view") {
      setStatusNote(`${String(item.meta?.name ?? item.label)} is a server view file (preview only — reload the page to re-list; view defs load via File > Import)`);
      return;
    }
    if (src === "disk-data" && item.kind === "view") {
      setStatusNote(`${String(item.meta?.name ?? item.label)} is a server data file (preview only — restart the dev server to pick up data changes)`);
      return;
    }
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
            value:
              typeof item.meta?.name === "string" ? item.meta.name : "",
          }),
      });
      items.push({
        label: "Delete measure",
        danger: true,
        onSelect: () => deleteMeasureEntry(item.meta?.measureId as string),
      });
    } else if (item.kind === "valueset" && item.meta?.source === "workspace") {
      items.push({
        label: "Rename valueset",
        onSelect: () =>
          setRenaming({
            id: item.id,
            value:
              typeof item.meta?.name === "string" ? item.meta.name : "",
          }),
      });
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
      const msrId = item.meta?.measureId as string;
      const hasExpectations = (expectedReports[msrId] ?? []).length > 0;
      if (hasExpectations) {
        items.push({
          label: "Clear expectations",
          danger: true,
          onSelect: () => clearExpectedReports(msrId),
        });
      }
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
      case "valueset": {
        // Tab identity follows the nav label (name → title → id → url
        // segment) so a nav rename retitles the tab too.
        const m = /^([a-z]+):(.*)$/.exec(t.resourceId);
        const src = m?.[1] ?? "ws";
        const url = m?.[2] ?? "";
        const pool: Array<Record<string, unknown>> =
          src === "ds"
            ? ((dataset?.valueset_resources ??
                []) as Array<Record<string, unknown>>)
            : terminology.valuesets;
        tabLabels[t.id] =
          valuesetLabel(
            pool.find((v) => (v as { url?: string }).url === url),
          ) ?? url;
        break;
      }
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
      case "parameter":
        // One shared form for the whole binding set (values are global).
        tabLabels[t.id] = "Parameters";
        break;
      default:
        tabLabels[t.id] = t.resourceId;
    }
  }
  // Prior run = nearest earlier entry OF THE SAME LIBRARY — active-tab
  // runs interleave entrypoint runs in the ring, and a cross-library
  // diff is noise. Falls back to null; FAILED entries (patients:null)
  // are skipped.
  const baselineArtifact: import("./lib/runDiff").Artifact | null = (() => {
    for (let i = runHistory.length - 2; i >= 0; i--) {
      const prev = runHistory[i];
      if (!prev?.artifact?.patients) continue;
      if (prev.payload?.library && runLib && prev.payload.library !== runLib.name)
        continue;
      return Object.fromEntries(
        Object.entries(prev.artifact.patients).map(([pid, p]) => [
          pid,
          (p as { populations: Record<string, boolean | null> }).populations,
        ]),
      );
    }
    return null;
  })();
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

  /** 6h: "+" on Measures — a blank measure (population skeleton pointing
   *  at the demo define names) bound to the entrypoint library; it
   *  becomes the active measure and opens its editor tab. */
  const addMeasure = () => {
    const id = newMeasureId(measures);
    const entry = {
      id,
      mainLibraryId: active?.id ?? "lib_0",
      resource: {
        ...DEFAULT_MEASURE,
        name: `Measure${measures.length + 1}`,
      },
    };
    setMeasures((ms) => [...ms, entry]);
    setActiveMeasureId(id);
    openEditorTab("measure", id);
  };

  // REORG 6d: every measure gets ONE default derived ViewDefinition
  // ("View 1", vd_default) so the nav's Views section lists a clickable
  // resource out of the box. One-shot per measure id: reset does not
  // re-seed while the measure is unchanged, and user deletions of other
  // views are not resurrected (the seed only fills an EMPTY collection).
  const ensuredViewForRef = useRef<string | null>(null);
  useEffect(() => {
    if (!restored || !activeMeasureEntry) return;
    if (ensuredViewForRef.current === activeMeasureEntry.id) return;
    ensuredViewForRef.current = activeMeasureEntry.id;
    setViewDefs((vs) =>
      vs.length > 0
        ? vs
        : [
            {
              id: "vd_default",
              name: "View 1",
              resource: buildDerivedView(activeMeasureEntry.resource, null),
            },
          ],
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [restored, activeMeasureEntry]);

  // REORG 6d: every measure gets an (empty) expected-reports slot so
  // its Expected item renders before anything is authored. Never
  // clobbers authored expectations.
  useEffect(() => {
    if (!restored) return;
    setExpectedReports((er) => {
      let changed = false;
      const next = { ...er };
      for (const m of measures) {
        if (!(m.id in next)) {
          next[m.id] = [];
          changed = true;
        }
      }
      return changed ? next : er;
    });
  }, [restored, measures]);

  // REORG phase 6b: the console's sub-tab set follows the ACTIVE editor
  // tab's kind — measure editors surface the Measure Report output,
  // view editors the ViewDefinition flatten, everything else the CQL
  // run pipeline (Results/SQL/AST/Diagnostics).
  const consoleContext: ConsoleContext =
    hostTab?.kind === "measure"
      ? "measure"
      : hostTab?.kind === "view"
        ? "view"
        : hostTab?.kind === "expected"
          ? "tests"
          : "library";
  const consoleNode = (
    <ResultsConsole
      connected={serverMode.kind === "connected"}
      libraries={mainLibs}
      main={main}
      dataset={evalDataset}
      parameters={runtimeParameters}
      outputColumns={effectiveOutputColumns}
      selection={consoleSelection}
      result={evalResult}
      baselineArtifact={baselineArtifact}
      context={consoleContext}
      mrOutput={
        <MrPivot reports={lastReports} measure={measure} runDiff={appRunDiff} />
      }
      funnelOutput={<MrFunnel result={evalResult} />}
      runRequest={runRequest}
      runs={runHistory}
      displayRun={displayRun}
      onSelectRun={setSelectedRunId}
      onManualRun={appendManualRun}
      viewOutput={
        <ViewOutputPanel viewResult={viewResult} runDiff={appRunDiff} />
      }
      verifyCompare={verifyCompare}
      compareStale={compareStale}
      activeTab={consoleTab}
      onTabChange={setConsoleTab}
      recalcSeconds={recalcSeconds}
    />
  );

  const explainCellRow = async (
    patientId: string,
    define: string,
    context?: {
      composedText?: string;
      params?: Record<string, unknown>;
      /** S19 Muse: local-computed runs explain through the worker even
       *  while a server is connected (mirrors the S18 run-origin seam). */
      computedLocally?: boolean;
    },
  ) => {
    setCellEvidence({ patientId, define, evidence: null });
    // S19: explain EXACTLY the run's composition — the clicked row came
    // from a composed-closure evaluation (App.runCells), so evidence must
    // evaluate THAT library, not the full buffer (which may declare
    // parameters/defines outside the closure and mismatch or error).
    const explainText = context?.composedText ?? main.text;
    const explainParams = context?.params ?? runtimeParameters;
    // S19 Muse: keep the OTHER workspace libraries (includes) resolvable —
    // only the main library's text is replaced with the run composition.
    const explainLibs: LibraryText[] = [
      { name: main.name, text: explainText },
      ...mainLibs.filter((l) => l.name !== main.name),
    ];
    try {
      let env: import("./lib/protocol").EvidenceResult;
      if (serverMode.kind === "connected" && !context?.computedLocally) {
        const res = await fetch("/api/explain", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            libraries: explainLibs,
            library: main.name,
            patient_id: patientId,
            parameters: explainParams,
          }),
        });
        env = (await res.json()) as import("./lib/protocol").EvidenceResult;
      } else {
        const resp = await workerRequest({
          type: "explain_patient",
          libraries: explainLibs,
          main: { name: main.name, text: explainText },
          dataset: evalDataset,
          patient_id: patientId,
          parameters: explainParams,
        });
        env = JSON.parse(resp.envelope) as import("./lib/protocol").EvidenceResult;
      }
      setCellEvidence((cur) =>
        cur && cur.patientId === patientId && cur.define === define
          ? { patientId, define, evidence: env }
          : cur,
      );
    } catch (err) {
      setCellEvidence({
        patientId,
        define,
        evidence: {
          ok: false,
          diagnostics: [
            { code: "explain_error", severity: "error", message: String(err) },
          ],
        } as unknown as import("./lib/protocol").EvidenceResult,
      });
    }
  };

  return (
    <div className="app">
      <header className="app-header">
        <h1>CQL Cleanroom</h1>
        <div className="workspace-actions" data-testid="workspace-actions">
          {/* #64: desktop-app menu — Open (imports), Save (exports),
              Examples, share + reset under File; Settings stays
              separate. Open/Save/Examples are hover flyouts. */}
          <DropdownMenu label="File" testId="file-menu">
            <DropdownSubmenu label="Open" testId="file-open">
              {/* S18 rider: Open is MADiE-zip ONLY for compatibility —
                  generic bundles/resources import via File > Add. */}
              <button
                className="dropdown-item"
                data-testid="madie-import"
                onClick={() => madieFileRef.current?.click()}
              >
                Measure package (MADiE)…
              </button>
              <button
                className="dropdown-item"
                data-testid="madie-tests-import"
                onClick={() => madieTestsFileRef.current?.click()}
              >
                Test cases (MADiE)…
              </button>
              <DropdownSubmenu label="Examples" testId="file-examples">
                <NativeClickButton
                  testId="load-example-cms69"
                  onClick={() => void loadExample("cms69")}
                >
                  CMS69 BMI Screening
                </NativeClickButton>
              </DropdownSubmenu>
            </DropdownSubmenu>
            <DropdownSubmenu label="Add" testId="file-add">
              <button
                className="dropdown-item"
                data-testid="bundle-add"
                onClick={() => {
                  bundleModeRef.current = "merge";
                  bundleFileRef.current?.click();
                }}
                title="merges the bundle's resources into the current dataset"
              >
                FHIR Bundle… (merge)
              </button>
            </DropdownSubmenu>
            <DropdownSubmenu label="Save" testId="file-save">
              {/* S18 rider: Save exports the MADiE package-zip layout —
                  the full workspace carrier (MADiE-required entries at
                  their paths + cleanroom extras under resources/extras/). */}
              <button
                className="dropdown-item"
                data-testid="madie-export"
                onClick={exportMadieZip}
              >
                Measure package (MADiE, full workspace)
              </button>
            </DropdownSubmenu>
            <div className="dropdown-sep" />
            <button className="dropdown-item" data-testid="share-btn" onClick={shareLink}>
              Copy share link
            </button>
            <button
              className="dropdown-item"
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
                  setConsoleTab("results");
                  setCurrentRun(null);
                  setParamValues({});
                  void clearWorkspace().catch(() => undefined);
                }
              }}
            >
              Reset workspace
            </button>
          </DropdownMenu>
          {/* REORG 6e: workspace settings — console dock + recalc delay. */}
          <DropdownMenu label="Settings" testId="settings-menu">
            {serverMode.kind === "connected" && (
              <button
                className="dropdown-item"
                data-testid="settings-terminology"
                onClick={() => setTermSettingsOpen(true)}
                title="VSAC key, FHIR server, UMLS key, cache"
              >
                Terminology…
              </button>
            )}
            <label className="settings-row">
              <span>Console</span>
              <select
                data-testid="settings-console-placement"
                value={consolePlacement}
                onChange={(e) =>
                  setConsolePlacement(
                    e.target.value === "right" ? "right" : "bottom",
                  )
                }
              >
                <option value="bottom">Dock bottom</option>
                <option value="right">Dock right</option>
              </select>
            </label>
            <label className="settings-row">
              <span>Recalc every</span>
              <select
                data-testid="settings-recalc-seconds"
                value={String(recalcSeconds)}
                onChange={(e) => setRecalcSeconds(Number(e.target.value))}
              >
                <option value="0.5">0.5s</option>
                <option value="1">1s</option>
                <option value="2">2s</option>
                <option value="5">5s</option>
                <option value="10">10s</option>
                <option value="0">Off</option>
              </select>
            </label>
          </DropdownMenu>
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
            ref={madieTestsFileRef}
            type="file"
            accept=".zip"
            hidden
            data-testid="madie-tests-import-input"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void importMadieTestsZip(f);
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
              if (f) void importBundleFile(f, bundleModeRef.current);
              e.target.value = "";
            }}
          />
          <input
            ref={sectionImportInputRef}
            type="file"
            hidden
            data-testid="section-import-input"
            onChange={(e) => {
              const f = e.target.files?.[0];
              const pick = sectionImportPickRef.current;
              e.target.value = "";
              if (f && pick) pick.cb(f);
            }}
          />
        </div>
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
        <VersionBadge
          wheelVersion={boot.phase === "ready" ? boot.wheelVersion : null}
        />
      </header>
      <main
        className={`app-main ${consolePlacement === "right" ? "dock-right" : "dock-bottom"}`}
        data-testid="app-main"
        style={
          {
            "--nav-w": navPanel
              ? focusedPid && navPanel === "tests"
                ? `calc(74px + ${navWidths.panel}px + ${navWidths.detail}px)`
                : `calc(66px + ${navWidths.panel}px)`
              : "52px",
            "--navpanel-w": `${navWidths.panel}px`,
            "--navdetail-w": `${navWidths.detail}px`,
            "--col1-fr": `${col1Fr}fr`,
            "--editor-fr": `${editorFr}fr`,
          } as React.CSSProperties
        }
      >
        {serverMode.kind === "connected" && wsDataHint && (
          <div className="ws-data-hint" role="status" data-testid="ws-data-hint">
            <span>Data files changed on disk — the kernel keeps loaded data.</span>
            <button
              type="button"
              className="settings-button"
              onClick={() => {
                void fetch("/api/kernel/restart", { method: "POST" }).then(() => setWsDataHint(false));
              }}
            >
              Restart kernel
            </button>
            <button type="button" className="settings-button" aria-label="Dismiss" onClick={() => setWsDataHint(false)}>×</button>
          </div>
        )}
        <NavRail
          sections={{
            measures: { ...navSectionModels.measures, filter: navFilters.measures },
            libraries: { ...navSectionModels.libraries, filter: navFilters.libraries },
            valuesets: { ...navSectionModels.valuesets, filter: navFilters.valuesets },
            parameters: { ...navSectionModels.parameters, filter: navFilters.parameters },
            tests: {
              ...navSectionModels.tests,
              filter: navFilters.tests,
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
          onAddMeasures={addMeasure}
          onAddTests={addNewDatasetResource}
          onAddView={addStoredView}
          onAddExpected={openExpectedEditor}
          onAddValuesets={addWorkspaceValueset}
          onImportItem={handleNavImport}
          diskLoading={serverMode.kind === "connected" && wsFiles.loading}
          onRefreshDisk={
            serverMode.kind === "connected"
              ? () => {
                  wsFiles.reload();
                  setWsChanged(new Set());
                }
              : undefined
          }
          panelWidth={navWidths.panel}
          detailWidth={navWidths.detail}
          onPanelWidth={(w) => updateNavWidths({ ...navWidths, panel: w })}
          onDetailWidth={(w) => updateNavWidths({ ...navWidths, detail: w })}
          focusedPid={focusedPid}
          detailSlot={
            focusedGroup ? (
              <PatientDetailPanel
                group={focusedGroup}
                onBack={() => setFocusedPid(null)}
                onEditResource={editDatasetResource}
                onAddForPatient={addResourceForPatient}
                onImportItem={(item) => handleNavImport("tests", item)}
                onDelete={deleteDatasetResource}
              />
            ) : null
          }
          testsSlot={
            <DatasetPane
              dataset={dataset}
              focusedPid={focusedPid}
              onFocusedPidChange={setFocusedPid}
              filter={navFilters.tests}
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
            onSelect={(id) => {
              setActiveEditorTabId(id as TabId);
              // S5 fix: tab-bar library selections must drive the same
              // activeTab index sync as selectNavItem (see its comment).
              const { kind, resourceId } = parseTabId(id as TabId);
              if (kind === "library") {
                const idx = libraries.findIndex(
                  (l) => l.id === resourceId || l.name === resourceId,
                );
                if (idx >= 0) setActiveTab(idx);
              }
            }}
            onClose={(id) => closeEditorTabById(id as TabId)}
          />
          <div className="editor-area">
          <EditorPane
            text={active.text}
            tabKey={activeLibTabKey}
            knownTabKeys={editorTabs
              .filter((t) => t.kind === "library")
              .map((t) => t.id)}
            onTextChange={updateActiveText}
            onSelectionChange={setConsoleSelection}
            graphOpen={graphOpen}
            onGraphOpenChange={setGraphOpen}
            onRun={runViaConsole}
            onRunCells={runCells}
            connected={serverMode.kind === "connected"}
            onExplainRow={(pid, define, ctx) => void explainCellRow(pid, define, ctx)}
            parameters={runtimeParameters}
            cellEvidenceSlot={
              cellEvidence ? (
                <EvidencePopover
                  evidence={cellEvidence.evidence}
                  patientId={cellEvidence.patientId}
                  population={cellEvidence.define}
                  onClose={() => setCellEvidence(null)}
                />
              ) : null
            }

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
          {hostTab && (
            <TabHost
              tab={hostTab}
              measure={measure}
              onMeasureChange={updateActiveMeasure}
              measureLibs={mainLibs}
              measureMain={main}
              measureMainLibraryId={activeMeasureEntry?.mainLibraryId}
              measureLibraryChoices={libraries.map((l) => ({
                id: l.id,
                name: l.name,
              }))}
              onMeasureMainLibraryChange={setMainLibrary}
              measureClosure={measureClosure}
              measureValuesetSources={measureValuesetSources}
              measureExpectedReports={
                expectedReports[activeMeasureEntry?.id ?? ""] ?? []
              }
              onOpenExpected={openExpectedEditor}
              valueset={hostValueset}
              connected={serverMode.kind === "connected"}
              umlsReady={umlsReady || !!termSettings.umlsApiKey}
              umlsKey={termSettings.umlsApiKey || undefined}
              onValuesetChange={(vs) => {
                const nextUrl = String(vs.url ?? "");
                // The tab's resourceId (`ws:<url>`) is the identity of the
                // entry being edited. Editing the URL FIELD changes that
                // identity: swap out the OLD entry (not just same-url
                // ones) and re-key the tab, or the codes would land on a
                // stale duplicate while the renamed valueset stays empty.
                const tabUrl =
                  hostTab?.kind === "valueset" &&
                  hostTab.resourceId.startsWith("ws:")
                    ? hostTab.resourceId.slice(3)
                    : null;
                const oldTabId = hostTab?.id ?? null;
                setTerminology({
                  valuesets: [
                    ...terminology.valuesets.filter((v) => {
                      const u = String((v as { url?: string }).url ?? "");
                      if (u === nextUrl) return false;
                      if (tabUrl !== null && u === tabUrl && nextUrl !== tabUrl) {
                        return false;
                      }
                      return true;
                    }),
                    vs,
                  ],
                });
                if (
                  oldTabId &&
                  tabUrl !== null &&
                  nextUrl &&
                  nextUrl !== tabUrl
                ) {
                  const newTabId: TabId = `valueset:ws:${nextUrl}`;
                  setEditorTabs((ts) =>
                    ts.map((t) =>
                      t.id === oldTabId
                        ? { ...t, id: newTabId, resourceId: `ws:${nextUrl}` }
                        : t,
                    ),
                  );
                  setActiveEditorTabId((cur) =>
                    cur === oldTabId ? newTabId : cur,
                  );
                }
              }}
              params={detectParams(mainLib.text).map((d) => ({
                ...d,
                value: paramValues[d.name] ?? "",
              }))}
              onParamsChange={(next) => {
                const vals: Record<string, string> = {};
                for (const p of next) vals[p.name] = p.value;
                setParamValues(vals);
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
                  dataset={evalDataset}
                  populationCodes={populationCodes}
                  expectedValues={expectedValues}
                  onExpectedValuesChange={updateExpectedValues}
                  measure={measure}
                  onUseCurrentResult={captureExpectedFromRun}
                  hasCurrentResult={!!lastReports?.length}
                />
              }
              measureReports={lastReports}
              viewConfig={viewConfig?.overrides ?? null}
              onViewConfigChange={(overrides) => setViewConfig({ overrides })}
              onResult={setViewResult}
              recalcMs={recalcSeconds * 1000}
            />
          )}
          </div>
          {/* REORG 6e: the console is PINNED below the editor (default
              2/3 : 1/3) — drag to adjust; each row scrolls itself. */}
          {consolePlacement === "bottom" && (
            <Splitter
              orientation="horizontal"
              testid="editor-splitter"
              value={editorFr}
              onChange={setEditorFr}
              label="Resize editor and console"
            />
          )}
          {consolePlacement === "bottom" && consoleNode}
        </div>
        {consolePlacement === "right" && (
          <Splitter value={col1Fr} onChange={setCol1Fr} />
        )}
        {consolePlacement === "right" && (
          <div className="pane-col run-col console-dock">{consoleNode}</div>
        )}
      </main>
      <ResourceContextMenu menu={ctxMenu} onClose={() => setCtxMenu(null)} />
            {termSettingsOpen && (
        <div
          className="modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-label="Terminology Settings"
          data-testid="term-settings-dialog"
          onClick={() => setTermSettingsOpen(false)}
        >
          <div className="modal-card term-settings-card" onClick={(e) => e.stopPropagation()}>
            <h3>Terminology</h3>
            <label className="settings-row" data-testid="settings-vsac-key-row">
              <span>VSAC API key</span>
              <input
                type="password"
                data-testid="settings-vsac-key"
                disabled={envFieldSet.vsac}
                placeholder={
                  envFieldSet.vsac
                    ? "provided by server environment (VSAC_API_KEY)"
                    : "stored in this browser only"
                }
                value={envFieldSet.vsac ? "" : termSettings.vsacApiKey}
                onChange={(e) => {
                  const next = { ...termSettings, vsacApiKey: e.target.value };
                  setTermSettings(next);
                  void saveTerminologySettings(next);
                }}
              />
            </label>
            <label className="settings-row" data-testid="settings-fhir-base-row">
              <span>FHIR server</span>
              <input
                type="text"
                data-testid="settings-fhir-base"
                disabled={envFieldSet.fhirBase}
                placeholder={
                  envFieldSet.fhirBase
                    ? "provided by server environment"
                    : "cts.nlm.nih.gov/fhir (default)"
                }
                value={envFieldSet.fhirBase ? "" : termSettings.fhirTermServerBase}
                onChange={(e) => {
                  const next = { ...termSettings, fhirTermServerBase: e.target.value };
                  setTermSettings(next);
                  void saveTerminologySettings(next);
                }}
              />
            </label>
            <label className="settings-row" data-testid="settings-umls-key-row">
              <span>UMLS API key</span>
              <input
                type="password"
                data-testid="settings-umls-key"
                disabled={envFieldSet.umls}
                placeholder={
                  envFieldSet.umls
                    ? "provided by server environment (UMLS_API_KEY)"
                    : "stored in this browser only"
                }
                value={envFieldSet.umls ? "" : termSettings.umlsApiKey}
                onChange={(e) => {
                  const next = { ...termSettings, umlsApiKey: e.target.value };
                  setTermSettings(next);
                  void saveTerminologySettings(next);
                }}
              />
            </label>
            <label className="settings-row">
              <span>ValueSet cache</span>
              <button
                className="settings-button"
                data-testid="settings-clear-term-cache"
                onClick={() => void clearTerminologyCache()}
              >
                Clear
              </button>
            </label>
            <div className="modal-actions">
              <button data-testid="term-settings-close" onClick={() => setTermSettingsOpen(false)}>Close</button>
            </div>
          </div>
        </div>
      )}
      {termDiagnostics.length > 0 && (
        <div className="term-diag" data-testid="term-diag" role="status">
          {termDiagnostics.length} valueset url{termDiagnostics.length === 1 ? "" : "s"} unresolved — check Settings terminology source
        </div>
      )}
      <BootOverlay state={boot} />
    </div>
  );
}
