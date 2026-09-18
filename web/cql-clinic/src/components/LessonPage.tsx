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

  // persist editor content (lastCql) as it changes
  useEffect(() => {
    const id = window.setTimeout(() => {
      onProgressUpdate(lessonId, { lastCql: cqlRef.current });
    }, 600);
    return () => window.clearTimeout(id);
  }, [cql, lessonId, onProgressUpdate]);

  const handleRun = useCallback(async () => {
    if (!lesson) return;
    if (!pyodide.ready || !duckdb.ready) {
      setError(
        !pyodide.ready
          ? "CQL engine is still loading — try again in a moment."
          : "DuckDB is still loading — try again in a moment.",
      );
      return;
    }
    setRunning(true);
    setError(null);
    try {
      const { sql: translated, timeMs } = await pyodide.translate(cqlRef.current);
      setSql(translated);
      setTranslateTimeMs(timeMs);

      await duckdb.loadFixtures(lesson.fixtures as FHIRResource[]);
      const rows = await duckdb.executeQuery(translated);
      setExecutionTimeMs(rows.executionTimeMs);
      setResult({ columns: rows.columns, rows: rows.rows });

      const grade = gradeResults(lesson, { columns: rows.columns, rows: rows.rows });
      setReport(grade);
      if (grade.allPassed && !completed) {
        setCompleted(true);
        onProgressUpdate(lessonId, { completed: true });
      }
      // The point of Run is the grading — surface the fresh checks even if
      // the learner was studying the SQL when they clicked.
      setActiveTab("checks");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setResult(null);
      setReport(null);
    } finally {
      setRunning(false);
    }
  }, [pyodide, duckdb, lesson, completed, lessonId, onProgressUpdate]);

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

  /** Translate the CURRENT editor content on demand (SQL tab refresh). */
  const handleTranslate = useCallback(async (): Promise<{ sql: string; timeMs: number } | null> => {
    if (!pyodide.ready) {
      setError("CQL engine is still loading — try again in a moment.");
      return null;
    }
    try {
      const { sql: translated, timeMs } = await pyodide.translate(cqlRef.current);
      setSql(translated);
      setTranslateTimeMs(timeMs);
      return { sql: translated, timeMs };
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return null;
    }
  }, [pyodide]);

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
          <CQLEditor value={cql} onChange={setCql} solution={lesson.solution} />
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
          engineReady={pyodide.ready}
          onTranslate={handleTranslate}
          activeTab={activeTab}
          onTabChange={setActiveTab}
          selectedPatient={selectedPatient}
          onSelectPatient={setSelectedPatient}
          drill={drill}
          onDrillChange={setDrill}
          onRun={handleRun}
        />
      </div>
    </div>
  );
}
