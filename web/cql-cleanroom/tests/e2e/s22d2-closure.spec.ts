import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test, expect } from "@playwright/test";

// S22d-2 (§5): closure-driven MADiE export/import over the FHIR-type
// workspace + the patient-ID collision policy.

const BASE = "http://127.0.0.1:19200";
let dir: string | null = null;
let server: ChildProcess | null = null;

async function call(path: string, body?: unknown) {
  const res = await fetch(`${BASE}${path}`, {
    method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  return (await res.json()) as Record<string, unknown> & {
    data?: Record<string, unknown>;
  };
}

test.beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), "ccr-s22d2-"));
  await mkdir(join(dir, "Library"), { recursive: true });
  await mkdir(join(dir, "ValueSet"), { recursive: true });
  await mkdir(join(dir, "Measure", "ClosureM", "Measure"), { recursive: true });
  await mkdir(join(dir, "Measure", "ClosureM", "List"), { recursive: true });
  await mkdir(join(dir, "Measure", "ClosureM", "MeasureReport"), { recursive: true });
  await mkdir(join(dir, "Patient", "c1", "Observation"), { recursive: true });
  await mkdir(join(dir, "Patient", "c2"), { recursive: true });

  await writeFile(
    join(dir, "Library", "Shared.cql"),
    "library Shared version '1.0.0'\ncontext Patient\n\ndefine S: 1\n",
    "utf8",
  );
  await writeFile(
    join(dir, "Library", "MainLib.cql"),
    [
      "library MainLib version '1.0.0'",
      "include Shared version '1.0.0' called Shared",
      'valueset "VS": \'http://x/cvs\'',
      "context Patient",
      "",
      'define "IP": exists([Observation: "VS"])',
      "",
    ].join("\n"),
    "utf8",
  );
  await writeFile(
    join(dir, "Library", "NotInClosure.cql"),
    "library NotInClosure version '1.0.0'\ncontext Patient\n\ndefine N: 2\n",
    "utf8",
  );
  await writeFile(
    join(dir, "ValueSet", "cvs.json"),
    '{"resourceType":"ValueSet","id":"cvs","url":"http://x/cvs","compose":{"include":[]}}',
    "utf8",
  );
  await writeFile(
    join(dir, "Measure", "ClosureM", "Measure", "ClosureM.json"),
    JSON.stringify({
      resourceType: "Measure",
      id: "ClosureM",
      name: "ClosureM",
      library: ["urn:cleanroom:lib:MainLib"],
    }),
    "utf8",
  );
  // Test-set membership BY REFERENCE: c1 only.
  await writeFile(
    join(dir, "Measure", "ClosureM", "List", "TestCases.json"),
    JSON.stringify({
      resourceType: "List",
      status: "current",
      mode: "working",
      entry: [{ item: { reference: "Patient/c1" } }],
    }),
    "utf8",
  );
  await writeFile(
    join(dir, "Measure", "ClosureM", "MeasureReport", "c1.json"),
    JSON.stringify({
      resourceType: "MeasureReport",
      subject: { reference: "Patient/c1" },
    }),
    "utf8",
  );
  await writeFile(
    join(dir, "Patient", "c1", "c1.json"),
    JSON.stringify({ resourceType: "Patient", id: "c1", gender: "female" }),
    "utf8",
  );
  await writeFile(
    join(dir, "Patient", "c1", "Observation", "o1.json"),
    JSON.stringify({
      resourceType: "Observation",
      id: "o1",
      status: "final",
      subject: { reference: "Patient/c1" },
    }),
    "utf8",
  );
  await writeFile(
    join(dir, "Patient", "c2", "c2.json"),
    JSON.stringify({ resourceType: "Patient", id: "c2", gender: "male" }),
    "utf8",
  );

  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", dir, "--port", "19200", "--no-open"],
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
  if (dir) await rm(dir, { recursive: true, force: true });
});

test("S22d2-1: /api/measure/export builds the List-closure zip", async () => {
  const res = await call("/api/measure/export", { measure: "ClosureM" });
  const d = (res.data ?? res) as { ok?: boolean; zip_base64?: string };
  expect(d.ok).toBe(true);
  expect(typeof d.zip_base64).toBe("string");

  const zipBuf = Buffer.from(d.zip_base64!, "base64");
  // Parse the zip central directory names via a trick: use node's
  // built-in decompression through playwright-free JS (minimal zip lister).
  const names: string[] = [];
  {
    const dv = new DataView(zipBuf.buffer, zipBuf.byteOffset, zipBuf.byteLength);
    let i = 0;
    while (i < dv.byteLength - 4) {
      if (dv.getUint32(i, true) === 0x04034b50) {
        const nameLen = dv.getUint16(i + 26, true);
        const extraLen = dv.getUint16(i + 28, true);
        const compSize = dv.getUint32(i + 18, true);
        const name = zipBuf.toString("utf8", i + 30, i + 30 + nameLen);
        names.push(name);
        i += 30 + nameLen + extraLen + compSize;
      } else {
        i += 1;
      }
    }
  }
  // Closure of MainLib = MainLib + Shared (NotInClosure excluded).
  expect(names).toContain("cql/MainLib-1.0.0.cql");
  expect(names).toContain("cql/Shared-1.0.0.cql");
  expect(names.filter((n) => n.includes("NotInClosure"))).toEqual([]);
  // Referenced valueset ships.
  expect(names).toContain("resources/valueset-cvs.json");
  // List-referenced patient c1 (bundle + expected MR); c2 excluded.
  expect(names).toContain("testcase/patient-c1/c1.json");
  expect(names).toContain("testcase/patient-c1/c1-expected.json");
  expect(names.filter((n) => n.includes("patient-c2"))).toEqual([]);
});

test("S22d2-2: import collision rejects typed; tc- opt-in namespaces", async () => {
  // A test-case zip whose Patient id collides with the existing c1.
  const bundle = {
    resourceType: "Bundle",
    type: "collection",
    entry: [
      { resource: { resourceType: "Patient", id: "c1", gender: "other" } },
      {
        resource: {
          resourceType: "Observation",
          id: "ox",
          subject: { reference: "Patient/c1" },
        },
      },
    ],
  };
  // Build a zip via the browser page (JSZip-free: use the page's zip
  // builder? Simplest: construct with node's zlib STORED entries).
  // Build the colliding test-case zip with fflate (the app's zip lib).
  const { zipSync } = await import("fflate");
  const zip = zipSync({
    "c1/case-1.json": Buffer.from(JSON.stringify(bundle), "utf8"),
  });

  const b64 = Buffer.from(zip).toString("base64");

  // Default: typed rejection.
  const rejected = await call("/api/madie/import-tests", {
    zip_base64: b64,
    measure_name: "ClosureM",
  });
  const rd = (rejected.data ?? rejected) as {
    ok?: boolean;
    collisions?: string[];
  };
  expect(rd.ok).toBe(false);
  expect(rd.collisions).toEqual(["c1"]);

  // Opt-in: tc- namespacing lands the patient under tc-c1.
  const namespaced = await call("/api/madie/import-tests", {
    zip_base64: b64,
    measure_name: "ClosureM",
    namespace_collisions: true,
  });
  const nd = (namespaced.data ?? namespaced) as { ok?: boolean };
  expect(nd.ok).toBe(true);
});
