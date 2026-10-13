import pytest
from helpers.assertions import (
    assert_integrity,
    assert_rejects_without_output,
    assert_segments,
    paragraphs,
    text,
    xml_part,
    xml_without_font_colors,
)
from helpers.fixtures import (
    PNG,
    M,
    W,
    delete,
    field,
    fraction,
    image_run,
    insert,
    p,
    relationships,
    run,
    story,
)
from lxml import etree

from docx_color_cli.cli import convert

MARK = '<w:rPr><w:del w:id="1"/></w:rPr>'


@pytest.mark.parametrize(
    "props",
    [
        "",
        '<w:pStyle w:val="Heading1"/>',
        '<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>',
    ],
)
def test_CF002_chained_merges_preserve_order_and_properties(docx, tmp_path, props):
    source = docx(
        "source.docx",
        p(run("A ") + delete("gone"), props + MARK)
        + p(insert("B "), props + MARK)
        + p(run("C"), props),
    )
    target = tmp_path / "out.docx"
    convert(source, target)
    assert paragraphs(target) == ["A B C"]
    assert_segments(
        xml_part(target), [("A ", "000000"), ("B ", "FF0000"), ("C", "000000")]
    )
    for tag in ("pStyle", "numPr"):
        assert len(xml_part(target).findall(".//" + W + tag)) == int(tag in props)
    assert_integrity(target)


def test_CF002_merge_preserves_zotero_math_image_and_hyperlink(docx, tmp_path):
    left = (
        field(' ADDIN ZOTERO_ITEM CSL_CITATION {"id":"sample"} ', run("(1)"))
        + fraction()
        + image_run()
    )
    right = '<w:hyperlink r:id="link">' + insert("article") + "</w:hyperlink>"
    parts = {
        "word/media/pixel.png": PNG,
        "word/_rels/document.xml.rels": relationships(
            [
                ("image1", "image", "media/pixel.png", False),
                ("link", "hyperlink", "https://example.org", True),
            ]
        ),
    }
    source = docx("source.docx", p(left, MARK) + p(right), parts)
    target = tmp_path / "out.docx"
    convert(source, target)
    root = xml_part(target)
    assert len(root.findall(".//" + W + "p")) == 1
    assert_segments(root, [("(1)", "000000"), ("article", "FF0000")])
    assert [n.text for n in root.iter(W + "instrText")] == [
        ' ADDIN ZOTERO_ITEM CSL_CITATION {"id":"sample"} '
    ]
    for tag in (M + "oMath", W + "drawing"):
        serialize = xml_without_font_colors if tag == M + "oMath" else etree.tostring
        assert serialize(root.find(".//" + tag)) == serialize(
            xml_part(source).find(".//" + tag)
        )
    assert_integrity(target)


@pytest.mark.parametrize(
    "body",
    [
        p(run("A"), MARK),
        p(run("A"), MARK)
        + "<w:tbl><w:tr><w:tc>"
        + p(run("B"))
        + "</w:tc></w:tr></w:tbl>",
        p(run("A"), "<w:sectPr/>" + MARK) + p(run("B")),
        "<w:tbl><w:tr><w:tc>"
        + p(run("A"), MARK)
        + "</w:tc><w:tc>"
        + p(run("B"))
        + "</w:tc></w:tr></w:tbl>",
    ],
    ids=["terminal", "table-boundary", "section-boundary", "cell-boundary"],
)
def test_CF002_ambiguous_merge_refused(docx, tmp_path, body):
    assert_rejects_without_output(
        convert, docx("source.docx", body), tmp_path / "out.docx"
    )


def row(content, mark="", cell_props=""):
    return (
        "<w:tr>"
        + ("<w:trPr>" + mark + "</w:trPr>" if mark else "")
        + "<w:tc><w:tcPr>"
        + cell_props
        + "</w:tcPr>"
        + p(content)
        + "</w:tc></w:tr>"
    )


def test_CF003_delete_rows_and_retain_editable_objects(docx, tmp_path):
    body = (
        '<w:tbl><w:tblGrid><w:gridCol w:w="2000"/></w:tblGrid>'
        + row(run("gone"), '<w:del w:id="1"/>')
        + row(field(" REF target ", run("kept")) + fraction())
        + row(insert("new"), '<w:ins w:id="2"/>')
        + "</w:tbl>"
    )
    source = docx("source.docx", body)
    target = tmp_path / "out.docx"
    convert(source, target)
    root = xml_part(target)
    assert [text(r) for r in root.iter(W + "tr")] == ["keptxy", "new"]
    assert_segments(root, [("kept", "000000"), ("new", "FF0000")])
    assert len(list(root.iter(M + "f"))) == 1
    assert len(list(root.iter(W + "fldChar"))) == 3
    assert_integrity(target)


@pytest.mark.parametrize("mark", ["ins", "del"])
def test_CF003_vertical_merge_row_revision(docx, tmp_path, mark):
    body = (
        "<w:tbl>"
        + row(run("A"), "", '<w:vMerge w:val="restart"/>')
        + row(run("B"), f'<w:{mark} w:id="1"/>', "<w:vMerge/>")
        + "</w:tbl>"
    )
    if mark == "ins":
        assert_rejects_without_output(
            convert, docx("source.docx", body), tmp_path / "out.docx"
        )
    else:
        target = tmp_path / "out.docx"
        convert(docx("source.docx", body), target)
        assert_segments(xml_part(target), [("A", "000000")])
        assert len(list(xml_part(target).iter(W + "tr"))) == 1
        assert_integrity(target)


def test_CF002_cell_and_header_paragraph_merge(docx, tmp_path):
    body = (
        "<w:tbl>"
        + row(run("A"))
        .replace("</w:tc>", p(run("B")) + "</w:tc>")
        .replace("<w:p>", "<w:p><w:pPr>" + MARK + "</w:pPr>", 1)
        + "</w:tbl>"
    )
    source = docx(
        "source.docx",
        body,
        {"word/header1.xml": story("hdr", p(run("H"), MARK) + p(insert("I")))},
    )
    target = tmp_path / "out.docx"
    convert(source, target)
    assert [text(c) for c in xml_part(target).iter(W + "tc")] == ["AB"]
    assert_segments(
        xml_part(target, "word/header1.xml"), [("H", "000000"), ("I", "FF0000")]
    )
    assert_integrity(target)


def test_CF002_field_spanning_merged_paragraphs(docx, tmp_path):
    left = (
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText> ADDIN ZOTERO_BIBL </w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        + run("A ")
    )
    right = insert("B") + '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
    source = docx("source.docx", p(left, MARK) + p(right))
    target = tmp_path / "out.docx"
    convert(source, target)
    assert paragraphs(target) == ["A B"]
    assert [n.get(W + "fldCharType") for n in xml_part(target).iter(W + "fldChar")] == [
        "begin",
        "separate",
        "end",
    ]
    assert_segments(xml_part(target), [("A ", "000000"), ("B", "FF0000")])
    assert_integrity(target)
