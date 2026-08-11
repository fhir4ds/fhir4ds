/**
 * Cross-resource normalization SQL.
 *
 * FHIR4DS's ViewDefinition parser accepts a top-level `joins` clause per the
 * SQL-on-FHIR v2 spec, but the SQL generator does not currently emit JOIN SQL
 * for cross-resource joins (it parses and validates, then drops them). For the
 * demo's multi-provider federation use case we compose joins by hand here.
 *
 * The 5 published providers use 4 different schema patterns. Slot/Schedule
 * navigation falls into 3 categories:
 *
 *   1. PractitionerRole actor (Allina, Children's, Mayo):
 *      Slot → Schedule → actor[PractitionerRole] → practitioner, location
 *
 *   2. Direct Practitioner actor (Hennepin):
 *      Slot → Schedule → actor[Practitioner, Location]
 *
 *   3. HealthcareService actor with contained PractitionerRole (Fairview):
 *      Slot → Schedule → actor[HealthcareService] → contained PractitionerRole
 *                                                                    → practitioner
 *                                                                    → location
 *
 * The SQL below defines 3 CTEs, one per pattern, then UNION ALLs them into a
 * single `v_schedules` virtual table. The main query LEFT JOINs v_slots to
 * v_schedules via the schedule_ref column produced by the ViewDefinition.
 *
 * Geo fallback: published Location resources sometimes omit `position`
 * (spec-optional). When that happens, we resolve lat/lon from the location's
 * postalCode via the bundled `zip_centroids` table (loaded at ingest). The
 * COALESCE in each CTE handles this: try Location.position first, fall back to
 * ZIP-centroid lookup. The synthesizer strips position from ~25% of locations
 * so the fallback is exercised in every demo run.
 *
 * Performance note: JOINs use the typed `id` and `resourceType` columns that
 * are extracted at ingest time (cheap indexed equality). fhirpath_text is
 * reserved for fields that aren't pre-extracted (deep JSON navigation like
 * position.lat, contained PractitionerRole links, etc).
 */

/**
 * Build a lat or lon extraction expression with ZIP-centroid fallback.
 *
 * Tries Location.position.{latitude|longitude} first; if absent (NULL or
 * empty string), falls back to the zip_centroids table matched on the
 * location's postalCode. This is the consumer-side geo fallback: the FHIR
 * spec makes Location.position optional, so we handle the case where
 * publishers omit it.
 *
 * `field` is "latitude" or "longitude". `coord` is "lat" or "lon" (the
 * zip_centroids column name).
 */
function geoExpr(locAlias: string, field: "latitude" | "longitude", coord: "lat" | "lon"): string {
  return `COALESCE(
        NULLIF(fhirpath_text(${locAlias}.resource, 'position.${field}'), ''),
        (SELECT CAST(z.${coord} AS VARCHAR) FROM zip_centroids z WHERE z.zip = json_extract_string(${locAlias}.resource, '$.address.postalCode') LIMIT 1)
    )`;
}

/** Convenience: build the (lat, lon) pair of expressions for a given alias. */
function geoPair(locAlias: string): { lat: string; lon: string } {
  return {
    lat: geoExpr(locAlias, "latitude", "lat"),
    lon: geoExpr(locAlias, "longitude", "lon"),
  };
}

/**
 * Returns the SQL for the 3 CTEs that normalize Schedule rows across the 3
 * schema patterns. Each CTE produces one row per schedule with:
 *   schedule_id, practitioner_given, practitioner_family, location_name,
 *   location_city, location_lat, location_lon
 *
 * The lat/lon columns are COALESCE'd: Location.position first, then ZIP-
 * centroid lookup from the `zip_centroids` table.
 */
