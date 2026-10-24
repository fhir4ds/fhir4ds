/**
 * S31: per-patient MeasureReport materialization from evaluation rows.
 *
 * The row→report transform is a pure operation (fhir4ds.operations
 * .measure_report_from_rows). CONNECTED mode calls it on the dev server
 * — the Pyodide worker must never be required for a heartbeat (its boot
 * was the ~10s connected startup cost). Standalone keeps the in-browser
 * worker (same Python capability, same shape).
 */
import { workerRequest } from "../components/BootOverlay";

export interface MeasureReportsEnvelope {
  ok?: boolean;
  reports?: Array<Record<string, unknown>>;
  diagnostics?: Array<{ message?: string }>;
}

export async function materializeMeasureReports(
  connected: boolean,
  measure: Record<string, unknown>,
  rows: Array<Record<string, unknown>>,
  columns: string[],
): Promise<MeasureReportsEnvelope> {
  if (connected) {
    const res = await fetch("/api/measure/report-from-rows", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ measure, rows, columns }),
    });
    const body = (await res.json()) as {
      data?: MeasureReportsEnvelope;
    } & MeasureReportsEnvelope;
    return (body?.data ?? body) as MeasureReportsEnvelope;
  }
  const repResp = await workerRequest({
    type: "measure_report_from_rows",
    measure,
    rows,
    columns,
  });
  return JSON.parse(
    (repResp as { envelope: string }).envelope,
  ) as MeasureReportsEnvelope;
}
