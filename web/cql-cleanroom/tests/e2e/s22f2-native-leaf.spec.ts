import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";

// S22f-promotion downstream pin: the EvidencePopover renders the
// MACRO-SOURCED context-patient leaf (Patient/<id> · birthDate ·
// derived) for an AgeInYearsAt define — the native translator path
// (the explain-seam backfill is retired).

const BASE = "http://127.0.0.1:19210";
let dir: string | null = null;
let server: ChildProcess | null = null;

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "ccr-s22f2-"));
  await mkdir(join(dir, "cql"), { recursive: true });
  await mkdir(join(dir, "data"), { recursive: true });
  await writeFile(
    join(dir, "cql", "AgeLib.cql"),
    [
      "library AgeLib version '1.0.0'",
      "using FHIR version '4.0.1'",
      "include FHIRHelpers version '4.0.1' called FHIRHelpers",
      "context Patient",
      "",
      "// # %% [name: InAgeRange]",
      'define "InAgeRange":',
      "  AgeInYearsAt(@2024-01-01) >= 18",
      "",
    ].join("\n"),
    "utf8",
  );
  await writeFile(
    join(dir, "data", "patients.ndjson"),
    [
      '{"resourceType":"Patient","id":"e1","birthDate":"2000-04-04"}',
      '{"resourceType":"Patient","id":"e2","birthDate":"2020-04-04"}',
    ].join("\n") + "\n",
    "utf8",
  );
  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", dir, "--port", "19210", "--no-open"],
    {
      cwd: "/mnt/d/fhir4ds",
      env: { ...process.env, PYTHONPATH: "/mnt/d/fhir4ds", PATH: process.env.PATH ?? "" },
      stdio: "ignore",
    },
  );
  for (let i = 0; i < 90; i++) {
    try {
      const r = await fetch(`${BASE}/health`);
      if (r.ok) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("dev server did not become healthy");
});

test.afterAll(async () => {
  if (server?.pid) {
    try {
      process.kill(server.pid);
      await new Promise((r) => setTimeout(r, 300));
    } catch {
      /* already gone */
    }
  }
  if (dir) await rm(dir, { recursive: true, force: true });
});

test("S22f2-1: evidence popover shows the macro-sourced birthDate leaf", async ({ page }) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(18000);

  // Open the library, cells view, run the cell.
  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  const libPanel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await libPanel.locator(".nav-item", { hasText: "AgeLib" }).first().click({ timeout: 15000 });
  await expect(page.getByRole("tab", { name: /AgeLib/i })).toBeVisible({ timeout: 30000 });
  await page.waitForTimeout(3000);
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) !== "true") {
    await toggle.click();
    await page.waitForTimeout(1000);
  }
  const card = page.locator('[data-testid="cell-card"]', { hasText: "InAgeRange" }).first();
  await card.locator('[data-testid="cell-run"]').click();
  const table = card.locator('[data-testid="cell-table"]');
  await expect(table).toBeVisible({ timeout: 60000 });

  // Click the TRUE patient row (e1, born 2000) -> the evidence popover
  // shows the MACRO-SOURCED leaf: Patient/e1 · birthDate · derived.
  await table.locator("tbody tr", { hasText: "e1" }).first().click();
  const popover = page.locator('[data-testid="evidence-popover"]');
  await expect(popover).toBeVisible({ timeout: 30000 });
  await expect(popover).toContainText("Patient/e1");
  await expect(popover).toContainText("birthDate");
  await expect(popover).toContainText("2000-04-04");
  await expect(popover).toContainText(/derived/);
  await expect(popover.locator('[data-testid="evidence-popover-error"]')).toHaveCount(0);
});
