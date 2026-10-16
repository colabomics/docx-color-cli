"""One focused public benchmark; expectations come from authored provenance."""

import json
from pathlib import Path

from benchmark.cases import scenarios
from benchmark.run import evaluate


def test_manifest_is_authored_corpus_metadata():
    expected = json.loads(
        (Path(__file__).parent / "benchmark/manifest.json").read_text(encoding="utf-8")
    )
    assert expected == json.loads(json.dumps([s.manifest() for s in scenarios()]))


def test_public_benchmark(tmp_path):
    result = evaluate(tmp_path)
    assert result["metrics"]["FP"] == 0
    assert result["metrics"]["inserted_already_target_noop"] == 0
    assert result["math_controls"]["FP"] == 0
    assert result["correct_invalid_pair_refusals"] == 1
