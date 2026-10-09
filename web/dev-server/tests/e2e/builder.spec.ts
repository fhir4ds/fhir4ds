import { test, expect } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { mkdtempSync, writeFileSync, mkdirSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PORT = 19001;
const BASE = `http://127.0.0.1:${PORT}`;

let server: ChildProcess | null = null;
let dir: string | null = null;

test.beforeAll(async () => {
  dir = mkdtempSync(join(tmpdir(), "v41-builder-"));
  mkdirSync(join(dir, "cql"));
  mkdirSync(join(dir, "valuesets"));
  mkdirSync(join(dir, "data"));
  writeFileSync(
    join(dir, "cql", "Demographics.cql"),
    [
      "library Demographics version '1.0.0'",
      "using FHIR version '4.0.1'",
      "",
      "valueset \"BPVS\": 'http://example.com/bp'",
      "context Patient",
      "",
      "// # %% [name: IsMale]",
      "define IsMale: Patient.gender = 'male'",
      "",
    ].join("\n"),
  );
  writeFileSync(
    join(dir, "valuesets", "vs1.json"),
    JSON.stringify({
      resourceType: "ValueSet",
      id: "vs1",
      url: "http://example.com/bp",
      compose: { include: [{ system: "http://loinc.org", concept: [{ code: "8480-6", display: "BP" }] }] },
    }),
  );
  writeFileSync(
    join(dir, "data", "patients.ndjson"),
    [
      JSON.stringify({ resourceType: "Patient", id: "p1", gender: "male", birthDate: "1974-12-25" }),
      JSON.stringify({ resourceType: "Patient", id: "p2", gender: "female", birthDate: "1990-01-01" }),
    ].join("\n") + "\n",
  );

  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", dir, "--port", String(PORT), "--no-open"],
    { cwd: dir, env: { PYTHONPATH: "/mnt/d/fhir4ds-umls-20261008", PATH: process.env.PATH ?? "" }, stdio: "ignore" },
  );
  for (let i = 0; i < 120; i++) {
    try {
      const r = await fetch(`${BASE}/health`);
      if (r.ok) return;
    } catch {}
    await new Promise((res) => setTimeout(res, 500));
  }
  throw new Error("server never became healthy");
});

test.afterAll(async () => {
  if (server?.pid) {
    try {
      process.kill(server.pid, "SIGKILL");
    } catch {
      /* already gone */
    }
    await new Promise((res) => setTimeout(res, 300));
  }
  server = null;
});

test("builder pane opens from rail with type picker and templates", async ({ page }) => {
  await page.goto(BASE);
  await page.locator(".dev-lib.small", { hasText: "+ Resource" }).click();
  await expect(page.locator(".dev-rbpane")).toBeVisible();
  await expect(page.locator(".dev-rbtemplates")).toBeVisible();
  await expect(page.locator(".dev-rbtpl", { hasText: "Observation" })).toHaveCount(1);
});

test("template loads, form renders, validate passes, save appends ndjson", async ({ page }) => {
  await page.goto(BASE);
  await page.locator(".dev-lib.small", { hasText: "+ Resource" }).click();
  await page.locator(".dev-rbtpl", { hasText: "Patient" }).click();
  await expect(page.locator(".dev-rbform")).toBeVisible();
  await expect(page.locator(".dev-rbrow").first()).toBeVisible();

  // JSON writer: set a fresh id via the textarea
  const area = page.locator(".dev-rbjsonarea");
  await area.click();
  await page.keyboard.press("Control+A");
  await page.keyboard.type(
    JSON.stringify({ resourceType: "Patient", id: "p9", gender: "male", birthDate: "1980-05-05" }, null, 2),
  );
  await page.locator(".dev-rbvalidate").click();
  await expect(page.locator(".dev-rbok", { hasText: "valid" })).toBeVisible();

  await page.locator(".dev-rbdataset").selectOption({ index: 0 });
  await page.locator(".dev-rbsavebtn").click();
  await expect(page.locator(".dev-rbsavemsg")).toContainText("Saved to", { timeout: 15000 });
  await expect(page.locator(".dev-rbsavemsg")).toContainText("restart the kernel");

  // file-side pin (API test also pins this, cheap to double-check)
  const text = readFileSync(join(dir!, "data", "patients.ndjson"), "utf8");
  expect(text.trim().split("\n").length).toBe(3);
  expect(text).toContain('"id": "p9"');
});

