/**
 * Transport interface: the engine-agnostic seam shared by the dev server
 * (HttpTransport) and the in-browser WASM engine (WasmTransport fixture).
 *
 * The reused wasm-demo components stay engine-agnostic because everything
 * they render flows through this interface.
 */

export interface WorkspaceLibrary {
  name: string;
  path: string;
  parse_ok: boolean;
  error: string | null;
  definitions: string[];
}

export interface WorkspaceInfo {
  libraries: WorkspaceLibrary[];
  valuesets: string[];
  measures: string[];
  datasets: string[];
  views?: string[];
  data_changed_hint: boolean;
}

export interface Diagnostic {
  code: string;
  message: string;
  detail?: string | null;
}

export interface TranslateResult {
  schema: number;
  ok: boolean;
  diagnostics: Diagnostic[];
  sql: string;
  column_types: Record<string, string>;
  definitions: string[];
}

export interface EvaluateResult {
  schema: number;
  ok: boolean;
  diagnostics: Diagnostic[];
  patient_count: number;
  columns: string[];
  rows: Record<string, unknown>[];
  column_types: Record<string, string>;
  sql: string | null;
  timing_ms: Record<string, number>;
}

export interface EvidenceResult {
  schema: number;
  ok: boolean;
  diagnostics: Diagnostic[];
  patient_id: string;
  rows?: Record<string, unknown>[];
  evidence?: Record<string, unknown>;
}

export interface VerifyResult {
  schema: number;
  ok: boolean;
  passed: boolean | null;
  diagnostics: Diagnostic[];
  summary: Record<string, number>;
  tests: Record<string, unknown>;
}

export interface HealthInfo {
  schema: number;
  ok: boolean;
  status: string;
  version: string;
  kernel_id: string;
  watching: number;
  /** Terminology provider status (c-vsac-cleanroom); presence-only — never key material. */
  terminology?: {
    provider: string;
    configured: boolean;
    api_key_set: boolean;
  };
}

export interface WorkspaceEvent {
  kind: "changed" | "data-hint" | "stale";
  paths: string[];
  workspace?: WorkspaceInfo;
  valuesets_stale?: boolean;
}

export type RunMode = "cell" | "cell_only" | "cell_deps" | "all" | "to_here";

export interface CellState {
  library: string;
  cell: string;
  status: "idle" | "running" | "ok" | "error" | "stale";
  run_seq: number;
  rows?: Record<string, unknown>[];
  sql?: string | null;
  error?: string | null;
}

export interface CellEvent {
  kind: "cellstate" | "result" | "cellerror" | "runerror" | "synced";
  library?: string;
  cell?: string;
  cells?: string[];
  run_seq?: number;
  states?: Record<string, string>;
  stale_reasons?: Record<string, string>;
  per_cell?: Record<string, { rows?: Record<string, unknown>[]; sql?: string | null }>;
  rows?: Record<string, unknown>[];
  timing_ms?: Record<string, number>;
  sql?: string | null;
  diagnostics?: Diagnostic[];
  message?: string;
}

export interface LibraryHeaderInfo {
  library: string;
  includes: { path: string; version: string | null; local: boolean }[];
  parameters: { name: string; type: string; default: string | null }[];
}

export interface ValueSetInfo {
  path: string;
  url: string | null;
  concepts: { system: string; code: string; display: string | null }[];
  used_by: string[];
  stale: boolean;
}

export interface ParametersResult {
  text: string;
  parameters: { name: string; type: string; default: string | null }[];
}

export interface MeasureMappingEntry {
  define: string;
  code: string;
}

export interface MeasureScaffoldResult {
  schema: number;
  ok: boolean;
  diagnostics: Diagnostic[];
  measure: Record<string, unknown> | null;
  mapping: MeasureMappingEntry[];
}

export interface MeasureRunResult {
  schema: number;
  ok: boolean;
  diagnostics: Diagnostic[];
  counts: Record<string, number>;
  columns: Record<string, string>;
  rows: Record<string, unknown>[];
  reports: Record<string, unknown>[];
  sql?: string | null;
}

