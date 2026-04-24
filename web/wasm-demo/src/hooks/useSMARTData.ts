/**
 * React hook: Ingest SMART on FHIR patient data into the DuckDB resources table.
 *
 * Reuses the playground's DuckDB connection to load fetched FHIR resources
 * so that FHIRPath and CQL queries can run against live patient data.
 */

import { useState, useCallback } from "react";
import type { FHIRResource, FHIRDataset, FetchProgress } from "../lib/smart-data";
import { fetchPatientData } from "../lib/smart-data";
import type { SmartToken } from "../lib/smart-auth";
import type { Vendor } from "../lib/smart-config";

// ── Types ────────────────────────────────────────────────────────────────────

export interface SMARTDataState {
  loading: boolean;
  error: string | null;
  dataset: FHIRDataset | null;
  progress: FetchProgress | null;
  resourceCount: number;
}

// ── Patient reference extraction ─────────────────────────────────────────────

function extractPatientRef(resource: FHIRResource): string | null {
  // Store plain patient ID (no "Patient/" prefix) so CQL-generated SQL
  // `_pt.id = _outer.patient_ref` resolves correctly.
  if (resource.resourceType === "Patient") return resource.id ?? null;
  for (const path of ["subject", "patient", "beneficiary"]) {
    const refObj = resource[path] as { reference?: string } | undefined;
    if (refObj?.reference) {
      const ref = refObj.reference;
      if (typeof ref === "string") {
        if (ref.startsWith("Patient/")) return ref.slice("Patient/".length);
        return ref.split("/").pop() ?? null;
      }
    }
  }
  return null;
}

// ── Hook ─────────────────────────────────────────────────────────────────────

/**
 * @param getConnection - Function returning the active DuckDB connection (from useDuckDB or useCMSDuckDB)
 */
export function useSMARTData(getConnection: () => any | null) {
  const [state, setState] = useState<SMARTDataState>({
    loading: false,
    error: null,
    dataset: null,
    progress: null,
    resourceCount: 0,
  });

  /**
   * Fetch patient data from a FHIR server and load it into DuckDB.
   */
  const loadPatientData = useCallback(
    async (
      fhirBaseUrl: string,
      token: SmartToken,
      vendor: Vendor,
      clientId?: string,
    ) => {
      const conn = getConnection();
      if (!conn) {
        // DuckDB not yet initialised — caller should retry once duckdbReady
        return;
      }

      if (!token.patientId) {
        setState((s) => ({ ...s, error: "No patient ID in token response" }));
        return;
      }

      setState({
        loading: true,
        error: null,
        dataset: null,
        progress: null,
        resourceCount: 0,
      });

      try {
        // Fetch from FHIR server
        const dataset = await fetchPatientData(
          fhirBaseUrl,
          token.patientId,
          token.accessToken,
          vendor,
          clientId,
          (progress) => setState((s) => ({ ...s, progress })),
        );

        // Clear existing resources and insert new ones
        await conn.query("DELETE FROM resources;");

        const stmt = await conn.prepare("INSERT INTO resources VALUES (?, ?, ?, ?)");
        let count = 0;
        for (const resource of dataset.resources) {
          const id = resource.id ?? `${resource.resourceType}-${count}`;
          const resourceType = resource.resourceType;
          const json = JSON.stringify(resource);
          const patientRef = extractPatientRef(resource);
          await stmt.query(id, resourceType, json, patientRef);
          count++;
        }
        await stmt.close();

        setState({
          loading: false,
          error: null,
          dataset,
          progress: null,
          resourceCount: count,
        });

        console.log(
          `[SMARTData] Loaded ${count} resources for patient ${token.patientId}`,
        );
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setState({
          loading: false,
          error: message,
          dataset: null,
          progress: null,
          resourceCount: 0,
        });
      }
    },
    [getConnection],
  );

  /**
   * Clear loaded SMART data from DuckDB.
   */
  const clearData = useCallback(async () => {
    const conn = getConnection();
    if (conn) {
      try {
        await conn.query("DELETE FROM resources;");
      } catch {
        // Ignore if table doesn't exist
      }
    }
    setState({
      loading: false,
      error: null,
      dataset: null,
      progress: null,
      resourceCount: 0,
    });
  }, [getConnection]);

  return { ...state, loadPatientData, clearData };
}
