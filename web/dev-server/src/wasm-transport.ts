/**
 * WasmTransport: compile-time-checked fixture proving the Transport seam
 * stays engine-agnostic (the wasm-demo in-browser engine could implement
 * it). Not wired into the dev-server UI; exists so refactors that touch
 * Transport must keep both shapes valid.
 */
import type { Transport } from "./transport";

export type WasmTransportContract = Transport;

export class WasmTransport {
  // Intentionally skeletal: the fixture's contract is "the interface can
  // be implemented without HTTP", nothing more.
  readonly engine = "wasm";
}
