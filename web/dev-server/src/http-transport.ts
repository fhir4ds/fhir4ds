import type {
  CellEvent,
  DefineTypeInfo,
  ViewInfo,
  ViewRunResult,
  DatasetInfo,
  TerminologyPreviewResult,
  TerminologyImportResult,
  TerminologyResolutionResult,
  ResourceSaveResult,
  ResourceValidateResult,
  SchemaTreeResult,
  EvaluateResult,
  EvidenceResult,
  HealthInfo,
  LibraryHeaderInfo,
  MeasureMappingEntry,
  MeasureCompareResult,
  BaselineInfo,
  BaselineSaveResult,
  MeasureRunResult,
  MeasureScaffoldResult,
  ParametersResult,
  RunMode,
  TranslateResult,
  Transport,
  Diagnostic,
  ValueSetInfo,
  VerifyResult,
  WorkspaceEvent,
  WorkspaceInfo,
  WorkspaceLibrary,
} from "./transport";

/** Server-side transport: thin fetch wrappers over the dev-server API. */
type CellListener = (e: CellEvent) => void;

export class HttpTransport implements Transport {
  private base: string;
  private ws: WebSocket | null = null;
  private wsReady: Promise<WebSocket> | null = null;
  private cellListeners: Set<CellListener> = new Set();
  private wsListeners: Set<(e: WorkspaceEvent) => void> = new Set();

  constructor(base = "") {
    this.base = base;
  }