export function buildScheduleNormalizationCTEs(): string {
  const { lat, lon } = geoPair("loc");
  return `
-- Pattern 1: PractitionerRole actor (Allina, Children's, Mayo)
-- Schedule.actor[0].reference = "PractitionerRole/<id>"
WITH schedules_via_role AS (
    SELECT
        sch.id AS schedule_id,
        fhirpath_text(prac.resource, 'name.first().given.first()') AS practitioner_given,
        fhirpath_text(prac.resource, 'name.first().family') AS practitioner_family,
        fhirpath_text(loc.resource,  'name') AS location_name,
        fhirpath_text(loc.resource,  'address.city') AS location_city,
        ${lat} AS location_lat,
        ${lon} AS location_lon,
        fhirpath_text(sch.resource, 'serviceType.coding.first().code') AS schedule_specialty_code,
        fhirpath_text(sch.resource, 'serviceType.coding.first().display') AS schedule_specialty_display
    FROM resources sch
    JOIN resources role
        ON role.resourceType = 'PractitionerRole'
       AND role.id = regexp_extract(
               json_extract_string(sch.resource, '$.actor[0].reference'),
               'PractitionerRole/(.*)', 1)
    JOIN resources prac
        ON prac.resourceType = 'Practitioner'
       AND ('Practitioner/' || prac.id) =
           json_extract_string(role.resource, '$.practitioner.reference')
    JOIN resources loc
        ON loc.resourceType = 'Location'
       AND ('Location/' || loc.id) =
           json_extract_string(role.resource, '$.location[0].reference')
    WHERE sch.resourceType = 'Schedule'
      AND json_extract_string(sch.resource, '$.actor[0].reference') LIKE 'PractitionerRole/%'
),

-- Pattern 2: Direct Practitioner + Location actors (Hennepin)
-- Schedule.actor = [Practitioner/..., Location/...]
schedules_via_direct AS (
    SELECT
        sch.id AS schedule_id,
        fhirpath_text(prac.resource, 'name.first().given.first()') AS practitioner_given,
        fhirpath_text(prac.resource, 'name.first().family') AS practitioner_family,
        fhirpath_text(loc.resource,  'name') AS location_name,
        fhirpath_text(loc.resource,  'address.city') AS location_city,
        ${lat} AS location_lat,
        ${lon} AS location_lon,
        fhirpath_text(sch.resource, 'serviceType.coding.first().code') AS schedule_specialty_code,
        fhirpath_text(sch.resource, 'serviceType.coding.first().display') AS schedule_specialty_display
    FROM resources sch
    JOIN resources prac
        ON prac.resourceType = 'Practitioner'
       AND ('Practitioner/' || prac.id) =
           json_extract_string(sch.resource, '$.actor[0].reference')
    JOIN resources loc
        ON loc.resourceType = 'Location'
       AND ('Location/' || loc.id) =
           json_extract_string(sch.resource, '$.actor[1].reference')
    WHERE sch.resourceType = 'Schedule'
      AND json_extract_string(sch.resource, '$.actor[0].reference') LIKE 'Practitioner/%'
),

-- Pattern 3: HealthcareService actor with contained PractitionerRole (Fairview)
-- Schedule.actor[0].reference = "HealthcareService/<id>"
-- The HealthcareService has a contained[] array with PractitionerRole resources
schedules_via_contained AS (
    SELECT
        sch.id AS schedule_id,
        fhirpath_text(prac.resource, 'name.first().given.first()') AS practitioner_given,
        fhirpath_text(prac.resource, 'name.first().family') AS practitioner_family,
        fhirpath_text(loc.resource,  'name') AS location_name,
        fhirpath_text(loc.resource,  'address.city') AS location_city,
        ${lat} AS location_lat,
        ${lon} AS location_lon,
        fhirpath_text(sch.resource, 'serviceType.coding.first().code') AS schedule_specialty_code,
        fhirpath_text(sch.resource, 'serviceType.coding.first().display') AS schedule_specialty_display
    FROM resources sch
    JOIN resources hcs
        ON hcs.resourceType = 'HealthcareService'
       AND ('HealthcareService/' || hcs.id) =
           json_extract_string(sch.resource, '$.actor[0].reference')
    JOIN resources prac
        ON prac.resourceType = 'Practitioner'
       AND ('Practitioner/' || prac.id) =
           json_extract_string(hcs.resource, '$.contained[0].practitioner.reference')
    JOIN resources loc
        ON loc.resourceType = 'Location'
       AND ('Location/' || loc.id) =
           json_extract_string(hcs.resource, '$.contained[0].location[0].reference')
    WHERE sch.resourceType = 'Schedule'
      AND json_extract_string(sch.resource, '$.actor[0].reference') LIKE 'HealthcareService/%'
),

-- Pattern 4: Direct Location actor (COVID-era SMART Scheduling Links: CVS, Walgreens)
-- Schedule.actor = [Location/...] — no Practitioner, no PractitionerRole.
-- This is the original COVID vaccine scheduling shape. No practitioner data
-- exists; we populate NULL for practitioner fields and resolve location only.
schedules_via_location_only AS (
    SELECT
        sch.id AS schedule_id,
        CAST(NULL AS VARCHAR) AS practitioner_given,
        CAST(NULL AS VARCHAR) AS practitioner_family,
        fhirpath_text(loc.resource,  'name') AS location_name,
        fhirpath_text(loc.resource,  'address.city') AS location_city,
        ${lat} AS location_lat,
        ${lon} AS location_lon,
        fhirpath_text(sch.resource, 'serviceType.coding.first().code') AS schedule_specialty_code,
        fhirpath_text(sch.resource, 'serviceType.coding.first().display') AS schedule_specialty_display
    FROM resources sch
    JOIN resources loc
        ON loc.resourceType = 'Location'
       AND ('Location/' || loc.id) =
           json_extract_string(sch.resource, '$.actor[0].reference')
    WHERE sch.resourceType = 'Schedule'
      AND json_extract_string(sch.resource, '$.actor[0].reference') LIKE 'Location/%'
),

-- All schedules, normalized across the 4 patterns
v_schedules AS (
    SELECT * FROM schedules_via_role
    UNION ALL
    SELECT * FROM schedules_via_direct
    UNION ALL
    SELECT * FROM schedules_via_contained
    UNION ALL
    SELECT * FROM schedules_via_location_only
)`;
}
