"""Table boundaries and independently authored character truth, not status alone."""

import pytest
from helpers.corpus import package
from helpers.fidelity import accuracy, compare, digest
from helpers.table_cases import cases

from docx_color_cli import ColoringError, color_revisions


@pytest.mark.parametrize(
    "case,missed,invalid", cases(), ids=lambda c: getattr(c, "ident", None)
)
def test_table_character_provenance(tmp_path, case, missed, invalid):
    tracked = package(tmp_path / "tracked.docx", case.tracked)
    accepted = package(tmp_path / "accepted.docx", case.accepted)
    hashes = digest(tracked), digest(accepted)
    truth = case.truth()
    for color in ("FF0000", "00A060"):
        output = tmp_path / f"out-{color}.docx"
        if invalid:
            output.write_bytes(b"existing output")
            with pytest.raises(ColoringError) as error:
                color_revisions(tracked, accepted, output, color)
            assert error.value.code == "INVALID_DOCUMENT_PAIR"
            assert output.read_bytes() == b"existing output"
        else:
            result = color_revisions(tracked, accepted, output, color)
            checked, before, after = compare(
                accepted,
                output,
                allowed={k for k, v in truth.items() if v == "INSERTED"},
                rgb=color,
            )
            assert checked["overall"] == "PASS", checked
            assert before.keys() == truth.keys()
            for pi, spans in enumerate(case.expected):
                text = "".join(t for t, _ in spans)
                assert text == "".join(
                    before["word/document.xml", pi, i].text for i in range(len(text))
                )
            counts = accuracy(before, after, truth, color)
            assert counts["FP"] == 0
            assert counts["FN"] == missed
            assert result["publication_status"] == "SUCCESS"
            if missed:
                assert result["overall_status"] == "PARTIAL"
                assert (
                    result["completeness"]["eligible_characters_uncolored"]
                    + result["completeness"]["other_projected_candidates_uncolored"]
                    >= missed
                )
        assert (digest(tracked), digest(accepted)) == hashes
    assert not list(tmp_path.glob("*.tmp"))
