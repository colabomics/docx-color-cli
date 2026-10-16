"""Run the supported package as the system under test; expected labels stay external."""

import json
from pathlib import Path

from helpers.corpus import cases, materialize
from helpers.fidelity import accuracy, compare, digest
from helpers.oracle import corroborate


def aggregate(rows):
    counts = {
        k: sum(r[k] for r in rows)
        for k in (
            "TP",
            "FP",
            "FN",
            "TN",
            "inserted_already_target_noop",
            "labeled_characters",
        )
    }
    tp, fp, fn, tn = (counts[k] for k in ("TP", "FP", "FN", "TN"))
    return {
        **counts,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "false_positive_rate": fp / (fp + tn) if fp + tn else None,
        "false_negative_rate": fn / (fn + tp) if fn + tp else None,
    }


def evaluate_corpus(directory):
    from docx_color_cli.engine import (
        convert,  # System under test ONLY, never expected truth.
    )

    directory = Path(directory)
    manifest = materialize(directory)
    rows = []
    for case in cases():
        folder = directory / case.ident
        tracked, accepted = folder / "tracked.docx", folder / "accepted.docx"
        hashes = [digest(tracked), digest(accepted)]
        truth = case.truth()
        allowed = {k for k, label in truth.items() if label == "INSERTED"}
        row = {"id": case.ident, "name": case.name}
        for name, rgb in (("default", "FF0000"), ("control", "00A060")):
            colored = folder / f"colored-{name}.docx"
            conversion = convert(tracked, accepted, colored, inserted_color=rgb)
            fidelity, before, after = compare(
                accepted, colored, allowed=allowed, rgb=rgb
            )
            assert before.keys() == truth.keys(), "Gold corpus missing character labels"
            for pi, paragraph in enumerate(case.manifest()["paragraphs"]):
                observed = "".join(
                    before["word/document.xml", pi, i].text
                    for i in range(len(paragraph["labels"]))
                )
                assert observed == paragraph["text"], (
                    "Authored expected text differs from accepted fixture"
                )
            row[name] = {
                "accuracy": accuracy(before, after, truth, rgb),
                "fidelity": fidelity,
                "reported_selected_characters": conversion["coloring"][
                    "characters_colored"
                ],
            }
        labels, _, summary = corroborate(tracked, accepted)
        row["level_b_against_gold"] = {
            **summary,
            "disagreements": sum(truth[k] != label for k, label in labels.items()),
        }
        row["input_hashes_unchanged"] = hashes == [digest(tracked), digest(accepted)]
        rows.append(row)
    result = {
        "evidence_level": "A_AUTHORED_SYNTHETIC",
        "word_generated": False,
        "case_count": len(rows),
        "default_metrics": aggregate([r["default"]["accuracy"] for r in rows]),
        "control_metrics": aggregate([r["control"]["accuracy"] for r in rows]),
        "cases": rows,
    }
    (directory / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    return result, manifest
