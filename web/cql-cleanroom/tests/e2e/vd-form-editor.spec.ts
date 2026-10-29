import { expect, test, type Page } from "@playwright/test";
import { bootDemoReady } from "./bootText";

/**
 * VD FORM EDITOR journey tests — FEATURE_VD_FORM_EDITOR.md §3.3.
 *
 * Journey-test doctrine: every test below is derived from the PLAN'S
 * OWN WORDS, not from implementation mechanics. Each block quotes the
 * promise it pins. Runs on the standalone demo (bootDemoReady), the
 * same harness as measure.spec.ts.
 */

async function boot(page: Page) {
  await bootDemoReady(page);
}

/** Open the Views tab via "+" (creates the derived VD, per measure.spec). */
async function openCustomRawEditor(page: Page) {
  await page.click("[data-testid=nav-toggle-views]");
  await page.click("[data-testid=nav-add-views]");
  await page.waitForSelector("[data-testid=vd-source-toggle]", {
    timeout: 30_000,
  });
  // Level 1 → Custom (Raw presentation by default).
  await page.click("[data-testid=vd-source-custom]");
  await page.waitForSelector("[data-testid=vd-editor]", { timeout: 10_000 });
}

/** §2.1: "Level 1 (Source) [From Measure | Custom] … Level 2 … Form ⇄ Raw" */
test("journey: two-level control — source switch then Form/Raw presentation", async ({ page }) => {
  await boot(page);
  await openCustomRawEditor(page);

  // Level 1: Custom is selected; Level 2 toggle exists (Raw on).
  await expect(
    page.locator("[data-testid=vd-source-custom]"),
  ).toHaveAttribute("aria-selected", "true");
  const presentation = page.locator('[data-testid="vd-presentation-toggle"]');
  await expect(presentation).toBeVisible();
  await expect(presentation).toHaveAttribute("role", "switch");
  await expect(presentation).toContainText("Raw ⇄");

  // A simple tabular VD flips into Form mode.
  await page.fill(
    "[data-testid=vd-editor]",
    JSON.stringify(
      {
        resource: "Patient",
        name: "patients",
        status: "draft",
        select: [
          {
            column: [
              { name: "id", path: "id", type: "string" },
              { name: "gender", path: "gender", type: "code" },
            ],
          },
        ],
      },
      null,
      2,
    ),
  );
  await presentation.click();
  await expect(page.locator("[data-testid=vd-form]")).toBeVisible();
  await expect(page.locator("[data-testid=vd-editor]")).toHaveCount(0);

  // "Raw is always one click away": flip back, seeded from the form.
  await page.locator('[data-testid="vd-presentation-toggle"]').click();
  await expect(page.locator("[data-testid=vd-editor]")).toBeVisible();
  const text = await page.inputValue("[data-testid=vd-editor]");
  const parsed = JSON.parse(text) as {
    resource?: string;
    select?: Array<{ column: Array<{ name?: string }> }>;
  };
  expect(parsed.resource).toBe("Patient");
  expect(parsed.select?.[0]?.column?.length).toBe(2);
});

/** §2.2/§2.4: "name/resource/status + select/column table … the table IS
 *  select[0].column (a 1:1 projection)" */
