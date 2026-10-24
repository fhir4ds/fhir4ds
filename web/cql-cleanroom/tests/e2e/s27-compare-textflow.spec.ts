import { spawn, type ChildProcess } from "node:child_process";
import { test, expect } from "@playwright/test";

// S27-2: reproduce Joel's flow — open the CMS125 TEXT editor first (the
// heartbeat runs there), THEN switch to Expected Results > Compare.
// Symptom under investigation: `exp true · got —` on every cell even
// though the fresh-boot journey (S27-1) reads 264/264.

const BASE = "http://127.0.0.1:19234";
let server: ChildProcess | null = null;

test.beforeAll(async () => {
  server = spawn(
    "/usr/bin/python3",
    [
      "-m",
      "fhir4ds.cli",
      "dev",
      "/mnt/d/fhir4ds/examples/cms125-workspace",
      "--port",
      "19234",
      "--no-open",
    ],
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
});

test("S27-2: text-editor flow then compare still resolves populations", async ({
  page,
}) => {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(18000);
  // Open the CMS125 primary library in the TEXT editor (heartbeat target).
  await page.locator('[data-testid="nav-toggle-libraries"]').click();
  const libPanel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await libPanel
    .locator(".nav-item", { hasText: "CMS125FHIRBreastCancerScreening" })
    .first()
    .click({ timeout: 30000 });
  await page.waitForTimeout(12000); // heartbeat debounce + server eval
  // Now the Expected Results surface > Compare.
  await page.locator('[data-testid="nav-toggle-expected"]').click();
  const panel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await panel.locator(".nav-item", { hasText: "CMS125" }).first().click({ timeout: 30000 });
  await page.locator('[data-testid="console-tab-compare"]').click({ timeout: 30000 });
  const chip = page.locator('[data-testid="tests-summary"]');
  await expect(chip).toContainText("264/264 passed", { timeout: 90000 });
});
