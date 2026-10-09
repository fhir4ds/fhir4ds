import { test, expect, Page } from "@playwright/test";
import { spawn, ChildProcess } from "node:child_process";
import { mkdtempSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const WORKTREE = "/mnt/d/fhir4ds-ux5-20261008";
const PORT = 19121;
const BASE = `http://127.0.0.1:${PORT}`;

const CQL = "library NavLib\nusing FHIR version '4.0.1'\ncontext Patient\ndefine \"Initial Population\": exists [Patient]\n";

let server: ChildProcess | undefined;
let page: Page;
let wsDir = "";

test.beforeAll(async () => {
  wsDir = mkdtempSync(join(tmpdir(), "ux5-s7-"));
  mkdirSync(join(wsDir, "cql"));
  writeFileSync(join(wsDir, "cql", "NavLib.cql"), CQL);
  mkdirSync(join(wsDir, "data"));
  writeFileSync(
    join(wsDir, "data", "patients.ndjson"),
    '{"resourceType": "Patient", "id": "p1", "gender": "male"}\n',
  );
});

test.afterAll(async () => {
  rmSync(wsDir, { recursive: true, force: true });
});

test.beforeEach(async ({ browser }) => {
  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", wsDir, "--port", String(PORT), "--no-open"],
    {
      cwd: wsDir,
      env: { PATH: process.env.PATH ?? "", PYTHONPATH: WORKTREE },
      stdio: "ignore",
    },
  );
  for (let i = 0; i < 60; i++) {
    try {
      const r = await fetch(`${BASE}/health`);
      if (r.ok) break;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 500));
    if (i === 59) throw new Error("dev server did not become healthy");
  }
  const ctx = await browser.newContext();
  page = await ctx.newPage();
  await page.goto(BASE);
  await expect(page.locator(".dev-iconrail")).toBeVisible({ timeout: 20000 });
});

test.afterEach(async () => {
  if (server?.pid) {
    server.kill();
    await new Promise((r) => setTimeout(r, 200));
  }
});

test("icon rail: every section opens its slide-out content; Esc closes", async () => {
  // alt+3 opens Libraries; NavLib row visible
  await page.keyboard.press("Alt+3");
  const slide = page.locator(".dev-libraries.dev-slideout");
  await expect(slide).toHaveClass(/open/);
  await expect(slide.locator("h2", { hasText: "Libraries" })).toBeVisible();
  await expect(page.locator('.dev-lib', { hasText: "NavLib" }).filter({ has: page.getByText("NavLib", { exact: true }) })).toBeVisible();
  await expect(slide.locator(".dev-slidesearchinput")).toBeVisible();

  // alt+1 Datasets: data rows + builder entry
  await page.keyboard.press("Alt+1");
  await expect(slide.locator("h2", { hasText: "Data" })).toBeVisible();
  await expect(page.locator(".dev-dataset", { hasText: "patients" })).toBeVisible();
  await expect(slide.locator("text=+ Resource")).toBeVisible();
  // Libraries h2 hidden while Data section active
  await expect(slide.locator("h2", { hasText: "Libraries" })).toHaveCount(0);

  // alt+6 Tests: Measures section (scaffold entries live here)
  await page.keyboard.press("Alt+6");
  await expect(slide.locator("h2", { hasText: "Measures" })).toBeVisible();
  await expect(page.locator(".dev-lib.small", { hasText: "NavLib scaffold" })).toBeVisible();

  // alt+5 Views: ViewDefinitions h2 (empty list still shows header)
  await page.keyboard.press("Alt+5");
  await expect(slide.locator("h2", { hasText: "ViewDefinitions" })).toBeVisible();

  // alt+2 Terminology: ValueSets h2 hidden when none exist — search box + section chip still active
  await page.keyboard.press("Alt+2");
  await expect(page.locator(".dev-iconrail-btn.active", { hasText: "Term" })).toBeVisible();

  // Esc closes
  await page.keyboard.press("Escape");
  await expect(slide).not.toHaveClass(/open/);
  // slide hidden: content rows not visible
  await expect(slide).toBeHidden();

  // alt+4 opens the builder CENTER pane (icon routes to center, not slide-out)
  await page.keyboard.press("Alt+4");
  await expect(page.locator(".dev-rbpane").first()).toBeVisible({ timeout: 10000 });
});

test("search filter narrows section lists; click-outside closes", async () => {
  await page.keyboard.press("Alt+3");
  const slide = page.locator(".dev-libraries.dev-slideout");
  await expect(slide).toHaveClass(/open/);
  // exact-match row (params row "NavLib · parameters" shares .dev-lib)
  const navRow = page.locator(".dev-lib").filter({ has: page.getByText("NavLib", { exact: true }) });
  await expect(navRow).toBeVisible();
  await slide.locator(".dev-slidesearchinput").fill("nomatch");
  await expect(navRow).toHaveCount(0);
  await slide.locator(".dev-slidesearchinput").fill("nav");
  await expect(navRow).toBeVisible();

  // click-outside (center editor) closes
  await page.locator("main").click({ position: { x: 600, y: 300 } });
  await expect(slide).toBeHidden();
});
