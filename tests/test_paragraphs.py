from pathlib import Path

import pytest
from helpers.assertions import assert_integrity, assert_segments, paragraphs, xml_part
from helpers.fixtures import W, delete, insert, p, run

from docx_color_cli.cli import convert

DELETED_MARK = (
    Path(__file__).parent / "fixtures/paragraphs/deleted_mark.xml"
).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "body,expected,segments",
    [
        (p(insert("new paragraph")), ["new paragraph"], [("new paragraph", "FF0000")]),
        (p(delete("all text")), [""], []),
        (
            p(run("Title ") + insert("new"), '<w:pStyle w:val="Heading1"/>'),
            ["Title new"],
            [("Title ", "000000"), ("new", "FF0000")],
        ),
        (
            p("") + p(insert("after empty")),
            ["", "after empty"],
            [("after empty", "FF0000")],
        ),
        (
            p(delete("old A") + insert("new A")) + p(delete("old B") + insert("new B")),
            ["new A", "new B"],
            [("new A", "FF0000"), ("new B", "FF0000")],
        ),
    ],
    ids=[
        "P001-paragraph-text-insert",
        "P002-paragraph-text-delete-preserve-mark",
        "P003-heading",
        "P004-empty",
        "P005-cross-paragraph-replacement",
    ],
)
def test_paragraph_text_boundaries(docx, tmp_path, body, expected, segments):
    source = docx("source.docx", body)
    target = tmp_path / "out.docx"
    convert(source, target)
    assert paragraphs(target) == expected
    assert_segments(xml_part(target), segments)
    assert [n.attrib for n in xml_part(target).iter(W + "pStyle")] == [
        n.attrib for n in xml_part(source).iter(W + "pStyle")
    ]
    assert_integrity(target)


@pytest.mark.parametrize(
    "body,expected,segments",
    [
        (DELETED_MARK, ["AB"], [("AB", "000000")]),
        (
            p(insert("new"), '<w:rPr><w:ins w:id="1"/></w:rPr>'),
            ["new"],
            [("new", "FF0000")],
        ),
        (
            p(delete("whole paragraph"), '<w:rPr><w:del w:id="1"/></w:rPr>')
            + p(run("next")),
            ["next"],
            [("next", "000000")],
        ),
        (
            p("", '<w:rPr><w:del w:id="1"/></w:rPr>') + p(run("next")),
            ["next"],
            [("next", "000000")],
        ),
    ],
    ids=[
        "P006-delete-mark-merge",
        "P007-whole-paragraph-insertion",
        "P008-whole-paragraph-deletion",
        "P009-empty-mark-deletion",
    ],
)
def test_structural_paragraph_revisions_accepted(
    docx, tmp_path, body, expected, segments
):
    source = docx("source.docx", body)
    before = source.read_bytes()
    target = tmp_path / "out.docx"
    convert(source, target)
    assert paragraphs(target) == expected
    assert_segments(xml_part(target), segments)
    assert_integrity(target)
    assert source.read_bytes() == before
    assert target.exists()


def test_CF002_paragraph_merge(docx, tmp_path):
    target = tmp_path / "out.docx"
    convert(docx("source.docx", DELETED_MARK), target)
    assert paragraphs(target) == ["AB"]


def test_CF002_whole_paragraph_deletion(docx, tmp_path):
    target = tmp_path / "out.docx"
    body = p(delete("gone"), '<w:rPr><w:del w:id="1"/></w:rPr>') + p(run("keep"))
    convert(docx("source.docx", body), target)
    assert paragraphs(target) == ["keep"]


def test_P010_list_structure_preserved(docx, tmp_path):
    numbering = '<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/></w:lvl></w:abstractNum><w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num></w:numbering>'
    props = '<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>'
    target = tmp_path / "out.docx"
    source = docx(
        "source.docx",
        p(run("one") + insert("!"), props) + p(run("two"), props),
        {"word/numbering.xml": numbering},
    )
    convert(source, target)
    assert paragraphs(target) == ["one!", "two"]
    assert len(xml_part(target).findall(".//" + W + "numPr")) == 2
    assert_segments(
        xml_part(target), [("one", "000000"), ("!", "FF0000"), ("two", "000000")]
    )
    assert_integrity(target)
