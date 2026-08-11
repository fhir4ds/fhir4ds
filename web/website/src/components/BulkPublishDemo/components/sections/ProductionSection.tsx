import { useEffect, useState } from "react";
import type { QueryResult } from "../../hooks/useDuckDB";
import { RADII } from "../../lib/search-presets";
import { buildRuntimeQuery, type RuntimeQueryInputs } from "../../lib/search";
import { LocationField } from "../LocationField";
import type { GeoPoint } from "../../lib/geo";

interface ProductionSectionProps {
  materialized: boolean;
  executeQuery: (sql: string) => Promise<QueryResult>;
  lookupZip: (zip: string) => Promise<{ city: string; state: string; lat: number; lon: number } | null>;
  lookupCityState?: (city: string, state: string) => Promise<{ zip: string; city: string; state: string; lat: number; lon: number } | null>;
  reverseGeocode?: (
    lat: number,
    lon: number,
  ) => Promise<{ zip: string; city: string; state: string; distanceMiles: number } | null>;
  defaults?: { status: string; dateFrom: string; dateTo: string; geo: { lat: number; lon: number; label: string } | null } | null;
}

/**
 * §5: The same DuckDB-WASM engine, the same multi-provider federation, the
 * same in-browser execution — but with all the educational panels stripped
 * away. This is what ships to patients.
 */
