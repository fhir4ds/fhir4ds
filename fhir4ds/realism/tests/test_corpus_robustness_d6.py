"""D6 SKEPTIC v0.0.26 — realism corpus loader robustness (QA-D6S-001..003).

Red-first regressions for the corpus loader's public error contract:

* QA-D6S-001 — ``_sorted`` crashed with a raw ``TypeError`` when a
  resource carried a non-string ``id`` (structurally-valid JSON,
  invalid FHIR); the loader is tolerance-first and must keep loading
  with a deterministic (str-coerced) ordering key.
* QA-D6S-002 — ``_read_text`` leaked raw ``gzip.BadGzipFile`` /
  ``UnicodeDecodeError`` with no file attribution; corrupt inputs must
  raise ``ValueError`` naming the file.
* QA-D6S-003 — ``load_bundle_file`` on a ``.json`` file holding a JSONL
  stream of Bundles raised a raw ``JSONDecodeError`` although the
  method's own docstring promises "JSONL bundle stream" support (the
  directory path documents the same fallback). Additionally, Bundle
  lines in JSONL/NDJSON streams were appended UNFLATTENED, so their
  entries were invisible to every downstream consumer — single-document
  Bundles are flattened, streamed ones must be too.
"""

from __future__ import annotations

import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fhir4ds.realism.corpus import load_bundle_file, load_corpus


class TestEvolV0026D6Skeptic(unittest.TestCase):
    def test_non_string_id_loads_with_deterministic_order(self):
        with TemporaryDirectory() as td:
            d = Path(td)
            (d / "P.ndjson").write_text(
                '{"resourceType":"Patient","id":5}\n'
                '{"resourceType":"Patient","id":"abc"}\n'
                '{"resourceType":"Observation"}\n')
            out = load_corpus(d)
        self.assertEqual(len(out), 3)
        self.assertEqual([r.get("resourceType") for r in out],
                         ["Observation", "Patient", "Patient"])

    def test_corrupt_gz_raises_value_error_naming_file(self):
        with TemporaryDirectory() as td:
            d = Path(td)
            (d / "bad.ndjson.gz").write_bytes(b"not gzip data at all")
            with self.assertRaises(ValueError) as ctx:
                load_corpus(d)
            self.assertIn("bad.ndjson.gz", str(ctx.exception))

    def test_invalid_utf8_raises_value_error_naming_file(self):
        with TemporaryDirectory() as td:
            d = Path(td)
            (d / "x.ndjson").write_bytes(
                b'{"resourceType":"Patient","id":"\xff\xfe"}\n')
            with self.assertRaises(ValueError) as ctx:
                load_corpus(d)
            self.assertIn("x.ndjson", str(ctx.exception))

    def test_valid_gz_still_loads(self):
        with TemporaryDirectory() as td:
            d = Path(td)
            payload = json.dumps({"resourceType": "Patient", "id": "p1"}) + "\n"
            (d / "P.ndjson.gz").write_bytes(gzip.compress(payload.encode()))
            out = load_corpus(d)
        self.assertEqual([r["id"] for r in out], ["p1"])

    def test_jsonl_bundle_stream_single_file(self):
        b1 = {"resourceType": "Bundle", "entry": [
            {"resource": {"resourceType": "Patient", "id": "p1"}}]}
        b2 = {"resourceType": "Bundle", "entry": [
            {"resource": {"resourceType": "Patient", "id": "p2"}}]}
        with TemporaryDirectory() as td:
            f = Path(td) / "stream.json"
            f.write_text(json.dumps(b1) + "\n" + json.dumps(b2) + "\n")
            out = load_bundle_file(f)
        # Bundles in a stream are FLATTENED like single-document Bundles.
        self.assertEqual(sorted(r["id"] for r in out), ["p1", "p2"])

    def test_jsonl_bundle_stream_via_directory(self):
        b1 = {"resourceType": "Bundle", "entry": [
            {"resource": {"resourceType": "Patient", "id": "p1"}}]}
        plain = {"resourceType": "Observation", "id": "o1"}
        with TemporaryDirectory() as td:
            d = Path(td)
            (d / "stream.json").write_text(json.dumps(b1) + "\n" + json.dumps(plain) + "\n")
            out = load_corpus(d)
        self.assertEqual(sorted((r["resourceType"], r["id"]) for r in out),
                         [("Observation", "o1"), ("Patient", "p1")])

    def test_ndjson_bundle_lines_flatten(self):
        b = {"resourceType": "Bundle", "entry": [
            {"resource": {"resourceType": "Patient", "id": "deep"}}]}
        with TemporaryDirectory() as td:
            d = Path(td)
            (d / "B.ndjson").write_text(json.dumps(b) + "\n")
            out = load_corpus(d)
        self.assertEqual([(r["resourceType"], r["id"]) for r in out],
                         [("Patient", "deep")])

    def test_single_doc_bundle_still_flattens(self):
        b = {"resourceType": "Bundle", "entry": [
            {"resource": {"resourceType": "Patient", "id": "p1"}}]}
        with TemporaryDirectory() as td:
            f = Path(td) / "b.json"
            f.write_text(json.dumps(b))
            out = load_bundle_file(f)
        self.assertEqual([r["id"] for r in out], ["p1"])


if __name__ == "__main__":
    unittest.main()
