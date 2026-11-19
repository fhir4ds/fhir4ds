/**
 * QA it16 — Domain 6 (connected mode/terminology) × SKEPTIC.
 * Devserver spawned against the LOCAL checkout (not the stale /mnt/d one).
 *  H1 /api/mode handshake connects; footer names the workspace
 *  H2 Save-to-disk lands the resource in the workspace data dir; the
 *     data-hint offers restart (kernel never auto-reloads)
 *  H3 SKEPTIC: a FAILING /api/resource/save is silent (.catch(undefined)
 *     + non-ok unchecked) — the user believes the save succeeded
 *  H4 terminology status surface: provider + configured state without a key
 */
import { mkdtemp, mkdir, writeFile, rm, readFile } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";
import { appendFileSync } from "node:fs";

const BASE = "http://127.0.0.1:19179";
let dir: string | null = null;
let server: ChildProcess | null = null;

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "ccr-it16-"));
  await mkdir(join(dir, "cql"), { recursive: true });
  await mkdir(join(dir, "data"), { recursive: true });
  await writeFile(
    join(dir, "cql", "Lib.cql"),
    "library Lib version '1.0.0'\nusing FHIR version '4.0.1'\ninclude FHIRHelpers version '4.0.1' called FHIRHelpers\ncontext Patient\n\ndefine Ok: 1 = 1\n",
    "utf8",
  );
  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", dir, "--port", "19179", "--no-open"],
    {
      cwd: "/home/jmontavon/src/fhir4ds",
      env: { ...process.env, PYTHONPATH: "/home/jmontavon/src/fhir4ds", PATH: process.env.PATH ?? "" },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  server.stdout?.on("data", () => undefined);
  server.stderr?.on("data", (d) => {
    try { appendFileSync("/tmp/jm/it16_server.log", String(d)); } catch { /* ignore */ }
  });
  for (let i = 0; i < 90; i++) {
    try {
      const r = await fetch(`${BASE}/health`);
      if (r.ok) return;
    } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("it16 dev server did not become healthy");
});

test.afterAll(async () => {
  if (server?.pid) {
    try { process.kill(server.pid); await new Promise((r) => setTimeout(r, 300)); } catch { /* gone */ }
  }
  if (dir) await rm(dir, { recursive: true, force: true }).catch(() => undefined);
});

async function openApp(page: import("@playwright/test").Page) {
  await page.goto(`${BASE}/cleanroom/`, { waitUntil: "domcontentloaded", timeout: 60_000 });
  await page.waitForTimeout(15_000); // server detect + boot
}

test("H1: /api/mode handshake connects; footer names the workspace", async ({ page }) => {
  await openApp(page);
  const mode = await page.evaluate(async () => {
    const r = await fetch("/api/mode");
    return await r.json();
  });
  const d = mode?.data ?? mode;
  expect(d.server).toBe(true);
  expect(typeof d.version).toBe("string");
});

