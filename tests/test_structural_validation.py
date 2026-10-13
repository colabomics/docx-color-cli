import pytest
from helpers.assertions import assert_rejects_without_output
from helpers.fixtures import p, run

from docx_color_cli.cli import convert


@pytest.mark.parametrize(
    "body",
    [
        p("<m:oMath><m:sSup><m:e/></m:sSup></m:oMath>"),
        p("<m:oMath><m:rad><m:deg/><m:e/><m:e/></m:rad></m:oMath>"),
        "<w:tbl><w:tr><w:tc><w:tcPr><w:vMerge/></w:tcPr>"
        + p(run("A"))
        + "</w:tc></w:tr></w:tbl>",
        '<w:tbl><w:tr><w:tc><w:tcPr><w:gridSpan w:val="0"/></w:tcPr>'
        + p(run("A"))
        + "</w:tc></w:tr></w:tbl>",
    ],
)
def test_malformed_retained_structure_refused(docx, tmp_path, body):
    assert_rejects_without_output(convert, docx("in.docx", body), tmp_path / "out.docx")
