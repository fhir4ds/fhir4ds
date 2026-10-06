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
  kind: "cellstate" | "result" | "cellerror" | "runerror";
  library?: string;
  cell?: string;
  cells?: string[];
  run_seq?: number;
  states?: Record<string, string>;
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
  viewRun(text?: string, path?: string): Promise<ViewRunResult>;
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
  restartKernel(): Promise<HealthInfo>;
  onWorkspaceEvent(cb: (e: WorkspaceEvent) => void): () => void;
  runCell(library: string, cell: string, mode: RunMode, text?: string): void;
  syncCells(library: string, text: string): void;
  onCellEvent(cb: (e: CellEvent) => void): () => void;
}