export interface MeasureCompareRow {
  code: string;
  expected: number;
  actual: number;
  delta: number;
}

export interface MeasureCompareResult {
  schema: number;
  ok: boolean;
  diagnostics: Diagnostic[];
  passed: boolean;
  strict: boolean;
  rows: MeasureCompareRow[];
  expected_measure: { matches: boolean; canonical: string | null };
}

export interface BaselineInfo {
  path: string;
  name: string;
  provenance?: {
    captured_at?: string;
    library?: string;
    dataset?: string | null;
    kernel_id?: string;
    patient_count?: number;
    counts?: Record<string, number>;
  };
  reports?: number;
  error?: string;
}

export interface BaselineSaveResult {
  schema: number;
  ok: boolean;
  diagnostics: Diagnostic[];
  path?: string;
  name?: string;
  provenance?: BaselineInfo["provenance"];
  reports?: number;
}

export interface DefineTypeInfo {
  name: string;
  cql_type: string | null;
  boolean: boolean;
}

export interface ViewInfo {
  schema: number;
  ok: boolean;
  diagnostics: Diagnostic[];
  path: string;
  text: string;
  resource: string | null;
  name: string | null;
}

export interface DatasetInfo {
  schema: number;
  ok: boolean;
  diagnostics: Diagnostic[];
  path: string;
  resources: Record<string, unknown>[];
  parse_errors: { line: number; error: string }[];
}

/** Terminology preview: expanded codes for a URL/OID (no disk writes). */
export interface TerminologyPreviewResult {
  schema: number;
  ok: boolean;
  diagnostics: Diagnostic[];
  url: string;
  concepts: { system: string; code: string; display?: string | null }[];
  count: number;
}

/** Terminology import: writes a local valueset file w/ provenance. */
export interface TerminologyImportResult {
  schema: number;
  ok: boolean;
  diagnostics: Diagnostic[];
  path: string;
  url: string;
  code_count: number;
  stale: boolean;
}

/** Terminology search (UMLS): candidate codes for a free-text query. */
export interface TerminologySearchResult {
  schema: number;
  ok: boolean;
  diagnostics: Diagnostic[];
  query: string;
  results: { system: string; code: string; display: string | null; rootSource?: string | null }[];
  count: number;
}

export interface TerminologyConfigResult {
  schema: number;
  ok: boolean;
  diagnostics: Diagnostic[];
  config?: {
    provider: string;
    base_url: string | null;
    timeout_seconds: number;
    api_key_env: string;
    key_env_resolves?: boolean;
  };
}

export interface FsListResult {
  schema: number;
  ok: boolean;
  diagnostics: Diagnostic[];
  path: string;
  entries: { name: string; kind: "dir" | "file"; suffix: string }[];
}

export interface AddPathResult {
  schema: number;
  ok: boolean;
  diagnostics: Diagnostic[];
  kind?: string;
  added?: string;
  snapshot?: { datasets: number; libraries: number };
}

export interface TestsSaveResult {
  schema: number;
  ok: boolean;
  diagnostics: Diagnostic[];
  measure?: string;
  count?: number;
}

export interface MadieImportResult {
  schema: number;
  ok: boolean;
  diagnostics?: { message: string }[];
  written?: Record<string, string[]>;
  counts?: Record<string, number>;
  cases?: string[];
  expected?: string[];
}

export interface PatientResourceEntry {
  id: string;
  resourceType: string;
  status?: string | null;
  date?: string | null;
  preview: string;
}

export interface PatientResourcesResult {
  schema: number;
  ok: boolean;
  patient?: string;
  total?: number;
  by_type?: Record<string, PatientResourceEntry[]>;
  diagnostics?: { message: string }[];
}

export interface TestsExpectedPatient {
  patient: string;
  report: Record<string, unknown>;
  groups: { id?: string; population: { code: string; count: number; display_id?: string }[] }[];
}

