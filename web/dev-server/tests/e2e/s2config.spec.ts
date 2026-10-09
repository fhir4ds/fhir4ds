import { test, expect, Page } from "@playwright/test";
import { spawn, ChildProcess } from "node:child_process";
import { mkdtempSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const WORKTREE = "/mnt/d/fhir4ds-ux5-20261008";
const PORT = 19071;
const BASE = `http://127.0.0.1:${PORT}`;

const CQL = "library TerminologyConfig\ndefine Administered: 1\n";

let server: ChildProcess | undefined;
let page: Page;
let wsDir = "";

test.beforeAll(async () => {
  wsDir = mkdtempSync(join(tmpdir(), "ux5-s2-"));
  mkdirSync(join(wsDir, "cql"));
  writeFileSync(join(wsDir, "cql", "TerminologyConfig.cql"), CQL);
  mkdirSync(join(wsDir, "data"));
  writeFileSync(
    join(wsDir, "data", "patients.ndjson"),
    '{"resourceType": "Patient", "id": "p1", "gender": "male"}\n',
  );
  mkdirSync(join(wsDir, "extra"));
  writeFileSync(
    join(wsDir, "extra", "more.ndjson"),
    '{"resourceType": "Patient", "id": "q1"}\n',
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
  await expect(page.locator(".dev-lib").first()).toContainText("TerminologyConfig", { timeout: 20000 });
});

test.afterEach(async () => {
  if (server?.pid) {
    server.kill();
    // Wait for the process to actually exit so the port is released
    // before the next test spawns a fresh server on the same port.
    const exited = new Promise<void>((resolve) => {
      server!.once("exit", () => resolve());
      setTimeout(resolve, 5000);
    });
    await exited;
    await new Promise((r) => setTimeout(r, 200));
  }
});

test("terminology config dialog saves to toml (env-name only)", async () => {
  const pill = page.locator(".dev-termpill");
  await expect(pill).toBeVisible();
  await pill.click();
  const dlg = page.locator(".dev-dialog");
  await expect(dlg).toBeVisible();
  await dlg.locator("select").selectOption("vsac");
  await dlg.locator('input[placeholder="UMLS_API_KEY"]').fill("MY_TEST_KEY_VAR");
  await dlg.getByRole("button", { name: "Save" }).click();
  await expect(dlg.locator(".dev-vsimportmsg")).toContainText("Saved to fhir4ds.toml");
  const cfg = await page.evaluate(async () => {
    const r = await fetch("/api/terminology/config");
    return r.json();
  });
  expect(cfg.config.provider).toBe("vsac");
  expect(cfg.config.api_key_env).toBe("MY_TEST_KEY_VAR");
});

test("path picker: browse, add data dir, rescan surfaces it", async () => {
  const addBtn = page.locator("h2", { hasText: "Data" }).locator(".dev-addrail");
  await addBtn.click();
  const dlg = page.locator(".dev-dialog");
  await expect(dlg).toBeVisible();
  const row = dlg.locator(".dev-pickerrow", { hasText: "extra" });
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "+ add" }).click();
  await expect(dlg.locator(".dev-vsimportmsg")).toContainText("Added extra");
  await expect(page.locator(".dev-dataset", { hasText: "more" })).toBeVisible({ timeout: 15000 });
});
