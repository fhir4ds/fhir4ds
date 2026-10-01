/**
 * Vitest mirror of the shared attribution-doctrine fixture (F5).
 * Reads the SAME JSON the pytest suite reads:
 * fhir4ds/operations/tests/fixtures/attribution_doctrine_cases.json
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { attributePatient, type DoctrineCase } from "../../src/lib/attribution";

const FIXTURE = resolve(
  __dirname,
  "../../../../fhir4ds/operations/tests/fixtures/attribution_doctrine_cases.json",
);

const payload = JSON.parse(readFileSync(FIXTURE, "utf-8")) as {
  cases: DoctrineCase[];
};

describe("attributePatient mirrors the loader doctrine (shared fixture)", () => {
  it("fixture carries cases with the contracted shape", () => {
    expect(payload.cases.length).toBeGreaterThan(10);
    for (const c of payload.cases) {
      expect(Object.keys(c).sort()).toEqual(["expected", "id", "resource", "why"]);
    }
  });

  for (const c of payload.cases) {
    it(`${c.id}: ${c.why}`, () => {
      expect(attributePatient(c.resource)).toBe(c.expected);
    });
  }
});
