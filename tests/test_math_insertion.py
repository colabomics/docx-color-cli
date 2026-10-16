"""Authored elementary math truth and exact non-color structural preservation."""

import pytest
from helpers.corpus import package
from helpers.fidelity import accuracy, compare, digest
from helpers.math_cases import cases
from helpers.math_oracle import corroborate_math

from docx_color_cli import color_revisions


@pytest.mark.parametrize(
    "case,controls,missed,missed_controls",
    cases(),
    ids=lambda v: getattr(v, "ident", None),
)
def test_math_truth(tmp_path, case, controls, missed, missed_controls):
    a = package(tmp_path / "source.docx", case.tracked)
    b = package(tmp_path / "reference.docx", case.accepted)
    hashes = digest(a), digest(b)
    truth = case.truth()
    allowed = {k for k, v in truth.items() if v == "INSERTED"}
    controls = {("word/document.xml", e, c) for e, c in controls}
    for rgb in ["FF0000", "00A060"]:
        out = tmp_path / f"out-{rgb}.docx"
        result = color_revisions(a, b, out, rgb)
        checked, before, after = compare(
            b, out, allowed=allowed, rgb=rgb, allowed_math_controls=controls
        )
        assert checked["overall"] == "PASS"
        assert checked["math_control_color_edits"] == len(controls)
        assert before.keys() == truth.keys()
        for pi, spans in enumerate(case.expected):
            text = "".join(t for t, _ in spans)
            assert text == "".join(
                before["word/document.xml", pi, i].text for i in range(len(text))
            )
        metrics = accuracy(before, after, truth, rgb)
        assert metrics["FP"] == 0
        assert metrics["FN"] == missed
        assert result["mathematics"]["uncolored_inserted_controls"] == missed_controls
        assert result["overall_status"] == (
            "PARTIAL" if missed or missed_controls else "SUCCESS"
        )
        assert (digest(a), digest(b)) == hashes
    labels, evidence = corroborate_math(a, b)
    assert all(truth[k] == label for k, label in labels.items())
    assert evidence["independent_human_truth"] is False
