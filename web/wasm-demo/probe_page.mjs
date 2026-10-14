// Direct DOM probe of the connected page to see what renders
import { chromium } from "@playwright/test";
const browser = await chromium.launch();
const page = await browser.newPage();
page.on("console", (m) => { if (m.type() === "error") console.log("CONSOLE-ERR:", m.text().slice(0, 200)); });
page.on("pageerror", (e) => console.log("PAGE-ERR:", String(e).slice(0, 200)));
await page.goto("http://127.0.0.1:19063", { waitUntil: "domcontentloaded" }).catch((e) => console.log("goto err", String(e).slice(0, 100)));
await page.waitForTimeout(15000);
const state = await page.evaluate(() => {
  const q = (s) => document.querySelector(s);
  const vis = (s) => { const el = q(s); if (!el) return "absent"; const r = el.getBoundingClientRect(); return `${Math.round(r.width)}x${Math.round(r.height)}`; };
  return {
    overlay: !!q(".loading-overlay"),
    overlayText: q(".loading-overlay")?.textContent?.slice(0, 80) ?? null,
    tabnav: vis(".tab-nav"),
    app: vis(".app"),
    cellEditor: vis(".cell-editor"),
    editorPane: vis(".editor-pane"),
    monaco: vis(".monaco-editor"),
    statusMessage: q(".status-message")?.textContent?.slice(0, 60) ?? null,
    badge: q(".status-engine")?.textContent ?? null,
  };
});
console.log(JSON.stringify(state, null, 1));
await browser.close();
