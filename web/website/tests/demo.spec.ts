import { test, expect } from "@playwright/test";
import { readdirSync } from "node:fs";
import { join } from "node:path";

test.describe("Landing page", () => {
  test("loads with correct hero subtitle and stats", async ({ page }) => {
    await page.goto(".");
    await expect(page).toHaveTitle(/FHIR for Data Science/);

    // Hero secondary line
    await expect(page.getByText("Production-Scale FHIR Analytics")).toBeVisible();

    // Hero tagline (hero__subtitle) — case-insensitive substrings
    const subtitle = page.locator(".hero__subtitle");
    await expect(subtitle).toContainText("blazing fast", { ignoreCase: true });
    await expect(subtitle).toContainText("zero server infrastructure", { ignoreCase: true });
    await expect(subtitle).toContainText("auditable", { ignoreCase: true });

    // Stats bar — mean per-patient timing
    await expect(page.getByText("~3.9ms").first()).toBeVisible();
    await expect(page.getByText("SQL mean / patient").first()).toBeVisible();
    await expect(page.getByText("Zero").first()).toBeVisible();
    await expect(page.getByText("Audit Evidence").first()).toBeVisible();
  });

  test("feature cards show speed-first ordering", async ({ page }) => {
    await page.goto(".");
    await expect(page.getByRole("heading", { name: "Columnar Speed" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Zero Infrastructure" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "SQL-on-FHIR v2" })).toBeVisible();
  });

  test("comparison table references FHIR4DS vs CQF Clinical Reasoning", async ({ page }) => {
    await page.goto(".");
    await expect(page.getByRole("heading", { level: 2 }).filter({ hasText: "FHIR4DS vs" })).toBeVisible();
    // Per-patient metric row in table (mean)
    await expect(page.getByRole("cell", { name: "SQL execution per patient (all 47 measures)" })).toBeVisible();
    // Speedup row
    await expect(page.getByRole("cell", { name: /137×/ })).toBeVisible();
    // Benchmarking report link is present
    await expect(page.getByRole("link", { name: /View Full Benchmarking Report/ })).toBeVisible();
  });
});

test.describe("Demo page", () => {
  test("title has good contrast and loads correctly", async ({ page }) => {
    await page.goto("demo");
    await expect(page).toHaveTitle(/Live Demo/);

    const title = page.locator("h1:has-text('Live Demo')");
    await expect(title).toBeVisible();

    // Title must have explicit light color applied (inline style guarantees it regardless of theme)
    const titleColor = await title.evaluate((el) => (el as HTMLElement).style.color);
    // Inline style sets color to #f1f5f9 = rgb(241,245,249)
    expect(titleColor).toBeTruthy();
    expect(titleColor).not.toBe(""); // inline color must be set
  });

  test("loads and shows WasmDemo launch button", async ({ page }) => {
    await page.goto("demo");
    await expect(page).toHaveTitle(/Live Demo/);

    // The WasmDemo component should show the launch UI before the iframe
    await expect(page.locator("text=Interactive CQL/DQM Demo")).toBeVisible();
    await expect(page.locator("button:has-text('Launch Demo')")).toBeVisible();
  });

  test("Launch Demo button reveals iframe pointing to wasm-app", async ({ page }) => {
    await page.goto("demo");
    await page.click("button:has-text('Launch Demo')");

    // After clicking, an iframe should appear
    const iframeElement = page.locator("iframe[title='FHIR4DS Interactive CQL/DQM Demo']");
    await expect(iframeElement).toBeVisible({ timeout: 5_000 });
    const src = await iframeElement.getAttribute("src");
    expect(src).toContain("wasm-app");
  });

  test("wasm-app WHL is accessible at the current Vite asset path", async ({
    request,
    baseURL,
  }) => {
    const base = (baseURL ?? "http://localhost:3000/").replace(/\/$/, "");
    const assetsDir = join(process.cwd(), "static", "wasm-app", "assets");
    const wheel = readdirSync(assetsDir).find((name) =>
      /^fhir4ds_v2-.*\.whl$/.test(name)
    );

    expect(wheel, "deployed fhir4ds_v2 wheel in wasm-app assets").toBeTruthy();
    const response = await request.get(`${base}/wasm-app/assets/${wheel}`);
    expect(response.status(), `${wheel} at /wasm-app/assets/`).toBe(200);
    expect((await response.body()).byteLength).toBeGreaterThan(0);
  });

  test("DuckDB extension files accessible at both extensions/ and assets/ paths", async ({
    request,
    baseURL,
  }) => {
    // The extensions/ path is where registerFileURL points (explicit URL)
    const base = (baseURL ?? "http://localhost:3000/").replace(/\/$/, "");
    const wasmAppBase = `${base}/wasm-app`;

    for (const ext of ["fhirpath", "cql"]) {
      const filename = `${ext}.duckdb_extension.wasm`;

      // Extensions/ path — used by registerFileURL
      const r1 = await request.get(`${wasmAppBase}/extensions/${filename}`);
      expect(r1.status(), `${filename} at extensions/`).toBe(200);
      const bytes1 = await r1.body();
      expect(bytes1.slice(0, 4).toString("hex")).toBe("0061736d"); // \0asm magic

      // Assets/ path — resolved by Emscripten's dlopen relative to worker URL
      const r2 = await request.get(`${wasmAppBase}/assets/${filename}`);
      expect(r2.status(), `${filename} at assets/`).toBe(200);
      const bytes2 = await r2.body();
      expect(bytes2.slice(0, 4).toString("hex")).toBe("0061736d"); // \0asm magic
    }
  });
});