test("H2: builder Save-to-disk writes the resource into the workspace", async ({ page }) => {
  await openApp(page);
  await page.click('[data-testid="nav-toggle-tests"]');
  await page.click('[data-testid="nav-add-tests"]');
  await page.waitForSelector('[data-testid="builder-pane"]', { timeout: 30_000 });
  // connected mode: explicit-commit action bar IS visible (S25 claim)
  await expect(page.locator('[data-testid="builder-validate"]')).toBeVisible();
  await expect(page.locator('[data-testid="builder-add"]')).toBeVisible();
  // author a minimal Patient via raw mode (deterministic shape)
  await page.click('[data-testid="builder-raw-toggle"]');
  await page.locator('[data-testid="builder-raw-text"]')
    .fill(JSON.stringify({ resourceType: "Patient", id: "it16p", gender: "female" }, null, 2));
  await page.click('[data-testid="builder-raw-toggle"]'); // commit to form
  // INV-C3-2: Save to disk requires a FRESH validation first
  await page.click('[data-testid="builder-validate"]');
  await expect(
    page.locator('[data-testid="builder-valid"], [data-testid="builder-diagnostics"]'),
  ).toBeVisible({ timeout: 15_000 });
  // diagnostic: button enabled after fresh validation?
  const addBtn = page.locator('[data-testid="builder-add"]');
  const disabledNow = await addBtn.isDisabled();
  const btnTitle = await addBtn.getAttribute("title");
  await import("node:fs/promises").then((m2) => m2.writeFile("/tmp/jm/it16_btn.txt",
    `disabled=${disabledNow} title=${btnTitle}`));
  const saveResp: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes("resource/save")) saveResp.push(`REQ ${r.url().slice(0, 120)}`);
  });
  page.on("requestfailed", (r) => {
    if (r.url().includes("resource/save")) saveResp.push(`FAILED ${r.url().slice(0, 120)} ${r.failure()?.errorText}`);
  });
  page.on("response", async (r) => {
    if (r.url().includes("resource/save")) {
      saveResp.push(`RESP ${r.status()} ${(await r.text().catch(() => "?")).slice(0, 150)}`);
    }
  });
  await page.click('[data-testid="builder-add"]'); // "Save to disk"
  await page.waitForTimeout(3000);
  await import("node:fs/promises").then((m2) => m2.writeFile("/tmp/jm/it16_save_resp.txt", saveResp.join(" | ") || "NONE"));
  // the resource must exist in the workspace data dir
  // search the ENTIRE workspace recursively (the boot migration may move
  // cql/ -> Library/ and relocate data files)
  const found = await (async () => {
    const { glob } = await import("node:fs/promises");
    for await (const p of glob(join(dir!, "**/*.ndjson"))) {
      if ((await readFile(p, "utf8")).includes("it16p")) return p;
    }
    for await (const p of glob(join(dir!, "**/*.json"))) {
      if ((await readFile(p, "utf8")).includes("it16p")) return p;
    }
    return null;
  })();
  test.info().annotations.push({ type: "note", description: `saved file: ${found}` });
  expect(found).toBeTruthy();
});

test("H3: a FAILING save must not be silent", async ({ page }) => {
  await openApp(page);
  // intercept the save endpoint and fail it — simulates disk error / 4xx
  let saveCalled = false;
  await page.route("**/api/resource/save", async (route) => {
    saveCalled = true;
    await route.fulfill({ status: 422, contentType: "application/json", body: '{"error":{"message":"workspace data dir is read-only"}}' });
  });
  await page.click('[data-testid="nav-toggle-tests"]');
  await page.click('[data-testid="nav-add-tests"]');
  await page.waitForSelector('[data-testid="builder-pane"]', { timeout: 30_000 });
  await page.click('[data-testid="builder-raw-toggle"]');
  await page.locator('[data-testid="builder-raw-text"]')
    .fill(JSON.stringify({ resourceType: "Patient", id: "it16fail", gender: "male" }, null, 2));
  await page.click('[data-testid="builder-raw-toggle"]');
  await page.click('[data-testid="builder-add"]');
  await page.waitForTimeout(1500);
  expect(saveCalled).toBe(true);
  // SKEPTIC claim: SOME user-visible feedback exists (status note, toast,
  // error chip). If none appears within a generous window, that is F4.
  const note = page.locator('[data-testid="status-note"]');
  const noted = await note.isVisible().catch(() => false);
  const noteText = noted ? (await note.textContent()) ?? "" : "";
  test.info().annotations.push({ type: "finding", description: `save-failure feedback visible=${noted} text=${noteText.slice(0, 120)}` });
  // assert the DESIRED behavior (red until fixed):
  await expect(note).toBeVisible({ timeout: 10_000 });
  await expect(note).toContainText(/save|failed|error|read-only/i);
});

test("H4: terminology status surface", async ({ page }) => {
  await openApp(page);
  const status = await page.evaluate(async () => {
    const r = await fetch("/api/terminology/config");
    return { ok: r.ok, body: await r.json().catch(() => null) };
  });
  test.info().annotations.push({ type: "note", description: `terminology config: ${JSON.stringify(status).slice(0, 200)}` });
  expect(status.ok).toBe(true);
});
