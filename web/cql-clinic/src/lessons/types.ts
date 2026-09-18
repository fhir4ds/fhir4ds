export interface LessonHint {
  trigger: string;
  message: string;
}

export interface LessonExpected {
  columns: string[];
  /** Rows keyed by patient id; column order matches `columns`. */
  rows: Record<string, unknown[]>;
}

export interface Lesson {
  id: string;
  title: string;
  description: string;
  difficulty: "beginner" | "intermediate" | "advanced";
  estimatedTime: string;
  learningObjectives: string[];
  template: string;
  solution: string;
  fixtures: unknown[];
  expected: LessonExpected;
  /** Defines excluded from deterministic grading (e.g. Today()-dependent). */
  ungradedDefines: string[];
  hints: LessonHint[];
}
