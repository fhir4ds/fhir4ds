import { test, expect } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { mkdtemp, writeFile, mkdir } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";

const PORT = 18981;
let server: ChildProcess | null = null;
let dir: string | null = null;

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "v3views-"));
  await mkdir(join(dir, "cql"));
  await mkdir(join(dir, "views"));
  await mkdir(join(dir, "valuesets"));
  await mkdir(join(dir, "data"));

  await writeFile(
    join(dir, "cql", "Demographics.cql"),
    [
      "library Demographics version '1.0.0'",
      "using FHIR version '4.0.1'",
      "",
      "context Patient",
      "",
      "// # %% [name: IsMale]",
      "define IsMale: Patient.gender = 'male'",
      "",
    ].join("\n"),
  );

  await writeFile(
    join(dir, "views", "pxdemo.json"),
    JSON.stringify(
      {
        resource: "Patient",
        name: "PxDemo",
        select: [
          {
            column: [
              { name: "id", path: "id" },
              { name: "gender", path: "gender" },
              { name: "given", path: "name.given", collection: true },
            ],
          },
        ],
      },
      null,
      2,
    ),
  );

  const patients: string[] = [];
  for (let i = 1; i <= 6; i++) {
    const gender = i % 2 ? "male" : "female";
    const p: Record<string, unknown> = {
      resourceType: "Patient",
      id: `p${i}`,
      gender,
      birthDate: i % 2 ? "1974-12-25" : "1990-01-01",
    };
    if (i % 2) p.name = [{ given: ["John", "Kim"], family: "Doe" }];
    patients.push(JSON.stringify(p));
  }
  await writeFile(join(dir, "data", "patients.ndjson"), patients.join("\n") + "\n");

  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", dir, "--port", String(PORT), "--no-open"],
    {
      env: {
        PYTHONPATH: "/mnt/d/fhir4ds-devserver-v3-20261005",
        PATH: process.env.PATH ?? "",
      },
      cwd: dir,
      stdio: "ignore",
    },
  );

  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/health`);
      if (r.ok) return;
    } catch {
      /* retry */
    }
    await new Promise((res) => setTimeout(res, 500));
  }
  throw new Error("server never became healthy");
});

test.afterAll(async () => {
  if (server?.pid) {
    process.kill(server.pid, "SIGKILL");
    await new Promise((res) => setTimeout(res, 500));
  }
});

test.beforeEach(async ({ page }) => {
  await page.goto(`http://127.0.0.1:${PORT}`);
});

test("ViewDefinitions rail section lists pxdemo and opens the pane", async ({ page }) => {
  await expect(page.locator("aside").locator("h2", { hasText: "ViewDefinitions" })).toBeVisible();
  await page.locator(".dev-lib.small", { hasText: "pxdemo" }).first().click();
  await expect(page.locator(".dev-vdpane")).toBeVisible();
  await expect(page.locator(".dev-vdhead")).toContainText("pxdemo");
  await expect(page.locator(".dev-vdhead")).toContainText("Patient");
});

test("run view renders results table and SQL tab", async ({ page }) => {
  await page.locator(".dev-lib.small", { hasText: "pxdemo" }).first().click();
  await expect(page.locator(".dev-vdpane")).toBeVisible();
  await page.locator(".dev-vdrun").click();
  await expect(page.locator(".dev-vdcount")).toContainText("6 resources staged");
  await expect(page.locator(".dev-vdresults table")).toBeVisible();
  await expect(page.locator(".dev-vdresults").getByText("John").first()).toBeVisible();
  await page.locator(".dev-vdtabs button", { hasText: "SQL" }).click();
  await expect(page.locator(".dev-vdresults").getByText("SELECT")).toBeVisible();
});

test("inline invariant error surfaces for a bad ViewDefinition", async ({ page }) => {
  // Write a bad VD file into the workspace at runtime (the writer), then open it.
  const badVd = JSON.stringify({
    resource: "Patient",
    name: "BadDemo",
    select: [{ column: [{ name: "id", path: "id", nam: "oops" }] }],
  });
  await writeFile(join(dir!, "views", "bad.json"), badVd);
  // Wait for the watcher to pick the new file up (500ms poll).
  await page.waitForTimeout(2000);
  await page.reload();
  await page.locator(".dev-lib.small", { hasText: "bad" }).first().click();
  await expect(page.locator(".dev-vdpane")).toBeVisible();
  await page.locator(".dev-vdrun").click();
  await expect(page.locator(".dev-vderror")).toBeVisible();
  await expect(page.locator(".dev-vderror")).toContainText("Unsupported column field");
});
