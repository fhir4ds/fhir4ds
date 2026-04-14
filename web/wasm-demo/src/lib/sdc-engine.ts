/**
 * SDC FHIRPath evaluation engine.
 *
 * Unified evaluation using FHIR4DS DuckDB WASM extensions (fhirpath_text).
 * This demonstrates the power of the project's own C++ UDFs for SDC logic.
 */
import type {
  Questionnaire,
  QuestionnaireItem,
  QuestionnaireResponse,
  QuestionnaireResponseItem,
  QuestionnaireResponseAnswer,
} from "./sdc-types";
import { flattenItems, getCalculatedExpression, getInitialExpression } from "./sdc-types";

export interface CalcResult {
  linkId: string;
  value: unknown;
  error?: string;
}

/**
 * Evaluate all `calculatedExpression` extensions in the questionnaire
 * against the current QuestionnaireResponse using DuckDB fhirpath_text.
 */
export async function evaluateCalculatedExpressionsAsync(
  questionnaire: Questionnaire,
  response: QuestionnaireResponse,
  executeQuery: (sql: string) => Promise<any>,
): Promise<CalcResult[]> {
  const allItems = flattenItems(questionnaire.item);
  const results: CalcResult[] = [];

  for (const item of allItems) {
    let expr = getCalculatedExpression(item);
    if (!expr) continue;

    // SDC expressions often use %resource to refer to the QuestionnaireResponse.
    // In our DuckDB fhirpath_text UDF, $this is the input JSON.
    expr = expr.replace(/%resource/g, "$this");

    try {
      // Evaluate against the in-memory response by passing it as a JSON parameter to DuckDB
      const sql = `SELECT fhirpath_text(CAST('${JSON.stringify(response).replace(/'/g, "''")}' AS JSON), '${expr.replace(/'/g, "''")}')`;
      const result = await executeQuery(sql);
      
      const value = result.rows.length > 0 ? result.rows[0][0] : null;
      results.push({ linkId: item.linkId, value });
    } catch (e) {
      results.push({
        linkId: item.linkId,
        value: null,
        error: e instanceof Error ? e.message : String(e),
      });
    }
  }

  return results;
}

/**
 * Evaluate all `initialExpression` extensions to pre-populate a response
 * using DuckDB fhirpath_text queries against the resources table.
 */