test("journey: form fields and the column table edit the JSON", async ({ page }) => {
  await boot(page);
  await openCustomRawEditor(page);
  await page.fill(
    "[data-testid=vd-editor]",
    JSON.stringify(
      {
        resource: "Patient",
        select: [{ column: [{ name: "id", path: "id", type: "string" }] }],
      },
      null,
      2,
    ),
  );
  await page.locator('[data-testid="vd-presentation-toggle"]').click();
  await expect(page.locator("[data-testid=vd-form]")).toBeVisible();

  // Edit name → JSON updates (form edits rewrite the text, §2.5).
  await page.fill("[data-testid=vd-form-name]", "patient_view");
  await page.locator('[data-testid="vd-presentation-toggle"]').click();
  let parsed = JSON.parse(
    await page.inputValue("[data-testid=vd-editor]"),
  ) as Record<string, unknown>;
  expect(parsed.name).toBe("patient_view");

  // Add a column row, fill it, reorder it above, and re-enter the form.
  await page.locator('[data-testid="vd-presentation-toggle"]').click();
  await expect(page.locator("[data-testid=vd-form]")).toBeVisible();
  await page.click("[data-testid=vd-form-col-add]");
  await page.fill("[data-testid=vd-form-col-name-1]", "gender");
  await page.fill("[data-testid=vd-form-col-path-1]", "gender");
  await page.selectOption("[data-testid=vd-form-col-type-1]", "code");
  // Reorder arrows rewrite column order (Muse #7).
  await page.click("[data-testid=vd-form-col-up-1]");
  await page.locator('[data-testid="vd-presentation-toggle"]').click();
  const after = JSON.parse(
    await page.inputValue("[data-testid=vd-editor]"),
  ) as { select: Array<{ column: Array<{ name: string }> }> };
  expect(after.select[0].column.map((c) => c.name)).toEqual(["gender", "id"]);
});

/** §2.3: "VD with joins → Form blocked with a named reason" and
 *  "the guarded flip NEVER mutates the text" */
test("journey: joins VD blocks Form entry with a named reason, text intact", async ({ page }) => {
  await boot(page);
  await openCustomRawEditor(page);
  const joinedVd = JSON.stringify(
    {
      resource: "Patient",
      select: [{ column: [{ name: "id", path: "id" }] }],
      joins: [{ name: "enc", resource: "Encounter" }],
    },
    null,
    2,
  );
  await page.fill("[data-testid=vd-editor]", joinedVd);
  await page.locator('[data-testid="vd-presentation-toggle"]').click();

  // BLOCKED: the form never mounts; the error names joins.
  await expect(page.locator("[data-testid=vd-form]")).toHaveCount(0);
  await expect(page.locator("[data-testid=vd-flip-error]")).toContainText(
    /joins/i,
  );
  // "Raw is always available and the guarded flip NEVER mutates the text."
  expect(await page.inputValue("[data-testid=vd-editor]")).toBe(joinedVd);
});

/** §2.2 blocking list: "multi-select ViewDefinitions must be edited in Raw mode" */
test("journey: multi-select VD blocks Form entry", async ({ page }) => {
  await boot(page);
  await openCustomRawEditor(page);
  await page.fill(
    "[data-testid=vd-editor]",
    JSON.stringify(
      {
        resource: "Patient",
        select: [
          { column: [{ name: "a", path: "id" }] },
          { column: [{ name: "b", path: "id" }] },
        ],
      },
      null,
      2,
    ),
  );
  await page.locator('[data-testid="vd-presentation-toggle"]').click();
  await expect(page.locator("[data-testid=vd-form]")).toHaveCount(0);
  await expect(page.locator("[data-testid=vd-flip-error]")).toContainText(
    /multi-select/i,
  );
});

/** §2.3.1: "Columns (evaluated per item in: <expr>)" scope pill for a
 *  forEach VD (which does NOT block) + the preserved pill. */
test("journey: forEach VD enters Form with the scope pill and preserved pill", async ({ page }) => {
  await boot(page);
  await openCustomRawEditor(page);
  await page.fill(
    "[data-testid=vd-editor]",
    JSON.stringify(
      {
        resource: "Patient",
        select: [
          {
            forEach: "contact",
            column: [{ name: "system", path: "system" }],
          },
        ],
        constants: [{ name: "k", valueString: "v" }],
      },
      null,
      2,
    ),
  );
  await page.locator('[data-testid="vd-presentation-toggle"]').click();
  await expect(page.locator("[data-testid=vd-form]")).toBeVisible();
  const pill = page.locator("[data-testid=vd-form-scope-pill]");
  await expect(pill).toBeVisible();
  await expect(pill).toContainText("contact");
  // Calm preserved pill counts the constant.
  await expect(page.locator("[data-testid=vd-form-preserved]")).toContainText(
    /1 constant/i,
  );
});

