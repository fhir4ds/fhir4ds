/**
 * Dev-server UI smoke (Playwright, chromium).
 *
 * Boots the real Python dev server (`fhir4ds dev`) on a scratch workspace
 * and asserts the three UX-polish surfaces: visible editor text, cell
 chips in the rail, and run producing visible inline output.
 */
import { test, expect } from "@playwright/test";
import { spawn, ChildProcess } from "child_process";
import path from "path";
import fs from "fs";
import os from "os";

const PORT = 18901;
const BASE = `http://127.0.0.1:${PORT}`;

let server: ChildProcess | null = null;
let workdir: string | null = null;

test.beforeAll(async () => {
  workdir = fs.mkdtempSync(path.join(os.tmpdir(), "ds-e2e-"));
  fs.mkdirSync(path.join(workdir, "cql"), { recursive: true });
  fs.mkdirSync(path.join(workdir, "data"), { recursive: true });
  fs.writeFileSync(
    path.join(workdir, "cql", "Demographics.cql"),
    [
      "library Demographics version '1.0.0'",
      "using FHIR version '4.0.1'",
      "context Patient",
      "",
      "// # %% [name: IsMale]",
      "define IsMale: Patient.gender = 'male'",
      "",
      "// # %%",
      "define BirthYear: Patient.birthDate.substring(0, 4)",
      "",
    ].join("\n"),
  );
  const patients = ["p1", "p2", "p3", "p4", "p5", "p6"].map((id, i) =>
    JSON.stringify({
      resourceType: "Patient",
      id,
      gender: i % 2 === 0 ? "male" : "female",
      birthDate: i % 2 === 0 ? "1974-12-25" : "1990-01-01",
    }),
  );
  fs.writeFileSync(path.join(workdir, "data", "patients.ndjson"), patients.join("\n"));
  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", workdir, "--port", String(PORT), "--no-open"],
    { env: { PATH: process.env.PATH, PYTHONPATH: "/mnt/d/fhir4ds" }, stdio: "ignore" },
  );
  // Wait for /health.
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${BASE}/health`);
      if (res.ok) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error("dev server did not become healthy");
});

test.afterAll(() => {
  server?.kill();
  if (workdir) fs.rmSync(workdir, { recursive: true, force: true });
});

test("editor shows library text with visible cells", async ({ page }) => {
  await page.goto(BASE);
  await expect(page.locator(".dev-lib.selected")).toHaveText(
    "Demographics",
    { timeout: 30_000 },
  );
  // Editor content is rendered by Monaco (token spans split words, so
  // assert on the container's full text rather than a phrase locator).
  await expect
    .poll(async () => {
      const t = await page.locator(".view-lines").allTextContents();
      const joined = t.join(" ");
      return joined.includes("define") && joined.includes("IsMale");
    }, { timeout: 30_000 })
    .toBe(true);
  // ux2: the hint bar was replaced by the empty-Results guide.
  await expect(page.locator(".dev-guide h3")).toHaveText("Getting started");
});

test("cell chip exists and run produces visible output", async ({ page }) => {
  await page.goto(BASE);
  await expect(page.locator(".dev-box-title").nth(1)).toHaveText("IsMale", {
    timeout: 30_000,
  });
  await expect(page.locator(".dev-boxbar .dev-cellrun")).toHaveCount(2);
  const chip = page.locator(".dev-chip").first();
  await expect(chip).toBeVisible();
  // Run the cell via the rail button (mode defaults to strict cell).
  await page.locator(".dev-cellrun").first().click();
  // Inline result rows appear beneath the cell row in the rail.
  await expect(page.locator(".dev-cellresult-row").first()).toBeVisible({
    timeout: 60_000,
  });
  // The chip flips to ok after the run completes.
  await expect(page.locator(".dev-chip.ok").first()).toBeVisible({ timeout: 60_000 });
});

test("ux2: right Results pane populates on cell run", async ({ page }) => {
  await page.goto(BASE);
  await expect(page.locator(".dev-box-title").nth(1)).toHaveText("IsMale", {
    timeout: 30_000,
  });
  await page.locator(".dev-cellrun").first().click();
  await expect(page.locator(".dev-resultheader")).toContainText(/IsMale - 6 rows/, {
    timeout: 60_000,
  });
  // Results tab auto-switched and the table is visible.
  await expect(page.locator(".dev-pane table").first()).toBeVisible();
});

test("ux2: toolbar says Run all and empty-state guide shows pre-run", async ({ page }) => {
  await page.goto(BASE);
  await expect(page.getByRole("button", { name: /Run all/ })).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.locator(".dev-guide h3")).toHaveText("Getting started");
  // The jargon hint bar is gone.
  await expect(page.locator(".dev-hintbar")).toHaveCount(0);
});

test("ux2: string tokens are not red", async ({ page }) => {
  await page.goto(BASE);
  await expect(page.locator(".dev-box-title").nth(1)).toHaveText("IsMale", {
    timeout: 30_000,
  });
  const color = await page.evaluate(() => {
    const spans = [...document.querySelectorAll(".view-lines span")];
    const hit = spans.find((s) => s.textContent?.includes("male"));
    return hit ? getComputedStyle(hit).color : "span-not-found";
  });
  expect(color).not.toBe("rgb(255, 0, 0)");
});

test("ux2: inline cell table has patient column", async ({ page }) => {
  await page.goto(BASE);
  await expect(page.locator(".dev-box-title").nth(1)).toHaveText("IsMale", {
    timeout: 30_000,
  });
  await page.locator(".dev-cellrun").first().click();
  await expect(page.locator(".dev-celltable-row").first()).toBeVisible({
    timeout: 60_000,
  });
  await expect(page.locator(".dev-celltable-head")).toContainText("patient");
  await expect(
    page.locator(".dev-celltable-body .dev-cellresult-row").first(),
  ).toContainText("p1");
});

test("marker comments are hidden inside box editors", async ({ page }) => {
  await page.goto(BASE);
  await expect(page.locator(".dev-box-title").nth(1)).toHaveText("IsMale", {
    timeout: 30_000,
  });
  // The marker line must NEVER render inside a box editor body —
  // regression pin for the span-offset fix (leading-newline convention).
  const editors = page.locator(".dev-box-editor .view-lines");
  const n = await editors.count();
  for (let i = 0; i < n; i++) {
    const t = (await editors.nth(i).textContent()) ?? "";
    if (t.includes("#")) {
      throw new Error(`marker leaked into box editor ${i}: ${t.slice(0, 80)}`);
    }
  }
});
