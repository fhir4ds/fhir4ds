import { describe, expect, it } from "vitest";
import {
  graphToCql,
  type Graph,
} from "../../src/lib/graphToCql";

function nodes(...ns: Graph["nodes"]) {
  return ns;
}

describe("C3-U5: graphToCql emitter", () => {
  it("emits a retrieve→exists population define", () => {
    const g: Graph = {
      nodes: nodes(
        { id: "r1", kind: "Retrieve", data: { label: "Patient" } },
        { id: "e1", kind: "Exists", data: {} },
        { id: "o1", kind: "DefineOutput", data: { label: "Initial Population" } },
      ),
      edges: [
        { source: "r1", target: "e1" },
        { source: "e1", target: "o1" },
      ],
    };
    const cql = graphToCql(g);
    expect(cql).toContain('library Visual version');
    expect(cql).toContain('include FHIRHelpers version');
    expect(cql).toContain('define "Initial Population":');
    expect(cql).toContain("exists [Patient]");
  });

  it("emits where + comparison + literal", () => {
    const g: Graph = {
      nodes: nodes(
        { id: "r1", kind: "Retrieve", data: { label: "Patient" } },
        { id: "p1", kind: "Property", data: { path: "gender" } },
        { id: "l1", kind: "Literal", data: { value: "female" } },
        { id: "c1", kind: "Comparison", data: { operator: "=" } },
        { id: "w1", kind: "Where", data: {} },
        { id: "e1", kind: "Exists", data: {} },
        { id: "o1", kind: "DefineOutput", data: { label: "FemPop" } },
      ),
      edges: [
        { source: "r1", target: "w1" },
        { source: "p1", target: "c1", slot: "left" },
        { source: "l1", target: "c1", slot: "right" },
        { source: "c1", target: "w1" },
        { source: "w1", target: "e1" },
        { source: "e1", target: "o1" },
      ],
    };
    const cql = graphToCql(g);
    // Where-with-predicate lowers through a query with a $this-free path:
    // the Property node without operands emits the bare path.
    expect(cql).toContain("where");
    expect(cql).toContain("= 'female'");
  });

  it("boolean operators combine with parens", () => {
    const g: Graph = {
      nodes: nodes(
        { id: "a", kind: "Literal", data: { value: "true" } },
        { id: "b", kind: "Literal", data: { value: "false" } },
        { id: "and1", kind: "And", data: {} },
        { id: "o", kind: "DefineOutput", data: { label: "X" } },
      ),
      edges: [
        { source: "a", target: "and1", slot: "left" },
        { source: "b", target: "and1", slot: "right" },
        { source: "and1", target: "o" },
      ],
    };
    const cql = graphToCql(g);
    expect(cql).toContain("(true and false)");
  });

  it("is deterministic: identical graphs emit identical bytes (S-C3-C)", () => {
    const g: Graph = {
      nodes: nodes(
        { id: "r1", kind: "Retrieve", data: { label: "Condition" } },
        { id: "e1", kind: "Exists", data: {} },
        { id: "o1", kind: "DefineOutput", data: { label: "HasCond" } },
      ),
      edges: [
        { source: "r1", target: "e1" },
        { source: "e1", target: "o1" },
      ],
    };
    const g2: Graph = {
      nodes: [...g.nodes].reverse(), // node order must not matter
      edges: [...g.edges].reverse(),
    };
    expect(graphToCql(g)).toBe(graphToCql(g2));
  });

  it("throws typed errors for malformed graphs", () => {
    expect(() => graphToCql({ nodes: [], edges: [] })).toThrow(/no DefineOutput/);
    expect(() =>
      graphToCql({
        nodes: nodes(
          { id: "n1", kind: "Not", data: {} },
          { id: "o", kind: "DefineOutput", data: { label: "X" } },
        ),
        edges: [{ source: "n1", target: "o" }],
      }),
    ).toThrow(/malformed subgraph/);
  });

  it("string literals escape single quotes", () => {
    const g: Graph = {
      nodes: nodes(
        { id: "l", kind: "Literal", data: { value: "o'clock" } },
        { id: "o", kind: "DefineOutput", data: { label: "S" } },
      ),
      edges: [{ source: "l", target: "o" }],
    };
    expect(graphToCql(g)).toContain("'o''clock'");
  });
});
