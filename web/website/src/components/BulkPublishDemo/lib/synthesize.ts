/**
 * Browser-side synthetic data generator.
 *
 * Ports the core logic from tools/synthesize.py to TypeScript so we can
 * generate a realistic multi-provider scheduling dataset centered on the
 * USER'S location — not just the Twin Cities. When a user in Palatine, IL
 * clicks "Generate near me," they get 5 health systems placed at nearby ZIPs
 * with ~5k slots, all generated in-browser in <1 second.
 *
 * Uses the same resource shapes and 4 schema variants as the Python synthesizer.
 */

import type { QueryResult } from "../hooks/useDuckDB";

export interface SyntheticDataset {
  resources: Array<{ id: string; resourceType: string; resource: string; patient_ref: string | null }>;
  providerCount: number;
  slotCount: number;
  generateTimeMs: number;
}

// Provider templates — generic names that work anywhere in the US.
const PROVIDER_TEMPLATES = [
  { id: "riverside", name: "Riverside Health", schema: "spec" as const },
  { id: "summit", name: "Summit Medical Group", schema: "spec" as const },
  { id: "lakeside", name: "Lakeside Clinic", schema: "role_specialty" as const },
  { id: "northgate", name: "Northgate Family Medicine", schema: "direct_practitioner" as const },
  { id: "westend", name: "Westend Specialists", schema: "contained_role" as const },
];

const SPECIALTIES = [
  { code: "primary-care", display: "Primary Care", system: "http://terminology.hl7.org/CodeSystem/service-type", minutes: 20 },
  { code: "cardiology", display: "Cardiology", system: "http://terminology.hl7.org/CodeSystem/service-type", minutes: 30 },
  { code: "dermatology", display: "Dermatology", system: "http://terminology.hl7.org/CodeSystem/service-type", minutes: 20 },
  { code: "pediatrics", display: "Pediatrics", system: "http://terminology.hl7.org/CodeSystem/service-type", minutes: 20 },
  { code: "orthopedics", display: "Orthopedics", system: "http://terminology.hl7.org/CodeSystem/service-type", minutes: 30 },
];

const FIRST_NAMES = ["Aaron", "Alice", "Amir", "Ben", "Carlos", "Dana", "Elena", "Eric", "Grace", "Hannah", "Jamal", "Julia", "Keiko", "Leila", "Liam", "Maria", "Nadia", "Omar", "Priya", "Quinn", "Rosa", "Ravi", "Sofia", "Samuel", "Tara", "Uma", "Victor", "Wei", "Yara", "Zane"];
const LAST_NAMES = ["Adams", "Baker", "Chen", "Davis", "Fischer", "Garcia", "Hayashi", "Iyer", "Johnson", "Kim", "Larson", "Martinez", "Nguyen", "Patel", "Robinson", "Smith", "Thompson", "Vargas", "Wang", "Young", "Cohen", "Greene", "Hughes", "Jackson", "Khan"];

const BOOKING_URL = "http://fhir-registry.smarthealthit.org/StructureDefinition/booking-deep-link";

