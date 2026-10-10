import { test, expect, Page } from "@playwright/test";
import { spawn, ChildProcess } from "node:child_process";
import { mkdtempSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const WORKTREE = "/mnt/d/fhir4ds-shellrebuild-20261009";
const PORT = 19161;
const BASE = `http://127.0.0.1:${PORT}`;

const CQL = "library AstLib\nusing FHIR version '4.0.1'\ncontext Patient\n\n// # %%\ndefine IsPatient: exists [Patient]\n";

let server: ChildProcess | undefined;
let page: Page;
let wsDir = "";

test.beforeAll(async () => {
  wsDir = mkdtempSync(join(tmpdir(), "shell-ast-"));
  mkdirSync(join(wsDir, "cql"));
  writeFileSync(join(wsDir, "cql", "AstLib.cql"), CQL);
  mkdirSync(join(wsDir, "data"));
  writeFileSync(
    join(wsDir, "data", "p.ndjson"),
    '{"resourceType": "Patient", "id": "p1"}\n',
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
  await expect(page.locator(".dev-lib").first()).toBeVisible({ timeout: 20000 });
  await page.evaluate((t) => { (window as unknown as { __astLibText?: string }).__astLibText = t; }, CQL);
});

test.afterEach(async () => {
  if (server?.pid) {
    server.kill();
    await new Promise((r) => setTimeout(r, 200));
  }
});

test("bottom bar: cql/sql/ast tabs; translate fills ast pane", async ({ page: p }) => {
  // capture app console for diagnosis
  const logs: string[] = [];
  p.on("console", (m) => logs.push(m.text()));
  p.on("pageerror", (e) => logs.push("PAGEERROR: " + e.message));
  // select the library, run the cell, then Show SQL (translate path fills ast)
  await page.locator(".dev-lib", { hasText: "AstLib" }).first().click();
  const editorShowSql = page.locator("button", { hasText: "Show SQL" }).first();
  await expect(editorShowSql).toBeEnabled({ timeout: 15000 });
  await editorShowSql.click(); // translate path — fills sql + ast
  const astJson = (await page.evaluate(async (text) => {
    const r = await fetch("/api/translate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        libraries: [{ name: "AstLib", text }],
        library: "AstLib",
        emit_sql: true,
        include_ast: true,
      }),
    });
    return r.json();
  }, CQL)) as { ast?: { statements: Record<string, unknown> } } | null;
  expect(Object.keys(astJson?.ast?.statements ?? {})).toContain("IsPatient");
  // seed the pane through the app path: click the toolbar button
  await editorShowSql.click();

  // bottom-bar tab set
  const bar = page.locator(".dev-bottombar, .dev-out").first();
  await expect(page.getByRole("button", { name: "ast", exact: true })).toBeVisible({ timeout: 15000 });

  // ast tab renders statement JSON
  await page.getByRole("button", { name: "ast", exact: true }).click();
  const astPane = page.locator(".dev-astpane");
  await expect(astPane).toBeVisible();
  console.log("APP CONSOLE:", logs.slice(-10).join(" | "));
  await expect(astPane).toContainText("IsPatient", { timeout: 15000 });

  // cql tab shows the buffer
  await page.getByRole("button", { name: "cql", exact: true }).click();
  await expect(page.locator(".dev-cqlpane")).toContainText("library AstLib");

  // sql tab still works
  await page.locator("button", { hasText: "Show SQL" }).nth(1).click();
  await expect(page.locator("button", { hasText: "Show SQL" }).nth(1)).toBeVisible();
});
