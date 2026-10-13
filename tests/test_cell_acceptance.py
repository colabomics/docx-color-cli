import pytest
from helpers.assertions import (
    assert_integrity,
    assert_rejects_without_output,
    assert_segments,
    text,
    xml_part,
)
from helpers.fixtures import W, insert, p, run

from docx_color_cli.cli import convert


def cell(content="", props=""):
    return "<w:tc><w:tcPr>" + props + "</w:tcPr>" + p(content) + "</w:tc>"


def row(cells, props=""):
    return "<w:tr><w:trPr>" + props + "</w:trPr>" + cells + "</w:tr>"


def table(rows, columns=2):
    return (
        "<w:tbl><w:tblGrid>"
        + '<w:gridCol w:w="1000"/>' * columns
        + "</w:tblGrid>"
        + rows
        + "</w:tbl>"
    )


def test_cell_insert_delete_preserve_order_and_color(docx, tmp_path):
    body = table(
        row(
            cell(run("A"))
            + cell(run("gone"), '<w:cellDel w:id="1"/>')
            + cell(insert("B"), '<w:cellIns w:id="2"/>')
        )
    )
    target = tmp_path / "out.docx"
    convert(docx("in.docx", body), target)
    root = xml_part(target)
    assert [text(n) for n in root.iter(W + "tc")] == ["A", "B"]
    assert len(list(root.iter(W + "gridCol"))) == 2
    assert_segments(root, [("A", "000000"), ("B", "FF0000")])
    assert_integrity(target)


@pytest.mark.parametrize("state,expected", [("cont", "continue"), ("rest", "restart")])
def test_cell_merge_state_acceptance(docx, tmp_path, state, expected):
    body = table(
        row(cell(run("A"), '<w:vMerge w:val="restart"/>'))
        + row(
            cell("", f'<w:cellMerge w:id="1" w:vMerge="{state}" w:vMergeOrig="cont"/>')
        ),
        1,
    )
    target = tmp_path / "out.docx"
    convert(docx("in.docx", body), target)
    cells = list(xml_part(target).iter(W + "tc"))
    assert cells[1].find(W + "tcPr/" + W + "vMerge").get(W + "val") == expected
    assert [text(c) for c in cells] == ["A", ""]
    assert_integrity(target)


def test_deleted_continuation_row_preserves_merge(docx, tmp_path):
    body = table(
        row(cell(run("A"), '<w:vMerge w:val="restart"/>'))
        + row(cell("", "<w:vMerge/>"), '<w:del w:id="1"/>')
        + row(cell("", "<w:vMerge/>")),
        1,
    )
    target = tmp_path / "out.docx"
    convert(docx("in.docx", body), target)
    assert len(list(xml_part(target).iter(W + "tr"))) == 2
    assert_segments(xml_part(target), [("A", "000000")])
    assert_integrity(target)


def test_deleted_merge_owner_with_live_continuation_is_rejected(docx, tmp_path):
    body = table(
        row(cell(run("owner"), '<w:vMerge w:val="restart"/>'), '<w:del w:id="1"/>')
        + row(cell(run("live"), "<w:vMerge/>")),
        1,
    )
    assert_rejects_without_output(convert, docx("in.docx", body), tmp_path / "out.docx")


def test_cell_delete_with_unresolved_horizontal_span_refused(docx, tmp_path):
    body = table(
        row(
            cell(run("A")) + cell(run("gone"), '<w:cellDel w:id="1"/>') + cell(run("B"))
        ),
        3,
    )
    assert_rejects_without_output(convert, docx("in.docx", body), tmp_path / "out.docx")


def test_inserted_merge_continuation_with_equation_is_not_assumed_empty(docx, tmp_path):
    from helpers.fixtures import fraction

    body = table(
        row(cell(run("owner"), '<w:vMerge w:val="restart"/>'))
        + row(cell(fraction(), "<w:vMerge/>"), '<w:ins w:id="1"/>'),
        1,
    )
    assert_rejects_without_output(convert, docx("in.docx", body), tmp_path / "out.docx")
