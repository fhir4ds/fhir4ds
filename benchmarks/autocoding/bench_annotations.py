"""Annotations (NER $extract) scaling — in-process, medterm4ds 0.0.10.

Notes are synthesized from Synthea condition/discovery texts at three
length buckets; rungs 100 / 1000 / 10000 notes per bucket (10k only for
the medium bucket to bound runtime). Runs under the numpy<2 venv
(scispaCy/thinc binary compat).

Also measures the batched extract(text_list) path vs per-note calls.
"""
import json, random, statistics, sys, time
from pathlib import Path

HERE = Path(__file__).parent
WORKLOAD = HERE / "workload.ndjson"

SYNTH_SEED = 42


def build_notes():
    """Synthesize clinically-plausible notes from Synthea texts.

    Returns per bucket a GENERATOR of distinct notes (rotation offset
    varies each note) so per-note caching cannot flatter throughput.
    """
    texts = [json.loads(l)["text"] for l in WORKLOAD.open()]
    texts = [t for t in texts if len(t) > 15]
    random.seed(SYNTH_SEED)
    random.shuffle(texts)

    def note_at(offset, target_words):
        words, n, i = [], 0, offset
        while n < target_words:
            chunk = texts[i % len(texts)]
            i += 1
            words.append(chunk)
            n += len(chunk.split())
        return ". ".join(words) + "."

    def gen(target_words):
        off = 0
        while True:
            yield note_at(off, target_words)
            off += 37  # co-prime stride: every note distinct

    return {
        "sentence": gen(15),
        "medium_200w": gen(200),
        "long_2000w": gen(2000),
    }


def main():
    from medterm4ds.services.extraction import extract

    templates = build_notes()
    sample = {k: next(g) for k, g in templates.items()}
    print("note lengths (words):",
          {k: len(v.split()) for k, v in sample.items()}, flush=True)

    results = []
    # Rung sizes tuned to measured per-note cost (~230ms sentence, ~2.2s/200w,
    # ~12s/2000w) so the whole ladder stays under ~45 min.
    # Per-note guard: two input-dependent crash classes exist in the NER
    # dependency stack (PyRuSH UnboundLocalError — one observed heap
    # corruption; medspaCy ConText TypeError) and they are non-deterministic
    # across replays. Guard, count, continue.
    RUNGS = {
        "sentence": [100, 1000, 10000],
        "medium_200w": [100, 300],
        "long_2000w": [20, 50],
    }
    for bucket, note_iter in templates.items():
        for n in RUNGS[bucket]:
            note = next(note_iter)  # sample note for word count
            t0 = time.perf_counter()
            n_concepts, n_err = 0, 0
            for i in range(n):
                body = next(note_iter)
                try:
                    res = extract(body, include_family=True,
                                  include_historical=True,
                                  include_uncertain=True)
                    n_concepts += len(res) if isinstance(res, list) else 0
                except Exception:
                    n_err += 1
            wall = time.perf_counter() - t0
            m = {
                "label": f"{bucket}_{n}",
                "notes": n,
                "words_per_note": len(note.split()),
                "concepts_per_note": round(n_concepts / n, 1),
                "wall_s": round(wall, 2),
                "notes_per_s": round(n / wall, 1),
                "ms_per_note": round(wall / n * 1000, 1),
            }
            print(json.dumps(m), flush=True)
            results.append(m)

    # Batched path on the sentence bucket (engine-side batching)
    batch_notes = [next(templates["sentence"]) for _ in range(1000)]
    for n in (100, 1000):
        payload = batch_notes[:n]
        t0 = time.perf_counter()
        res = extract(payload, include_family=True, include_historical=True,
                      include_uncertain=True)
        wall = time.perf_counter() - t0
        m = {
            "label": f"batched_sentence_{n}",
            "notes": n,
            "words_per_note": len(payload[0].split()),
            "wall_s": round(wall, 2),
            "notes_per_s": round(n / wall, 1),
            "ms_per_note": round(wall / n * 1000, 1),
        }
        print(json.dumps(m), flush=True)
        results.append(m)

    out = {
        "benchmark": "annotations_ner_scaling",
        "date": time.strftime("%Y-%m-%d"),
        "engine": "medterm4ds.services.extraction.extract (NER cascade, in-process)",
        "medterm4ds_version": "0.0.10",
        "flags": {"include_family": True, "include_historical": True,
                  "include_uncertain": True},
        "runs": results,
    }
    (HERE / "results_annotations.json").write_text(json.dumps(out, indent=1))
    print("\nwrote", HERE / "results_annotations.json")


if __name__ == "__main__":
    main()
