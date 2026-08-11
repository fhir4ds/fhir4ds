import { useEffect, useState } from "react";
import type { QueryResult } from "../../hooks/useDuckDB";
import { viewDefToJson, SLOTS_VIEW } from "../../lib/viewdef";
import { buildScheduleNormalizationCTEs } from "../../lib/cross-resource";
import { CollapsibleCallout } from "../CollapsibleCallout";

interface TranslationSectionProps {
  /** The FHIR4DS-generated SQL (raw output of generate_view_sql). Empty until translated. */
  generatedSql: string;
  /** Whether the v_slot_flat / v_schedules / v_slots tables are materialized. */
  materialized: boolean;
  /** Function that executes a SQL query against the in-browser DuckDB. */
  executeQuery: (sql: string) => Promise<QueryResult>;
  /** Time the ViewDefinition took to translate, in ms. */
  translateMs: number | null;
}

/**
 * §3: Show the ViewDefinition, the FHIR4DS-generated SQL, and a sample of the
 * resulting flat table. The cross-resource normalization SQL (the hand-written
 * CTE chain that handles the 4 schema variants) is hidden behind a collapsible
 * callout — available for the curious, out of the way for everyone else.
 *
 * Slice 7e: also surfaces the consumer-side geo fallback — when a published
 * Location omits `position` (spec-optional), the cross-resource SQL COALESCEs
 * to a ZIP-centroid lookup. The audit widget below the first-10-rows table
 * shows which Locations needed the fallback.
 */