export interface TestsExpectedGetResult {
  schema: number;
  ok: boolean;
  diagnostics: Diagnostic[];
  measure?: string;
  patients?: TestsExpectedPatient[];
  count?: number;
}

export interface TestsCaptureResult {
  schema: number;
  ok: boolean;
  diagnostics: Diagnostic[];
  measure?: string;
  reports?: Record<string, unknown>[];
  counts?: Record<string, number>;
  columns?: string[];
  sql?: string | null;
}

export interface TestsRunResult {
  schema: number;
  ok: boolean;
  diagnostics: Diagnostic[];
  measure?: string;
  rows?: { patient: string; code: string; expected: number | null; actual: number | null; pass: boolean; reason?: string }[];
  total?: number;
  passed?: number;
  failed?: number;
  sql?: string | null;
}

/** Per-valueset-declaration resolution status. */
export interface ResolutionRow {
  library: string;
  id: string;
  url: string;
  resolved: "local" | "VSAC" | "server" | "unresolved";
}

export interface TerminologyResolutionResult {
  schema: number;
  ok: boolean;
  diagnostics: Diagnostic[];
  resolutions: ResolutionRow[];
}

export interface ViewRunResult {
  schema: number;
  ok: boolean;
  diagnostics: Diagnostic[];
  sql: string;
  columns: string[];
  rows: Record<string, unknown>[];
  resource_count: number;
}

export interface SchemaTreeResult {
  schema: number;
  ok: boolean;
  diagnostics: Diagnostic[];
  resource_type: string;
  root: SchemaTreeNode | null;
}

export interface SchemaTreeNode {
  name: string;
  type: string;
  cardinality: string;
  types?: string[];
  children?: SchemaTreeNode[];
  reference_targets?: string[];
  hatch?: boolean;
  /** Choice-arm marker: e.g. deceasedBoolean carries choice_group 'deceased[x]'. */
  choice_group?: string;
}

export interface ResourceValidateResult {
  schema: number;
  ok: boolean;
  valid: boolean;
  resource_type: string | null;
  resource_id: string | null;
  diagnostics: Diagnostic[];
}

export interface ResourceSaveResult {
  schema: number;
  ok: boolean;
  diagnostics: Diagnostic[];
  path: string;
  appended: boolean;
}

export interface Transport {
  health(): Promise<HealthInfo>;
  workspace(): Promise<WorkspaceInfo>;
  defineTypes(library: string, text?: string): Promise<DefineTypeInfo[]>;
  view(path: string): Promise<ViewInfo>;

  dataset(path: string): Promise<DatasetInfo>;
  viewRun(text?: string, path?: string, resources?: Record<string, unknown>[]): Promise<ViewRunResult>;

  /** Terminology (VSAC / FHIR R4 server) integration — preview, import, resolution. */
  terminologyPreview(url: string): Promise<TerminologyPreviewResult>;
  terminologyImport(url: string, name?: string): Promise<TerminologyImportResult>;
  terminologyResolution(): Promise<TerminologyResolutionResult>;
  terminologySearch(query: string, system?: string): Promise<TerminologySearchResult>;

  /** S1/S2 (c-cleanroom-ux5): in-app VSAC config + fs pickers. */
  terminologyConfigGet(): Promise<TerminologyConfigResult>;
  terminologyConfigPost(
    updates: Partial<{
      provider: string;
      base_url: string | null;
      timeout_seconds: number;
      api_key_env: string;
    }>,
  ): Promise<TerminologyConfigResult>;
  fsList(path?: string): Promise<FsListResult>;
  workspaceAddPath(
    kind: "cql" | "valueset" | "measure" | "data" | "view",
    path: string,
  ): Promise<AddPathResult>;

  /** S4 (c-cleanroom-ux5 item 4): MADiE importers. */
  patientResources(patient: string): Promise<PatientResourcesResult>;

  madieImportPackage(zipBase64: string): Promise<MadieImportResult>;
  madieImportTests(zipBase64: string, measureName?: string): Promise<MadieImportResult>;