test("invalid resource blocks save with inline red", async ({ page }) => {
  await page.goto(BASE);
  await page.locator(".dev-lib.small", { hasText: "+ Resource" }).click();
  await page.locator(".dev-rbtpl", { hasText: "Patient" }).click();

  const area = page.locator(".dev-rbjsonarea");
  await area.click();
  await page.keyboard.press("Control+A");
  await page.keyboard.type(JSON.stringify({ resourceType: "Patient", id: "" }, null, 2));
  await page.locator(".dev-rbvalidate").click();
  await expect(page.locator(".dev-rberror").first()).toBeVisible({ timeout: 15000 });
  await expect(page.locator(".dev-rbsavebtn")).toBeDisabled();
});

test("dataset click opens the dataset pane with stats (no crash)", async ({ page }) => {
  await page.goto(BASE);
  await expect(page.locator(".dev-dataset").first()).toBeVisible();
  await page.locator(".dev-dataset").first().click();
  const pane = page.locator(".dev-dspane");
  await expect(pane).toBeVisible();
  await expect(pane.locator(".dev-dstotal")).toContainText("total: 2", { timeout: 20000 });
  await expect(pane.locator(".dev-dschipstat").first()).toContainText("Patient");
});

test("Build section gone; '+ Resource' lives under Data; add-element adds second telecom", async ({ page }) => {
  await page.goto(BASE);
  // The standalone Build rail section is GONE (exact-text h2).
  await expect(page.locator("h2", { hasText: /^Build$/ })).toHaveCount(0);
  // '+ Resource' opens the builder from the Data section.
  await page.locator(".dev-lib.small", { hasText: "+ Resource" }).click();
  await expect(page.locator(".dev-rbpane")).toBeVisible();
  // Load the Patient template (no telecom seeded).
  await page.locator(".dev-rbtpl", { hasText: "Patient" }).click();
  // Add-element picker: add a telecom (repeatable) via the root picker.
  // (Wait for the schema-tree fetch to populate the picker options first.)
  const pane = page.locator(".dev-rbpane");
  await expect(pane.locator(".dev-rbaddsel option", { hasText: "telecom" })).toHaveCount(1, { timeout: 20000 });
  await pane.locator(".dev-rbaddsel").selectOption("telecom");
  // Scope to the addrbar add button — .dev-rbaddbtn is shared with per-row '+' affordances.
  await pane.locator(".dev-rbaddrbar .dev-rbaddbtn").click();
  // The JSON writer now holds a telecom array (was absent; the picker added it).
  // Poll the textarea value — the click → setResource → setJsonText re-render is async.
  await expect(pane.locator(".dev-rbjsonarea")).toHaveValue(/telecom/, { timeout: 5000 });
  const jsonVal = await pane.locator(".dev-rbjsonarea").inputValue();
  const parsed = JSON.parse(jsonVal);
  if (!Array.isArray(parsed.telecom) || parsed.telecom.length < 1) {
    throw new Error(`expected a telecom array from the add-element picker, got ${JSON.stringify(parsed.telecom)}`);
  }
});

test("rbux2: typed widgets — date picker, choice dropdown, repeatable rows", async ({ page }) => {
  await page.goto(BASE);
  await page.locator(".dev-lib.small", { hasText: "+ Resource" }).click();
  await expect(page.locator(".dev-rbpane")).toBeVisible();
  await page.locator(".dev-rbtpl", { hasText: "Patient" }).click();
  const pane = page.locator(".dev-rbpane");

  // 1. Date widget: Patient.birthDate renders a native date input seeded from the template.
  const dateInput = pane.locator(".dev-rbdate");
  await expect(dateInput).toHaveCount(1, { timeout: 10000 });
  await expect(dateInput).toHaveValue("1974-12-25");

  // 2. Choice dropdown: deceased[x] choice group offers the boolean arm; selecting writes JSON.
  //    Scope by page-level :has filter (nested pane-scope locators inside `has:` don't match);
  //    multiple choice groups render sibling selects.
  const deceasedSel = page
    .locator(".dev-rbchoicesel")
    .filter({ has: page.locator("option[value=deceasedBoolean]") });
  await expect(deceasedSel).toHaveCount(1, { timeout: 10000 });
  await expect(deceasedSel.locator("option", { hasText: "deceased (boolean)" })).toHaveCount(1);
  await deceasedSel.selectOption("deceasedBoolean");
  await expect(pane.locator(".dev-rbjsonarea")).toHaveValue(/deceasedBoolean/, { timeout: 5000 });

  // 3. Nested structured groups: name renders as a HumanName group with
  // family + given typed rows (Coding-style children, not raw JSON).
  const nameGroup = pane.locator(".dev-rbgroupitem", { hasText: "name" }).first();
  await expect(nameGroup).toBeVisible({ timeout: 10000 });
  await expect(nameGroup.locator(".dev-rbrow").first()).toBeVisible();
  // Observation-style check via template: code renders Coding children.
  await page.locator(".dev-rbtpl", { hasText: "Observation" }).click();
  const codeGroup = pane.locator(".dev-rbgroupitem", { hasText: "code" }).first();
  await expect(codeGroup.locator(".dev-rbgroup").first()).toBeVisible({ timeout: 10000 });
});

