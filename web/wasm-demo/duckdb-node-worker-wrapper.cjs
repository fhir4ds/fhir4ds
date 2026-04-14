/**
 * Node.js worker wrapper for @duckdb/duckdb-wasm async API.
 *
 * DuckDB's node worker uses globalThis.onmessage / globalThis.postMessage,
 * which do not exist in worker_threads. This shim bridges the worker_threads
 * message channel to the globalThis interface that the DuckDB worker expects.
 */
"use strict";
const { parentPort } = require("worker_threads");

// Bridge parentPort → globalThis.postMessage (DuckDB worker sends responses)
globalThis.postMessage = (data, transfer) => {
  if (transfer && transfer.length) {
    parentPort.postMessage(data, transfer);
  } else {
    parentPort.postMessage(data);
  }
};

// Bridge parentPort → globalThis.onmessage (DuckDB worker receives requests)
parentPort.on("message", (data) => {
  if (typeof globalThis.onmessage === "function") {
    globalThis.onmessage({ data });
  }
});

// Load the actual DuckDB node worker
require("@duckdb/duckdb-wasm/dist/duckdb-node-eh.worker.cjs");