// Seeded RNG (mulberry32) for reproducibility
function createRng(seed: number) {
  return () => {
    seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function pick<T>(rng: () => number, arr: T[]): T {
  return arr[Math.floor(rng() * arr.length)];
}

function pickN<T>(rng: () => number, arr: T[], n: number): T[] {
  const copy = [...arr];
  const result: T[] = [];
  for (let i = 0; i < n && copy.length > 0; i++) {
    const idx = Math.floor(rng() * copy.length);
    result.push(copy.splice(idx, 1)[0]);
  }
  return result;
}

function coding(system: string, code: string, display?: string) {
  return display ? { system, code, display } : { system, code };
}

interface NearbyZip {
  zip: string; city: string; state: string; lat: number; lon: number; distanceMiles: number;
}

/**
 * Find nearby ZIP codes from the in-memory zip_centroids table.
 * Returns up to `limit` ZIPs sorted by distance.
 */
export async function findNearbyZips(
  executeQuery: (sql: string) => Promise<QueryResult>,
  lat: number,
  lon: number,
  limit: number = 25,
): Promise<NearbyZip[]> {
  const result = await executeQuery(`
    SELECT zip, city, state, CAST(lat AS DOUBLE) AS lat, CAST(lon AS DOUBLE) AS lon,
      2 * 3959 * asin(sqrt(
        pow(sin(radians(CAST(lat AS DOUBLE) - ${lat}) / 2), 2) +
        cos(radians(${lat})) * cos(radians(CAST(lat AS DOUBLE))) *
        pow(sin(radians(CAST(lon AS DOUBLE) - ${lon}) / 2), 2)
      )) AS distance_miles
    FROM zip_centroids
    ORDER BY distance_miles ASC
    LIMIT ${limit};
  `);
  const zips: NearbyZip[] = [];
  for (let i = 0; i < result.rowCount; i++) {
    zips.push({
      zip: String(result.rows[i][0]),
      city: String(result.rows[i][1] ?? "").trim(),
      state: String(result.rows[i][2] ?? ""),
      lat: Number(result.rows[i][3]),
      lon: Number(result.rows[i][4]),
      distanceMiles: Number(result.rows[i][5]),
    });
  }
  return zips;
}

/**
 * Generate a synthetic multi-provider scheduling dataset centered on (lat, lon).
 *
 * Produces 5 providers placed at nearby ZIPs, with ~15 locations, ~60
 * practitioners, ~60 schedules, and ~5,000 slots over the next 30 days.
 * Same 4 schema variants as the Python synthesizer.
 *
 * Returns an array of {id, resourceType, resource, patient_ref} rows ready
 * for INSERT into the `resources` table.
 */
export function generateDataset(
  lat: number,
  lon: number,
  nearbyZips: NearbyZip[],
): SyntheticDataset {
  const start = performance.now();
  // Seed from lat+lon so the same location always produces the same dataset
  const seed = Math.floor((Math.abs(lat) * 1000 + Math.abs(lon) * 1000)) || 42;
  const rng = createRng(seed);

  // Distribute ZIPs across providers (3-6 ZIPs each)
  const zipPool = nearbyZips.slice(0, 20);
  if (zipPool.length < 5) {
    // Not enough ZIPs — duplicate to ensure each provider has at least 3
    while (zipPool.length < 15) zipPool.push(zipPool[rng() * zipPool.length | 0]);
  }

  const resources: SyntheticDataset["resources"] = [];
  let slotCount = 0;
  const today = new Date();
  const startDate = new Date(today);
  startDate.setDate(startDate.getDate() + 1); // Start tomorrow

  let zipIdx = 0;
  let pracCounter = 0;

  for (const provider of PROVIDER_TEMPLATES) {
    const nLocations = 3 + Math.floor(rng() * 3); // 3-5
    const providerZips: NearbyZip[] = [];
    for (let i = 0; i < nLocations; i++) {
      providerZips.push(zipPool[zipIdx % zipPool.length]);
      zipIdx++;
    }

    // 1) Locations
    const locations: any[] = [];
    for (let i = 0; i < providerZips.length; i++) {
      const z = providerZips[i];
      const locId = `${provider.id}-loc-${i + 1}`;
      const loc: any = {
        resourceType: "Location",
        id: locId,
        name: `${provider.name} ${z.city} Clinic`,
        address: { line: [`${100 + i * 7} Main St`], city: z.city, state: z.state, postalCode: z.zip },
        telecom: [{ system: "phone", value: `(555) 555-${1000 + i}` }],
      };
      // ~75% of locations have position; ~25% omit it (demonstrates ZIP fallback)
      if (i % 4 !== 0) {
        loc.position = { latitude: z.lat, longitude: z.lon };
      }
      locations.push(loc);
      resources.push({ id: locId, resourceType: "Location", resource: JSON.stringify(loc), patient_ref: null });
    }

    // 2) HealthcareServices — one per (location, specialty)
    const chosenSpecialties = pickN(rng, SPECIALTIES, 3 + Math.floor(rng() * 2));
    const hcsByLoc: Record<string, string[]> = {};
    for (const loc of locations) {
      const locId = loc.id;
      hcsByLoc[locId] = [];
      for (const sp of chosenSpecialties) {
        const hcsId = `${locId}-svc-${sp.code}`;
        const hcs: any = {
          resourceType: "HealthcareService",
          id: hcsId,
          location: [{ reference: `Location/${locId}` }],
        };
        if (provider.schema !== "role_specialty") {
          hcs.type = [{ coding: [coding(sp.system, sp.code, sp.display)] }];
        }
        resources.push({ id: hcsId, resourceType: "HealthcareService", resource: JSON.stringify(hcs), patient_ref: null });
        hcsByLoc[locId].push(hcsId);
      }
    }

    // 3) Practitioners + PractitionerRoles
    const assignments: Array<{ pracId: string; locId: string; hcsIds: string[]; roleSpecialtyCodes: string[] }> = [];
    for (const loc of locations) {
      const nPrac = 2 + Math.floor(rng() * 2); // 2-3
      for (let p = 0; p < nPrac; p++) {
        pracCounter++;
        const pracId = `${provider.id}-prac-${pracCounter.toString().padStart(3, "0")}`;
        const given = pick(rng, FIRST_NAMES);
        const family = pick(rng, LAST_NAMES);
        const npi = String(Math.floor(rng() * 9_000_000_000) + 1_000_000_000);
        const prac: any = {
          resourceType: "Practitioner",
          id: pracId,
          name: [{ family, given: [given], prefix: ["Dr."] }],
          identifier: [{ system: "http://hl7.org/fhir/sid/us-npi", value: npi }],
          qualification: [{ code: { coding: [coding("http://terminology.hl7.org/CodeSystem/v2-0360", "MD", "Doctor of Medicine")] } }],
        };
        resources.push({ id: pracId, resourceType: "Practitioner", resource: JSON.stringify(prac), patient_ref: null });

        const availableHcs = hcsByLoc[loc.id] ?? [];
        const nSvc = Math.min(1 + Math.floor(rng() * 2), availableHcs.length);
        const chosenHcs = pickN(rng, availableHcs, nSvc);
        const roleSpecialtyCodes = provider.schema === "role_specialty"
          ? chosenHcs.map(h => h.split("-svc-")[1])
          : [];
        assignments.push({ pracId, locId: loc.id, hcsIds: chosenHcs, roleSpecialtyCodes });

        // Build PractitionerRole for schemas that need it
        if (provider.schema !== "direct_practitioner") {
          const roleId = `${pracId}-role`;
          const role: any = {
            resourceType: "PractitionerRole",
            id: roleId,
            practitioner: { reference: `Practitioner/${pracId}` },
            location: [{ reference: `Location/${loc.id}` }],
          };
          if (chosenHcs.length > 0 && provider.schema !== "role_specialty") {
            role.healthcareService = chosenHcs.map((h: string) => ({ reference: `HealthcareService/${h}` }));
          }
          if (provider.schema === "role_specialty" && roleSpecialtyCodes.length > 0) {
            role.specialty = roleSpecialtyCodes.map(code => {
              const sp = SPECIALTIES.find(s => s.code === code)!;
              return { coding: [coding(sp.system, sp.code, sp.display)] };
            });
          }
          resources.push({ id: roleId, resourceType: "PractitionerRole", resource: JSON.stringify(role), patient_ref: null });

          // For contained_role: embed role in HealthcareService
          if (provider.schema === "contained_role") {
            for (const hcsId of chosenHcs) {
              const hcsRes = resources.find(r => r.id === hcsId);
              if (hcsRes) {
                const hcs = JSON.parse(hcsRes.resource);
                if (!hcs.contained) hcs.contained = [];
                hcs.contained.push(JSON.parse(JSON.stringify(role)));
                hcsRes.resource = JSON.stringify(hcs);
              }
            }
          }
        }
      }
    }

    // 4) Schedules
    for (const a of assignments) {
      const specialtyCodes = a.hcsIds.map(h => h.split("-svc-")[1]).filter(Boolean);
      if (!specialtyCodes.length) continue;

      const schedId = `${a.pracId}-sched`;
      const primarySp = SPECIALTIES.find(s => s.code === specialtyCodes[0])!;
      const actors: any[] = [];

      if (provider.schema === "direct_practitioner") {
        actors.push({ reference: `Practitioner/${a.pracId}` });
        actors.push({ reference: `Location/${a.locId}` });
      } else if (provider.schema === "contained_role") {
        for (const h of a.hcsIds) actors.push({ reference: `HealthcareService/${h}` });
      } else {
        actors.push({ reference: `PractitionerRole/${a.pracId}-role` });
      }

      const sched: any = {
        resourceType: "Schedule",
        id: schedId,
        actor: actors,
        serviceType: [{ coding: [coding(primarySp.system, primarySp.code, primarySp.display)] }],
      };
      resources.push({ id: schedId, resourceType: "Schedule", resource: JSON.stringify(sched), patient_ref: null });

      // 5) Slots — next 30 days, business hours
      for (let dayOffset = 0; dayOffset < 30; dayOffset++) {
        const d = new Date(startDate);
        d.setDate(d.getDate() + dayOffset);
        if (d.getDay() >= 5) continue; // Skip Fri-Sun for variety
        if (rng() < 0.15) continue; // Off day

        for (const [startH, endH] of [[8, 12], [13, 17]] as const) {
          const t = new Date(d);
          t.setHours(startH, 0, 0, 0);
          const end = new Date(d);
          end.setHours(endH, 0, 0, 0);
          while (t < end) {
            const status = rng() < 0.6 ? "free" : "busy";
            const slotEnd = new Date(t.getTime() + primarySp.minutes * 60000);
            const slotId = `${schedId}-slot-${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}-${String(t.getHours()).padStart(2, "0")}${String(t.getMinutes()).padStart(2, "0")}`;
            const handle = Math.random().toString(36).slice(2, 14);
            const slot: any = {
              resourceType: "Slot",
              id: slotId,
              schedule: { reference: `Schedule/${schedId}` },
              status,
              start: t.toISOString(),
              end: slotEnd.toISOString(),
              serviceType: [{ coding: [coding(primarySp.system, primarySp.code, primarySp.display)] }],
              extension: [{ url: BOOKING_URL, valueUrl: `https://book.${provider.id}.example.org/slots/${slotId}?h=${handle}` }],
            };
            resources.push({ id: slotId, resourceType: "Slot", resource: JSON.stringify(slot), patient_ref: null });
            slotCount++;
            t.setTime(slotEnd.getTime());
          }
        }
      }
    }
  }

  return {
    resources,
    providerCount: PROVIDER_TEMPLATES.length,
    slotCount,
    generateTimeMs: performance.now() - start,
  };
}

/**
 * Ingest a generated dataset into the `resources` table, replacing all
 * existing data. Returns a summary suitable for the roster UI.
 */
export async function ingestGeneratedDataset(
  dataset: SyntheticDataset,
  executeQuery: (sql: string) => Promise<QueryResult>,
): Promise<void> {
  await executeQuery("TRUNCATE resources");
  // Batch insert via VALUES
  const batchSize = 500;
  for (let i = 0; i < dataset.resources.length; i += batchSize) {
    const batch = dataset.resources.slice(i, i + batchSize);
    const values = batch
      .map(r => `('${r.id.replace(/'/g, "''")}', '${r.resourceType}', '${r.resource.replace(/'/g, "''")}', NULL)`)
      .join(", ");
    await executeQuery(`INSERT INTO resources (id, resourceType, resource, patient_ref) VALUES ${values};`);
  }
}
