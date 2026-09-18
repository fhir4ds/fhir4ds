import { LESSONS } from "../lessons";
import type { ProgressMap } from "../lib/progress";

interface Props {
  progress: ProgressMap;
  onOpenLesson: (lessonId: string) => void;
}

const DIFFICULTY_CLASS: Record<string, string> = {
  beginner: "badge-beginner",
  intermediate: "badge-intermediate",
  advanced: "badge-advanced",
};

export default function LessonList({ progress, onOpenLesson }: Props) {
  const completedCount = LESSONS.filter((l) => progress[l.id]?.completed).length;

  return (
    <div className="home">
      <header className="home-header">
        <h1>CQL Clinic</h1>
        <p className="subtitle">
          Learn Clinical Quality Language by writing real CQL, translated and executed entirely
          in your browser with FHIR4DS.
        </p>
        <p className="progress-note">
          {completedCount} of {LESSONS.length} lessons complete · progress saved locally
        </p>
      </header>

      <div className="lesson-grid">
        {LESSONS.map((lesson, i) => {
          const done = progress[lesson.id]?.completed ?? false;
          return (
            <button
              key={lesson.id}
              className={`lesson-card ${done ? "lesson-card-done" : ""}`}
              onClick={() => onOpenLesson(lesson.id)}
            >
              <div className="lesson-card-top">
                <span className="lesson-number">{i + 1}</span>
                <span className={`badge ${DIFFICULTY_CLASS[lesson.difficulty] ?? ""}`}>
                  {lesson.difficulty}
                </span>
                {done && <span className="check" aria-label="completed">✓</span>}
              </div>
              <h2>{lesson.title}</h2>
              <p>{lesson.description}</p>
              <div className="lesson-card-meta">
                ~{lesson.estimatedTime} · {lesson.learningObjectives.length} objectives
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
