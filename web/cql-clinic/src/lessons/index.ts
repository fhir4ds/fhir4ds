import dataTypes from "./data-types";
import comparisons from "./comparisons";
import fhirQueries from "./fhir-queries";
import stringsConversions from "./strings-conversions";
import nullSafety from "./null-safety";
import quantities from "./quantities";
import temporalLogic from "./temporal-logic";
import terminology from "./terminology";
import querySyntax from "./query-syntax";
import measureBuilding from "./measure-building";
import type { Lesson } from "./types";

export const LESSONS: Lesson[] = [
  dataTypes,
  comparisons,
  fhirQueries,
  stringsConversions,
  nullSafety,
  quantities,
  temporalLogic,
  terminology,
  querySyntax,
  measureBuilding,
];

export function getLesson(id: string): Lesson | undefined {
  return LESSONS.find((l) => l.id === id);
}

export type { Lesson, LessonHint, LessonExpected } from "./types";
