/** Shared synthetic MADiE-shaped zip builders for e2e + probes. */
import * as zlib from "node:zlib";

// Minimal ZIP writer (store method) — avoids a dev dependency.
function crc32(buf: Buffer): number {
  let c: number;
  const table: number[] = [];
  for (let n = 0; n < 256; n++) {
    c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c >>> 0;
  }
  let crc = 0xffffffff;
  for (const b of buf) crc = table[(crc ^ b) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

function zipEntry(name: string, data: Buffer): Buffer {
  const nameBuf = Buffer.from(name, "utf8");
  const crc = crc32(data);
  const local = Buffer.alloc(30);
  local.writeUInt32LE(0x04034b50, 0);
  local.writeUInt16LE(20, 4); // version
  local.writeUInt16LE(0, 6); // flags
  local.writeUInt16LE(0, 8); // store
  local.writeUInt16LE(0, 10); // time
  local.writeUInt16LE(0x21, 12); // date (1996-01-01, deterministic)
  local.writeUInt32LE(crc, 14);
  local.writeUInt32LE(data.length, 18);
  local.writeUInt32LE(data.length, 22);
  local.writeUInt16LE(nameBuf.length, 26);
  local.writeUInt16LE(0, 28);
  return Buffer.concat([local, nameBuf, data]);
}

function centralEntry(name: string, data: Buffer, offset: number): Buffer {
  const nameBuf = Buffer.from(name, "utf8");
  const crc = crc32(data);
  const c = Buffer.alloc(46);
  c.writeUInt32LE(0x02014b50, 0);
  c.writeUInt16LE(20, 4);
  c.writeUInt16LE(20, 6);
  c.writeUInt16LE(0, 8);
  c.writeUInt16LE(0, 10);
  c.writeUInt16LE(0, 12);
  c.writeUInt16LE(0x21, 14);
  c.writeUInt32LE(crc, 16);
  c.writeUInt32LE(data.length, 20);
  c.writeUInt32LE(data.length, 24);
  c.writeUInt16LE(nameBuf.length, 28);
  c.writeUInt32LE(offset, 42);
  return Buffer.concat([c, nameBuf]);
}

export function makeZip(files: Record<string, string>): Buffer {
  const locals: Buffer[] = [];
  const centrals: Buffer[] = [];
  let offset = 0;
  for (const [name, text] of Object.entries(files)) {
    const data = Buffer.from(text, "utf8");
    const l = zipEntry(name, data);
    locals.push(l);
    centrals.push(centralEntry(name, data, offset));
    offset += l.length;
  }
  const body = Buffer.concat(locals);
  const cd = Buffer.concat(centrals);
  const end = Buffer.alloc(22);
  const n = Object.keys(files).length;
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(n, 8); // entries on this disk
  end.writeUInt16LE(n, 10); // total entries
  end.writeUInt32LE(cd.length, 12); // central directory size
  end.writeUInt32LE(body.length, 16); // central directory offset
  void zlib; // (kept import-free on purpose)
  return Buffer.concat([body, cd, end]);
}

export function buildMadieTestsZip(): Buffer {
  const isTestCases = {
    url: "http://hl7.org/fhir/us/cqf-measures/StructureDefinition/cqfm-isTestCases",
    valueBoolean: true,
  };
  const mkcase = (pid: string) => ({
    resourceType: "Bundle",
    type: "collection",
    entry: [
      { resource: { resourceType: "Patient", id: pid, gender: "male" } },
      {
        resource: {
          resourceType: "MeasureReport",
          status: "complete",
          type: "individual",
          measure: "http://example.org/TestMeasure|1.0.0",
          subject: { reference: `Patient/${pid}` },
          modifierExtension: [isTestCases],
          group: [
            {
              id: "g1",
              population: [
                {
                  id: "Initial Population",
                  code: { coding: [{ code: "initial-population" }] },
                  count: 1,
                },
              ],
            },
          ],
        },
      },
    ],
  });
  return makeZip({
    "patient-1/TestMeasure-v1.0.000-Case1.json": JSON.stringify(mkcase("patient-1")),
    "patient-2/TestMeasure-v1.0.000-Series1-Case2.json": JSON.stringify(mkcase("patient-2")),
  });
}
