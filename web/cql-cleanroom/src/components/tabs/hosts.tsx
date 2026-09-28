import type { EditorTab } from "../../lib/editorTabs";
import { MeasurePane } from "../MeasurePane";
import { ViewPane } from "../ViewPane";
import { ValuesetEditor } from "./ValuesetEditor";
import type { ViewOverrides } from "../../lib/viewDerivation";
import type { LibraryClosure } from "../../lib/libraryGraph";
import type { FlattenViewResult } from "../../lib/protocol";
import type { ParamBinding } from "../../lib/params";
import { ParameterEditor } from "./ParameterEditor";

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
  /* 6f: primary-library + expected-results association */
  measureMainLibraryId?: string;
  measureLibraryChoices?: Array<{ id: string; name: string }>;
  onMeasureMainLibraryChange?: (id: string) => void;
  measureClosure?: LibraryClosure;
  measureValuesetSources?: Record<string, "workspace" | "dataset">;
  measureExpectedReports?: Array<Record<string, unknown>>;
  onOpenExpected?: () => void;
  /* valueset */
  valueset: Record<string, unknown> | null;
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
          mainLibraryId={p.measureMainLibraryId}
          libraryChoices={p.measureLibraryChoices}
          onMainLibraryChange={p.onMeasureMainLibraryChange}
          closure={p.measureClosure}
          valuesetSources={p.measureValuesetSources}
          expectedReports={p.measureExpectedReports}
          onOpenExpected={p.onOpenExpected}
        />
      );
    case "valueset":
      return p.valueset ? (
        <ValuesetEditor
          valueset={p.valueset}
          onChange={p.onValuesetChange}
        />
      ) : (
        <p className="pane-hint">valueset not found: {p.tab.resourceId}</p>
      );
    case "parameter":
      return <ParameterEditor params={p.params} onChange={p.onParamsChange} />;
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
    case "library":
      return null;
  }
}
