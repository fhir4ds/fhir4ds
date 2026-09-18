import { useCallback, useEffect, useRef, useState } from "react";
import { getLesson } from "../lessons";
import { usePyodide } from "../hooks/usePyodide";
import { useDuckDB, type FHIRResource } from "../hooks/useDuckDB";
import InstructionsPanel from "./InstructionsPanel";
import CQLEditor from "./CQLEditor";
import ResultsPanel, { gradeResults, type GradeReport, type Drill, type ResultsTab } from "./ResultsPanel";
import type { LessonProgress } from "../lib/progress";

interface Props {
  lessonId: string;
  progress: LessonProgress | null;
  onBack: () => void;
  onProgressUpdate: (lessonId: string, patch: { completed?: boolean; lastCql?: string | null }) => void;
}

/** Idle delay before an edited CQL buffer re-runs automatically. */
const AUTO_RUN_DEBOUNCE_MS = 1200;

export default function LessonPage({ lessonId, progress, onBack, onProgressUpdate }: Props) {
  const lesson = getLesson(lessonId);
  const pyodide = usePyodide(true);
  const duckdb = useDuckDB(undefined, true);

  const [cql, setCql] = useState(() => progress?.lastCql ?? lesson?.template ?? "");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sql, setSql] = useState<string | null>(null);
  const [translateTimeMs, setTranslateTimeMs] = useState<number | null>(null);
  const [executionTimeMs, setExecutionTimeMs] = useState<number | null>(null);
  const [result, setResult] = useState<{ columns: string[]; rows: unknown[][] } | null>(null);
  const [report, setReport] = useState<GradeReport | null>(null);
  const [completed, setCompleted] = useState(progress?.completed ?? false);
  const cqlRef = useRef(cql);
  cqlRef.current = cql;

  // Right-pane tab + shared cross-tab state (patient selection, drill-down).
  const [activeTab, setActiveTab] = useState<ResultsTab>("checks");
  const [selectedPatient, setSelectedPatient] = useState("");
  const [drill, setDrill] = useState<Drill | null>(null);

  // Monotonic run token: a slow older run that finishes after a newer one
  // started must not overwrite fresh results.
  const runTokenRef = useRef(0);
  // First run after engines are ready is immediate (no debounce).
  const firstAutoRunRef = useRef(true);

  // persist editor content (lastCql) as it changes
  useEffect(() => {
    const id = window.setTimeout(() => {
      onProgressUpdate(lessonId, { lastCql: cqlRef.current });
    }, 600);
    return () => window.clearTimeout(id);
  }, [cql, lessonId, onProgressUpdate]);

  const handleRun = useCallback(async (explicit = false) => {
    if (!lesson) return;
    if (!pyodide.ready || !duckdb.ready) {
      setError(
        !pyodide.ready
          ? "CQL engine is still loading — try again in a moment."
          : "DuckDB is still loading — try again in a moment.",
      );
      return;
    }
    const token = ++runTokenRef.current;
    setRunning(true);
    setError(null);
    try {
      const { sql: translated, timeMs } = await pyodide.translate(cqlRef.current);
      if (token !== runTokenRef.current) return;

      setSql(translated);
      setTranslateTimeMs(timeMs);

      await duckdb.loadFixtures(lesson.fixtures as FHIRResource[]);
      if (token !== runTokenRef.current) return;

      const rows = await duckdb.executeQuery(translated);
      if (token !== runTokenRef.current) return;

      setExecutionTimeMs(rows.executionTimeMs);
      setResult({ columns: rows.columns, rows: rows.rows });

      const grade = gradeResults(lesson, { columns: rows.columns, rows: rows.rows });
      setReport(grade);
      if (grade.allPassed && !completed) {
        setCompleted(true);
        onProgressUpdate(lessonId, { completed: true });
      }
      // Only a deliberate Run click yanks the view to the fresh checks —
      // auto-runs never pull the learner away from the tab they're studying.
      if (explicit) setActiveTab("checks");
    } catch (e) {
      if (token === runTokenRef.current) {
        setError(e instanceof Error ? e.message : String(e));
        setResult(null);
        setReport(null);
      }
    } finally {
      if (token === runTokenRef.current) setRunning(false);
    }
  }, [pyodide, duckdb, lesson, completed, lessonId, onProgressUpdate]);

  // Auto-run: immediate once engines are ready, then debounced after CQL
  // edits so the right pane stays live as the learner types.
  useEffect(() => {
    if (!lesson || !pyodide.ready || !duckdb.ready) return;
    if (firstAutoRunRef.current) {
      firstAutoRunRef.current = false;
      handleRun();
      return;
    }
    const id = window.setTimeout(() => handleRun(), AUTO_RUN_DEBOUNCE_MS);
    return () => window.clearTimeout(id);
  // handleRun/lesson are stable per lesson mount; deps are the triggers.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cql, pyodide.ready, duckdb.ready]);

  const handleReset = useCallback(() => {
    if (!lesson) return;
    setCql(lesson.template);
    setError(null);
    setReport(null);
    setResult(null);
    setSql(null);
    setCompleted(false);
    onProgressUpdate(lessonId, { completed: false, lastCql: lesson.template });
  }, [lesson, lessonId, onProgressUpdate]);

  if (!lesson) return null;

  const runtimeStatus = !pyodide.ready
    ? `Loading CQL engine… ${pyodide.error ?? ""}`
    : !duckdb.ready
      ? `Loading DuckDB… ${duckdb.error ?? ""}`
      : null;

  return (
    <div className="lesson-page">
      <header className="lesson-header">
        <button className="btn btn-ghost" onClick={onBack}>← Lessons</button>
        <h1>{lesson.title}</h1>
        {runtimeStatus ? <span className="runtime-status">{runtimeStatus}</span> : <span className="runtime-status ok">engine ready</span>}
      </header>
      <div className="lesson-grid-2">
        <div className="lesson-left">
          <InstructionsPanel lesson={lesson} cql={cql} completed={completed} onResetProgress={handleReset} />
          <CQLEditor
            value={cql}
            onChange={setCql}
            solution={lesson.solution}
            running={running}
            onRun={() => handleRun(true)}
          />
        </div>
        <ResultsPanel
          running={running}
          error={error}
          translateTimeMs={translateTimeMs}
          executionTimeMs={executionTimeMs}
          report={report}
          result={result}
          fixtures={lesson.fixtures}
          lessonCql={lesson.solution}
          executeQuery={duckdb.executeQuery}
          duckdbReady={duckdb.ready}
          sql={sql}
          activeTab={activeTab}
          onTabChange={setActiveTab}
          selectedPatient={selectedPatient}
          onSelectPatient={setSelectedPatient}
          drill={drill}
          onDrillChange={setDrill}
        />
      </div>
    </div>
  );
}
