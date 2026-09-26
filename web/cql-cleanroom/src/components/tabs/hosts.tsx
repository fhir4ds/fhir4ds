import type { EditorTab } from "../../lib/editorTabs";
import { MeasurePane } from "../MeasurePane";
import { ViewPane } from "../ViewPane";
import { TerminologyPane } from "../TerminologyPane";
import { ValuesetEditor } from "./ValuesetEditor";
import type { ViewOverrides } from "../../lib/viewDerivation";
import type { FlattenViewResult } from "../../lib/protocol";
import type { ParamBinding } from "../EditorPane";

/**
 * WORKBENCH_REORG phase 3 — per-kind tab hosts (non-library kinds).
 * The LIBRARY host is NOT here: EditorPane stays mounted beside the
 * switch (hidden while a non-library tab is active) so the Monaco
 * instance and its per-library model cache survive tab flips.
 */

export interface TabHostProps {
  tab: EditorTab;
  /* measure */
  measure: Record<string, unknown> | null;
  onMeasureChange: (m: Record<string, unknown> | null) => void;
  measureLibs: Array<{ name: string; text: string }>;
  measureMain: { name: string; text: string };
  /* valueset */
  valueset: Record<string, unknown> | null;
  valuesetProvenance?: string;
  onValuesetChange: (vs: Record<string, unknown>) => void;
  /* parameter */
  params: ParamBinding[];
  onParamsChange: (next: ParamBinding[]) => void;
  /* test (Resource Builder) */
  builder: React.ReactNode;
  /* expected (TestsPane expected grid) */
  testsSlot: React.ReactNode;
  /* view */
  measureReports: Array<Record<string, unknown>> | null;
  viewConfig: ViewOverrides | null;
  onViewConfigChange: (v: ViewOverrides) => void;
  onSql?: (sql: string | null) => void;
  onResult: (r: FlattenViewResult | null) => void;
  /* REORG 6e: settings recalc delay passed through to the view. */
  recalcMs?: number;
  /* terminology (REORG 6e — drawer became an editor tab) */
  terminologyDeclarations: Array<Record<string, unknown>>;
  terminologyDatasetValuesets: Array<Record<string, unknown>>;
  terminologyValuesets: Array<Record<string, unknown>>;
  onTerminologyChange: (valuesets: Array<Record<string, unknown>>) => void;
}

export function TabHost(p: TabHostProps) {
  switch (p.tab.kind) {
    case "measure":
      return (
        <MeasurePane
          libraries={p.measureLibs}
          main={p.measureMain}
          measure={p.measure}
          onChange={p.onMeasureChange}
        />
      );
    case "valueset":
      return p.valueset ? (
        <ValuesetEditor
          valueset={p.valueset}
          provenance={p.valuesetProvenance}
          onChange={p.onValuesetChange}
        />
      ) : (
        <p className="pane-hint">valueset not found: {p.tab.resourceId}</p>
      );
    case "parameter":
      return (
        <section className="pane" data-testid="parameter-editor">
          <div className="pane-header">
            <h2>Parameters</h2>
            <span className="pane-meta">entrypoint bindings</span>
          </div>
          <div className="drawer-body">
            {p.params.length === 0 && (
              <p className="pane-hint">
                No parameters declared in the entrypoint library.
              </p>
            )}
            {p.params.map((param, i) => (
              <label key={param.name} className="param-row builder-tree-row">
                <span className="builder-caret placeholder" aria-hidden="true" />
                <span className="builder-label">{param.name}</span>
                <input
                  data-testid={`param-input-${param.name}`}
                  value={param.value}
                  placeholder="value or start..end"
                  onChange={(e) => {
                    const v = e.target.value;
                    p.onParamsChange(
                      p.params.map((x, j) => (j === i ? { ...x, value: v } : x)),
                    );
                  }}
                />
              </label>
            ))}
          </div>
        </section>
      );
    case "test":
      return <>{p.builder}</>;
    case "expected":
      return <>{p.testsSlot}</>;
    case "view":
      return (
        <ViewPane
          measure={p.measure}
          measureReports={p.measureReports}
          viewConfig={p.viewConfig}
          onViewConfigChange={p.onViewConfigChange}
          onSql={p.onSql}
          onResult={p.onResult}
          recalcMs={p.recalcMs}
        />
      );
    case "terminology":
      return (
        <TerminologyPane
          cqlDeclarations={p.terminologyDeclarations}
          datasetValuesets={p.terminologyDatasetValuesets}
          workspaceValuesets={p.terminologyValuesets}
          onWorkspaceChange={p.onTerminologyChange}
        />
      );
    case "library":
      return null;
  }
}
