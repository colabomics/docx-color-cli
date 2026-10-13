import pytest
from helpers.assertions import assert_integrity, xml_part
from helpers.fixtures import M, W, p, revision

from docx_color_cli.cli import convert


@pytest.mark.parametrize(
    "middle,expected",
    [
        (
            revision("ins", "<m:t>B</m:t>"),
            [("A", "000000"), ("B", "FF0000"), ("C", "000000")],
        ),
        (revision("del", "<m:t>B</m:t>"), [("A", "000000"), ("C", "000000")]),
        (
            revision("ins", "<m:t>B</m:t>" + revision("del", "<m:t>gone</m:t>")),
            [("A", "000000"), ("B", "FF0000"), ("C", "000000")],
        ),
    ],
)
def test_mixed_math_run_split_preserves_properties(docx, tmp_path, middle, expected):
    content = (
        '<m:oMath><m:r><m:rPr><m:sty m:val="p"/></m:rPr><w:rPr><w:rFonts w:ascii="Cambria Math"/><w:sz w:val="24"/></w:rPr><m:t>A</m:t>'
        + middle
        + "<m:t>C</m:t></m:r></m:oMath>"
    )
    source = docx("in.docx", p(content))
    before = source.read_bytes()
    target = tmp_path / "out.docx"
    convert(source, target)
    runs = list(xml_part(target).iter(M + "r"))
    assert [
        (r.find(M + "t").text, r.find(W + "rPr/" + W + "color").get(W + "val"))
        for r in runs
    ] == expected
    for r in runs:
        assert r.find(M + "rPr/" + M + "sty").get(M + "val") == "p"
        assert r.find(W + "rPr/" + W + "rFonts").get(W + "ascii") == "Cambria Math"
        assert r.find(W + "rPr/" + W + "sz").get(W + "val") == "24"
    assert source.read_bytes() == before
    assert_integrity(target)
