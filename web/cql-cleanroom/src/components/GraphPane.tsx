import { useCallback, useState, type ReactElement } from "react";
import { workerRequest } from "./BootOverlay";
import { graphToCql, type Graph } from "../lib/graphToCql";

/**
 * C3-U6: visual algorithm editor pane.
 *
 * v1 scope (plan §3.3): a fixed-shape palette graph editor. The canvas
 * writes CQL ONLY (INV-C3-5) and the Apply button is explicit (S-C3-D)
 * — it replaces the active library tab text after a parse round-trip
 * check (emit → parse_cql ok). ReactFlow loads via dynamic import so
 * the ~150KB dep never touches the core bundle (INV-C3-4).
 */

type Result = { ok: boolean; detail: string };

interface Props {
  onApplyCql: (cql: string) => void;
}

export function GraphPane({ onApplyCql }: Props) {
  const [graph, setGraph] = useState<Graph>(defaultGraph());
  const [preview, setPreview] = useState<string>("");
  const [result, setResult] = useState<Result | null>(null);
  const [canvas, setCanvas] = useState<Awaited<ReturnType<typeof loadCanvas>> | null>(
    null,
  );
  const [canvasError, setCanvasError] = useState<string | null>(null);

  const loadCanvasLazy = useCallback(async () => {
    if (canvas) return canvas;
    try {
      const c = await loadCanvas();
      setCanvas(c);
      return c;
    } catch (e) {
      setCanvasError(e instanceof Error ? e.message : String(e));
      return null;
    }
  }, [canvas]);

  const emit = useCallback(() => {
    try {
      const cql = graphToCql(graph, "Visual");
      setPreview(cql);
      setResult(null);
      return cql;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setPreview("");
      setResult({ ok: false, detail: msg });
      return null;
    }
  }, [graph]);

  const apply = useCallback(async () => {
    const cql = emit();
    if (cql === null) return;
    // Round-trip guard: emitted CQL must parse before applying (S-C3-D).
    const resp = await workerRequest({ type: "parse_cql", text: cql });
    let parsed: { ok?: boolean; diagnostics?: Array<{ message: string }> } | null = null;
    try {
      parsed = JSON.parse(resp.envelope);
    } catch {
      /* fall through to reject */
    }
    if (resp?.ok && parsed?.ok) {
      onApplyCql(cql);
      setResult({ ok: true, detail: "applied to the active library tab" });
    } else {
      const msg = parsed?.diagnostics?.[0]?.message ?? "parse failed";
      setResult({ ok: false, detail: `round-trip parse failed: ${msg}` });
    }
  }, [emit, onApplyCql]);

  return (
    <section className="pane graph-pane" data-testid="graph-pane">
      <div className="pane-header">
        <h2>Visual Editor</h2>
        <span className="lineage-badge" title="Emits CQL text one-way; never edits SQL">
          emits CQL
        </span>
      </div>

      <div className="graph-toolbar">
        <button type="button" data-testid="graph-add-retrieve" onClick={() => addNode(setGraph, "Retrieve")}>
          + Retrieve
        </button>
        <button type="button" data-testid="graph-add-exists" onClick={() => addNode(setGraph, "Exists")}>
          + Exists
        </button>
        <button type="button" data-testid="graph-add-output" onClick={() => addNode(setGraph, "DefineOutput")}>
          + Output
        </button>
        <button type="button" data-testid="graph-emit" onClick={emit}>
          Emit CQL
        </button>
        <button type="button" data-testid="graph-apply" onClick={apply} disabled={!preview}>
          Apply to library
        </button>
      </div>

      {canvasError ? (
        <div className="diag-row diag-error" data-testid="graph-canvas-error">
          canvas unavailable: {canvasError}
        </div>
      ) : (
        <div className="graph-canvas" data-testid="graph-canvas">
          <GraphJsonEditor graph={graph} onChange={setGraph} onLoadCanvas={loadCanvasLazy} />
        </div>
      )}

      {preview && (
        <pre className="builder-pre" data-testid="graph-preview">
          {preview}
        </pre>
      )}
      {result && (
        <div
          className={`diag-row ${result.ok ? "diag-info" : "diag-error"}`}
          data-testid={result.ok ? "graph-applied" : "graph-error"}
        >
          {result.detail}
        </div>
      )}
    </section>
  );
}

/** v1 fallback editor: JSON graph model + optional ReactFlow mount. */
function GraphJsonEditor({
  graph,
  onChange,
  onLoadCanvas,
}: {
  graph: Graph;
  onChange: (g: Graph) => void;
  onLoadCanvas: () => Promise<ReactFlowCanvas | null>;
}) {
  const [text, setText] = useState(() => JSON.stringify(graph, null, 2));
  const [flowMounted, setFlowMounted] = useState(false);
  const [flowError, setFlowError] = useState<string | null>(null);

  const applyJson = () => {
    try {
      const parsed = JSON.parse(text) as Graph;
      if (!Array.isArray(parsed.nodes) || !Array.isArray(parsed.edges)) {
        throw new Error("graph must have nodes[] and edges[]");
      }
      onChange(parsed);
    } catch (e) {
      setFlowError(e instanceof Error ? e.message : String(e));
      return;
    }
    setFlowError(null);
  };

  const mountFlow = async () => {
    const Canvas = await onLoadCanvas();
    if (!Canvas) return;
    setFlowMounted(true);
  };

  return (
    <div className="graph-json">
      {!flowMounted && (
        <>
          <textarea
            data-testid="graph-json"
            rows={8}
            spellCheck={false}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="graph-json-actions">
            <button type="button" data-testid="graph-json-apply" onClick={applyJson}>
              Use graph JSON
            </button>
            <button type="button" data-testid="graph-canvas-mount" onClick={mountFlow}>
              Mount canvas (beta)
            </button>
          </div>
          {flowError && <div className="diag-row diag-error">{flowError}</div>}
        </>
      )}
      {flowMounted && <CanvasPlaceholder graph={graph} />}
    </div>
  );
}

function CanvasPlaceholder({ graph }: { graph: Graph }) {
  return (
    <div data-testid="graph-canvas-flow" className="graph-flow">
      {graph.nodes.map((n) => (
        <div key={n.id} className="graph-node" data-testid={`graph-node-${n.kind}`}>
          <strong>{n.kind}</strong>
          {n.data.label ? <span> {n.data.label}</span> : null}
        </div>
      ))}
    </div>
  );
}

type ReactFlowCanvas = (props: { graph: Graph }) => ReactElement;

async function loadCanvas(): Promise<ReactFlowCanvas> {
  // Dynamic import per INV-C3-4: the ReactFlow bundle loads only when
  // the user mounts the canvas. v1 falls back to the JSON editor shape
  // above regardless; this seam keeps the dependency out of core.
  await import(/* @vite-ignore */ "@xyflow/react");
  return ({ graph }) => <CanvasPlaceholder graph={graph} />;
}

function addNode(
  setGraph: (fn: (g: Graph) => Graph) => void,
  kind: Graph["nodes"][number]["kind"],
) {
  setGraph((g) => ({
    ...g,
    nodes: [
      ...g.nodes,
      { id: `n${g.nodes.length + 1}-${kind}`, kind, data: {} },
    ],
  }));
}

function defaultGraph(): Graph {
  return {
    nodes: [
      { id: "r1", kind: "Retrieve", data: { label: "Patient" } },
      { id: "e1", kind: "Exists", data: {} },
      { id: "o1", kind: "DefineOutput", data: { label: "Initial Population" } },
    ],
    edges: [
      { source: "r1", target: "e1" },
      { source: "e1", target: "o1" },
    ],
  };
}
