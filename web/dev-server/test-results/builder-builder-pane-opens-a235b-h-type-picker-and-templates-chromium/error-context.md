# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: builder.spec.ts >> builder pane opens from rail with type picker and templates
- Location: tests/e2e/builder.spec.ts:78:1

# Error details

```
Error: server never became healthy
```

# Test source

```ts
  1   | import { test, expect } from "@playwright/test";
  2   | import { spawn, type ChildProcess } from "node:child_process";
  3   | import { mkdtempSync, writeFileSync, mkdirSync, readFileSync } from "node:fs";
  4   | import { tmpdir } from "node:os";
  5   | import { join, dirname } from "node:path";
  6   | import { fileURLToPath } from "node:url";
  7   | 
  8   | const __dirname = dirname(fileURLToPath(import.meta.url));
  9   | const PORT = 19001;
  10  | const BASE = `http://127.0.0.1:${PORT}`;
  11  | 
  12  | let server: ChildProcess | null = null;
  13  | let dir: string | null = null;
  14  | 
  15  | test.beforeAll(async () => {
  16  |   dir = mkdtempSync(join(tmpdir(), "v41-builder-"));
  17  |   mkdirSync(join(dir, "cql"));
  18  |   mkdirSync(join(dir, "valuesets"));
  19  |   mkdirSync(join(dir, "data"));
  20  |   writeFileSync(
  21  |     join(dir, "cql", "Demographics.cql"),
  22  |     [
  23  |       "library Demographics version '1.0.0'",
  24  |       "using FHIR version '4.0.1'",
  25  |       "",
  26  |       "valueset \"BPVS\": 'http://example.com/bp'",
  27  |       "context Patient",
  28  |       "",
  29  |       "// # %% [name: IsMale]",
  30  |       "define IsMale: Patient.gender = 'male'",
  31  |       "",
  32  |     ].join("\n"),
  33  |   );
  34  |   writeFileSync(
  35  |     join(dir, "valuesets", "vs1.json"),
  36  |     JSON.stringify({
  37  |       resourceType: "ValueSet",
  38  |       id: "vs1",
  39  |       url: "http://example.com/bp",
  40  |       compose: { include: [{ system: "http://loinc.org", concept: [{ code: "8480-6", display: "BP" }] }] },
  41  |     }),
  42  |   );
  43  |   writeFileSync(
  44  |     join(dir, "data", "patients.ndjson"),
  45  |     [
  46  |       JSON.stringify({ resourceType: "Patient", id: "p1", gender: "male", birthDate: "1974-12-25" }),
  47  |       JSON.stringify({ resourceType: "Patient", id: "p2", gender: "female", birthDate: "1990-01-01" }),
  48  |     ].join("\n") + "\n",
  49  |   );
  50  | 
  51  |   server = spawn(
  52  |     "/usr/bin/python3",
  53  |     ["-m", "fhir4ds.cli", "dev", dir, "--port", String(PORT), "--no-open"],
  54  |     { cwd: dir, env: { PYTHONPATH: "/mnt/d/fhir4ds-devserver-rbux-20261007", PATH: process.env.PATH ?? "" }, stdio: "ignore" },
  55  |   );
  56  |   for (let i = 0; i < 120; i++) {
  57  |     try {
  58  |       const r = await fetch(`${BASE}/health`);
  59  |       if (r.ok) return;
  60  |     } catch {}
  61  |     await new Promise((res) => setTimeout(res, 500));
  62  |   }
> 63  |   throw new Error("server never became healthy");
      |         ^ Error: server never became healthy
  64  | });
  65  | 
  66  | test.afterAll(async () => {
  67  |   if (server?.pid) {
  68  |     try {
  69  |       process.kill(server.pid, "SIGKILL");
  70  |     } catch {
  71  |       /* already gone */
  72  |     }
  73  |     await new Promise((res) => setTimeout(res, 300));
  74  |   }
  75  |   server = null;
  76  | });
  77  | 
  78  | test("builder pane opens from rail with type picker and templates", async ({ page }) => {
  79  |   await page.goto(BASE);
  80  |   await page.locator(".dev-lib.small", { hasText: "+ Resource" }).click();
  81  |   await expect(page.locator(".dev-rbpane")).toBeVisible();
  82  |   await expect(page.locator(".dev-rbtemplates")).toBeVisible();
  83  |   await expect(page.locator(".dev-rbtpl", { hasText: "Observation" })).toHaveCount(1);
  84  | });
  85  | 
  86  | test("template loads, form renders, validate passes, save appends ndjson", async ({ page }) => {
  87  |   await page.goto(BASE);
  88  |   await page.locator(".dev-lib.small", { hasText: "+ Resource" }).click();
  89  |   await page.locator(".dev-rbtpl", { hasText: "Patient" }).click();
  90  |   await expect(page.locator(".dev-rbform")).toBeVisible();
  91  |   await expect(page.locator(".dev-rbrow").first()).toBeVisible();
  92  | 
  93  |   // JSON writer: set a fresh id via the textarea
  94  |   const area = page.locator(".dev-rbjsonarea");
  95  |   await area.click();
  96  |   await page.keyboard.press("Control+A");
  97  |   await page.keyboard.type(
  98  |     JSON.stringify({ resourceType: "Patient", id: "p9", gender: "male", birthDate: "1980-05-05" }, null, 2),
  99  |   );
  100 |   await page.locator(".dev-rbvalidate").click();
  101 |   await expect(page.locator(".dev-rbok", { hasText: "valid" })).toBeVisible();
  102 | 
  103 |   await page.locator(".dev-rbdataset").selectOption({ index: 0 });
  104 |   await page.locator(".dev-rbsavebtn").click();
  105 |   await expect(page.locator(".dev-rbsavemsg")).toContainText("Saved to", { timeout: 15000 });
  106 |   await expect(page.locator(".dev-rbsavemsg")).toContainText("restart the kernel");
  107 | 
  108 |   // file-side pin (API test also pins this, cheap to double-check)
  109 |   const text = readFileSync(join(dir!, "data", "patients.ndjson"), "utf8");
  110 |   expect(text.trim().split("\n").length).toBe(3);
  111 |   expect(text).toContain('"id": "p9"');
  112 | });
  113 | 
  114 | test("invalid resource blocks save with inline red", async ({ page }) => {
  115 |   await page.goto(BASE);
  116 |   await page.locator(".dev-lib.small", { hasText: "+ Resource" }).click();
  117 |   await page.locator(".dev-rbtpl", { hasText: "Patient" }).click();
  118 | 
  119 |   const area = page.locator(".dev-rbjsonarea");
  120 |   await area.click();
  121 |   await page.keyboard.press("Control+A");
  122 |   await page.keyboard.type(JSON.stringify({ resourceType: "Patient", id: "" }, null, 2));
  123 |   await page.locator(".dev-rbvalidate").click();
  124 |   await expect(page.locator(".dev-rberror").first()).toBeVisible({ timeout: 15000 });
  125 |   await expect(page.locator(".dev-rbsavebtn")).toBeDisabled();
  126 | });
  127 | 
  128 | test("dataset click opens the dataset pane with stats (no crash)", async ({ page }) => {
  129 |   await page.goto(BASE);
  130 |   await expect(page.locator(".dev-dataset").first()).toBeVisible();
  131 |   await page.locator(".dev-dataset").first().click();
  132 |   const pane = page.locator(".dev-dspane");
  133 |   await expect(pane).toBeVisible();
  134 |   await expect(pane.locator(".dev-dstotal")).toContainText("total: 2", { timeout: 20000 });
  135 |   await expect(pane.locator(".dev-dschipstat").first()).toContainText("Patient");
  136 | });
  137 | 
  138 | test("Build section gone; '+ Resource' lives under Data; add-element adds second telecom", async ({ page }) => {
  139 |   await page.goto(BASE);
  140 |   // The standalone Build rail section is GONE (exact-text h2).
  141 |   await expect(page.locator("h2", { hasText: /^Build$/ })).toHaveCount(0);
  142 |   // '+ Resource' opens the builder from the Data section.
  143 |   await page.locator(".dev-lib.small", { hasText: "+ Resource" }).click();
  144 |   await expect(page.locator(".dev-rbpane")).toBeVisible();
  145 |   // Load the Patient template (no telecom seeded).
  146 |   await page.locator(".dev-rbtpl", { hasText: "Patient" }).click();
  147 |   // Add-element picker: add a telecom (repeatable) via the root picker.
  148 |   // (Wait for the schema-tree fetch to populate the picker options first.)
  149 |   const pane = page.locator(".dev-rbpane");
  150 |   await expect(pane.locator(".dev-rbaddsel option", { hasText: "telecom" })).toHaveCount(1, { timeout: 20000 });
  151 |   await pane.locator(".dev-rbaddsel").selectOption("telecom");
  152 |   // Scope to the addrbar add button — .dev-rbaddbtn is shared with per-row '+' affordances.
  153 |   await pane.locator(".dev-rbaddrbar .dev-rbaddbtn").click();
  154 |   // The JSON writer now holds a telecom array (was absent; the picker added it).
  155 |   // Poll the textarea value — the click → setResource → setJsonText re-render is async.
  156 |   await expect(pane.locator(".dev-rbjsonarea")).toHaveValue(/telecom/, { timeout: 5000 });
  157 |   const jsonVal = await pane.locator(".dev-rbjsonarea").inputValue();
  158 |   const parsed = JSON.parse(jsonVal);
  159 |   if (!Array.isArray(parsed.telecom) || parsed.telecom.length < 1) {
  160 |     throw new Error(`expected a telecom array from the add-element picker, got ${JSON.stringify(parsed.telecom)}`);
  161 |   }
  162 | });
  163 | 
```