"""Generic character provenance, field boundaries and hyperlink equivalence."""

import pytest
from helpers.corpus import package
from helpers.fidelity import accuracy, compare, digest
from helpers.field_cases import cases, relationships

from docx_color_cli import color_revisions


@pytest.mark.parametrize(
    "case,missed,target_uri", cases(), ids=lambda v: getattr(v, "ident", None)
)
def test_field_and_hyperlink_truth(tmp_path, case, missed, target_uri):
    a = package(tmp_path / "source.docx", case.tracked, relationships())
    b = package(tmp_path / "reference.docx", case.accepted, relationships(target_uri))
    hashes = digest(a), digest(b)
    truth = case.truth()
    for rgb in ["FF0000", "00A060"]:
        out = tmp_path / f"out-{rgb}.docx"
        result = color_revisions(a, b, out, rgb)
        checked, before, after = compare(
            b, out, allowed={k for k, v in truth.items() if v == "INSERTED"}, rgb=rgb
        )
        assert checked["overall"] == "PASS"
        assert before.keys() == truth.keys()
        for pi, spans in enumerate(case.expected):
            expected = "".join(t for t, _ in spans)
            assert expected == "".join(
                before["word/document.xml", pi, i].text for i in range(len(expected))
            )
        counts = accuracy(before, after, truth, rgb)
        assert counts["FP"] == 0
        assert counts["FN"] == missed
        assert result["overall_status"] == ("PARTIAL" if missed else "SUCCESS")
        assert (digest(a), digest(b)) == hashes
