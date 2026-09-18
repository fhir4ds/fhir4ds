export interface LessonProgress {
  completed: boolean;
  lastCql: string | null;
  timestamp: number;
}

export type ProgressMap = Record<string, LessonProgress>;

const STORAGE_KEY = "cql-clinic-progress";

export function loadProgress(): ProgressMap {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object") return parsed as ProgressMap;
    return {};
  } catch {
    return {};
  }
}

export function saveProgress(map: ProgressMap): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
  } catch {
    // storage full/blocked — progress is best-effort
  }
}

export function getLessonProgress(map: ProgressMap, lessonId: string): LessonProgress | null {
  return map[lessonId] ?? null;
}

export function updateLessonProgress(
  map: ProgressMap,
  lessonId: string,
  patch: Partial<LessonProgress>,
): ProgressMap {
  const existing = map[lessonId] ?? { completed: false, lastCql: null, timestamp: Date.now() };
  return {
    ...map,
    [lessonId]: { ...existing, ...patch, timestamp: Date.now() },
  };
}

export function resetLessonProgress(map: ProgressMap, lessonId: string): ProgressMap {
  const next = { ...map };
  delete next[lessonId];
  return next;
}