test("rbux2 gate: form mirrors JSON coding values; arm-switch hides inactive arms", async ({ page }) => {
  await page.goto(BASE);
  await page.locator(".dev-lib.small", { hasText: "+ Resource" }).click();
  const pane = page.locator(".dev-rbpane");
  await page.locator(".dev-rbtpl", { hasText: "Observation" }).click();

  // P0: the JSON carries code.coding[0] {system, code, display}; the form's
  // coding rows must MIRROR those values (JSON-is-authoritative).
  await expect(pane.locator(".dev-rbjsonarea")).toHaveValue(/8480-6/, { timeout: 10000 });
  const codingInputs = pane.locator(".dev-rbgroup .dev-rbrow input.dev-rbinput");
  await expect(codingInputs.first()).toBeVisible({ timeout: 10000 });
  const values: string[] = [];
  const count = await codingInputs.count();
  for (let i = 0; i < count; i++) values.push(await codingInputs.nth(i).inputValue());
  const joined = values.join("|");
  if (!joined.includes("http://loinc.org") || !joined.includes("8480-6") || !joined.includes("BP")) {
    throw new Error(`coding rows do not mirror JSON values: ${joined}`);
  }

  // P1: switch the value[x] arm — the JSON must carry ONLY the new arm and
  // the old arm's rows must not linger (choice arms render only via the
  // choice dropdown, never duplicated in the structured tree).
  const valueSel = page
    .locator(".dev-rbchoicesel")
    .filter({ has: page.locator("option[value=valueBoolean]") });
  await expect(valueSel).toHaveCount(1, { timeout: 10000 });
  await valueSel.selectOption("valueBoolean");
  await expect(pane.locator(".dev-rbjsonarea")).toHaveValue(/valueBoolean/, { timeout: 5000 });
  await expect(pane.locator(".dev-rbjsonarea")).not.toHaveValue(/valueQuantity/);
});

test("rbux3 parity: Quantity choice arm renders typed inputs; + coding shows inputs", async ({ page }) => {
  await page.goto(BASE);
  await page.locator(".dev-lib.small", { hasText: "+ Resource" }).click();
  await expect(page.locator(".dev-rbpane")).toBeVisible();
  await page.locator(".dev-rbtpl", { hasText: "Observation" }).click();
  const pane = page.locator(".dev-rbpane");

  // DEFECT 1 pin: valueQuantity renders the triple-input widget, seeded from JSON.
  const qtyVal = pane.locator(".dev-rbqtyval");
  await expect(qtyVal).toHaveCount(1, { timeout: 10000 });
  await expect(qtyVal).toHaveValue("120");
  const qtyUnit = pane.locator(".dev-rbqtyunit").first();
  await expect(qtyUnit).toHaveValue("mmHg");

  // DEFECT 2 pin: '+' on the code group adds a second coding WITH inputs.
  // (PAGE-scope has: filter — nested pane-scope never matches.)
  const codeGroup = page.locator(".dev-rbgroupitem").filter({
    has: page.locator(".dev-rbgrouplabel", { hasText: /^code\s/ }),
  }).first();
  await codeGroup.locator(".dev-rbgrouplabel .dev-rbaddbtn").click();
  // The JSON textarea is pretty-printed — parse and assert array growth instead of a compact regex.
  await expect
    .poll(async () => {
      const v = await pane.locator(".dev-rbjsonarea").inputValue();
      try {
        return JSON.parse(v).code.coding.length;
      } catch {
        return -1;
      }
    }, { timeout: 5000 })
    .toBe(2);
  const newSys = codeGroup.locator(".dev-rbrow", { hasText: "coding#1.system" }).locator("input.dev-rbinput");
  await expect(newSys).toHaveCount(1, { timeout: 5000 });
  const newCode = codeGroup.locator(".dev-rbrow", { hasText: "coding#1.code" }).locator("input.dev-rbinput");
  await expect(newCode).toHaveCount(1);

  // Type into the new coding element — the widget must write JSON.
  await newSys.fill("http://snomed.info/sct");
  await newCode.fill("123456");
  await expect(pane.locator(".dev-rbjsonarea")).toHaveValue(/123456/, { timeout: 5000 });
  await expect(pane.locator(".dev-rbjsonarea")).toHaveValue(/snomed/, { timeout: 5000 });
});
