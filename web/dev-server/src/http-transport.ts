import type {
  CellEvent,
  EvaluateResult,
  EvidenceResult,
  HealthInfo,
  RunMode,
  TranslateResult,
  Transport,
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
        kind === "runerror"
      ) {
        const cellListeners = [...this.cellListeners];
        for (const cb of cellListeners) cb(parsed as CellEvent);
      } else if (kind === "changed" || kind === "data-hint") {
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

  translate(
    libraries: { name: string; text: string }[],
    library: string,
  ): Promise<TranslateResult> {
    return this.post("/api/translate", { libraries, library, emit_sql: true });
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
  ): Promise<VerifyResult> {
    return this.post("/api/verify", { libraries, library, cases });
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
