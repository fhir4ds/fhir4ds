import { useMemo } from "react";
import type { Lesson, LessonHint } from "../lessons/types";

interface Props {
  lesson: Lesson;
  cql: string;
  completed: boolean;
  onResetProgress: () => void;
}

/** A hint becomes visible once its trigger substring appears in the learner's CQL. */
export function activeHints(hints: LessonHint[], cql: string): LessonHint[] {
  const lower = cql.toLowerCase();
  return hints.filter((h) => h.trigger && lower.includes(h.trigger.toLowerCase()));
}

export default function InstructionsPanel({ lesson, cql, completed, onResetProgress }: Props) {
  const hints = useMemo(() => activeHints(lesson.hints, cql), [lesson.hints, cql]);

  return (
    <aside className="panel instructions">
      <div className="instructions-header">
        <h2>{lesson.title}</h2>
        {completed && <span className="badge badge-done">completed ✓</span>}
      </div>
      <p className="lesson-description">{lesson.description}</p>

      <section>
        <h3>Learning objectives</h3>
        <ul className="objectives">
          {lesson.learningObjectives.map((o) => (
            <li key={o}>{o}</li>
          ))}
        </ul>
      </section>

      <section>
        <h3>Hints</h3>
        {hints.length === 0 ? (
          <p className="hint-empty">
            Hints appear automatically as you work — start writing CQL in the editor.
          </p>
        ) : (
          <ul className="hints">
            {hints.map((h, i) => (
              <li key={i}>{h.message}</li>
            ))}
          </ul>
        )}
      </section>

      <footer className="instructions-footer">
        <button className="btn btn-ghost" onClick={onResetProgress}>
          Reset lesson
        </button>
        <span className="meta">~{lesson.estimatedTime} min · {lesson.difficulty}</span>
      </footer>
    </aside>
  );
}
