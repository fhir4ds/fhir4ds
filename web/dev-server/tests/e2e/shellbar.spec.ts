import { test, expect, Page } from "@playwright/test";
import { spawn, ChildProcess } from "node:child_process";
import { mkdtempSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const WORKTREE = "/mnt/d/fhir4ds-shellrebuild-20261009";
const PORT = 19171;
const BASE = `http://127.0.0.1:${PORT}`;

const CQL = "library ShellLib\nusing FHIR version '4.0.1'\ncontext Patient\ndefine ShellCheck: exists [Patient]\n";

let server: ChildProcess | undefined;
let page: Page;
let wsDir = "";

test.beforeAll(async () => {
  wsDir = mkdtempSync(join(tmpdir(), "shell-bar-"));
  mkdirSync(join(wsDir, "cql"));
  writeFileSync(join(wsDir, "cql", "ShellLib.cql"), CQL);
  mkdirSync(join(wsDir, "data"));
  writeFileSync(join(wsDir, "data", "p.ndjson"), '{"resourceType": "Patient", "id": "p1"}\n');
});

test.afterAll(async () => rmSync(wsDir, { recursive: true, force: true }));

test.beforeEach(async ({ browser }) => {
  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", wsDir, "--port", String(PORT), "--no-open"],
    { cwd: wsDir, env: { PATH: process.env.PATH ?? "", PYTHONPATH: WORKTREE }, stdio: "ignore" },
  );
  for (let i = 0; i < 60; i++) {
    try { const r = await fetch(`${BASE}/health`); if (r.ok) break; } catch { /* boot */ }
    await new Promise((r) => setTimeout(r, 500));
    if (i === 59) throw new Error("dev server did not become healthy");
  }
  const ctx = await browser.newContext();
  page = await ctx.newPage();
  await page.goto(BASE);
  await expect(page.locator(".dev-iconrail")).toBeVisible({ timeout: 20000 });
});

test.afterEach(async () => {
  if (server?.pid) { server.kill(); await new Promise((r) => setTimeout(r, 200)); }
});

test("shell: File/Settings header buttons + File menu entries", async () => {
  const fileBtn = page.locator("header button", { hasText: "File" });
  await expect(fileBtn).toBeVisible();
  await fileBtn.click();
  const menu = page.locator(".dev-filemenu");
  await expect(menu).toBeVisible();
  await expect(menu.getByRole("button", { name: /Import MADiE package/i })).toBeVisible();
  await expect(menu.getByRole("button", { name: /Import MADiE test-case/i })).toBeVisible();
  await expect(menu.getByRole("button", { name: /Add CQL path/i })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(menu).toBeHidden();

  await page.locator("header button", { hasText: "Settings" }).click();
  await expect(page.locator(".dev-dialog")).toBeVisible({ timeout: 10000 });
  await page.keyboard.press("Escape");
});

test("shell: bottom bar has results/cql/sql/ast/history; history pane reachable", async () => {
  for (const t of ["results", "cql", "sql", "ast", "history"]) {
    await expect(page.locator(".dev-tabs button", { hasText: t === "sql" ? "Show SQL" : t })).toBeVisible();
  }
  await page.locator(".dev-tabs button", { hasText: "history" }).click();
  await expect(page.locator(".dev-runhistory")).toBeVisible();
  await expect(page.locator(".dev-rhempty")).toBeVisible(); // no runs yet
});

test("shell: slide-out nav sections still work (alt+3 libraries)", async () => {
  await page.keyboard.press("Alt+3");
  const slide = page.locator(".dev-libraries.dev-slideout");
  await expect(slide).toHaveClass(/open/);
  await expect(page.locator(".dev-lib").filter({ has: page.getByText("ShellLib", { exact: true }) })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(slide).toBeHidden();
});
