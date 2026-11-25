// Node driver for the real-browser WASM parity harness (Tier B).
//
// usage: node run.mjs <node_modules> <url> <jobJson> <outJson>
//
// One headless chromium per invocation (boot is ~0.5 s), zero retries. The job is
// {macros?: string[], statements?: [[label, sql], ...], hardTimeoutMs?: number}; the output is
// written after every phase so a timeout still leaves the partial evidence behind.
import { createRequire } from "module";
import { readFileSync, writeFileSync } from "fs";
import path from "path";

const [nodeModules, url, jobJson, outJson] = process.argv.slice(2);
const require = createRequire(import.meta.url);
const { chromium } = require(path.join(nodeModules, "playwright", "index.js"));

const job = JSON.parse(readFileSync(jobJson, "utf8"));
const out = { loads: null };
const save = () => writeFileSync(outJson, JSON.stringify(out, null, 1));

const HARD_MS = Number(job.hardTimeoutMs ?? 120_000);
const hard = setTimeout(() => {
  out.hardTimeout = true;
  save();
  process.exit(3);
}, HARD_MS);

let browser;
try {
  browser = await chromium.launch({
    headless: true,
    args: ["--enable-features=SharedArrayBuffer"],
  });
} catch (e) {
  // Not a parity finding: the browser binary is an environment input.
  out.environment = "chromium";
  out.error = String(e?.message ?? e).slice(0, 600);
  save();
  process.exit(2);
}

try {
  const page = await browser.newPage();
  page.on("response", (r) => {
    if (r.status() >= 400) (out.badResponses ??= []).push([r.status(), r.url().replace(url, "")]);
  });
  page.on("pageerror", (e) => (out.pageErrors ??= []).push(String(e).slice(0, 300)));
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(
    () => globalThis.__harness?.status.booted || globalThis.__harness?.status.error,
    null,
    { timeout: 60_000 },
  );
  out.status = await page.evaluate(() => globalThis.__harness.status);
  if (!out.status.booted) {
    process.exitCode = 4;
  } else {
    out.version = await page.evaluate(() => globalThis.__harness.version);
    out.loads = await page.evaluate(() => globalThis.__harness.loads);
    save();
    if (job.macros) out.macros = await page.evaluate((s) => globalThis.__harness.macros(s), job.macros);
    if (job.statements?.length) {
      out.results = await page.evaluate((s) => globalThis.__harness.run(s), job.statements);
    }
  }
} catch (e) {
  out.error = String(e?.message ?? e).slice(0, 600);
  process.exitCode = 5;
} finally {
  save();
  clearTimeout(hard);
  await browser.close();
}