export function TranslationSection({
  generatedSql,
  materialized,
  executeQuery,
  translateMs,
}: TranslationSectionProps) {
  const [sample, setSample] = useState<QueryResult | null>(null);
  const [sampleError, setSampleError] = useState<string | null>(null);
  const [audit, setAudit] = useState<QueryResult | null>(null);

  useEffect(() => {
    if (!materialized) return;
    (async () => {
      try {
        const result = await executeQuery(
          `SELECT slot_id, "status", "start", specialty, schedule_ref FROM v_slot_flat LIMIT 10;`,
        );
        setSample(result);
      } catch (e: any) {
        setSampleError(e?.message ?? String(e));
      }
      try {
        // Per-Location audit: did its lat/lon come from Location.position or
        // from the ZIP-centroid fallback? Sort fallbacks to the top so the
        // viewer sees them first.
        const auditResult = await executeQuery(`
          SELECT
            loc.id AS location_id,
            json_extract_string(loc.resource, '$.address.city') AS city,
            json_extract_string(loc.resource, '$.address.postalCode') AS zip,
            COALESCE(
              NULLIF(fhirpath_text(loc.resource, 'position.latitude'), ''),
              (SELECT CAST(z.lat AS VARCHAR) FROM zip_centroids z WHERE z.zip = json_extract_string(loc.resource, '$.address.postalCode') LIMIT 1)
            ) AS lat,
            COALESCE(
              NULLIF(fhirpath_text(loc.resource, 'position.longitude'), ''),
              (SELECT CAST(z.lon AS VARCHAR) FROM zip_centroids z WHERE z.zip = json_extract_string(loc.resource, '$.address.postalCode') LIMIT 1)
            ) AS lon,
            CASE
              WHEN json_extract_string(loc.resource, '$.position.latitude') IS NOT NULL
                AND json_extract_string(loc.resource, '$.position.latitude') != ''
                THEN 'Location.position'
              ELSE 'zip_centroids (fallback)'
            END AS lat_source
          FROM resources loc
          WHERE loc.resourceType = 'Location'
          ORDER BY
            CASE WHEN lat_source = 'zip_centroids (fallback)' THEN 0 ELSE 1 END,
            location_id;
        `);
        setAudit(auditResult);
      } catch {
        // ignore — audit is best-effort
      }
    })();
  }, [materialized, executeQuery]);

  const viewDefJson = viewDefToJson(SLOTS_VIEW);

  return (
    <>
      <div className="widget">
        <div className="translation-grid">
          <div className="translation-panel">
            <div className="translation-panel__title">
              ViewDefinition
              <span className="translation-panel__hint">SQL-on-FHIR v2</span>
            </div>
            <pre className="translation-panel__code">{viewDefJson}</pre>
          </div>
          <div className="translation-panel">
            <div className="translation-panel__title">
              Generated SQL
              <span className="translation-panel__hint">
                {translateMs !== null
                  ? `fhir4ds.generate_view_sql · ${Math.round(translateMs)}ms`
                  : "fhir4ds.generate_view_sql"}
              </span>
            </div>
            <pre className="translation-panel__code">
              {generatedSql || "(translating…)"}
            </pre>
          </div>
        </div>

        <div className="translation-output">
          <div className="translation-output__title">
            v_slot_flat — first 10 rows
            {sample && (
              <span className="translation-output__count">
                {sample.rowCount} shown
              </span>
            )}
          </div>
          {sampleError && <div className="widget__error">{sampleError}</div>}
          {sample && <SimpleTable result={sample} />}
        </div>

        <CollapsibleCallout
          prompt="Show how practitioner & location data gets here →"
          title="Cross-resource normalization SQL (runs once at ingest)"
        >
          <p className="callout__intro">
            FHIR4DS's ViewDefinition handles within-resource flattening. To get
            practitioner and location data into the slot row, we run hand-written
            SQL with the <code>fhirpath_text</code> UDFs against the{" "}
            <code>resources</code> table. The four published schema variants
            (PractitionerRole actor, direct Practitioner actor, contained
            PractitionerRole, role-with-specialty) are normalized via three CTEs
            UNIONed together. The lat/lon <code>COALESCE</code> shown above lives
            in these CTEs — Location.position first, ZIP-centroid fallback second.
            This runs <strong>once</strong> at ingest — runtime queries never see it.
          </p>
          <pre className="callout__code">{buildScheduleNormalizationCTEs()}</pre>
        </CollapsibleCallout>
      </div>

      {audit && audit.rowCount > 0 && (
        <>
          <p>
            The same step also fills in gaps the publishers leave. The FHIR
            spec makes <code>Location.position</code> optional — and not every
            publisher ships it. When it's missing, the cross-resource SQL
            COALESCEs to a ZIP-centroid lookup against a bundled 42k-row US ZIP
            database, so every Location ends up with coordinates regardless of
            what the publisher shipped. The audit table below shows which
            Locations needed the fallback.
          </p>
          <div className="widget">
            <div className="translation-output">
              <div className="translation-output__title">
                Lat/lon source per Location
                <span className="translation-output__count">
                  {countFallbacks(audit)} of {audit.rowCount} needed fallback
                </span>
              </div>
              <div className="audit-table-wrap">
                <table className="simple-table audit-table">
                  <thead>
                    <tr>
                      <th>Location</th>
                      <th>City</th>
                      <th>ZIP</th>
                      <th>Latitude</th>
                      <th>Longitude</th>
                      <th>lat/lon source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {audit.rows.map((row, i) => {
                      const isFallback = String(row[5] ?? "").includes("fallback");
                      return (
                        <tr key={i} className={isFallback ? "audit-row--fallback" : ""}>
                          <td><code>{String(row[0] ?? "")}</code></td>
                          <td>{String(row[1] ?? "")}</td>
                          <td>{String(row[2] ?? "")}</td>
                          <td className="audit-coord">{String(row[3] ?? "")}</td>
                          <td className="audit-coord">{String(row[4] ?? "")}</td>
                          <td>
                            <span className={`source-tag ${isFallback ? "source-tag--fallback" : ""}`}>
                              {String(row[5] ?? "")}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      )}
    </>
  );
}

function countFallbacks(audit: QueryResult): number {
  // Column 5 is "lat_source" (after adding lat/lon as columns 3 and 4);
  // fallback rows contain "fallback" in the value.
  let n = 0;
  for (const row of audit.rows) {
    if (String(row[5] ?? "").includes("fallback")) n++;
  }
  return n;
}

function SimpleTable({ result }: { result: QueryResult }) {
  if (result.rowCount === 0) {
    return <div className="widget__pending">No rows.</div>;
  }
  return (
    <table className="simple-table">
      <thead>
        <tr>
          {result.columns.map((c) => (
            <th key={c}>{c}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {result.rows.map((row, i) => (
          <tr key={i}>
            {row.map((cell, j) => (
              <td key={j}>
                {cell === null || cell === undefined
                  ? ""
                  : typeof cell === "object"
                    ? JSON.stringify(cell)
                    : String(cell)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