  /** S3b (c-cleanroom-ux5 item 3): expected-results editor surface. */
  testsExpectedGet(measure: string): Promise<TestsExpectedGetResult>;
  testsExpectedSave(measure: string, reports: Record<string, unknown>[]): Promise<TestsSaveResult>;
  testsExpectedDelete(measure: string, patient: string): Promise<{ schema: number; ok: boolean; removed?: boolean; diagnostics: Diagnostic[] }>;
  testsCapture(libraries: { name: string; text: string }[], library: string, measure: Record<string, unknown>, measureName: string): Promise<TestsCaptureResult>;
  testsRun(libraries: { name: string; text: string }[], library: string, measure: Record<string, unknown>, measureName: string): Promise<TestsRunResult>;

  schemaTree(resource: string, depth?: number): Promise<SchemaTreeResult>;
  resourceValidate(resource: Record<string, unknown>): Promise<ResourceValidateResult>;
  resourceSave(resource: Record<string, unknown>, datasetPath: string): Promise<ResourceSaveResult>;
  libraryHeader(library: string): Promise<LibraryHeaderInfo>;
  patients(): Promise<string[]>;
  valueset(path: string): Promise<ValueSetInfo>;
  valuesetEdit(
    path: string,
    edit: { action: string; system?: string | null; code?: string | null; display?: string | null; old_code?: string | null },
  ): Promise<ValueSetInfo>;
  parameters(
    library: string,
    action: "upsert" | "delete",
    name: string,
    type?: string,
    default_?: string | null,
    text?: string,
  ): Promise<ParametersResult>;
  measureScaffold(
    libraries: { name: string; text: string }[],
    library: string,
    mapping?: MeasureMappingEntry[],
    scoring?: string,
    measureName?: string,
  ): Promise<MeasureScaffoldResult>;
  measureRun(
    libraries: { name: string; text: string }[],
    library: string,
    measure: Record<string, unknown>,
    parameters?: Record<string, unknown>,
  ): Promise<MeasureRunResult>;
  measureCompare(
    libraries: { name: string; text: string }[],
    library: string,
    measure: Record<string, unknown>,
    expected: Record<string, unknown>[],
    strict?: boolean,
    parameters?: Record<string, unknown>,
  ): Promise<MeasureCompareResult>;
  measureBaselineSave(
    libraries: { name: string; text: string }[],
    library: string,
    measure: Record<string, unknown>,
    name?: string,
  ): Promise<BaselineSaveResult>;
  measureBaselines(measure?: string): Promise<{ schema: number; ok: boolean; diagnostics: Diagnostic[]; baselines: BaselineInfo[] }>;
  measureBaselineDelete(path: string): Promise<{ schema: number; ok: boolean; diagnostics: Diagnostic[] }>;
  library(name: string): Promise<WorkspaceLibrary>;
  translate(libraries: { name: string; text: string }[], library: string): Promise<TranslateResult>;
  evaluate(
    libraries: { name: string; text: string }[],
    library: string,
    define?: string,
  ): Promise<EvaluateResult>;
  verify(
    libraries: { name: string; text: string }[],
    library: string,
    cases: unknown[],
    parameters?: Record<string, unknown>,
  ): Promise<VerifyResult>;
  explain(
    libraries: { name: string; text: string }[],
    library: string,
    patientId: string,
  ): Promise<EvidenceResult>;
  runsList(): Promise<{ ok: boolean; runs?: import("./RunHistoryPane").RunEvent[]; count?: number }>;
  runsClear(): Promise<{ ok: boolean }>;
  runSqlGet(sha: string): Promise<{ ok: boolean; sql?: string; diagnostics?: { message: string }[] }>;

  restartKernel(): Promise<HealthInfo>;
  onWorkspaceEvent(cb: (e: WorkspaceEvent) => void): () => void;
  runCell(library: string, cell: string, mode: RunMode, text?: string): void;
  syncCells(library: string, text: string): void;
  onCellEvent(cb: (e: CellEvent) => void): () => void;
}
