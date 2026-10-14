import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";

// c-wasm-bolton S3: cell-based editing. Connected (--ui wasm server):
// cell mode toggles on, markers split cells with named chips, per-cell
// runs execute server-side (evaluate per define), RunMode control present,
// dep-closure info on chips. Standalone covered by playground regression.

const BASE = "http://127.0.0.1:19063";
let dir: string | null = null;
let server: ChildProcess | null = null;

const CELL_LIB = [
  "library CellLib version '1.0.0'",
  "using FHIR version '4.0.1'",
  "context Patient",
  "",
  "// # %% [name: IsMale]",
  "define IsMale: Patient.gender = 'male'",
  "",
  "// # %% [name: UsesIt]",
  "define UsesIt: exists({ IsMale })",
  "",
].join("\n");

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "bolton-s3-"));
  await mkdir(join(dir, "cql"), { recursive: true });
  await mkdir(join(dir, "data"), { recursive: true });
  await writeFile(join(dir, "cql", "CellLib.cql"), CELL_LIB);
  await writeFile(
    join(dir, "data", "p.ndjson"),
    JSON.stringify({ resourceType: "Patient", id: "p1", gender: "male" }) + "\n" +
    JSON.stringify({ resourceType: "Patient", id: "p2", gender: "female" }) + "\n",
  );

  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", dir, "--port", "19063", "--ui", "wasm", "--no-open"],
    {
      cwd: dir,
      env: {
        ...process.env,
        PYTHONPATH: "/mnt/d/fhir4ds-wasm-bolton",
        PATH: process.env.PATH ?? "",
      },
      stdio: "ignore",
    },
  );
  for (let i = 0; i < 60; i++) {
    try {
      const r = await fetch(`${BASE}/health`);
      if (r.ok) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("dev server (--ui wasm) did not become healthy");
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


/** Type text into the monaco editor (its textarea is readonly for IME —
 *  drive the real input hidden textarea via clipboard paste). */
async function setEditorText(page: import("@playwright/test").Page, text: string) {
  await page.evaluate((t) => navigator.clipboard.writeText(t), text);
  await page.locator(".cell-editor .monaco-editor").first().click();
  await page.keyboard.press("Control+a");
  await page.keyboard.press("Control+v");
  await page.waitForTimeout(300);
}

async function openEditor(page: import("@playwright/test").Page) {
  await page.goto(BASE);
  // Wait for engine readiness (same discipline as playground.spec: status
  // dots; the loading overlay hides the app until init completes).
  await expect(page.locator(".loading-overlay")).toHaveCount(0, { timeout: 60000 });
  const editor = page.locator(".cell-editor");
  await expect(editor).toBeVisible({ timeout: 20000 });
  return editor;
}


test("cell mode toggle reveals cells with named chips + dep counts", async ({ page }) => {
  const editor = await openEditor(page);
  // Put cell text into the buffer via clipboard paste into monaco
  await setEditorText(page, CELL_LIB);
  const toggle = editor.locator(".cell-toggle");
  await toggle.click();
  const cards = editor.locator(".cell-card");
  await expect(cards).toHaveCount(2, { timeout: 10000 });
  await expect(cards.first().locator(".cell-namechip")).toHaveText("IsMale");
  await expect(cards.nth(1).locator(".cell-namechip")).toContainText("UsesIt");
  // UsesIt depends on IsMale — aria label carries the dep list
  await expect(cards.nth(1).locator(".cell-namechip")).toHaveAttribute(
    "aria-label",
    /dependencies IsMale/i,
  );
});

test("RunMode segmented control present with three options, default cell+deps", async ({ page }) => {
  const editor = await openEditor(page);
  const group = editor.locator(".cell-runmode");
  await expect(group).toBeVisible();
  await expect(group.locator('[role="radio"][aria-checked="true"]')).toHaveText(
    "cell + deps",
  );
  await expect(group.locator('[role="radio"]')).toHaveCount(3);
});

test("per-cell run executes server-side and renders inline result", async ({ page }) => {
  const editor = await openEditor(page);
  await setEditorText(page, CELL_LIB);
  const toggle = editor.locator(".cell-toggle");
  await toggle.click();
  const firstRun = editor.locator(".cell-card").first().locator(".cell-run");
  await firstRun.click();
  const out = editor.locator(".cell-card").first().locator(".cell-out");
  await expect(out).toBeVisible({ timeout: 30000 });
  // Connected run: NO 'computed locally' badge
  await expect(out.locator(".cell-localbadge")).toHaveCount(0);
  // server evaluate returns columns for the define
  await expect(out.locator("pre")).toContainText(/IsMale/i, { timeout: 30000 });
});
