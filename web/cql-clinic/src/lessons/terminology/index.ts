import template from "./template.cql?raw";
import solution from "./solution.cql?raw";
import fixtures from "./fixtures.json";
import expected from "./expected.json";
import meta from "./lesson.json";
import type { Lesson } from "../types";

const lesson: Lesson = {
  id: meta.id,
  title: meta.title,
  description: meta.description,
  difficulty: meta.difficulty as Lesson["difficulty"],
  estimatedTime: meta.estimatedTime,
  learningObjectives: meta.learningObjectives,
  template,
  solution,
  fixtures: fixtures as unknown[],
  expected: expected as Lesson["expected"],
  ungradedDefines: meta.ungradedDefines,
  hints: meta.hints,
};

export default lesson;
