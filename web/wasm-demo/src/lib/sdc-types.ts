/**
 * Minimal FHIR R4 Questionnaire / QuestionnaireResponse types
 * with SDC (Structured Data Capture) extension helpers.
 *
 * These are intentionally lightweight — only the fields needed
 * for the interactive forms demo are included.
 */

// ── Questionnaire ──────────────────────────────────────────────

export interface Questionnaire {
  resourceType: "Questionnaire";
  id?: string;
  title?: string;
  status: "draft" | "active" | "retired" | "unknown";
  item?: QuestionnaireItem[];
}

export type ItemType =
  | "group"
  | "display"
  | "string"
  | "integer"
  | "decimal"
  | "date"
  | "boolean"
  | "choice"
  | "text";

export interface AnswerOption {
  valueCoding?: { system?: string; code: string; display?: string };
  valueString?: string;
  valueInteger?: number;
}

export interface QuestionnaireItem {
  linkId: string;
  text?: string;
  type: ItemType;
  required?: boolean;
  readOnly?: boolean;
  repeats?: boolean;
  answerOption?: AnswerOption[];
  item?: QuestionnaireItem[];
  extension?: Extension[];
}

// ── QuestionnaireResponse ──────────────────────────────────────

export interface QuestionnaireResponse {
  resourceType: "QuestionnaireResponse";
  questionnaire?: string;
  status: "in-progress" | "completed" | "amended" | "stopped";
  item?: QuestionnaireResponseItem[];
}

export interface QuestionnaireResponseItem {
  linkId: string;
  text?: string;
  answer?: QuestionnaireResponseAnswer[];
  item?: QuestionnaireResponseItem[];
}

export interface QuestionnaireResponseAnswer {
  valueString?: string;
  valueInteger?: number;
  valueDecimal?: number;
  valueBoolean?: boolean;
  valueDate?: string;
  valueCoding?: { system?: string; code: string; display?: string };
}

// ── Extensions ─────────────────────────────────────────────────

export interface Extension {
  url: string;
  valueExpression?: {
    language: string;
    expression: string;
    description?: string;
  };
  valueString?: string;
  valueBoolean?: boolean;
}

const SDC_CALCULATED =
  "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-calculatedExpression";
const SDC_INITIAL =
  "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-initialExpression";

/** Extract calculatedExpression FHIRPath from an item's extensions. */
export function getCalculatedExpression(item: QuestionnaireItem): string | null {
  const ext = item.extension?.find((e) => e.url === SDC_CALCULATED);
  return ext?.valueExpression?.expression ?? null;
}

/** Extract initialExpression FHIRPath from an item's extensions. */
export function getInitialExpression(item: QuestionnaireItem): string | null {
  const ext = item.extension?.find((e) => e.url === SDC_INITIAL);
  return ext?.valueExpression?.expression ?? null;
}

/** Recursively collect all items (flattened) from a Questionnaire. */
export function flattenItems(items: QuestionnaireItem[] | undefined): QuestionnaireItem[] {
  if (!items) return [];
  const result: QuestionnaireItem[] = [];
  for (const item of items) {
    result.push(item);
    if (item.item) result.push(...flattenItems(item.item));
  }
  return result;
}