/** §2.4: "an untouched explicit `"collection": false` in raw survives
 *  round-trip verbatim" */
test("journey: explicit collection:false survives the form round-trip", async ({ page }) => {
  await boot(page);
  await openCustomRawEditor(page);
  await page.fill(
    "[data-testid=vd-editor]",
    JSON.stringify(
      {
        resource: "Patient",
        select: [
          {
            column: [
              { name: "id", path: "id", collection: false },
            ],
          },
        ],
      },
      null,
      2,
    ),
  );
  await page.locator('[data-testid="vd-presentation-toggle"]').click();
  await expect(page.locator("[data-testid=vd-form]")).toBeVisible();
  // Checkbox unchecked (binary), explicit false preserved in state.
  await expect(page.locator("[data-testid=vd-form-col-collection-0]")).not.toBeChecked();
  await page.locator('[data-testid="vd-presentation-toggle"]').click();
  const parsed = JSON.parse(await page.inputValue("[data-testid=vd-editor]")) as {
    select: Array<{ column: Array<{ collection?: boolean }> }>;
  };
  expect(parsed.select[0].column[0].collection).toBe(false);
});

/** §2.4: per-row "extra fields preserved" badge carries description/tag. */
test("journey: columns with description/tag carry them verbatim", async ({ page }) => {
  await boot(page);
  await openCustomRawEditor(page);
  await page.fill(
    "[data-testid=vd-editor]",
    JSON.stringify(
      {
        resource: "Patient",
        select: [
          {
            column: [
              {
                name: "id",
                path: "id",
                description: "the id",
                tag: [{ name: "core", value: "true" }],
              },
            ],
          },
        ],
      },
      null,
      2,
    ),
  );
  await page.locator('[data-testid="vd-presentation-toggle"]').click();
  await expect(page.locator("[data-testid=vd-form]")).toBeVisible();
  await expect(page.locator("[data-testid=vd-form-col-extras-0]")).toContainText(
    /2 preserved/i,
  );
  await page.locator('[data-testid="vd-presentation-toggle"]').click();
  const parsed = JSON.parse(await page.inputValue("[data-testid=vd-editor]")) as {
    select: Array<{ column: Array<{ description?: string }> }>;
  };
  expect(parsed.select[0].column[0].description).toBe("the id");
});

/** §2.6: "entering Custom with an EMPTY draft seeds it from the derived
 *  view … never overwrites existing text" */
test("journey: Copy from Measure seeds an empty custom draft only", async ({ page }) => {
  await boot(page);
  // Open the Views drawer FIRST (the + lives there), create a fresh VD.
  await page.click("[data-testid=nav-toggle-views]");
  await page.click("[data-testid=nav-add-views]");
  await page.waitForSelector("[data-testid=vd-source-toggle]", { timeout: 30_000 });
  await page.click("[data-testid=vd-source-custom]");
  await page.waitForSelector("[data-testid=vd-editor]", { timeout: 10_000 });
  // The seed fired on entering Custom with an empty draft.
  const seeded = await page.inputValue("[data-testid=vd-editor]");
  expect(seeded.trim()).not.toBe("");
  expect(() => JSON.parse(seeded)).not.toThrow();
  // Existing text is never overwritten: fill, leave, come back.
  const mine = '{"resource":"Patient","select":[{"column":[{"name":"id","path":"id"}]}]}';
  await page.fill("[data-testid=vd-editor]", mine);
  await page.click("[data-testid=vd-source-derived]");
  await page.click("[data-testid=vd-source-custom]");
  expect(await page.inputValue("[data-testid=vd-editor]")).toBe(mine);
});
