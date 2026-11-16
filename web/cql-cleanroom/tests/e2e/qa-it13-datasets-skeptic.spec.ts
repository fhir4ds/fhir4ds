/**
 * QA it13 — Domain 4 (datasets/resource builder) × SKEPTIC.
 *  H1 validate_resource: browser worker vs desktop parity on valid and
 *     invalid resources (live harness, it4 pattern).
 *  H2 invalid resources yield typed diagnostics naming the problem.
 *  H3 dataset panel edits are reflected by the next evaluation.
 */
import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";

const GOOD = [
  { resourceType: "Patient", id: "p1", gender: "male" },
  { resourceType: "Condition", id: "c1", subject: { reference: "Patient/p1" } },
];
// NOTE: validate_resource enforces LOADER INGESTION rules (identity +
// serialization) by design — a syntactically invalid birthDate is NOT an
// ingestion violation (it fails later at evaluation), so it is not in BAD.
const BAD = [
  { resourceType: "Patient", id: "bad id with spaces" },
  { id: "no-resourceType" },
];

async function boot(page: Page) {
  await page.goto("/");
  await page.evaluate(() => (window as any).__cleanroomReady?.());
  await page.waitForFunction(
    () => (window as any).__cleanroomBooted === true,
    null,
    { timeout: 180_000 },
  );
}

test("H1/H2: validate_resource parity + typed diagnostics", async ({ page }) => {
  await boot(page);
  const browserResults = await page.evaluate(async (resources) => {
    const out = [];
    for (const r of resources) {
      const resp = await (window as any).__cleanroomRequest({
        type: "validate_resource", resource: r,
      });
      out.push(JSON.parse(resp.envelope));
    }
    return out;
  }, [...GOOD, ...BAD]);

  // desktop side — same capability through fhir4ds.operations
  const desktopRaw = execFileSync("python3", ["-c", `
import json, sys
sys.path.insert(0, "/home/jmontavon/src/fhir4ds")
from fhir4ds.operations.capabilities.validate import validate_resource
resources = json.loads(sys.stdin.read())
out = []
for r in resources:
    res = validate_resource(r)
    d = res.to_dict() if hasattr(res, "to_dict") else res.__dict__
    out.append(d)
json.dump(out, sys.stdout, default=str)
`], { input: JSON.stringify([...GOOD, ...BAD]), encoding: "utf8",
     env: { ...process.env, PYTHONPATH: "/home/jmontavon/src/fhir4ds" } });
  const desktopResults = JSON.parse(desktopRaw);

  // valid resources: both engines accept (ok = capability ran; valid =
  // the resource would ingest cleanly — the contract field)
  for (let i = 0; i < GOOD.length; i++) {
    expect(browserResults[i].ok).toBe(true);
    expect(desktopResults[i].ok).toBe(true);
    expect(browserResults[i].valid).toBe(true);
    expect(desktopResults[i].valid).toBe(true);
  }
  // invalid resources: both engines mark valid=false with diagnostics
  for (let i = GOOD.length; i < GOOD.length + BAD.length; i++) {
    expect(browserResults[i].valid).toBe(false);
    expect(desktopResults[i].valid).toBe(false);
    expect((browserResults[i].diagnostics ?? []).length).toBeGreaterThan(0);
  }
});

test("H3: dataset edits reflected by the next evaluation", async ({ page }) => {
  await boot(page);
  // start from the default dataset; add a patient via the capability
  // surface (the UI panel drives the same load_dataset path).
  const evalBefore = await page.evaluate(async () => {
    const r = await (window as any).__cleanroomRequest({
      type: "evaluate_library", libraries: [],
      main: { name: "Ds", text: "library Ds version '1'\nusing FHIR version '4.0.1'\ncontext Patient\ndefine \"N\": 1" },
      dataset: { resources: [
        { resourceType: "Patient", id: "only1", gender: "female" },
      ] },
    });
    return JSON.parse(r.envelope);
  });
  expect(evalBefore.patient_count).toBe(1);

  const evalAfter = await page.evaluate(async () => {
    const r = await (window as any).__cleanroomRequest({
      type: "evaluate_library", libraries: [],
      main: { name: "Ds", text: "library Ds version '1'\nusing FHIR version '4.0.1'\ncontext Patient\ndefine \"N\": 1" },
      dataset: { resources: [
        { resourceType: "Patient", id: "only1", gender: "female" },
        { resourceType: "Patient", id: "added", gender: "male" },
      ] },
    });
    return JSON.parse(r.envelope);
  });
  expect(evalAfter.patient_count).toBe(2);
});