export function ProductionSection({
  materialized,
  executeQuery,
  lookupZip,
  lookupCityState,
  reverseGeocode,
  defaults,
}: ProductionSectionProps) {
  const [status, setStatus] = useState("free");
  const [specialty, setSpecialty] = useState("");
  const [geo, setGeo] = useState<GeoPoint | null>(null);
  const [radiusMiles, setRadiusMiles] = useState(25);
  const [dateFrom, setDateFrom] = useState(todayPlus(0));
  const [dateTo, setDateTo] = useState(todayPlus(14));
  const [textSearch, setTextSearch] = useState("");
  const [specialtyOptions, setSpecialtyOptions] = useState<Array<{code: string; label: string}>>([]);

  useEffect(() => {
    if (!materialized) return;
    executeQuery(`
      SELECT DISTINCT specialty, specialty_display
      FROM v_slots
      WHERE specialty IS NOT NULL AND specialty != ''
      ORDER BY specialty_display
    `).then(result => {
      const options = result.rows.map(r => ({
        code: String(r[0] ?? ""),
        label: String(r[1] ?? r[0] ?? ""),
      }));
      setSpecialtyOptions([{ code: "", label: "(any)" }, ...options]);
    }).catch(() => {
      setSpecialtyOptions([{ code: "", label: "(any)" }]);
    });
  }, [materialized, executeQuery]);

  // Apply preset defaults when the user switches endpoints
  useEffect(() => {
    if (!defaults) return;
    setStatus(defaults.status);
    setDateFrom(defaults.dateFrom);
    setDateTo(defaults.dateTo);
    if (defaults.geo) {
      setGeo({ lat: defaults.geo.lat, lon: defaults.geo.lon, label: defaults.geo.label, source: "preset" });
    }
  }, [defaults]);

  const [results, setResults] = useState<QueryResult | null>(null);
  const [totalCount, setTotalCount] = useState<number | null>(null);
  const [queryMs, setQueryMs] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const inputs: RuntimeQueryInputs = {
    status,
    specialty,
    dateFrom,
    dateTo,
    geo,
    radiusMiles,
    textSearch,
  };
  const query = buildRuntimeQuery(inputs);

  useEffect(() => {
    if (!materialized) return;
    const t = setTimeout(() => {
      setError(null);
      Promise.all([executeQuery(query.display), executeQuery(query.count)])
        .then(([display, count]) => {
          setResults(display);
          setQueryMs(display.executionTimeMs);
          const n = count.rows[0]?.[0];
          setTotalCount(typeof n === "number" ? n : Number(n ?? 0));
        })
        .catch((e) => setError(e?.message ?? String(e)));
    }, 250);
    return () => clearTimeout(t);
  }, [materialized, query, executeQuery]);

  if (!materialized) {
    return (
      <div className="widget widget--pending">
        Production UI appears here once data is materialized.
      </div>
    );
  }

  const useGeo = !!geo && radiusMiles > 0;

  return (
    <div className="widget production">
      <div className="production__search">
        <div className="query-group">
          <span className="query-group__label">Where</span>
          <div className="query-group__fields">
            <div className="production__field production__field--wide">
              <label>Location</label>
              <LocationField
                value={geo}
                onChange={setGeo}
                lookupZip={lookupZip} lookupCityState={lookupCityState}
                reverseGeocode={reverseGeocode}
                compact
              />
            </div>
            <div className="production__field">
              <label>Within</label>
              <select
                value={radiusMiles}
                onChange={(e) => setRadiusMiles(Number(e.target.value))}
              >
                {RADII.filter((r) => r > 0).map((r) => (
                  <option key={r} value={r}>
                    {r} miles
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        <div className="query-group">
          <span className="query-group__label">Who</span>
          <div className="query-group__fields">
            <div className="production__field">
              <label>Specialty</label>
              <select
                value={specialty}
                onChange={(e) => setSpecialty(e.target.value)}
              >
                {specialtyOptions.map((s) => (
                  <option key={s.code} value={s.code}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="production__field">
              <label>Search</label>
              <input
                type="text"
                placeholder="provider or clinic name"
                value={textSearch}
                onChange={(e) => setTextSearch(e.target.value)}
              />
            </div>
          </div>
        </div>

        <div className="query-group">
          <span className="query-group__label">Status</span>
          <div className="query-group__fields">
            <div className="production__field">
              <label>Availability</label>
              <select value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="free">free</option>
                <option value="busy">busy</option>
                <option value="">(any)</option>
              </select>
            </div>
          </div>
        </div>

        <div className="query-group">
          <span className="query-group__label">When</span>
          <div className="query-group__fields">
            <div className="production__field">
              <label>Date from</label>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
              />
            </div>
            <div className="production__field">
              <label>Date to</label>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
              />
            </div>
          </div>
        </div>
      </div>

      <div className="production__meta">
        {results && queryMs !== null && totalCount !== null && (
          <span>
            <strong>{totalCount.toLocaleString()}</strong> appointment
            {totalCount === 1 ? "" : "s"} available ·{" "}
            <span className="production__meta-light">
              found in {Math.round(queryMs)}ms
            </span>
          </span>
        )}
        {results && results.rowCount === 0 && (
          <span className="production__meta-light">
            No appointments match — try widening the radius or date range.
          </span>
        )}
      </div>

      {error && <div className="widget__error">{error}</div>}

      <div className="production__results">
        {results && results.rowCount > 0 && (
          <SlotList results={results} useGeo={useGeo} />
        )}
      </div>
    </div>
  );
}

function SlotList({ results, useGeo }: { results: QueryResult; useGeo: boolean }) {
  const cols = results.columns;
  const idx = (name: string) => cols.indexOf(name);
  const iStart = idx("start");
  const iProvider = idx("provider");
  const iPrac = idx("practitioner_name");
  const iLoc = idx("location_name");
  const iCity = idx("location_city");
  const iDist = idx("distance_miles");
  const iBook = idx("book_url");
  const iSpecialty = idx("specialty");

  return (
    <ul className="slot-list">
      {results.rows.slice(0, 50).map((row, n) => {
        const startRaw = String(row[iStart] ?? "");
        const d = new Date(startRaw);
        const dateLabel = isNaN(d.getTime())
          ? startRaw
          : d.toLocaleString("en-US", {
              weekday: "short",
              month: "short",
              day: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            });
        return (
          <li key={n} className="slot-card">
            <div className="slot-card__time">{dateLabel}</div>
            <div className="slot-card__body">
              <div className="slot-card__provider">
                <span className="slot-card__specialty">{String(row[iSpecialty] ?? "")}</span>
                <span className="slot-card__prac">{String(row[iPrac] ?? "")}</span>
              </div>
              <div className="slot-card__location">
                {String(row[iLoc] ?? "")} · {String(row[iCity] ?? "")}
              </div>
              <div className="slot-card__meta">
                <span className="slot-card__system">{String(row[iProvider] ?? "")}</span>
                {useGeo && iDist >= 0 && row[iDist] !== null && (
                  <span className="slot-card__distance">
                    {Number(row[iDist]).toFixed(1)} mi away
                  </span>
                )}
              </div>
            </div>
            <a
              className="slot-card__book"
              href={String(row[iBook] ?? "#")}
              target="_blank"
              rel="noreferrer"
            >
              Book →
            </a>
          </li>
        );
      })}
    </ul>
  );
}

function todayPlus(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}
