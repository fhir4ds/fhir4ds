import { useCallback, useEffect, useState } from "react";
import LessonList from "./components/LessonList";
import LessonPage from "./components/LessonPage";
import { loadProgress, saveProgress, type ProgressMap } from "./lib/progress";

export default function App() {
  const [activeLessonId, setActiveLessonId] = useState<string | null>(null);
  const [progress, setProgress] = useState<ProgressMap>(() => loadProgress());

  useEffect(() => {
    saveProgress(progress);
  }, [progress]);

  const openLesson = useCallback((lessonId: string) => {
    setActiveLessonId(lessonId);
  }, []);

  const backHome = useCallback(() => {
    setActiveLessonId(null);
  }, []);

  const updateProgress = useCallback((lessonId: string, patch: { completed?: boolean; lastCql?: string | null }) => {
    setProgress((prev) => {
      const existing = prev[lessonId] ?? { completed: false, lastCql: null, timestamp: Date.now() };
      return {
        ...prev,
        [lessonId]: {
          ...existing,
          ...(patch.completed !== undefined ? { completed: patch.completed } : {}),
          ...(patch.lastCql !== undefined ? { lastCql: patch.lastCql } : {}),
          timestamp: Date.now(),
        },
      };
    });
  }, []);

  if (activeLessonId) {
    return (
      <LessonPage
        key={activeLessonId}
        lessonId={activeLessonId}
        progress={progress[activeLessonId] ?? null}
        onBack={backHome}
        onProgressUpdate={updateProgress}
      />
    );
  }

  return <LessonList progress={progress} onOpenLesson={openLesson} />;
}