  private ensureSocket(): Promise<WebSocket> {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      return Promise.resolve(this.ws);
    }
    if (this.wsReady) return this.wsReady;
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${proto}//${location.host}${this.base}/api/events`;
    const socket = new WebSocket(url);
    this.ws = socket;
    this.wsReady = new Promise<WebSocket>((resolve, reject) => {
      socket.onopen = () => resolve(socket);
      socket.onerror = () => reject(new Error("websocket failed"));
    });
    socket.onmessage = (msg: MessageEvent) => {
      let parsed: unknown;
      try {
        parsed = JSON.parse(msg.data);
      } catch {
        return; /* ignore malformed frames */
      }
      const kind = (parsed as { kind?: string }).kind;
      if (
        kind === "cellstate" ||
        kind === "result" ||
        kind === "cellerror" ||
        kind === "runerror" ||
        kind === "synced"
      ) {
        const cellListeners = [...this.cellListeners];
        for (const cb of cellListeners) cb(parsed as CellEvent);
      } else if (kind === "changed" || kind === "data-hint" || kind === "stale") {
        const wsListeners = [...this.wsListeners];
        for (const cb of wsListeners) cb(parsed as WorkspaceEvent);
      }
    };
    return this.wsReady;
  }

  private async sendSocket(obj: unknown): Promise<void> {
    const socket = await this.ensureSocket();
    socket.send(JSON.stringify(obj));
  }

  private async get<T>(path: string): Promise<T> {
    const r = await fetch(`${this.base}${path}`);
    return (await r.json()) as T;
  }

  private async post<T>(path: string, body: unknown): Promise<T> {
    const r = await fetch(`${this.base}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return (await r.json()) as T;
  }

  health(): Promise<HealthInfo> {
    return this.get("/health");
  }

  workspace(): Promise<WorkspaceInfo> {
    return this.get("/api/workspace").then((w: any) => w.workspace);
  }

  library(name: string): Promise<WorkspaceLibrary> {
    return this.get(`/api/libraries/${encodeURIComponent(name)}`);
  }

  /** Unwrap a devserver envelope (HTTP 200, ok flag) into its payload. */
  private async unwrap<T>(path: string): Promise<T> {
    const d = await this.get<Record<string, unknown>>(path);
    if (d.ok === false) {
      const diags = (d.diagnostics as { message?: string }[] | undefined) ?? [];
      throw new Error(diags[0]?.message ?? "request failed");
    }
    return d as unknown as T;
  }

  libraryHeader(library: string): Promise<LibraryHeaderInfo> {
    return this.unwrap(`/api/library-header?library=${encodeURIComponent(library)}`);
  }

  defineTypes(library: string, text?: string): Promise<DefineTypeInfo[]> {
    let q = `/api/define-types?library=${encodeURIComponent(library)}`;
    if (text !== undefined) q += `&text=${encodeURIComponent(text)}`;
    return this.unwrap<{ defines: DefineTypeInfo[] }>(q).then((d) => d.defines);
  }

  view(path: string): Promise<ViewInfo> {
    return this.unwrap(`/api/view?path=${encodeURIComponent(path)}`);
  }

  dataset(path: string): Promise<DatasetInfo> {
    return this.unwrap(`/api/dataset?path=${encodeURIComponent(path)}`);
  }

  terminologyPreview(url: string): Promise<TerminologyPreviewResult> {
    return this.post<TerminologyPreviewResult>("/api/terminology/preview", { url });
  }

  terminologyImport(url: string, name?: string): Promise<TerminologyImportResult> {
    return this.post<TerminologyImportResult>("/api/terminology/import", { url, name });
  }

  terminologyResolution(): Promise<TerminologyResolutionResult> {
    return this.unwrap("/api/terminology/resolution");
  }

  viewRun(text?: string, path?: string, resources?: Record<string, unknown>[]): Promise<ViewRunResult> {
    return this.post<ViewRunResult>("/api/view/run", { text, path, resources });
  }

  schemaTree(resource: string, depth?: number): Promise<SchemaTreeResult> {
    let q = `/api/schema-tree?resource=${encodeURIComponent(resource)}`;
    if (depth !== undefined) q += `&depth=${depth}`;
    return this.unwrap(q);
  }

  async resourceValidate(
    resource: Record<string, unknown>,
  ): Promise<ResourceValidateResult> {
    const d = await this.post<Record<string, unknown>>(
      "/api/resource/validate",
      { resource },
    );
    if (d.ok === false) {
      const diags = (d.diagnostics as { message?: string }[] | undefined) ?? [];
      throw new Error(diags[0]?.message ?? "validate failed");
    }
    return d as unknown as ResourceValidateResult;
  }

  async resourceSave(
    resource: Record<string, unknown>,
    datasetPath: string,
  ): Promise<ResourceSaveResult> {
    const d = await this.post<Record<string, unknown>>("/api/resource/save", {
      resource,
      dataset_path: datasetPath,
    });
    if (d.ok === false) {
      const diags = (d.diagnostics as { message?: string }[] | undefined) ?? [];
      throw new Error(diags[0]?.message ?? "save failed");
    }
    return d as unknown as ResourceSaveResult;
  }

  patients(): Promise<string[]> {
    return this.unwrap<{ patients: string[] }>("/api/patients").then(
      (d) => d.patients,
    );
  }

  valueset(path: string): Promise<ValueSetInfo> {
    return this.unwrap(`/api/valueset?path=${encodeURIComponent(path)}`);
  }

  async valuesetEdit(
    path: string,
    edit: { action: string; system?: string | null; code?: string | null; display?: string | null; old_code?: string | null },
  ): Promise<ValueSetInfo> {
    const d = await this.post<Record<string, unknown>>("/api/valueset/edit", {
      path,
      edit,
    });
    if (d.ok === false) {
      const diags = (d.diagnostics as { message?: string }[] | undefined) ?? [];
      throw new Error(diags[0]?.message ?? "edit failed");
    }
    return d as unknown as ValueSetInfo;
  }

  async parameters(
    library: string,
    action: "upsert" | "delete",
    name: string,
    type?: string,
    default_?: string | null,
    text?: string,
  ): Promise<ParametersResult> {
    const body: Record<string, unknown> = { library, action, name };
    if (type !== undefined) body.type = type;
    if (default_ !== undefined && default_ !== null) body.default = default_;
    if (text !== undefined) body.text = text;
    const d = await this.post<Record<string, unknown>>("/api/parameters", body);
    if (d.ok === false) {
      const diags = (d.diagnostics as { message?: string }[] | undefined) ?? [];
      throw new Error(diags[0]?.message ?? "parameter edit failed");
    }
    return d as unknown as ParametersResult;
  }

  translate(
    libraries: { name: string; text: string }[],
    library: string,
  ): Promise<TranslateResult> {
    return this.post("/api/translate", { libraries, library, emit_sql: true });
  }

  measureScaffold(
    libraries: { name: string; text: string }[],
    library: string,
    mapping?: MeasureMappingEntry[],
    scoring?: string,
    measureName?: string,
  ): Promise<MeasureScaffoldResult> {
    const body: Record<string, unknown> = { library, libraries };
    if (mapping !== undefined) body.mapping = mapping;
    if (scoring !== undefined) body.scoring = scoring;
    if (measureName !== undefined) body.measure_name = measureName;
    return this.post("/api/measure/scaffold", body);
  }

  measureRun(
    libraries: { name: string; text: string }[],
    library: string,
    measure: Record<string, unknown>,
    parameters?: Record<string, unknown>,
  ): Promise<MeasureRunResult> {
    const body: Record<string, unknown> = { library, libraries, measure };
    if (parameters !== undefined) body.parameters = parameters;
    return this.post("/api/measure/run", body);
  }

  measureCompare(
    libraries: { name: string; text: string }[],
    library: string,
    measure: Record<string, unknown>,
    expected: Record<string, unknown>[],
    strict?: boolean,
    parameters?: Record<string, unknown>,
  ): Promise<MeasureCompareResult> {
    const body: Record<string, unknown> = { library, libraries, measure, expected };
    if (strict !== undefined) body.strict = strict;
    if (parameters !== undefined) body.parameters = parameters;
    return this.post("/api/measure/compare", body);
  }

  measureBaselineSave(
    libraries: { name: string; text: string }[],
    library: string,
    measure: Record<string, unknown>,
    name?: string,
  ): Promise<BaselineSaveResult> {
    const body: Record<string, unknown> = { library, libraries, measure };
    if (name !== undefined) body.name = name;
    return this.post("/api/measure/baseline/save", body);
  }

  measureBaselines(
    measure?: string,
  ): Promise<{ schema: number; ok: boolean; diagnostics: Diagnostic[]; baselines: BaselineInfo[] }> {
    const q = measure ? `?measure=${encodeURIComponent(measure)}` : "";
    return this.get(`/api/measure/baselines${q}`);
  }

  measureBaselineDelete(path: string): Promise<{ schema: number; ok: boolean; diagnostics: Diagnostic[] }> {
    return this.post("/api/measure/baseline/delete", { path });
  }

  evaluate(
    libraries: { name: string; text: string }[],
    library: string,
    define?: string,
  ): Promise<EvaluateResult> {
    return this.post("/api/evaluate", { libraries, library, define });
  }

  verify(
    libraries: { name: string; text: string }[],
    library: string,
    cases: unknown[],
    parameters?: Record<string, unknown>,
  ): Promise<VerifyResult> {
    return this.post("/api/verify", { libraries, library, cases, parameters });
  }

  explain(
    libraries: { name: string; text: string }[],
    library: string,
    patientId: string,
  ): Promise<EvidenceResult> {
    return this.post("/api/explain", {
      libraries,
      library,
      patient_id: patientId,
    });
  }

  restartKernel(): Promise<HealthInfo> {
    return this.post("/api/kernel/restart", {});
  }

  onWorkspaceEvent(cb: (e: WorkspaceEvent) => void): () => void {
    this.wsListeners.add(cb);
    this.ensureSocket().catch(() => {});
    return () => {
      this.wsListeners.delete(cb);
    };
  }

  runCell(library: string, cell: string, mode: RunMode, text?: string): void {
    const payload: Record<string, unknown> = { kind: "run", library, cell, mode };
    if (text !== undefined) payload.text = text;
    this.sendSocket(payload).catch(() => {});
  }

  syncCells(library: string, text: string): void {
    this.sendSocket({ kind: "sync", library, text }).catch(() => {});
  }

  onCellEvent(cb: (e: CellEvent) => void): () => void {
    this.cellListeners.add(cb);
    return () => this.cellListeners.delete(cb);
  }
}
