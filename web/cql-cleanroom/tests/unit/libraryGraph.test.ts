import { describe, expect, it } from "vitest";
import { libraryClosure } from "../../src/lib/libraryGraph";

describe("libraryClosure (6f measure primary-library graph)", () => {
  const LIBS = [
    {
      name: "Main",
      text: `library Main version '1.0.0'
include Mid
valueset "BP" : 'urn:vs:bp'
valueset "Shared"='urn:vs:shared'`,
    },
    {
      name: "Mid",
      text: `library Mid
include Leaf called L
valueset "Shared": 'urn:vs:shared'
valueset "Mid Only": 'urn:vs:midonly'`,
    },
    { name: "Leaf", text: "library Leaf\nvalueset \"Leaf VS\": 'urn:vs:leaf'" },
    { name: "Unrelated", text: "library Unrelated" },
  ];

  it("walks multi-level includes BFS-first from the primary", () => {
    const { libraryNames } = libraryClosure(LIBS, "Main");
    expect(libraryNames).toEqual(["Main", "Mid", "Leaf"]);
  });

  it("collects valueset declarations across the closure, deduped by url", () => {
    const { valuesetDecls } = libraryClosure(LIBS, "Main");
    expect(valuesetDecls.map((v) => v.url)).toEqual([
      "urn:vs:bp",
      "urn:vs:shared",
      "urn:vs:midonly",
      "urn:vs:leaf",
    ]);
    expect(valuesetDecls.find((v) => v.url === "urn:vs:shared")?.name).toBe(
      "Shared",
    );
  });

  it("skips missing dependencies without throwing", () => {
    const { libraryNames, valuesetDecls } = libraryClosure(
      [{ name: "Solo", text: "include Ghost\nvalueset \"A\": 'urn:a'" }],
      "Solo",
    );
    expect(libraryNames).toEqual(["Solo"]);
    expect(valuesetDecls).toHaveLength(1);
  });

  it("an unknown primary yields an empty closure", () => {
    expect(libraryClosure(LIBS, "Nope")).toEqual({
      libraryNames: [],
      valuesetDecls: [],
    });
  });
});
