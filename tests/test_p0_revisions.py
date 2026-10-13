import pytest
from helpers.assertions import (
    assert_integrity,
    assert_rejects_without_output,
    assert_segments,
    xml_part,
)
from helpers.fixtures import p, revision, run, story

from docx_color_cli.cli import convert


def move(kind, ident, name="m", text="moved"):
    return (
        f'<w:{kind}RangeStart w:id="{ident}" w:name="{name}"/>'
        + revision(kind, run(text), ident)
        + f'<w:{kind}RangeEnd w:id="{ident}"/>'
    )


@pytest.mark.parametrize(
    "body",
    [
        p(move("moveFrom", "1") + move("moveTo", "2", "other")),
        p(move("moveFrom", "1") + move("moveTo", "2") + move("moveTo", "3")),
        p(
            move("moveFrom", "1")
            + move("moveTo", "2").replace(
                'moveToRangeEnd w:id="2"', 'moveToRangeEnd w:id="3"'
            )
        ),
        p(
            move("moveFrom", "1")
            + '<w:moveToRangeEnd w:id="2"/><w:moveToRangeStart w:id="2" w:name="m"/>'
            + revision("moveTo", run("moved"))
        ),
        p(
            move("moveFrom", "1")
            + move("moveTo", "2").replace(
                "</w:moveTo>", "</w:moveTo>" + run("untracked")
            )
        ),
        p(
            '<w:customXmlInsRangeStart w:id="1"/>'
            + run("uncertain")
            + '<w:customXmlInsRangeEnd w:id="1"/>'
        ),
        p("<w:r><w:rPr><w:unexpectedPrChange/></w:rPr><w:t>text</w:t></w:r>"),
    ],
    ids=[
        "names",
        "duplicate-destination",
        "end-id",
        "reversed-range",
        "untracked-range-text",
        "custom-range",
        "unknown-property-change",
    ],
)
def test_CF006_CF007_guard_cannot_be_bypassed(docx, tmp_path, body):
    assert_rejects_without_output(
        convert, docx("source.docx", body), tmp_path / "out.docx"
    )


def test_CF007_moves_cannot_pair_across_notes(docx, tmp_path):
    notes = story(
        "footnotes",
        '<w:footnote w:id="1">'
        + p(move("moveFrom", "1"))
        + '</w:footnote><w:footnote w:id="2">'
        + p(move("moveTo", "2"))
        + "</w:footnote>",
    )
    assert_rejects_without_output(
        convert,
        docx("source.docx", p(run("body")), {"word/footnotes.xml": notes}),
        tmp_path / "out.docx",
    )


def test_CF007_multiple_move_runs_keep_order(docx, tmp_path):
    source_range = move("moveFrom", "1", text="A").replace(
        "</w:moveFrom><",
        "</w:moveFrom>" + revision("moveFrom", run(" B"), "3") + "<",
        1,
    )
    destination = move("moveTo", "2", text="A").replace(
        "</w:moveTo><", "</w:moveTo>" + revision("moveTo", run(" B"), "4") + "<", 1
    )
    source = docx("source.docx", p(source_range + run("start ")) + p(destination))
    target = tmp_path / "out.docx"
    convert(source, target)
    assert_segments(xml_part(target), [("start ", "000000"), ("A B", "FF0000")])
    assert_integrity(target)


def test_CF006_simple_field_result_revision(docx, tmp_path):
    source = docx(
        "source.docx",
        p(
            '<w:fldSimple w:instr="PAGE">'
            + revision("del", run("1"))
            + revision("ins", run("2"))
            + "</w:fldSimple>"
        ),
    )
    target = tmp_path / "out.docx"
    convert(source, target)
    from helpers.fixtures import W

    assert xml_part(target).find(".//" + W + "fldSimple").get(W + "instr") == "PAGE"
    assert_segments(xml_part(target), [("2", "FF0000")])
    assert_integrity(target)


@pytest.mark.parametrize(
    "content",
    ['<w:trPr><w:del w:id="1"/></w:trPr>', '<w:rPr><w:del w:id="1"/></w:rPr>'],
)
def test_CF006_misplaced_structural_markers_refused(docx, tmp_path, content):
    assert_rejects_without_output(
        convert, docx("source.docx", p(content + run("keep"))), tmp_path / "out.docx"
    )


def test_CF006_nested_deletion_accepted(docx, tmp_path):
    source = docx(
        "source.docx", p(revision("del", revision("ins", run("gone"))) + run("keep"))
    )
    target = tmp_path / "out.docx"
    convert(source, target)
    assert_segments(xml_part(target), [("keep", "000000")])
    assert_integrity(target)
