import { expect, test } from "@playwright/test";

/**
 * NLP annotations: the DERIVED RESOURCE TYPE must follow the concept.
 *
 * The extractor reports a `result_type` per concept; the demo maps it to a FHIR
 * resource (Condition / MedicationStatement / Immunization / Procedure /
 * Observation) instead of filing everything as a Condition. The `$extract`
 * response is intercepted here so the assertion does not depend on the live
 * Space being awake, and so the payload can pin the real-world wrinkle that
 * motivated the ATC rule: "influenza vaccine" resolves to ATC J07BB and reports
 * `result_type: "drug_class"`, not `"vaccine"`.
 */

const EXTRACT_URL = /CodeSystem\/\$extract/;

const CONCEPTS = [
  {
    code: "44054006",
    source: "SNOMEDCT_US",
    display: "Diabetes mellitus",
    matched_text: "type 2 diabetes",
    status: "affirmed",
    confidence: 0.93,
    match_grade: "certain",
    ner_label: "disease",
    result_type: "condition",
    span_start: 30,
    span_end: 45,
  },
  {
    code: "6809",
    source: "RXNORM",
    display: "Metformin",
    matched_text: "metformin",
    status: "affirmed",
    confidence: 0.9,
    match_grade: "certain",
    ner_label: "medication",
    result_type: "medication",
    span_start: 60,
    span_end: 69,
  },
  {
    // ATC chapter J07 = vaccines. result_type is drug_class because it
    // describes the ANCHOR, so the mapper has to override it to Immunization.
    code: "J07BB",
    source: "ATC",
    display: "Influenza vaccines",
    matched_text: "influenza vaccine",
    status: "affirmed",
    confidence: 0.8,
    match_grade: "probable",
    ner_label: "medication",
    result_type: "drug_class",
    span_start: 0,
    span_end: 17,
  },
];

function bundle() {
  return {
    resourceType: "Bundle",
    type: "searchset",
    entry: CONCEPTS.map((c) => ({ resource: c })),
  };
}

function derivedStep(page: import("@playwright/test").Page) {
  return page.locator(".adc-step", { hasText: "Derived FHIR resources" });
}

test.describe("NLP annotations: derived resource types", () => {
  test.beforeEach(async ({ page }) => {
    await page.route(EXTRACT_URL, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(bundle()),
      }),
    );
  });

  test("maps each concept to its own resource type", async ({ page }) => {
    await page.goto("/docs/examples/autocoding");
    const step = derivedStep(page);
    await expect(step).toBeVisible({ timeout: 20_000 });

    const tree = step.locator(".adc-tree");
    await expect(tree).toContainText("Condition", { timeout: 20_000 });
    // metformin -> MedicationStatement
    await expect(tree).toContainText("MedicationStatement");
    // influenza vaccine (ATC J07BB, result_type=drug_class) -> Immunization
    await expect(tree).toContainText("Immunization");
    // The coded concept lands on the type's OWN element, not always `code`:
    // MedicationStatement -> medication, Immunization -> vaccineCode, and
    // Immunization references the patient through `patient`.
    await expect(tree).toContainText("medication");
    await expect(tree).toContainText("vaccineCode");
    await expect(tree).toContainText("6809");
    await expect(tree).toContainText('status: "active"');
    await expect(tree).toContainText('status: "completed"');
    await expect(tree).toContainText("patient");
  });

  test("type filter skips excluded types instead of coercing them", async ({ page }) => {
    await page.goto("/docs/examples/autocoding");
    const step = derivedStep(page);
    const tree = step.locator(".adc-tree");
    await expect(tree).toContainText("Immunization", { timeout: 20_000 });

    // Mirror NotesPipelineConfig(resource_types=("Condition",)): switching the
    // others off must REMOVE them, never re-file them as Conditions.
    for (const type of ["MedicationStatement", "Immunization", "Procedure", "Observation"]) {
      await step.getByRole("button", { name: type, exact: true }).click();
    }
    await expect(tree).toContainText("Condition");
    await expect(tree).not.toContainText("Immunization");
    await expect(tree).not.toContainText("MedicationStatement");

    // With every type filtered out there is nothing to derive — and a hint
    // says so rather than leaving a blank panel.
    await step.getByRole("button", { name: "Condition", exact: true }).click();
    await expect(step.locator(".adc-hint")).toContainText(
      "Every resource type is filtered out",
    );
  });
});
