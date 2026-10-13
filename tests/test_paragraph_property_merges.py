import pytest
from helpers.assertions import assert_integrity, assert_segments, paragraphs, xml_part
from helpers.fixtures import W, delete, field, fraction, insert, p, run

from docx_color_cli.cli import convert

MARK = '<w:rPr><w:del w:id="1"/></w:rPr>'


@pytest.mark.parametrize(
    "left,right",
    [
        ('<w:pStyle w:val="Heading1"/>', '<w:pStyle w:val="Normal"/>'),
        ('<w:spacing w:after="120"/>', '<w:spacing w:after="0"/>'),
        ('<w:jc w:val="center"/>', '<w:jc w:val="both"/>'),
        (
            '<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>',
            '<w:numPr><w:ilvl w:val="1"/><w:numId w:val="2"/></w:numPr>',
        ),
        ('<w:pStyle w:val="Heading2"/>', ""),
    ],
)
def test_final_mark_owns_merged_paragraph_properties(docx, tmp_path, left, right):
    source = docx(
        "in.docx", p(run("A ") + delete("gone"), left + MARK) + p(insert("B"), right)
    )
    original = source.read_bytes()
    target = tmp_path / "out.docx"
    convert(source, target)
    assert paragraphs(target) == ["A B"]
    assert_segments(xml_part(target), [("A ", "000000"), ("B", "FF0000")])

    actual = xml_part(target).find(".//" + W + "p/" + W + "pPr")
    expected = xml_part(source).findall(".//" + W + "p")[1].find(W + "pPr")

    def key(n):
        return None if n is None else (n.tag, dict(n.attrib), [key(c) for c in n])

    assert key(actual) == key(expected)
    assert source.read_bytes() == original
    assert_integrity(target)


def test_chained_differing_properties_preserve_editable_objects(docx, tmp_path):
    first = field(' ADDIN ZOTERO_ITEM CSL_CITATION {"id":"sample"} ', run("(1)"))
    body = (
        p(first, '<w:pStyle w:val="Heading1"/>' + MARK)
        + p(fraction(), '<w:jc w:val="center"/>' + MARK)
        + p(insert("end"), '<w:spacing w:after="0"/>')
    )
    target = tmp_path / "out.docx"
    convert(docx("in.docx", body), target)
    root = xml_part(target)
    assert len(root.findall(".//" + W + "p")) == 1
    assert root.find(".//" + W + "pPr/" + W + "pStyle") is None
    assert root.find(".//" + W + "pPr/" + W + "jc") is None
    assert root.find(".//" + W + "pPr/" + W + "spacing").get(W + "after") == "0"
    assert [n.text for n in root.iter(W + "instrText")] == [
        ' ADDIN ZOTERO_ITEM CSL_CITATION {"id":"sample"} '
    ]
    assert paragraphs(target) == ["(1)xyend"]
    assert_integrity(target)
