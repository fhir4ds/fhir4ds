import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";

// S26b slice-1 journey tests (items 9, 10-connected, 1, 2, 3, 8):
// (9) "Workspace switcher moves from the header into File > Workspace"
//     — the header control is GONE; File > Workspace lists workspaces,
//     active one checked, click = switch + reload.
// (10a) "File > Open > Examples lists the bundled workspaces (connected:
//      switches workspace)" — the examples flyout shows demo/cms69/cms125
//      as WORKSPACE switches, not browser fetch-bundles.
// (1) Text editor console has Results ONLY — no Defines tab.
// (2) Measure surface shows Measure Report + Funnel only — no Defines.
// (3) Cells view takes the console's vertical space.
// (8) Builder uses the Form ⇄ / Raw ⇄ switch widget.

const BASE = "http://127.0.0.1:19231";
let dir: string | null = null;
let server: ChildProcess | null = null;

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "ccr-s26b-"));
  await mkdir(join(dir, "Library"), { recursive: true });
  await mkdir(join(dir, "Patient", "q1"), { recursive: true });
  await writeFile(
    join(dir, "Library", "SliceLib.cql"),
    [
      "library SliceLib version '1.0.0'",
      "using FHIR version '4.0.1'",
      "include FHIRHelpers version '4.0.1' called FHIRHelpers",
      "context Patient",
      "",
      'define "Female":',
      "  Patient.gender = 'female'",
      "",
    ].join("\n") + "\n",
    "utf8",
  );
  await writeFile(
    join(dir, "Patient", "q1", "Patient-q1.json"),
    JSON.stringify({ resourceType: "Patient", id: "q1", gender: "female" }),
    "utf8",
  );
  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", dir, "--port", "19231", "--no-open"],
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
    } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("dev server did not become healthy");
});

test.afterAll(async () => {
  if (server?.pid) {
    try {
      process.kill(server.pid);
      await new Promise((r) => setTimeout(r, 300));
    } catch { /* already gone */ }
  }
  if (dir) await rm(dir, { recursive: true, force: true });
});

async function boot(page: import("@playwright/test").Page) {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(18000);
  // Dismiss auto-cellify tips when present.
  const gotIt = page.getByRole("button", { name: "Got it" });
  if (await gotIt.isVisible().catch(() => false)) await gotIt.click();
}

test("S26b-1 (item 9): File > Workspace submenu replaces the header picker", async ({ page }) => {
  await boot(page);
  // The header picker control is GONE.
  await expect(page.locator('[data-testid="workspace-picker"]')).toHaveCount(0);
  // S32: the old Workspace submenu is retired — Open Workspace… opens
  // the server folder picker, Recent Workspaces lists the examples.
  await page.locator('[data-testid="file-menu"]').click();
  await expect(page.locator('[data-testid="file-open-workspace"]')).toBeVisible();
  await page.locator('[data-testid="file-recent"]').hover();
  await expect(
    page.locator('[data-testid="example-workspace-cms125-workspace"]'),
  ).toBeVisible({ timeout: 15000 });
});

test("S26b-2 (item 10a): File > Recent Workspaces lists workspaces as switches (connected)", async ({ page }) => {
  await boot(page);
  await page.locator('[data-testid="file-menu"]').click();
  const exMenu = page.locator('[data-testid="file-recent"]');
  await expect(exMenu).toBeVisible({ timeout: 10000 });
  await exMenu.hover();
  // The three bundled example WORKSPACES are listed.
  await expect(page.locator('[data-testid="example-workspace-cms125-workspace"]')).toBeVisible({ timeout: 15000 });
  await expect(page.locator('[data-testid="example-workspace-cms69-workspace"]')).toBeVisible();
  await expect(page.locator('[data-testid="example-workspace-demo-workspace"]')).toBeVisible();
});

test("S26b-3 (item 1): library console shows Results tab ONLY — no Defines tab", async ({ page }) => {
  await boot(page);
  // Switch to text view if cells opened.
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) === "true") {
    await toggle.click();
    await page.waitForTimeout(1500);
  }
  await expect(page.locator('[data-testid="console-subtabs"]')).toBeVisible({ timeout: 20000 });
  const tabs = page.locator('[data-testid="console-subtabs"] button');
  const labels = await tabs.allTextContents();
  expect(labels.some((l) => l.includes("Results"))).toBeTruthy();
  expect(labels.some((l) => l.trim() === "Defines")).toBeFalsy();
});

test("S26b-4 (item 3): cells view claims the console's vertical space", async ({ page }) => {
  await boot(page);
  // Cells view may have auto-opened; land in TEXT first to prove the
  // console exists there, then flip to cells.
  const toggle = page.locator('[data-testid="cell-view-toggle"]');
  if ((await toggle.getAttribute("aria-checked")) === "true") {
    await toggle.click();
    await page.waitForFunction(
      () =>
        (document
          .querySelector('[data-testid="parse-status"]')
          ?.textContent ?? "").includes("parsed ✓"),
      { timeout: 30000 },
    );
  }
  await expect(page.locator('[data-testid="results-console"]')).toBeVisible({ timeout: 20000 });
  await toggle.click();
  await page.waitForTimeout(1500);
  // Cells view: console hidden, and the editor region extends (no splitter).
  await expect(page.locator('[data-testid="results-console"]')).toBeHidden({ timeout: 10000 });
  await expect(page.locator('[data-testid="editor-splitter"]')).toHaveCount(0);
});
