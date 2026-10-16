"""Materialize and score public fixtures with an independent stdlib oracle."""

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from helpers.corpus import package
from helpers.fidelity import (
    accuracy,
    compare,
    digest,
    math_control_colors,
    read_package,
)

from benchmark.cases import scenarios
from docx_color_cli import ColoringError, color_revisions


def evaluate(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    rows = []
    for scenario in scenarios():
        folder = directory / scenario.case.ident
        folder.mkdir(exist_ok=True)
        a = package(
            folder / "tracked.docx", scenario.case.tracked, scenario.tracked_parts
        )
        b = package(
            folder / "accepted.docx", scenario.case.accepted, scenario.accepted_parts
        )
        (folder / "expected.json").write_text(
            json.dumps(scenario.manifest(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        before_hashes = digest(a), digest(b)
        truth = scenario.truth()
        inserted = {k for k, v in truth.items() if v == "INSERTED"}
        for rgb in ("FF0000", "00A060"):
            out = folder / f"colored-{rgb}.docx"
            if scenario.expected_status == "FAILED":
                try:
                    color_revisions(a, b, out, rgb)
                except ColoringError as error:
                    assert error.code == "INVALID_DOCUMENT_PAIR"
                else:
                    raise AssertionError("Incompatible pair published")
                assert not out.exists()
                rows.append(
                    {
                        "id": scenario.case.ident,
                        "color": rgb,
                        "status": "FAILED",
                        "correct_refusal": True,
                        "reason": scenario.omission,
                        "accuracy": None,
                    }
                )
            else:
                result = color_revisions(a, b, out, rgb)
                assert result["overall_status"] == scenario.expected_status, (
                    scenario.case.ident
                )
                checked, before, after = compare(
                    b,
                    out,
                    allowed=inserted,
                    rgb=rgb,
                    mutable_parts=set(scenario.paragraphs()),
                    allowed_math_controls=scenario.controls,
                )
                assert checked["overall"] == "PASS", (scenario.case.ident, checked)
                assert before.keys() == truth.keys(), scenario.case.ident
                for part, paragraphs in scenario.paragraphs().items():
                    for pi, spans in enumerate(paragraphs):
                        authored = "".join(t for t, _ in spans)
                        assert authored == "".join(
                            before[part, pi, i].text for i in range(len(authored))
                        )
                metrics = accuracy(before, after, truth, rgb)
                assert metrics["FP"] == 0
                assert metrics["FN"] == scenario.missed, (scenario.case.ident, metrics)
                assert metrics["TP"] + metrics["FN"] + metrics[
                    "inserted_already_target_noop"
                ] == len(inserted)
                if scenario.missed:
                    assert (
                        result["completeness"]["eligible_characters_uncolored"]
                        + result["completeness"]["other_projected_candidates_uncolored"]
                        >= scenario.missed
                    )
                old_controls = math_control_colors(read_package(b)[1])
                new_controls = math_control_colors(read_package(out)[1])
                edits = {k for k in old_controls if old_controls[k] != new_controls[k]}
                assert edits == scenario.controls
                rows.append(
                    {
                        "id": scenario.case.ident,
                        "color": rgb,
                        "status": result["overall_status"],
                        "reason": scenario.omission,
                        "accuracy": metrics,
                        "fidelity": checked,
                        "math_controls": {
                            "TP": len(edits),
                            "FP": 0,
                            "FN": 0,
                            "TN": len(old_controls) - len(edits),
                        },
                        "unresolved": result["completeness"],
                        "mapping_eligible": result["extraction"][
                            "eligible_inserted_characters"
                        ],
                        "mapping_colored": result["mapping"][
                            "eligible_uniquely_mapped_characters"
                        ],
                        "performance": result["performance"],
                        "output_bytes": out.stat().st_size,
                    }
                )
            assert (digest(a), digest(b)) == before_hashes
    # Fresh control color makes even pre-existing red inserted text observable.
    scored = [r for r in rows if r["color"] == "00A060" and r["accuracy"] is not None]
    totals = {
        k: sum(r["accuracy"][k] for r in scored)
        for k in ("TP", "FP", "FN", "TN", "inserted_already_target_noop")
    }
    totals["precision"] = totals["TP"] / (totals["TP"] + totals["FP"])
    totals["recall"] = totals["TP"] / (totals["TP"] + totals["FN"])
    controls = {
        k: sum(r["math_controls"][k] for r in scored) for k in ("TP", "FP", "FN", "TN")
    }
    result = {
        "label": "Synthetic benchmark results; not universal accuracy",
        "scenarios": 30,
        "valid_pairs_scored": len(scored),
        "invalid_pairs_excluded": 1,
        "metrics": totals,
        "math_controls": controls,
        "unsupported_or_ambiguous_cases": [r["id"] for r in scored if r["reason"]],
        "correct_invalid_pair_refusals": 1,
        "cases": rows,
    }
    (directory / "results.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.output)
    print(json.dumps({k: v for k, v in result.items() if k != "cases"}, indent=2))
