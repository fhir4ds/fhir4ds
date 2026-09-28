import { describe, expect, it } from "vitest";
import {
  coerceParam,
  detectParams,
  isIntervalParam,
  joinInterval,
  splitInterval,
  toParametersResource,
} from "../../src/lib/params";

describe("params", () => {
  it("detectParams captures names AND declared types", () => {
    const decls = detectParams(
      `parameter "Measurement Period" Interval<DateTime>
       parameter "Payer" String
       parameter "MPDefault" Interval<DateTime> default Interval[@2024-01-01T00:00:00.0, @2024-12-31T23:59:59.999]
       parameter "Measurement Period" Interval<DateTime>`,
    );
    expect(decls).toHaveLength(3);
    expect(decls[0]).toEqual({ name: "Measurement Period", type: "Interval<DateTime>", value: "" });
    expect(decls[1].type).toBe("String");
    // a `default` clause must not bleed into the captured type
    expect(decls[2].type).toBe("Interval<DateTime>");
  });

  it("isIntervalParam keys on the declared type", () => {
    expect(isIntervalParam({ name: "A", type: "Interval<Date>", value: "" })).toBe(true);
    expect(isIntervalParam({ name: "A", type: "String", value: "" })).toBe(false);
    expect(isIntervalParam({ name: "A", value: "1..2" })).toBe(false);
  });

  it("splitInterval extracts yyyy-mm-dd halves from interval values", () => {
    expect(
      splitInterval("2026-01-01T00:00:00.0..2026-12-31T23:59:59.999"),
    ).toEqual({ start: "2026-01-01", end: "2026-12-31" });
    expect(splitInterval("2026-01-01/2026-12-31")).toEqual({
      start: "2026-01-01",
      end: "2026-12-31",
    });
    // scalars and date-less halves are not date-pickable
    expect(splitInterval("payers")).toBeNull();
    expect(splitInterval("")).toBeNull();
  });

  it("joinInterval writes canonical forms (DateTime gets inclusive end-day)", () => {
    expect(joinInterval("Interval<DateTime>", "2026-01-01", "2026-12-31")).toBe(
      "2026-01-01T00:00:00.0..2026-12-31T23:59:59.999",
    );
    expect(joinInterval("Interval<Date>", "2026-01-01", "2026-12-31")).toBe(
      "2026-01-01..2026-12-31",
    );
    // half-bound → unbound (never a one-sided value the engine chokes on)
    expect(joinInterval("Interval<DateTime>", "2026-01-01", "")).toBe("");
    expect(joinInterval(undefined, "", "")).toBe("");
  });

  it("toParametersResource maps intervals to valuePeriod, scalars to valueString", () => {
    const res = toParametersResource({
      "Measurement Period": "2026-01-01T00:00:00.0..2026-12-31T23:59:59.999",
      Payer: "Medicare",
      Empty: "",
    });
    expect(res).toEqual({
      resourceType: "Parameters",
      parameter: [
        {
          name: "Measurement Period",
          valuePeriod: {
            start: "2026-01-01T00:00:00.0",
            end: "2026-12-31T23:59:59.999",
          },
        },
        { name: "Payer", valueString: "Medicare" },
      ],
    });
  });

  it("coerceParam keeps the start..end shape the engine consumes", () => {
    expect(coerceParam("2026-01-01..2026-12-31")).toEqual({
      start: "2026-01-01",
      end: "2026-12-31",
    });
    expect(coerceParam("abc")).toBe("abc");
  });
});
