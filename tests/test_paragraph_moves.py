"""Permanent regressions for paired moves spanning paragraph marks."""

import pytest
from helpers.assertions import assert_integrity, assert_segments, paragraphs, xml_part
from helpers.fixtures import p, revision, run

from docx_color_cli.cli import convert


def start(kind, ident):
    return f'<w:{kind}RangeStart w:id="{ident}" w:name="paired"/>'


def end(kind, ident):
    return f'<w:{kind}RangeEnd w:id="{ident}"/>'


def mark(kind):
    return f'<w:rPr><w:{kind} w:id="9"/></w:rPr>'


@pytest.mark.parametrize("count", [1, 2, 3])
@pytest.mark.parametrize("body_end", [False, True])
def test_whole_and_cross_paragraph_moves(docx, tmp_path, count, body_end):
    source = "".join(
        p(
            (start("moveFrom", "1") if i == 0 else "")
            + revision("moveFrom", run(str(i))),
            mark("moveFrom"),
        )
        for i in range(count)
    )
    source += p(end("moveFrom", "1") + run("stay"))
    destination = "".join(
        p(
            (start("moveTo", "2") if i == 0 else "") + revision("moveTo", run(str(i))),
            mark("moveTo"),
        )
        for i in range(count)
    )
    destination += end("moveTo", "2") if body_end else p(end("moveTo", "2"))
    target = tmp_path / "out.docx"
    convert(docx("in.docx", source + destination), target)
    assert paragraphs(target) == ["stay"] + [str(i) for i in range(count)] + (
        [] if body_end else [""]
    )
    assert_segments(
        xml_part(target),
        [("stay", "000000"), ("".join(str(i) for i in range(count)), "FF0000")],
    )
    assert_integrity(target)


def test_partial_cross_paragraph_move_preserves_boundaries(docx, tmp_path):
    body = p(
        run("left ") + start("moveFrom", "1") + revision("moveFrom", run("A")),
        mark("moveFrom"),
    )
    body += p(revision("moveFrom", run("B")) + end("moveFrom", "1") + run("right"))
    body += p(
        run("prefix ") + start("moveTo", "2") + revision("moveTo", run("A")),
        mark("moveTo"),
    )
    body += p(revision("moveTo", run("B")) + end("moveTo", "2") + run(" suffix"))
    target = tmp_path / "out.docx"
    source = docx("in.docx", body)
    original = source.read_bytes()
    convert(source, target)
    assert paragraphs(target) == ["left right", "prefix A", "B suffix"]
    assert_segments(
        xml_part(target),
        [("left rightprefix ", "000000"), ("AB", "FF0000"), (" suffix", "000000")],
    )
    assert source.read_bytes() == original
    assert_integrity(target)


def test_moved_destination_mark_also_deleted(docx, tmp_path):
    body = p(start("moveFrom", "1") + revision("moveFrom", run("A")), mark("moveFrom"))
    body += p(end("moveFrom", "1") + run("stay"))
    destination_mark = '<w:rPr><w:moveTo w:id="8"/><w:del w:id="9"/></w:rPr>'
    body += p(start("moveTo", "2") + revision("moveTo", run("A")), destination_mark)
    body += end("moveTo", "2") + p(run("B"))
    target = tmp_path / "out.docx"
    convert(docx("in.docx", body), target)
    assert paragraphs(target) == ["stay", "AB"]
    assert_segments(
        xml_part(target), [("stay", "000000"), ("A", "FF0000"), ("B", "000000")]
    )
    assert_integrity(target)


def test_move_preserves_fields_equation_hyperlink_and_media(docx, tmp_path):
    from helpers.assertions import xml_without_font_colors
    from helpers.fixtures import PNG, M, W, field, fraction, image_run, relationships

    payload = (
        field(' ADDIN ZOTERO_ITEM CSL_CITATION {"id":"sample"} ', run("(1)"))
        + fraction()
        + image_run()
        + '<w:hyperlink r:id="link">'
        + run("article")
        + "</w:hyperlink>"
    )
    body = p(
        start("moveFrom", "1") + revision("moveFrom", payload), mark("moveFrom")
    ) + p(end("moveFrom", "1") + run("stay"))
    body += p(start("moveTo", "2") + revision("moveTo", payload), mark("moveTo")) + end(
        "moveTo", "2"
    )
    parts = {
        "word/media/pixel.png": PNG,
        "word/_rels/document.xml.rels": relationships(
            [
                ("image1", "image", "media/pixel.png", False),
                ("link", "hyperlink", "https://example.org", True),
            ]
        ),
    }
    source = docx("in.docx", body, parts)
    target = tmp_path / "out.docx"
    convert(source, target)
    root = xml_part(target)
    assert len(root.findall(".//" + W + "p")) == 2
    assert len(root.findall(".//" + W + "drawing")) == 1
    assert [n.text for n in root.iter(W + "instrText")] == [
        ' ADDIN ZOTERO_ITEM CSL_CITATION {"id":"sample"} '
    ]
    assert len(root.findall(".//" + W + "fldChar")) == 3
    assert xml_without_font_colors(
        root.find(".//" + M + "oMath")
    ) == xml_without_font_colors(xml_part(source).find(".//" + M + "oMath"))
    assert_segments(root, [("stay", "000000"), ("(1)article", "FF0000")])
    assert_integrity(target)


def test_adjacent_ranges_can_interleave_empty_endpoints(docx, tmp_path):
    s1 = start("moveFrom", "1")
    e1 = end("moveFrom", "1")
    s2 = start("moveFrom", "3").replace("paired", "second")
    e2 = end("moveFrom", "3")
    t1 = start("moveTo", "2")
    t2 = start("moveTo", "4").replace("paired", "second")
    body = p(s1 + revision("moveFrom", run("A")), mark("moveFrom"))
    body += p(s2 + e1 + revision("moveFrom", run("B")), mark("moveFrom")) + p(
        e2 + run("stay")
    )
    body += p(t1 + revision("moveTo", run("A")), mark("moveTo")) + end("moveTo", "2")
    body += p(t2 + revision("moveTo", run("B")), mark("moveTo")) + end("moveTo", "4")
    target = tmp_path / "out.docx"
    convert(docx("in.docx", body), target)
    assert paragraphs(target) == ["stay", "A", "B"]
    assert_integrity(target)


@pytest.mark.parametrize("kind", ["cross-cell", "terminal", "overlap"])
def test_unsafe_paragraph_move_refused(docx, tmp_path, kind):
    from helpers.assertions import assert_rejects_without_output

    destination = p(
        start("moveTo", "2") + revision("moveTo", run("A")) + end("moveTo", "2")
    )
    if kind == "cross-cell":
        body = (
            "<w:tbl><w:tr><w:tc>"
            + p(start("moveFrom", "1") + revision("moveFrom", run("A")))
            + "</w:tc><w:tc>"
            + p(end("moveFrom", "1"))
            + "</w:tc></w:tr></w:tbl>"
            + destination
        )
    elif kind == "terminal":
        body = (
            destination
            + p(
                start("moveFrom", "1") + revision("moveFrom", run("A")),
                mark("moveFrom"),
            )
            + end("moveFrom", "1")
        )
    else:
        body = (
            p(
                start("moveFrom", "1")
                + start("moveFrom", "3").replace("paired", "other")
                + revision("moveFrom", run("A"))
                + end("moveFrom", "3")
                + end("moveFrom", "1")
            )
            + destination
        )
    assert_rejects_without_output(convert, docx("in.docx", body), tmp_path / "out.docx")
