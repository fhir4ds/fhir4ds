import { spawn, type ChildProcess } from "node:child_process";
import { test, expect } from "@playwright/test";

// S29 design round: persistent footer, Config-grouped nav, library-first
// default section, watcher-driven disk mirror (no refresh button), and the
// Views Form⇄Text switch consistent with Builder/Cells.
const BASE = "http://127.0.0.1:19239";
let server: ChildProcess | null = null;

test.beforeAll(async () => {
  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", "/mnt/d/fhir4ds/examples/cms125-workspace", "--port", "19239", "--no-open"],
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
      /* wait */
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("dev server did not become healthy");
});

test.afterAll(async () => {
  if (server?.pid) {
    try {
      process.kill(server.pid);
    } catch {
      /* gone */
    }
  }
});

async function boot(page: import("@playwright/test").Page) {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(18000);
}

test("S29-1: footer shows location, engine, save state and version", async ({ page }) => {
  await boot(page);
  const bar = page.locator('[data-testid="status-bar"]');
  await expect(bar).toBeVisible();
  // Location: connected -> workspace name + "local files" (not "in memory").
  const loc = page.locator('[data-testid="footer-location"]');
  await expect(loc).toContainText("cms125-workspace");
  await expect(loc).toContainText("local files");
  await expect(loc).not.toContainText("in memory");
  // Engine chip names the server kernel.
  await expect(page.locator('[data-testid="footer-engine"]')).toContainText(/DuckDB/i);
  // Version badge lives in the footer, not the header.
  await expect(page.locator('[data-testid="footer-version"]')).toContainText("0.0.");
  // The old header workspace chip is gone.
  await expect(page.locator('[data-testid="workspace-name"]')).toHaveCount(0);
});

test("S29-2: nav is library-first; Config groups Measure + Parameters", async ({ page }) => {
  await boot(page);
  // Libraries opens by default (primary library is the landing section).
  await expect(page.locator('[data-testid="nav-toggle-libraries"]')).toHaveClass(/active/);
  // Config replaces the old Measures/Parameters sections.
  await expect(page.locator('[data-testid="nav-toggle-config"]')).toBeVisible();
  await expect(page.locator('[data-testid="nav-toggle-measures"]')).toHaveCount(0);
  await expect(page.locator('[data-testid="nav-toggle-parameters"]')).toHaveCount(0);
  // Labels follow the agreed naming.
  await expect(page.locator('[data-testid="nav-toggle-valuesets"]')).toContainText("Value Sets");
  await expect(page.locator('[data-testid="nav-toggle-tests"]')).toContainText("Test Cases");
  await expect(page.locator('[data-testid="nav-toggle-expected"]')).toContainText("Expected");
  // Config panel carries BOTH sub-groups.
  await page.locator('[data-testid="nav-toggle-config"]').click();
  await expect(page.locator('[data-testid="nav-group-measure"]')).toBeVisible();
  await expect(page.locator('[data-testid="nav-group-parameters"]')).toBeVisible();
  // The manual disk-refresh button is gone (the watcher auto-reloads).
  await expect(page.locator('[data-testid="nav-refresh-disk"]')).toHaveCount(0);
});

test("S29-3: Views toggles Form ⇄ Text with the standard switch", async ({ page }) => {
  await boot(page);
  await page.locator('[data-testid="nav-toggle-views"]').click();
  const panel = page.locator('[data-testid="nav-panel"], .nav-panel').first();
  await panel
    .locator(".nav-item", { hasText: "MeasureReportPopulations" })
    .first()
    .click({ timeout: 20000 });
  const viewPane = page.locator('[data-testid="view-pane"]');
  await expect(viewPane).toBeVisible({ timeout: 20000 });
  const mode = page.locator('[data-testid="view-mode"]');
  await expect(mode).toHaveAttribute("role", "switch");
  // A disk-VD click opens the one-shot Custom (text) editor: switch ON.
  await expect(mode).toHaveAttribute("aria-checked", "true");
  await expect(mode).toContainText("Form ⇄");
  await expect(page.locator('[data-testid="vd-editor"]')).toBeVisible();
  // Toggle to the From Measure form: switch OFF, text editor gone.
  await mode.click();
  await expect(mode).toHaveAttribute("aria-checked", "false");
  await expect(mode).toContainText("Text ⇄");
  await expect(page.locator('[data-testid="vd-editor"]')).toHaveCount(0);
  // And back to text.
  await mode.click();
  await expect(mode).toHaveAttribute("aria-checked", "true");
  await expect(page.locator('[data-testid="vd-editor"]')).toBeVisible();
});