export async function evaluateInitialExpressionsAsync(
  questionnaire: Questionnaire,
  patientData: Record<string, unknown> | null,
  executeQuery: (sql: string) => Promise<any>,
): Promise<CalcResult[]> {
  const allItems = flattenItems(questionnaire.item);
  const results: CalcResult[] = [];

  for (const item of allItems) {
    let expr = getInitialExpression(item);
    if (!expr) continue;

    try {
      let sql = "";
      if (expr.startsWith("[")) {
        // SQL-on-FHIR search across collection
        const match = expr.match(/^\[(\w+)\]\s*(.*)$/);
        if (match) {
          const [, resourceType, fhirPath] = match;
          const trimmedPath = (fhirPath || "").trim();
          
          // Determine patient filter for the query
          let patientFilter = "";
          if (patientData?.id) {
            const pid = patientData.id;
            patientFilter = `AND (patient_ref = '${pid}' OR patient_ref = 'Patient/${pid}')`;
          }

          if (trimmedPath === "count()") {
            sql = `SELECT count(*) FROM resources WHERE resourceType = '${resourceType}' ${patientFilter}`;
          } else {
            const cleanPath = (trimmedPath || "$this").replace(/'/g, "''");
            // Use a subquery to correctly filter for non-null fhirpath results
            // before applying LIMIT 1. This ensures we find the matching resource
            // in the collection (e.g. finding the specific Observation code).
            sql = `
              SELECT val FROM (
                SELECT fhirpath_text(resource, '${cleanPath}') as val
                FROM resources
                WHERE resourceType = '${resourceType}' ${patientFilter}
              )
              WHERE val IS NOT NULL AND val != '' AND val != 'null'
              LIMIT 1
            `;
          }
        }
      } else {
        // Simple path against the patient context
        // In DuckDB, we query the Patient resource in the resources table
        const patientId = patientData?.id;
        if (patientId) {
            expr = expr.replace(/%patient/g, "$this");
            sql = `SELECT fhirpath_text(resource, '${expr.replace(/'/g, "''")}') FROM resources WHERE resourceType = 'Patient' AND id = '${patientId}' LIMIT 1`;
        }
      }

      if (sql) {
        console.log(`[SDC] Pre-pop SQL for ${item.linkId}:`, sql.trim());
        const result = await executeQuery(sql);
        if (result.rows.length > 0) {
          let value = result.rows[0][0];
          console.log(`[SDC] Raw SQL result for ${item.linkId}:`, value);
          
          // 1. Handle stringified JSON from DuckDB
          if (typeof value === 'string' && (value.startsWith('{') || value.startsWith('['))) {
            try {
              value = JSON.parse(value);
            } catch { /* use raw string */ }
          }

          // 2. Handle DuckDB list-proxy objects {0: val, ...}
          if (typeof value === 'object' && value !== null) {
             const keys = Object.keys(value);
             if (keys.includes('0')) {
                value = (value as any)['0'];
                console.log(`[SDC] Extracted item '0' for ${item.linkId}:`, value);
             }
          }
          
          console.log(`[SDC] Final mapped value for ${item.linkId}:`, value);
          results.push({ linkId: item.linkId, value });
          continue;
        }
      }
      
      results.push({ linkId: item.linkId, value: null });
    } catch (e) {
      results.push({
        linkId: item.linkId,
        value: null,
        error: e instanceof Error ? e.message : String(e),
      });
    }
  }

  return results;
}

/**
 * Build an empty QuestionnaireResponse skeleton from a Questionnaire.
 */
export function buildEmptyResponse(q: Questionnaire): QuestionnaireResponse {
  return {
    resourceType: "QuestionnaireResponse",
    questionnaire: q.id,
    status: "in-progress",
    item: buildResponseItems(q.item ?? []),
  };
}

function buildResponseItems(
  items: QuestionnaireItem[],
): QuestionnaireResponseItem[] {
  return items.map((item) => {
    const responseItem: QuestionnaireResponseItem = {
      linkId: item.linkId,
      text: item.text,
    };
    if (item.type === "group" && item.item) {
      responseItem.item = buildResponseItems(item.item);
    }
    return responseItem;
  });
}

/**
 * Set an answer value on a QuestionnaireResponse item identified by linkId.
 * Returns a new response (immutable update).
 */
export function setAnswer(
  response: QuestionnaireResponse,
  linkId: string,
  answer: QuestionnaireResponseAnswer | null,
): QuestionnaireResponse {
  return {
    ...response,
    item: setAnswerInItems(response.item ?? [], linkId, answer),
  };
}

function setAnswerInItems(
  items: QuestionnaireResponseItem[],
  linkId: string,
  answer: QuestionnaireResponseAnswer | null,
): QuestionnaireResponseItem[] {
  return items.map((item) => {
    if (item.linkId === linkId) {
      return {
        ...item,
        answer: answer ? [answer] : undefined,
      };
    }
    if (item.item) {
      return {
        ...item,
        item: setAnswerInItems(item.item, linkId, answer),
      };
    }
    return item;
  });
}

/** Helper to extract current answer value from QR */
export function getAnswer(
  response: QuestionnaireResponse,
  linkId: string,
): QuestionnaireResponseAnswer | undefined {
  const allItems = flattenResponseItems(response.item);
  return allItems.find((i) => i.linkId === linkId)?.answer?.[0];
}

function flattenResponseItems(
  items: QuestionnaireResponseItem[] | undefined,
): QuestionnaireResponseItem[] {
  if (!items) return [];
  const result: QuestionnaireResponseItem[] = [];
  for (const item of items) {
    result.push(item);
    if (item.item) result.push(...flattenResponseItems(item.item));
  }
  return result;
}
