import { test, expect } from "@playwright/test";

/**
 * Monaco Editor Shadow DOM tests.
 *
 * Monaco 0.52+ uses `.ime-text-area` (not `.inputarea`) for its hidden
 * keyboard-capture textarea. In Shadow DOM context the browser-default styling
 * applies (visible gray box) unless our SHADOW_DOM_FIXES CSS overrides it.
 *
 * These tests verify that no visible Monaco textarea boxes appear in the WC
 * test harness (Shadow DOM) for each editor pane.
 */

const WAIT_FOR_MONACO = 20_000; // Monaco lazy-loads; give it time

test.describe("Monaco Shadow DOM — no visible textarea boxes", () => {
  /** Helper: check for visible textareas inside the fhir4ds-demo shadow root. */
  async function getVisibleTextareas(page: import("@playwright/test").Page) {
    return page.evaluate(() => {
      const demo = document.querySelector("fhir4ds-demo") as any;
      if (!demo?.shadowRoot) return { hasShadow: false, boxes: [] };

      const sr = demo.shadowRoot;
      const textareas = sr.querySelectorAll<HTMLElement>("textarea");
      const boxes = Array.from(textareas).map((ta) => {
        const rect = ta.getBoundingClientRect();
        const cs = window.getComputedStyle(ta);
        return {
          cls: ta.className,
          left: Math.round(rect.left),
          top: Math.round(rect.top),
          width: Math.round(rect.width),
          height: Math.round(rect.height),
          computedOpacity: cs.opacity,
          computedLeft: cs.left,
          inlineLeft: ta.style.left,
          // Visible = non-trivial size AND not far off-screen (left > -1000)
          isVisible: rect.width > 10 && rect.height > 10 && rect.left > -1000,
        };
      });
      return { hasShadow: true, boxes };
    });
  }

  test("cql-sandbox — no visible textarea in CQL editor or SQL panes", async ({ page }) => {
    await page.goto("/wc-test.html");
    // Click cql-sandbox scenario button
    await page.click("button[data-scenario='cql-sandbox']");
    // Wait for Monaco to fully initialise
    await page.waitForTimeout(WAIT_FOR_MONACO);

    const result = await getVisibleTextareas(page);
    expect(result.hasShadow).toBe(true);

    const visibleBoxes = result.boxes.filter((b) => b.isVisible);
    expect(
      visibleBoxes,
      `Expected no visible Monaco textarea boxes but found: ${JSON.stringify(visibleBoxes, null, 2)}`,
    ).toHaveLength(0);
  });

  test("sdc-forms — no visible textarea in Questionnaire JSON pane", async ({ page }) => {
    await page.goto("/wc-test.html");
    await page.click("button[data-scenario='sdc-forms']");
    await page.waitForTimeout(WAIT_FOR_MONACO);

    const result = await getVisibleTextareas(page);
    expect(result.hasShadow).toBe(true);

    const visibleBoxes = result.boxes.filter((b) => b.isVisible);
    expect(
      visibleBoxes,
      `Expected no visible Monaco textarea boxes but found: ${JSON.stringify(visibleBoxes, null, 2)}`,
    ).toHaveLength(0);
  });

  test("SHADOW_DOM_FIXES CSS targets ime-text-area class", async ({ page }) => {
    await page.goto("/wc-test.html");

    // Wait until the shadow root has been fully initialised and the
    // style element populated (web component connectedCallback runs async).
    await page.waitForFunction(() => {
      const demo = document.querySelector("fhir4ds-demo") as any;
      const styles = demo?.shadowRoot?.querySelectorAll("style") ?? [];
      return Array.from(styles as NodeList).some(
        (s: any) => s.textContent && s.textContent.length > 100,
      );
    }, { timeout: 30_000 });

    const hasRule = await page.evaluate(() => {
      const demo = document.querySelector("fhir4ds-demo") as any;
      const styles = demo?.shadowRoot?.querySelectorAll("style") ?? [];
      // Accept either new (0.52+) or old (<0.52) Monaco class name
      return Array.from(styles as NodeList).some((s: any) =>
        s.textContent?.includes("ime-text-area") || s.textContent?.includes("inputarea"),
      );
    });
    expect(hasRule).toBe(true);
  });

  test("fixMonacoInputArea applies !important left to ime-text-area", async ({ page }) => {
    await page.goto("/wc-test.html");
    await page.click("button[data-scenario='cql-sandbox']");
    await page.waitForTimeout(WAIT_FOR_MONACO);

    const result = await page.evaluate(() => {
      const demo = document.querySelector("fhir4ds-demo") as any;
      if (!demo?.shadowRoot) return { noShadow: true, textareas: [] };
      const sr = demo.shadowRoot;
      const tas = sr.querySelectorAll<HTMLElement>("textarea");
      return {
        noShadow: false,
        textareas: Array.from(tas).map((ta) => ({
          cls: ta.className,
          leftPriority: ta.style.getPropertyPriority("left"),
          leftValue: ta.style.left,
        })),
      };
    });

    // If Monaco rendered textareas, they must have !important applied
    for (const ta of result.textareas) {
      expect(
        ta.leftPriority,
        `textarea.${ta.cls} does not have !important left (left=${ta.leftValue})`,
      ).toBe("important");
    }
  });
});
