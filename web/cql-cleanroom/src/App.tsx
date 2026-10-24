import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { groupDataset, type DatasetRowRef, type PatientGroup } from "./lib/datasetGroup";
import { buildCellGraph } from "./lib/cell-deps";
import { mergeDiskLibraries, mergeDiskValuesets, mergeDiskViews } from "./lib/navSections";
import { useWorkspaceFiles } from "./lib/useWorkspaceFiles";
import { cellify } from "./lib/cellify";
import { composeCellClosure, splitCells, stripCellMarkers } from "./lib/cells";
import { PatientDetailPanel } from "./components/nav/PatientDetailPanel";
import {
  BootOverlay,
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
import { StatusBar } from "./components/StatusBar";
import { switchWorkspace as switchWorkspaceByName } from "./components/WorkspacePicker";
import { WorkspaceFolderModal } from "./components/WorkspaceFolderModal";
import {
  PINNED_EXAMPLES,
  loadRecents,
  pushRecent,
  savePackageToFolder,
  switchWorkspaceByPath,
  type RecentWorkspace,
} from "./lib/workspaceBrowser";
import { coerceParam, detectParams, joinInterval } from "./lib/params";
import { materializeMeasureReports } from "./lib/measureReports";
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
import { deriveCompare, populationRows } from "./lib/verifyCompare";
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
/**
 * S22a: the connected-boot pristine check for the in-editor CleanroomDemo
 * default — TRUE for the untouched default OR its S7 auto-cellified form
 * (markers appended in-buffer before the purity effect re-runs).
 */
function cellifiedDefaultPristine(text: string): boolean {
  const cellified = cellify(DEFAULT_CQL);
  return cellified !== null && text === cellified;
}

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

const EX_LABELS: Record<string, string> = {
  "demo-workspace": "Demo — Cleanroom basics",
  "cms69-workspace": "CMS69 BMI Screening (real eCQM)",
  "cms125-workspace": "CMS125 Breast Cancer Screening (real eCQM)",
};
const exLabel = (name: string) => EX_LABELS[name] ?? name;

export default function App() {
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
  // S27: a disk ViewDefinition opens ONCE in Custom mode; after leaving
  // the tab, the view pane defaults back to "From Measure".
  const [pendingViewOpen, setPendingViewOpen] = useState<{
    id: string;
    resource: Record<string, unknown>;
  } | null>(null);
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
  // S29: library-first — the primary library is the default-open section
  // (the measure's entrypoint is what users land to).
  const [navPanel, setNavPanel] = useState<NavSectionId | null>("libraries");
  const [navFilters, setNavFilters] = useState<
    Record<NavSectionId, string>
  >({
    libraries: "",
    valuesets: "",
    config: "",
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
  // S26 review fix: adopted disk measures may reference a primary
  // library whose tab isn't open yet — resolve by NAME first.
  const entrypointByName = activeMeasureEntry?.primaryLibraryName
    ? libraries.findIndex(
        (l) => l.name === activeMeasureEntry.primaryLibraryName,
      )
    : -1;
  const entrypoint = Math.max(
    0,
    libraries.findIndex((l) => l.id === activeMeasureEntry?.mainLibraryId),
  );
  const effectiveEntrypoint =
    entrypointByName >= 0 ? entrypointByName : entrypoint;
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
    // S26 review fix: disk-choice ids (connected picker) OPEN the
    // library on demand — fetch its text and bind the real tab id.
    if (libId.startsWith("disk:")) {
      const name = libId.slice("disk:".length);
      void fetch(`/api/libraries/${encodeURIComponent(name)}`)
        .then((r) => r.json())
        .then(
          (b: { text?: string }) => {
            if (typeof b?.text === "string" && b.text) {
              openWorkspaceCql(name, b.text);
              setStatusNote(`opened workspace library ${name}`);
            }
          },
        )
        .catch(() => undefined);
      // primaryLibraryName drives the entrypoint until the tab binds.
      setMeasures((ms) =>
        ms.map((m) =>
          m.id === activeMeasureEntry.id
            ? { ...m, primaryLibraryName: name }
            : m,
        ),
      );
      return;
    }
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
  // S26 review fix: an adopted disk measure's primary library binds its
  // tab id the first time that library OPENS (nav click opens on
  // demand; until then effectiveEntrypoint resolves by name).
  useEffect(() => {
    if (!activeMeasureEntry?.primaryLibraryName) return;
    const match = libraries.find(
      (l) => l.name === activeMeasureEntry.primaryLibraryName,
    );
    if (match && activeMeasureEntry.mainLibraryId !== match.id) {
      const mid = activeMeasureEntry.id;
      setMeasures((ms) =>
        ms.map((m) =>
          m.id === mid ? { ...m, mainLibraryId: match.id } : m,
        ),
      );
    }
  }, [libraries, activeMeasureEntry]);
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
      // S27: re-opening an already-open library must NOT clobber a
      // CELLIFIED buffer with the markerless disk text — that lost the
      // `// # %%` markers (cells view then rendered empty) and flagged
      // the tab as "cells removed", permanently suppressing auto-split.
      const current = libraries[idx].text ?? "";
      const stripMarkers = (t: string) =>
        t
          .split("\n")
          .filter((l) => !/^\s*\/\/\s*#\s*%%/.test(l))
          .join("\n")
          .trim();
      if (current && stripMarkers(current) === text.trim()) {
        openEditorTab("library", name);
        return;
      }
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
  // S29 footer: last content save (standalone IndexedDB autosave). The
  // connected workspace reads local files and writes nothing back, so
  // the footer explains that dash instead of inventing a timestamp.
  const [lastSavedAt, setLastSavedAt] = useState<number | null>(null);
  // S32: Open/Save workspace folder picker + switch overlay + recents.
  const [folderModal, setFolderModal] = useState<"open" | "save" | null>(null);
  // S32: view-flatten busy (console output shows the spinner while true).
  const [viewRunning, setViewRunning] = useState(false);
  const [switching, setSwitching] = useState<string | null>(null);
  const [recents, setRecents] = useState<RecentWorkspace[]>(() => loadRecents());
  // c-cleanroom-redo S1: connected mode (additive; standalone = zero server
  // calls — automated e2e guards this). Server is terminology provider only.
  const [serverMode, setServerMode] = useState<ServerMode>({ kind: "standalone" });
  // S22a: detection PENDING flag — the S7 auto-cellify must hold while
  // the handshake may still flip us to connected (the pristine demo
  // default would otherwise be adopted then swapped by boot purity,
  // persisting a bogus cellsRemoved entry for the tab). The hold lifts
  // only when detection AND (when connected) the boot-purity swap have
  // BOTH settled — a deterministic order instead of an effect race.
  const [serverDetectPending, setServerDetectPending] = useState(true);
  // S31: the browser engine (Pyodide + duckdb-wasm) boots LAZILY — never
  // during the mode-detection window and never for a connected session
  // (server-side evaluation). It still boots on demand for standalone and
  // for connected actions that use the in-browser engine (selection runs).
  const boot = useBootProgress(
    serverDetectPending || serverMode.kind === "connected",
  );
  const puritySettledRef = useRef(false);
  const [puritySettled, setPuritySettled] = useState(false);
  // S23-2: cell view visibility (lifted from EditorPane) — the auto-
  // recalc heartbeat is SUPPRESSED while cells are the active surface
  // (cell edits must not leak whole-library runs into the console).
  const [cellsViewActive, setCellsViewActive] = useState(false);
  const cellsViewActiveRef = useRef(cellsViewActive);
  cellsViewActiveRef.current = cellsViewActive;
  // S21: latest serverMode for call-time reads inside async restore.
  const serverModeRef = useRef(serverMode);
  serverModeRef.current = serverMode;
  // S21 Muse: server detection is a boot prerequisite — the restore
  // effect awaits it so serverModeRef is accurate before deciding
  // whether IndexedDB CONTENT may restore (detect races loadWorkspace).
  const serverDetectedRef = useRef<Promise<ServerMode> | null>(null);
  const [umlsReady, setUmlsReady] = useState(false);
  // Rider #2: per-field env-present flags from /health (booleans only).
  const [envFieldSet, setEnvFieldSet] = useState<{
    vsac: boolean;
    umls: boolean;
    fhirBase: boolean;
  }>({ vsac: false, umls: false, fhirBase: false });
  const [termSettings, setTermSettings] = useState<TerminologySettings>(DEFAULT_TERMINOLOGY_SETTINGS);
  const [termDiagnostics, setTermDiagnostics] = useState<string[]>([]); // surfaced via statusNote; kept for the editor strip + diagnostics pane
  // S31: disk ValueSet canonical URLs — the terminology resolver treats
  // them as workspace-resolved (never "unresolved").
  const [diskValuesetUrls, setDiskValuesetUrls] = useState<string[]>([]);
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
  // S20: the popover renders ONLY in the clicked cell's card — keyed by
  // (cellName, patientId) so opening cell A's evidence never bleeds into
  // cell B (single-slot state + per-card key check at render).
  const cellEvidenceKey = cellEvidence
    ? `${cellEvidence.define}::${cellEvidence.patientId}`
    : null;
  // S6: disk trees feed the TYPE drawers (Workspace rail dissolves).
  const wsFiles = useWorkspaceFiles(serverMode.kind === "connected");
  // S20/S22a: the SERVER workspace's patient roster (the dataset the
  // kernel actually evaluates in connected mode) — display surfaces label
  // with it; standalone surfaces address the browser store. S22a: in
  // connected mode the roster is authoritative EVEN WHEN EMPTY (a
  // workspace with no data shows "0 patients", never the in-browser
  // demo dataset); null = not connected yet.
  const [serverPatientIds, setServerPatientIds] = useState<string[] | null>(null);
  // S24-3: per-patient resource counts + type breakdown for the roster
  // chips + the type-grouped slideout.
  const [serverPatientResources, setServerPatientResources] = useState<
    import("./components/DatasetPane").ServerPatientEntry[] | null
  >(null);
  useEffect(() => {
    if (serverMode.kind !== "connected") {
      setServerPatientIds(null);
      return;
    }
    let cancelled = false;
    void fetch("/api/patients")
      .then((r) => r.json())
      .then(
        (
          b: {
            patients?: string[];
            patient_resources?: import("./components/DatasetPane").ServerPatientEntry[];
          },
        ) => {
          if (cancelled) return;
          setServerPatientIds(b?.patients ?? []);
          setServerPatientResources(b?.patient_resources ?? null);
        },
      )
      .catch(() => {
        if (!cancelled) setServerPatientIds([]);
      });
    return () => {
      cancelled = true;
    };
  }, [serverMode.kind, wsFiles.loading, wsChanged.size]);
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
        } else if (ev.kind === "switched") {
          // S22a: the server re-rooted onto another workspace — reload
          // so every drawer re-reads the new workspace (fresh handshake
          // nonce, fresh kernel, fresh disk trees).
          window.location.reload();
        }
      } catch {
        /* ignore malformed frames */
      }
    };
    return () => { try { ws?.close(); } catch { /* noop */ } };
  }, [serverMode.kind]);
  useEffect(() => {
    let cancelled = false;
    const detected = detectServer();
    serverDetectedRef.current = detected;
    void detected.then((m) => {
      if (cancelled) return;
      setServerMode(m);
      setServerDetectPending(false);
      if (m.kind !== "connected") {
        // Standalone: no purity pass runs — the hold lifts with detection.
        puritySettledRef.current = true;
        setPuritySettled(true);
      }
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
  const termResolveKey = `${serverMode.kind}:${terminology.valuesets.length}:${diskValuesetUrls.length}:${libraries.map((l) => l.text.length).join(",")}`;
  useEffect(() => {
    if (serverMode.kind !== "connected") return;
    let cancelled = false;
    const wsUrls = new Set<string>([
      ...(terminology.valuesets
        .map((v) => (typeof v?.url === "string" ? v.url : null))
        .filter(Boolean) as string[]),
      // S31: disk-backed workspace ValueSets resolve locally by URL —
      // they must not surface as "unresolved / check terminology source".
      ...diskValuesetUrls,
    ]);
    // Compose the library text from open libraries (declared urls scan).
    const libText = libraries.map((l) => l.text).join("\n");
    void resolveRuntimeValuesets(libText, wsUrls, termSettings, serverMode).then((r) => {
      if (cancelled) return;
      setTermDiagnostics(r.unresolved);
      if (r.unresolved.length === 0) {
        // S31: a LATER pass that resolves everything clears the stale
        // "not retrievable" note (the first pass can run before the disk
        // valueset URLs are known).
        setStatusNote((cur) =>
          cur && cur.startsWith("valueset not retrievable") ? null : cur,
        );
      }
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
  // S26 (item 11): true while an example package boot is in flight /
  // freshly landed — suppresses auto-cellify so examples open in TEXT
  // view with the console heartbeat running (showcase, not authoring).
  const exampleBootRef = useRef(false);
  const [exampleForceTextNonce, setExampleForceTextNonce] = useState(0);
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

  // S26 (item 11): examples are MADiE-layout ZIPS built from the repo
  // workspaces (one loader everywhere — importMadiePackage). The bespoke
  // 4-file fetch bundle (main.cql/measure.json/valuesets.json/
  // dataset.ndjson) is RETIRED.
  const loadExample = async (example: string) => {
    exampleBootRef.current = true;
    // S26: example loads REPLACE the workspace — land in TEXT view with
    // the console heartbeat (cells view may be open from the prior
    // library; showcase content is read-heavy).
    setCellsViewActive(false);
    setExampleForceTextNonce((n) => n + 1);
    try {
      const base = exampleAssetUrl(`examples/${example}.zip`);
      const buf = await fetch(base).then((r) => {
        if (!r.ok) throw new Error(`example zip not found (${r.status})`);
        return r.arrayBuffer();
      });
      const pkg = importMadiePackage(new Uint8Array(buf));
      if (!pkg.libraries.length) {
        throw new Error(pkg.warnings[0] ?? "no libraries in example zip");
      }
      const nextLibs = withLibraryIds(pkg.libraries);
      setLibraries(nextLibs);
      setActiveTab(0);
      const msrId = newMeasureId([]);
      setMeasures([
        {
          id: msrId,
          mainLibraryId: nextLibs[0].id,
          resource:
            pkg.measure ??
            ({
              resourceType: "Measure",
              name: example,
              status: "draft",
              scoring: { coding: [{ code: "proportion" }] },
              library: [`urn:cleanroom:lib:${nextLibs[0].name}`],
            } as Record<string, unknown>),
        },
      ]);
      setActiveMeasureId(msrId);
      setTerminology({ valuesets: pkg.valuesets });
      const resources = pkg.tests.flatMap((t) => t.resources);
      setDataset(resources.length ? { resources } : null);
      // eCQM reporting period default (fixture-encoded 2026 calendar
      // year — matches the example workspaces' expected MeasureReports).
      const defaults: Record<string, string> = {};
      const mainText = pkg.primary
        ? (pkg.libraries.find((l) => l.name === pkg.primary)?.text ?? pkg.libraries[0].text)
        : pkg.libraries[0].text;
      for (const pm of mainText.matchAll(
        /parameter\s+"([^"]+)"(?!.*default)/g,
      )) {
        if (pm[1] === "Measurement Period") {
          defaults[pm[1]] = "2026-01-01T00:00:00.0..2026-12-31T23:59:59.999";
        }
      }
      if (Object.keys(defaults).length) {
        setParamValues(defaults);
      }
      if (pkg.extras.parameters) {
        const extra = pkg.extras.parameters as Record<string, unknown>;
        setParamValues((p) => {
          const next = { ...p };
          for (const [k, v] of Object.entries(extra)) {
            if (typeof v === "string") next[k] = v;
          }
          return next;
        });
      }
      // S32: full-workspace round-trip — the example zips carry the
      // workspace ViewDefinitions and expected MeasureReports as
      // cleanroom extras; apply them so WASM matches the dev server
      // (same Views section, same Expected Results).
      if (pkg.extras.views.length) {
        setViewDefs(
          pkg.extras.views.map((v, i) => ({
            id: String(v.id ?? `view_${i}`),
            name: String(v.name ?? v.id ?? `View ${i + 1}`),
            resource: v,
          })),
        );
      }
      if (pkg.extras.expectedReports.length) {
        setExpectedReports({ [msrId]: pkg.extras.expectedReports });
      }
      setStatusNote(
        `loaded example ${example}: ${pkg.libraries.length} libraries, ${resources.length} test resources`,
      );
    } catch (e) {
      setStatusNote(`example load failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      // S27: the boot hold is only for the LOAD; leaving it set forever
      // suppressed auto-split on every later library open (cells view
      // rendered empty with no run output).
      exampleBootRef.current = false;
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
    void Promise.resolve(serverDetectedRef.current)
      .catch(() => serverModeRef.current)
      .then(() => loadWorkspace())
      .then((ws) => {
        // S21 storage doctrine: on CONNECTED sessions the browser store
        // may hold chrome only (content autosave is standalone-gated);
        // a stale pre-connect workspace snapshot must NOT resurrect as
        // the live content. Awaits server detection so the mode is
        // accurate at decision time. Chrome-only restores (prefs/run
        // history) still apply below via the pref branches.
        if (
          serverModeRef.current?.kind === "connected" &&
          ws?.libraries?.length
        ) {
          // skip content restore; keep chrome (prefs are read below from
          // the same object, so fall through with content cleared).
          ws = {
            ...ws,
            libraries: [],
            dataset: null,
            measures: [],
            expectedReports: {},
            viewDefs: [],
            terminology: { valuesets: [] },
          } as typeof ws;
        }
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

  // S22a connected-boot purity: a CONNECTED session that restored NO
  // browser content (server disk is the source of truth) must not sit
  // on the in-browser CleanroomDemo scratch defaults — it opens the
  // workspace's FIRST disk library instead (the demo workspace is a
  // real directory now, so "demo state" is just another disk library).
  // The pristine check tolerates the S7 auto-cellified form (markers
  // are appended in-buffer before this effect re-runs).
  useEffect(() => {
    if (!restored || serverMode.kind !== "connected") return;
    // Standalone-guard: this effect only runs connected; settle once the
    // pristine check has a verdict (swap done, declined, or error).
    const settle = () => {
      if (!puritySettledRef.current) {
        puritySettledRef.current = true;
        setPuritySettled(true);
      }
    };
    if (libraries.length !== 1) {
      settle();
      return;
    }
    if (libraries[0].name !== "CleanroomDemo") {
      settle();
      return;
    }
    const pristine =
      libraries[0].text === DEFAULT_CQL ||
      cellifiedDefaultPristine(libraries[0].text);
    if (!pristine) {
      settle();
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const res = await fetch("/api/workspace");
        const b = (await res.json()) as {
          workspace?: {
            libraries?: { name: string }[];
            measures?: Array<
              string | { resource?: Record<string, unknown> | null }
            >;
          };
          data?: { libraries?: { name: string }[] };
        };
        const d = b?.workspace ?? b?.data;
        const disk = d?.libraries ?? [];
        if (cancelled) return;
        if (disk.length === 0) {
          settle();
          return;
        }
        // S26 review fix: prefer the workspace MEASURE's primary library
        // (Measure.library[0] canonical tail — disk measures ship their
        // resource in this payload) over the alphabetical first — a
        // showcase workspace's point is its measure; otherwise the boot
        // opens an INCLUDE and the heartbeat targets the wrong library.
        let first = disk[0].name;
        const diskMeasure = (b?.workspace?.measures ?? []).find(
          (m) => typeof m !== "string" && !!m?.resource,
        );
        const primRef =
          diskMeasure && typeof diskMeasure !== "string"
            ? ((diskMeasure.resource?.library as string[] | undefined)?.[0] ??
              null)
            : null;
        const primName = primRef
          ? (primRef.split("/").filter(Boolean).pop()?.split("|")[0] ?? null)
          : null;
        if (primName && disk.some((l) => l.name === primName)) {
          first = primName;
        }
        const libRes = await fetch(
          `/api/libraries/${encodeURIComponent(first)}`,
        );
        const lb = (await libRes.json()) as {
          data?: { text?: string };
          text?: string;
        };
        const text = lb?.data?.text ?? lb?.text;
        if (cancelled) return;
        if (typeof text !== "string" || !text) {
          settle();
          return;
        }
        // Name-derived id — NOT the demo's "lib_0": the S7 cellsRemoved
        // list persists per tab key, and a stale "library:lib_0" entry
        // from the demo state would suppress auto-cellification for the
        // workspace library.
        // S27: NAME-derived id (the comment's intent) — newLibraryId([])
        // returned "lib_0", the SAME tab key the demo boot library used,
        // so the demo's adoptedRef entry blocked auto-split on the real
        // library (cells view opened empty and the heartbeat was
        // suppressed while cells were active → no results table).
        const libId = `lib_${first.toLowerCase()}`;
        setLibraries([{ id: libId, name: first, text }]);
        setMeasures((ms) =>
          ms.map((m) =>
            m.mainLibraryId === "lib_0" ? { ...m, mainLibraryId: libId } : m,
          ),
        );
        // S28: re-key the editor tab to the NEW library id. The stale
        // demo tab key (library:lib_0) kept rendering the swap-in text
        // under an ADOPTED tab key — the markerless-buffer effect then
        // persisted library:lib_0 into cellsRemoved, permanently
        // suppressing cellification for every fresh boot.
        setEditorTabs([{ id: `library:${libId}`, kind: "library", resourceId: libId }]);
        setActiveEditorTabId(`library:${libId}`);
        settle();
      } catch {
        /* offline/absent workspace listing — keep defaults */
        settle();
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [restored, serverMode.kind, libraries]);

  useEffect(() => {
    if (!restored) return;
    // S21 storage doctrine: STANDALONE persists the full workspace;
    // CONNECTED persists CHROME ONLY (prefs, run history, active tab —
    // INV-4) with content fields emptied (server disk is the source of
    // truth; a reconnecting session must not resurrect stale content).
    const connected = serverMode.kind === "connected";
    const t = setTimeout(() => {
      saveWorkspace({
        libraries: connected ? [] : libraries,
        dataset:
          connected || !dataset?.resources?.length
            ? null
            : { resources: dataset.resources as unknown[] },
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
        measures: connected ? [] : measures,
        activeMeasureId: connected ? null : activeMeasureId,
        expectedReports: connected ? {} : expectedReports,
        viewDefs: connected ? [] : viewDefs,
        paramValues: connected ? {} : paramValues,
        viewConfig: connected ? null : viewConfig,
        runHistory,
        activeTabPref: consoleTab,
        terminology: connected ? { valuesets: [] } : terminology,
      })
        .then(() => {
          // S29: "last saved" is a CONTENT save — connected writes are
          // chrome-only, so they must not claim the content was saved.
          if (!connected) setLastSavedAt(Date.now());
        })
        .catch(() => undefined);
    }, 800);
    return () => clearTimeout(t);
  }, [
    serverMode.kind,
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
  const mainLib = libraries[effectiveEntrypoint] ?? active;

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
  // S26 review fix: when the central editor has NO library open yet
  // (fresh connected boot), the heartbeat targets the MEASURE's primary
  // from the last EVALUATED workspace library (primary tx) or the first
  // workspace library — never the current tab placeholder, so the MR
  // tab materializes on boot and the measure entrypoint is never an
  // unrelated include.
  // S26d review fix: the tab KIND alone decides — never the buffer
  // content. The earlier `&& !!active?.text` guard flapped to
  // hosting-tab whenever a user emptied the editor (Ctrl+A Delete),
  // unmounting the editor pane mid-typing.
  const activeTabIsLibrary =
    !activeEditorTabId || parseTabId(activeEditorTabId).kind === "library";
  // S26d review fix: the connected NO-LIBRARY-OPEN heartbeat target —
  // when the editor holds NO library tab (fresh connected boot before
  // the purity open), the run falls to the measure's primary via
  // mainLib; keyed on the LIBRARY COUNT (never the transient text —
  // a Select-All+Delete empties text for a frame and must not flip the
  // editor column into hosting-tab).
  const runLib =
    activeTabIsLibrary && libraries.length > 0 ? (active ?? mainLib) : mainLib;
  const runIsEntrypoint = runLib === mainLib;
  // Stable identity across re-renders (same name+text → same object):
  // the auto-eval effect keys on [main, [main]] — a fresh object per
  // render would re-trigger the 2s debounce forever.
  const main = useMemo<LibraryText>(
    () => ({
      name: runLib.name,
      // S31: markers are editor metadata — stripping them makes the
      // evaluation payload identical to the disk text, so the server's
      // warm translation cache hits on first load (and no marker comment
      // ever reaches the engine).
      text: stripCellMarkers(runLib.text),
    }),
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
    // S31: disk ValueSets ARE workspace-sourced — the Measure inputs
    // table must not report them as "—/unsourced" just because they were
    // never opened in the browser this session.
    for (const url of diskValuesetUrls) map[url] = "workspace";
    for (const v of dataset?.valueset_resources ?? []) {
      const url = (v as Record<string, unknown>)?.url;
      if (typeof url === "string") map[url] = "dataset";
    }
    for (const v of terminology.valuesets) {
      const url = (v as Record<string, unknown>)?.url;
      if (typeof url === "string") map[url] = "workspace";
    }
    return map;
  }, [dataset, terminology, diskValuesetUrls]);

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
      if (!main.text) return Promise.resolve(null);
      if (serverMode.kind !== "connected" && !evalDataset) {
        return Promise.resolve(null);
      }
      if (hoverEvalRef.current) return hoverEvalRef.current;
      // S31: connected hover values come from the SERVER (same dataset as
      // the heartbeat, warm translation) — never the browser engine.
      const p = (serverMode.kind === "connected"
        ? fetch("/api/evaluate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              libraries: mainLibs,
              library: main.name,
              parameters: runtimeParameters,
            }),
          }).then((r) => r.json())
        : workerRequest({
            type: "evaluate_library",
            libraries: mainLibs,
            main,
            dataset: evalDataset,
            parameters: runtimeParameters,
            emit_sql: false,
          }).then((resp) => JSON.parse((resp as { envelope: string }).envelope))
      )
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
  // S26a (item 4): connected mode has NO in-browser dataset
  // requirement — the heartbeat evaluates the SERVER workspace dataset.
  // Standalone still needs the browser dataset (the worker is the
  // engine there).
  const canAutoEval =
    // S31: never evaluate before the mode handshake settles — a pre-
    // detection heartbeat used the STANDALONE branch and booted Pyodide
    // (~10s) even though the session is connected.
    !serverDetectPending &&
    !!main?.text &&
    (serverMode.kind === "connected" || !!evalDataset);

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
      _mode: "cell" | "cell_deps" | "to_here" | "run_all",
    ): Promise<Record<string, { ok: boolean; lines: string[] }>> => {
      const out: Record<
        string,
        { ok: boolean; lines: string[]; columns?: string[]; rows?: Array<Array<string>> }
      > = {};
      if (!main) return out;
      // S32 fix: main.text is the MARKER-STRIPPED evaluation payload
      // (S31) — the cell graph must read the raw editor buffer, or every
      // cell run composes an empty library ("no output" / diagnostics).
      const bufferText = runLib.text;
      const graph = buildCellGraph(bufferText);
      const cells = splitCells(bufferText).cells;
      const composed = composeCellClosure(graph.header, cells, names);
      // S32 fix: the composed library carries ONLY the main library — the
      // include closure must ride along or the STANDALONE worker cannot
      // resolve includes ("Could not resolve included library ..."). The
      // connected server backfills from disk, so this is parity-safe.
      const libs: LibraryText[] = [
        { name: main.name, text: composed },
        ...libraries
          .filter((l) => l.name !== main.name)
          .map((l) => ({ name: l.name, text: l.text })),
      ];
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
        // S28 (perf, option A): Run All is ONE evaluation — the composed
        // library translates once (full projection) and each nameable
        // cell slices its own column, exactly like the standalone
        // worker path. Single-cell runs keep per-closure evaluation.
        const batchAll = _mode === "run_all";
        if (batchAll) {
          try {
            const res = await fetch("/api/evaluate", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                libraries: libs,
                library: main.name,
                parameters: runtimeParameters,
              }),
            });
            const data = (await res.json()) as any;
            if (data?.ok === false) {
              const msg = data?.diagnostics?.[0]?.message ?? "evaluation failed";
              for (const n of names) out[n] = { ok: false, lines: [msg] };
              return out;
            }
            const cols: string[] = data?.columns ?? [];
            const rows = (data?.rows ?? []) as Array<Record<string, unknown>>;
            for (const n of names) {
              const own = nameable.has(n) ? cols.filter((c) => c === n) : [];
              // S28: patient_id rides along when present — a lone boolean
              // column per cell is unreadable against 66 patients.
              const useCols = own.length
                ? ["patient_id", ...own]
                : cols;
              out[n] = {
                ok: true,
                lines: [
                  useCols.join(" | "),
                  ...rows
                    .slice(0, 10)
                    .map((r) => useCols.map((c) => String(r[c] ?? "")).join(" | ")),
                ],
                columns: useCols,
                rows: rows.map((r) => useCols.map((c) => fmtCell(r[c]))),
              };
            }
          } catch (err) {
            const msg = `server run failed: ${err instanceof Error ? err.message : String(err)}`;
            for (const n of names) out[n] = { ok: false, lines: [msg] };
          }
          return out;
        }
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
    [main, runLib.text, libraries, serverMode.kind, evalDataset, runtimeParameters],
  );

  const runEvaluation = async (manualServer = false) => {
    if (!manualServer && !canAutoEval) return;
    const seq = ++evalSeqRef.current;
    evalBusyRef.current = true;
    // Checkpoint ruling (S26a item 4 revision): connected mode ALWAYS
    // evaluates SERVER-side — manual whole-library runs AND the
    // auto-recalc heartbeat (the server workspace dataset is the
    // connected engine's truth; a browser-origin heartbeat evaluated
    // the wrong default 3-patient dataset). Standalone keeps the
    // in-browser worker heartbeat. Unreachable server → typed error.
    const useServer = manualServer || serverMode.kind === "connected";
    if (useServer) {
      try {
        const res = await fetch("/api/evaluate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            libraries: mainLibs,
            library: main.name,
            // S26a/s26c: server runs honor the UI-entered parameters
            // (same contract as cell runs — UI values override workspace
            // Parameters-resource defaults server-side).
            parameters: runtimeParameters,
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
          `server run — ${b.patient_count} patients from the server workspace dataset (${main.name})`,
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
            surface: "console",
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
        // S26a: server runs also materialize per-patient MeasureReports
        // (the MR pane renders from any origin's rows — the worker
        // helper is a pure row transformation, engine-independent).
        if (measure && runIsEntrypoint) {
          try {
            // Define-keyed heartbeat rows → population columns from the
            // measure's own mapping (the MR helper reads snake_case codes).
            const popRows = populationRows(
              b.rows ?? [],
              b.columns ?? [],
              outputColumnsFromMeasure(measure),
            );
            const repEnv = await materializeMeasureReports(
              serverMode.kind === "connected",
              measure,
              popRows.rows,
              popRows.columns,
            );
            setLastReports(repEnv.ok ? repEnv.reports ?? [] : null);
          } catch {
            setLastReports(null);
          }
        } else {
          setLastReports(null);
        }
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
        // S23-1 (journey): the TEXT-MODE whole-library run shows ALL
        // defines — the measure-mapped narrowing belongs to the MEASURE
        // surface, never the editor's Run. 6j: non-entrypoint targets
        // already return every define of that library.
        output_columns: undefined,
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
            surface: "console",
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
            const popRows = populationRows(
              env.rows,
              env.columns,
              outputColumnsFromMeasure(measure),
            );
            const repEnv = await materializeMeasureReports(
              false,
              measure,
              popRows.rows,
              popRows.columns,
            );
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
    // S23-2 (PLAN §8): cell mode renders results inline per cell ONLY —
    // suppress the heartbeat while the cell view is open (manual console
    // runs return after switching back to text).
    // S26d review fix: the suppression is a LIBRARY-TAB concern — on
    // HOST tabs (measure/expected/valueset…) the cells view is hidden
    // and the measure surface NEEDS its heartbeat (MR/Funnel starve
    // otherwise on a fresh boot that auto-cellified).
    if (cellsViewActiveRef.current && activeTabIsLibrary) return;
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
  }, [mainLibs, main, evalDataset, effectiveOutputColumns, measure, runtimeParameters, canAutoEval, recalcSeconds, cellsViewActive, activeTabIsLibrary]);

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

  /** S32: switch to a workspace DIRECTORY (absolute path, connected).
   *  Shows the non-dismissible switching overlay through the server
   *  re-root + kernel rebuild, then reloads (boot overlay takes over). */
  const openWorkspacePath = async (path: string, name: string) => {
    if (serverMode.kind !== "connected") return;
    setFolderModal(null);
    setSwitching(`Switching workspace — ${name}`);
    // Record BEFORE the switch: the server's `switched` WS event reloads
    // the page immediately, so a post-success write would be dropped.
    setRecents(pushRecent({ name, path }));
    try {
      const r = await switchWorkspaceByPath(path);
      if (!r.ok) {
        setSwitching(null);
        setStatusNote(`workspace switch failed: ${r.message}`);
        return;
      }
      window.location.reload();
    } catch (e) {
      setSwitching(null);
      setStatusNote(`workspace switch failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  /** S32: named switch (registry name) — used by Recent Workspaces and
   *  pinned examples; records the recent after a successful switch. */
  const switchWorkspaceNamed = async (name: string) => {
    if (serverMode.kind === "connected") {
      setSwitching(`Switching workspace — ${name}`);
      // Record BEFORE the switch (the `switched` WS event reloads first).
      setRecents(pushRecent({ name, path: name }));
      try {
        const r = await switchWorkspaceByName(name);
        if (!r.ok) {
          setSwitching(null);
          setStatusNote(`workspace switch failed: ${r.message}`);
          return;
        }
        window.location.reload();
      } catch (e) {
        setSwitching(null);
        setStatusNote(`workspace switch failed: ${e instanceof Error ? e.message : String(e)}`);
      }
      return;
    }
    // Standalone: examples load as packaged zips (no directory concept).
    const zip = name !== "demo-workspace";
    if (!zip) {
      setStatusNote(
        "the demo example is a CONNECTED workspace — start a devserver on examples/demo-workspace (or open File > Open File > Measure package)",
      );
      return;
    }
    void loadExample(name);
  };

  /** S32: Save Workspace — connected writes the MADiE package into a
   *  chosen server folder; standalone downloads it (browser dialog). */
  const saveWorkspacePackage = async (folder: string, _name: string) => {
    setFolderModal(null);
    if (!measure) {
      setStatusNote("nothing to save — need a Measure");
      return;
    }
    const mname = String((measure as Record<string, unknown>).name ?? "measure");
    setStatusNote("building measure package…");
    try {
      const r = await savePackageToFolder(mname, folder);
      if (!r.ok) {
        setStatusNote(`package save failed: ${r.message}`);
        return;
      }
      setStatusNote(`package saved — ${r.path}`);
    } catch (e) {
      setStatusNote(`package save failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const exportMadieZip = () => {
    try {
      const primaryName = libraries[effectiveEntrypoint]?.name ?? libraries[0]?.name;
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
      case "config:measure-json":
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
      case "config:parameters-json":
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
  // S26 (slice 3): CONNECTED expected results come from DISK — the
  // workspace's MeasureReport/<measure>/<case>.json files
  // (fixture-official for the CMS example workspaces) surface through
  // the same expectedResults state the Tests/Compare panes render.
  const expectedDiskKey = `${serverMode.kind}:${activeMeasureEntry?.id ?? ""}:${
    (measure?.name as string) ?? ""
  }`;
  useEffect(() => {
    if (serverMode.kind !== "connected" || !activeMeasureEntry || !measure?.name) {
      return;
    }
    let cancelled = false;
    const mKey = String(measure.name);
    void fetch(
      `/api/tests/expected?measure=${encodeURIComponent(mKey)}`,
    )
      .then((r) => r.json())
      .then(
        (
          b: {
            patients?: Array<{ report?: Record<string, unknown> }>;
          },
        ) => {
          if (cancelled) return;
          const reports = (b?.patients ?? [])
            .map((p) => p.report)
            .filter(Boolean) as Array<Record<string, unknown>>;
          setExpectedReports((prev) =>
            reports.length
              ? { ...prev, [activeMeasureEntry.id]: reports }
              : prev,
          );
        },
      )
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expectedDiskKey]);

  // S17 Muse: canonical header names per file stem (one /api/workspace
  // read when connected) so disk rows display library names, not stems.
  const [diskHeaderNames, setDiskHeaderNames] = useState<Record<string, string>>({});
  // S30: version maps for the nav version pills (replacing "on disk").
  const [diskLibVersions, setDiskLibVersions] = useState<Record<string, string>>({});
  const [diskVsVersions, setDiskVsVersions] = useState<Record<string, string>>({});
  const [diskViewMeta, setDiskViewMeta] = useState<
    Record<string, { label?: string; version?: string }>
  >({});
  // S22a: disk valueset rows label by FHIR resource id (from the same
  // /api/workspace read — {path, id} entries), falling back to file stem.
  const [diskValuesetIds, setDiskValuesetIds] = useState<Record<string, string>>({});
  useEffect(() => {
    if (serverMode.kind !== "connected") return;
    let cancelled = false;
    void fetch("/api/workspace")
      .then((r) => r.json())
      .then((b: {
        workspace?: {
          libraries?: { name: string; path?: string; version?: string | null }[];
          valuesets?: Array<
            | string
            | {
                path: string;
                id?: string | null;
                name?: string | null;
                title?: string | null;
                version?: string | null;
                url?: string | null;
              }
          >;
          measures?: Array<string | { path: string; resource?: Record<string, unknown> | null }>;
          view_meta?: Array<{
            path: string;
            id?: string | null;
            name?: string | null;
            title?: string | null;
            version?: string | null;
          }>;
          parameters?: Record<string, string>;
        };
        data?: {
          libraries?: { name: string; path?: string; version?: string | null }[];
          valuesets?: Array<
            | string
            | {
                path: string;
                id?: string | null;
                name?: string | null;
                title?: string | null;
                version?: string | null;
                url?: string | null;
              }
          >;
          measures?: Array<string | { path: string; resource?: Record<string, unknown> | null }>;
          view_meta?: Array<{
            path: string;
            id?: string | null;
            name?: string | null;
            title?: string | null;
            version?: string | null;
          }>;
          parameters?: Record<string, string>;
        };
      }) => {
        if (cancelled) return;
        const d = b?.workspace ?? b?.data;
        const libs = d?.libraries ?? [];
        const out: Record<string, string> = {};
        const libVersions: Record<string, string> = {};
        for (const l of libs) {
          const file = (l.path ?? "").split("/").pop() ?? "";
          const stem = file.replace(/\.cql$/i, "");
          if (stem) out[stem] = l.name;
          if (stem && typeof l.version === "string" && l.version) {
            libVersions[stem] = l.version;
          }
        }
        setDiskHeaderNames(out);
        setDiskLibVersions(libVersions);
        // S26 review fix: disk valueset rows label by name → title → id
        // (OIDs are hostile nav labels).
        const vsOut: Record<string, string> = {};
        const vsVersions: Record<string, string> = {};
        for (const v of d?.valuesets ?? []) {
          if (typeof v === "string") continue;
          const file = (v.path ?? "").split("/").pop() ?? "";
          const stem = file.replace(/\.json$/i, "");
          const label =
            (typeof v.name === "string" && v.name.trim()) ||
            (typeof v.title === "string" && v.title.trim()) ||
            (typeof v.id === "string" && v.id.trim()) ||
            "";
          if (stem && label) {
            vsOut[stem] = label;
          }
          if (stem && typeof v.version === "string" && v.version) {
            vsVersions[stem] = v.version;
          }
        }
        setDiskValuesetIds(vsOut);
        setDiskVsVersions(vsVersions);

        // S31: disk ValueSet canonical URLs seed the terminology resolver's
        // workspace set — disk-backed valuesets are NEVER "unresolved".
        const vsUrls: string[] = [];
        for (const v of d?.valuesets ?? []) {
          if (typeof v === "string") continue;
          if (typeof v.url === "string" && v.url.trim()) vsUrls.push(v.url);
        }
        setDiskValuesetUrls(vsUrls);

        // S31: workspace Parameters defaults ARE the bound values the
        // server applies — surface them in the drawer (never clobber a
        // value the user already bound this session).
        const wsParams = d?.parameters ?? {};
        if (Object.keys(wsParams).length) {
          setParamValues((prev) => {
            const next = { ...wsParams, ...prev };
            return next;
          });
        }

        // S30: ViewDefinition nav labels + versions (disk is the source
        // of truth in connected mode).
        const viewMeta: Record<string, { label?: string; version?: string }> = {};
        for (const vm of d?.view_meta ?? []) {
          const file = (vm.path ?? "").split("/").pop() ?? "";
          const stem = file.replace(/\.json$/i, "");
          if (!stem) continue;
          const label =
            (typeof vm.name === "string" && vm.name.trim()) ||
            (typeof vm.title === "string" && vm.title.trim()) ||
            (typeof vm.id === "string" && vm.id.trim()) ||
            "";
          viewMeta[stem] = {
            label: label || undefined,
            version:
              typeof vm.version === "string" && vm.version
                ? vm.version
                : undefined,
          };
        }
        setDiskViewMeta(viewMeta);
        // S26 (slice 3): ADOPT disk Measures in connected mode — the
        // showcase workspaces' real eCQM Measures become the app's
        // measure list (disk is the source of truth; the seed
        // CleanroomMeasure is replaced, not merged).
        const diskMeasures = (d?.measures ?? []).filter(
          (m): m is { path: string; resource: Record<string, unknown> } =>
            typeof m !== "string" && !!m?.resource,
        );
        if (diskMeasures.length) {
          setMeasures((prev) => {
            // One-shot: only replace while the collection is the seed
            // (nothing user-authored to clobber).
            if (prev.length > 1 || prev[0]?.id !== "msr_0") return prev;
            const adopted = diskMeasures.map((m, i) => ({
              id: `disk_msr_${i}`,
              mainLibraryId: "lib_0",
              resource: m.resource,
            }));
            setActiveMeasureId(adopted[0]?.id ?? null);
            // S26 review fix: adopted disk measures carry the PRIMARY library
            // to a real tab — Measure.library[0]'s canonical tail names
            // it (e.g. https://madie.cms.gov/Library/CMS125FHIR...).
            // Adopted disk libraries are OPENED-ON-DEMAND (nav click);
            // until the primary tab exists, match by NAME so the
            // measure surface + heartbeat target the right library.
            const primRef = (adopted[0]?.resource?.library as string[] | undefined)?.[0];
            const primName = primRef
              ? primRef.split("/").filter(Boolean).pop()?.split("|")[0] ?? null
              : null;
            if (primName) {
              (adopted[0] as { primaryLibraryName?: string }).primaryLibraryName = primName;
            }
            return adopted;
          });
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [serverMode.kind, wsFiles.loading, wsChanged.size]);
  const navLibDiskItems = mergeDiskLibraries(
    navLibItems,
    diskRefs("cql"),
    diskHeaderNames,
    diskLibVersions,
  );
  const navVsDiskItems = mergeDiskValuesets(
    navValuesetItems,
    diskRefs("valuesets"),
    diskValuesetIds,
    diskVsVersions,
  );
  const navViewDiskItems = mergeDiskViews(
    navViewItems,
    diskRefs("views"),
    diskViewMeta,
  );

  const navSectionModels: Record<
    NavSectionId,
    { title: string; items: NavItem[]; count: number }
  > = {
    libraries: {
      title: "Libraries",
      items: filterItems(navLibDiskItems, navFilters.libraries),
      count: navLibDiskItems.length,
    },
    valuesets: {
      title: "Value Sets",
      items: filterItems(navVsDiskItems, navFilters.valuesets),
      count: navVsDiskItems.length,
    },
    // S29: Measure + Parameters ride ONE Setup/Config panel with
    // sub-group headings (group tags are rendered by NavRail).
    config: {
      title: "Config",
      items: filterItems(
        [
          ...navMeasureItems.map((it) => ({ ...it, group: "Measure" })),
          ...navParameterItems.map((it) => ({ ...it, group: "Parameters" })),
        ],
        navFilters.config,
      ),
      count: navMeasureItems.length + navParameterItems.length,
    },
    tests: {
      title: "Test Cases",
      items: [],
      count: dataset?.resources?.length ?? 0,
    },
    expected: {
      title: "Expected",
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
        surface: "console",
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
  const populationColumns = useMemo(
    () => outputColumnsFromMeasure(measure),
    [measure],
  );
  const verifyCompare = useMemo(
    () =>
      latestRunIsEntrypoint
        ? deriveCompare(
            latestLibraryRun?.payload?.rows,
            expectedValues ?? {},
            populationCodes,
            populationColumns,
          )
        : null,
    [
      latestRunIsEntrypoint,
      latestLibraryRun,
      expectedValues,
      populationCodes,
      populationColumns,
    ],
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
  // S25: CONNECTED mode feeds the SAME L3 panel from local files —
  // fetch the focused patient's bundle (Patient + every resource the
  // kernel attributes to them) and synthesize a PatientGroup from it.
  const [serverFocusedBundle, setServerFocusedBundle] = useState<{
    pid: string;
    resources: Array<Record<string, unknown>>;
  } | null>(null);
  useEffect(() => {
    if (serverMode.kind !== "connected" || !focusedPid) {
      setServerFocusedBundle(null);
      return;
    }
    let cancelled = false;
    void fetch(`/api/patient/${encodeURIComponent(focusedPid)}`)
      .then((r) => r.json())
      .then(
        (
          b: {
            resources?: Array<Record<string, unknown>>;
            data?: { resources?: Array<Record<string, unknown>> };
          },
        ) => {
          if (cancelled) return;
          const resources = b?.resources ?? b?.data?.resources ?? [];
          if (resources.length > 0) {
            setServerFocusedBundle({ pid: focusedPid, resources });
          } else {
            setServerFocusedBundle(null);
          }
        },
      )
      .catch(() => {
        if (!cancelled) setServerFocusedBundle(null);
      });
    return () => {
      cancelled = true;
    };
  }, [serverMode.kind, focusedPid]);
  const serverFocusedGroup = useMemo<PatientGroup | null>(() => {
    if (serverMode.kind !== "connected" || !focusedPid || !serverFocusedBundle)
      return null;
    if (serverFocusedBundle.pid !== focusedPid) return null;
    if (patientGroups.some((g) => g.key === focusedPid)) return null;
    const rows: DatasetRowRef[] = serverFocusedBundle.resources.map(
      (resource, i) => ({
        index: -(i + 1), // negative = server-backed (no storage index)
        resource,
        resourceType: String(resource.resourceType ?? "Unknown"),
        id: String(resource.id ?? ""),
      }),
    );
    return {
      key: focusedPid,
      label: focusedPid,
      phantom: false,
      unattributed: false,
      rows,
    };
  }, [serverMode.kind, focusedPid, serverFocusedBundle, patientGroups]);
  const focusedGroup = focusedPid
    ? (patientGroups.find((g) => g.key === focusedPid) ??
      serverFocusedGroup ??
      undefined)
    : undefined;
  useEffect(() => {
    if (
      focusedPid &&
      serverMode.kind !== "connected" &&
      !patientGroups.some((g) => g.key === focusedPid)
    ) {
      setFocusedPid(null);
    }
  }, [focusedPid, patientGroups, serverMode.kind]);

  // Dataset callbacks shared by the L2 list and the L3 detail panel.
  const editDatasetResource = (index: number) => {
    if (index < 0) {
      // S25: server-backed row (L3 over local files) — fetch the FULL
      // resource (the builder handoff contract; previews are truncated)
      // and prefill the builder from it.
      const row = serverFocusedGroup?.rows.find((r) => r.index === index);
      const rtype = row?.resourceType;
      const rid = row?.id;
      if (!rtype || !rid) return;
      void fetch(
        `/api/patient/resources?resourceType=${encodeURIComponent(rtype)}&rid=${encodeURIComponent(rid)}`,
      )
        .then((r) => r.json())
        .then(
          (
            b: {
              resource?: Record<string, unknown>;
              data?: { resource?: Record<string, unknown> };
            },
          ) => {
            const resource = b?.resource ?? b?.data?.resource;
            if (!resource) return;
            setBuilderPrefill((prev) => ({
              resource,
              nonce: (prev?.nonce ?? 0) + 1,
            }));
            openEditorTab("test", `server-${rtype}-${rid}`);
          },
        )
        .catch(() => undefined);
      return;
    }
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
    if (index < 0) return; // server-backed rows are disk-owned (S25)
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
          // S22a: valuesets entries are {path, id?} — path match by file
          // name (id is the drawer label, not the file identity).
          const wsB = (await wsRes.json()) as {
            workspace?: { valuesets?: Array<string | { path: string; id?: string | null }> };
            data?: { valuesets?: Array<string | { path: string; id?: string | null }> };
          };
          const d = wsB?.workspace ?? wsB?.data;
          const entries = (d?.valuesets ?? []).map((v) =>
            typeof v === "string" ? { path: v, id: undefined } : v,
          );
          const vsPath = entries.find(
            (e) => String(e.path).split("/").pop() === name,
          )?.path;
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
      // S27: a disk ViewDefinition OPENS — fetch its text, adopt it as a
      // session view def, and open the view tab (the pane runs it over
      // the session MeasureReports; the old "preview only" note was a
      // dead end).
      void (async () => {
        const name = String(item.meta?.name ?? `${item.label}.json`);
        setStatusNote(`opening ${name}…`);
        try {
          const wsRes = await fetch("/api/workspace");
          const wsB = (await wsRes.json()) as {
            workspace?: { views?: Array<string | { path: string }> };
            data?: { views?: Array<string | { path: string }> };
          };
          const d = wsB?.workspace ?? wsB?.data;
          const entries = (d?.views ?? []).map((v) =>
            typeof v === "string" ? { path: v } : v,
          );
          const vdPath = entries.find(
            (e) => String(e.path).split("/").pop() === name,
          )?.path;
          if (!vdPath) {
            setStatusNote(`could not resolve ${name}`);
            return;
          }
          const res = await fetch(`/api/view?path=${encodeURIComponent(vdPath)}`);
          const b = (await res.json()) as { ok?: boolean; text?: string };
          if (b?.ok === false || typeof b?.text !== "string") {
            setStatusNote(`could not load ${name}`);
            return;
          }
          const resource = JSON.parse(b.text) as Record<string, unknown>;
          const id =
            typeof resource.id === "string" && resource.id
              ? resource.id
              : `vd_${Date.now().toString(36)}`;
          const vName =
            (typeof resource.name === "string" && resource.name) || item.label;
          setViewDefs((vs) => [
            ...vs.filter((v) => v.id !== id),
            { id, name: vName, resource },
          ]);
          setPendingViewOpen({ id, resource });
          openEditorTab("view", id);
          setStatusNote(`opened view ${vName}`);
        } catch (e) {
          setStatusNote(
            `view open failed: ${e instanceof Error ? e.message : String(e)}`,
          );
        }
      })();
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
      case "patient":
        tabLabels[t.id] = `Patient ${t.resourceId}`;
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
  // S27: leaving the view tab drops the one-shot VD — reopening the tab
  // shows the "From Measure" default.
  useEffect(() => {
    if (hostTab?.kind !== "view") setPendingViewOpen(null);
  }, [hostTab?.id, hostTab?.kind]);
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
    // S30: connected workspaces list their DISK ViewDefinitions only —
    // the derived "View 1" seed duplicated the shipped VD (same report
    // shape, two nav rows). Standalone keeps the one-click default.
    if (serverMode.kind === "connected") return;
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
      funnelOutput={
        <MrFunnel
          result={evalResult}
          populationColumns={outputColumnsFromMeasure(measure)}
        />
      }
      runRequest={runRequest}
      runs={runHistory}
      displayRun={displayRun}
      onSelectRun={setSelectedRunId}
      onManualRun={appendManualRun}
      viewOutput={
        <ViewOutputPanel
          viewResult={viewResult}
          runDiff={appRunDiff}
          busy={viewRunning}
        />
      }
      verifyCompare={verifyCompare}
      compareStale={compareStale}
      activeTab={consoleTab}
      onTabChange={setConsoleTab}
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
        <div className="workspace-actions">
        <DropdownMenu label="File" testId="file-menu">
            {/* S32 menu redesign:
                Open File ▸ (MADiE package / test cases — separate MADiE
                exports), Open Workspace… (server folder picker),
                Recent Workspaces ▸ (pinned examples + last 10),
                Reset Workspace, Save Workspace… (server folder in
                connected / browser download in standalone), Share.
                Removed: Workspace submenu (folded into Open/Recent),
                Open > Examples (Recent covers it), Add > Bundle merge
                (the Test Cases nav ▾ menu imports bundles). */}
            <DropdownSubmenu label="Open File" testId="file-open">
              <button
                className="dropdown-item"
                data-testid="madie-import"
                onClick={() => madieFileRef.current?.click()}
              >
                MADiE Measure Package…
              </button>
              <button
                className="dropdown-item"
                data-testid="madie-tests-import"
                onClick={() => madieTestsFileRef.current?.click()}
              >
                MADiE Test Cases…
              </button>
            </DropdownSubmenu>
            {serverMode.kind === "connected" && (
              <button
                className="dropdown-item"
                data-testid="file-open-workspace"
                onClick={() => setFolderModal("open")}
              >
                Open Workspace…
              </button>
            )}
            <DropdownSubmenu label="Recent Workspaces" testId="file-recent">
              {PINNED_EXAMPLES.map((ex) => (
                <NativeClickButton
                  key={ex.name}
                  testId={`example-workspace-${ex.name}`}
                  onClick={() => void switchWorkspaceNamed(ex.name)}
                >
                  {exLabel(ex.name)}
                </NativeClickButton>
              ))}
              {/* Only NON-pinned recents: the three examples are always
                  listed above (S32 review: no duplicate rows). */}
              {recents.some(
                (r) => !PINNED_EXAMPLES.some((p) => p.name === r.name),
              ) && <div className="dropdown-sep" />}
              {recents
                .filter(
                  (r) => !PINNED_EXAMPLES.some((p) => p.name === r.name),
                )
                .map((r) => (
                <NativeClickButton
                  key={r.path}
                  testId={`recent-workspace-${r.name}`}
                  onClick={() =>
                    serverMode.kind === "connected" && r.path.startsWith("/")
                      ? void openWorkspacePath(r.path, r.name)
                      : void switchWorkspaceNamed(r.name)
                  }
                >
                  {r.name}
                </NativeClickButton>
              ))}
            </DropdownSubmenu>
            <button
              className="dropdown-item"
              data-testid="workspace-reset"
              onClick={() => {
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
              Reset Workspace
            </button>
            <div className="dropdown-sep" />
            <button
              className="dropdown-item"
              data-testid="file-save-workspace"
              onClick={() => {
                if (serverMode.kind === "connected") setFolderModal("save");
                else exportMadieZip();
              }}
            >
              Save Workspace…
            </button>
            <button className="dropdown-item" data-testid="share-btn" onClick={shareLink}>
              Share
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
        <NavRail
          sections={{
            libraries: { ...navSectionModels.libraries, filter: navFilters.libraries },
            valuesets: { ...navSectionModels.valuesets, filter: navFilters.valuesets },
            config: { ...navSectionModels.config, filter: navFilters.config },
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
              serverPatientIds={serverPatientIds}
              serverPatientResources={serverPatientResources}
              focusedPid={focusedPid}
              onFocusedPidChange={setFocusedPid}
              filter={navFilters.tests}
            />
          }
        />
        <div
          className={`pane-col editor-col ${activeTabIsLibrary ? "" : "hosting-tab"}${
            activeTabIsLibrary && cellsViewActive ? " cells-fullheight" : ""
          }`}
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
            onCellsViewChange={setCellsViewActive}
            connected={serverMode.kind === "connected"}
            enginePending={serverDetectPending}
            holdAutoSplit={
              serverDetectPending ||
              (serverMode.kind === "connected" && !puritySettled) ||
              // S26 (item 11): example boots land in TEXT view — showcase
              // packages are read-heavy content; auto-cellify + tips
              // modal + console-free cells suppress the heartbeat that
              // should immediately render results.
              exampleBootRef.current
            }
            cellsViewForceCloseNonce={exampleForceTextNonce}
            onExplainRow={(pid, define, ctx) => void explainCellRow(pid, define, ctx)}
            parameters={runtimeParameters}
            cellEvidenceSlot={(cellName: string) =>
              cellEvidence && cellEvidenceKey === `${cellName}::${cellEvidence.patientId}` ? (
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
              measureMainLibraryId={
                // S26 review fix: adopted disk measures pin by NAME when
                // the primary tab isn't open — the picker's value must
                // match its choices (disk:<name> ids in connected mode).
                serverMode.kind === "connected" &&
                  activeMeasureEntry?.primaryLibraryName
                  ? `disk:${activeMeasureEntry.primaryLibraryName}`
                  : activeMeasureEntry?.mainLibraryId
              }
              measureLibraryChoices={
                // S26 review fix: connected mode offers the DISK
                // libraries (tabs open on demand) — the session tabs
                // alone made the measure picker a one-item list.
                serverMode.kind === "connected" &&
                Object.keys(diskHeaderNames).length
                  ? Object.values(diskHeaderNames).map((n) => ({
                      id: `disk:${n}`,
                      name: n,
                    }))
                  : libraries.map((l) => ({
                      id: l.id,
                      name: l.name,
                    }))
              }
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
                  explicitCommitOnly={serverMode.kind === "connected"}
                  onAddResource={(resource) => {
                    if (serverMode.kind === "connected") {
                      // S25: connected saves land on DISK (validate +
                      // append inside a workspace data dir); the data-hint
                      // offers the kernel restart (never auto-reloads).
                      void fetch("/api/resource/save", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                          resource,
                          replace: builderPrefill?.sourceIndex === undefined,
                        }),
                      }).catch(() => undefined);
                      setBuilderPrefill(null);
                      setBuilderContext(null);
                      return;
                    }
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
                    if (serverMode.kind === "connected") {
                      // S25: replacing a server-backed resource rewrites
                      // it in place (per-patient folder or ndjson line).
                      void fetch("/api/resource/save", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ resource, replace: true }),
                      }).catch(() => undefined);
                      setBuilderPrefill(null);
                      return;
                    }
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
                  serverPatientIds={serverPatientIds}
                  populationCodes={populationCodes}
                  expectedValues={expectedValues}
                  onExpectedValuesChange={updateExpectedValues}
                  measure={measure}
                  onUseCurrentResult={captureExpectedFromRun}
                  hasCurrentResult={!!lastReports?.length}
                />
              }
              onPatientSaved={(pid) =>
                setStatusNote(`saved patient ${pid} — restart kernel to reload`)
              }
              measureReports={lastReports}
              viewConfig={viewConfig?.overrides ?? null}
              onViewConfigChange={(overrides) => setViewConfig({ overrides })}
              onResult={setViewResult}
              recalcMs={recalcSeconds * 1000}
              viewReportsPending={!evalResult}
              onViewBusy={setViewRunning}
              initialVd={
                hostTab?.kind === "view" &&
                pendingViewOpen?.id === hostTab.resourceId
                  ? pendingViewOpen.resource
                  : null
              }
            />
          )}
          </div>
          {/* REORG 6e: the console is PINNED below the editor (default
              2/3 : 1/3) — drag to adjust; each row scrolls itself.
              S25: the CELLS surface is console-FREE — cell output renders
              inline per card, so the docked console hides entirely while
              the active library tab is in cells view (raised repeatedly:
              cells view must not waste a third of the screen). */}
          {consolePlacement === "bottom" &&
            !(activeTabIsLibrary && cellsViewActive) && (
              <Splitter
                orientation="horizontal"
                testid="editor-splitter"
                value={editorFr}
                onChange={setEditorFr}
                label="Resize editor and console"
              />
            )}
          {consolePlacement === "bottom" &&
            !(activeTabIsLibrary && cellsViewActive) &&
            consoleNode}
        </div>
        {consolePlacement === "right" && (
          <Splitter value={col1Fr} onChange={setCol1Fr} />
        )}
        {consolePlacement === "right" &&
          !(activeTabIsLibrary && cellsViewActive) && (
            <div className="pane-col run-col console-dock">{consoleNode}</div>
          )}
      </main>
      <StatusBar
        connected={serverMode.kind === "connected"}
        workspace={
          serverMode.kind === "connected" ? serverMode.workspace : null
        }
        engine={
          serverMode.kind === "connected" ? (serverMode.engine ?? null) : null
        }
        lastSavedAt={lastSavedAt}
        diskSource={serverMode.kind === "connected"}
        note={statusNote}
        onDismissNote={() => setStatusNote(null)}
        dataHint={serverMode.kind === "connected" && wsDataHint}
        onRestartKernel={() => {
          void fetch("/api/kernel/restart", { method: "POST" }).then(() =>
            setWsDataHint(false),
          );
        }}
        version={
          serverMode.kind === "connected"
            ? serverMode.version
            : boot.phase === "ready"
              ? boot.wheelVersion
              : null
        }
      />
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
      {folderModal && (
        <WorkspaceFolderModal
          mode={folderModal}
          onClose={() => setFolderModal(null)}
          onPick={(path, name) => {
            if (folderModal === "open") void openWorkspacePath(path, name);
            else void saveWorkspacePackage(path, name);
          }}
        />
      )}
      {switching && (
        <div className="switch-overlay" data-testid="switch-overlay" role="status">
          <span className="spinner" aria-hidden="true" />
          <span className="switch-title">Switching workspace…</span>
        </div>
      )}
      <BootOverlay state={boot} />
    </div>
  );
}
