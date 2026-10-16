"""Preservation assertions migrated from the single-input acceptance tests.

Accepted payloads and insertion coordinates are authored independently here.
We preserve resources instead of testing the abandoned resource-pruning engine.
"""

from zipfile import ZipFile

import pytest
from helpers.assertions import xml_part, xml_tree
from helpers.fidelity import compare, digest
from helpers.fixtures import (
    PNG,
    W,
    field,
    fraction,
    image_run,
    insert,
    p,
    relationships,
    run,
    story,
)

from docx_color_cli import color_revisions

BOOKMARK = (
    '<w:bookmarkStart w:id="7" w:name="target"/>'
    + run("target")
    + '<w:bookmarkEnd w:id="7"/>'
)
LINKS = relationships(
    [
        ("image1", "image", "media/pixel.png", False),
        ("link", "hyperlink", "https://example.org/paper?q=1&x=2", True),
    ]
)


@pytest.mark.parametrize(
    "payload",
    [
        field(" REF target \\h ", run("Section 1")),
        field(" PAGEREF target ", run("1")),
        field(
            ' ADDIN ZOTERO_ITEM CSL_CITATION {"citationID":"synthetic"} ', run("(1)")
        ),
        field(' ADDIN ZOTERO_BIBL {"uncited":[]} CSL_BIBLIOGRAPHY ', run("Entry")),
        field(" SEQ Figure \\* ARABIC ", run("1")),
        field(" QUOTE ", field(" AUTHOR ", run("Synthetic Author"))),
        '<w:fldSimple w:instr="AUTHOR">' + run("Synthetic Author") + "</w:fldSimple>",
        '<w:hyperlink r:id="link">' + run("link") + "</w:hyperlink>",
        field(' HYPERLINK "https://example.org" \\h ', run("link")),
        '<w:hyperlink w:anchor="target">' + run("target") + "</w:hyperlink>",
        '<w:sdt><w:sdtPr><w:tag w:val="sample"/><w:id w:val="42"/></w:sdtPr><w:sdtContent>'
        + run("control")
        + "</w:sdtContent></w:sdt>",
        '<w:customXml w:element="item" w:uri="urn:synthetic">'
        + run("custom")
        + "</w:customXml>",
        '<w:r><w:tab/><w:t>B</w:t><w:br/><w:t>C</w:t><w:sym w:font="Symbol" w:char="F061"/></w:r>',
        image_run(),
        '<w:r><w:pict xmlns:v="urn:schemas-microsoft-com:vml"><v:shape><v:imagedata src="media/pixel.png"/></v:shape></w:pict></w:r>',
        fraction(),
        "<m:oMath/>",
        "<m:oMathPara><m:oMath/></m:oMathPara>",
        "<m:oMath><m:f><m:num/><m:den/></m:f></m:oMath>",
        run(
            "formatted",
            '<w:rFonts w:ascii="Cambria"/><w:b/><w:i/><w:u w:val="single"/><w:color w:val="123456" w:themeColor="accent1"/><w:sz w:val="24"/><w:vertAlign w:val="superscript"/>',
        ),
    ],
    ids=[
        "REF",
        "PAGEREF",
        "Zotero-item",
        "Zotero-bibliography",
        "SEQ",
        "nested-fields",
        "simple-field",
        "native-link",
        "hyperlink-field",
        "local-link",
        "content-control",
        "custom-xml",
        "tabs-breaks-symbols",
        "drawing",
        "VML",
        "fraction",
        "empty-math",
        "empty-display-math",
        "empty-fraction",
        "existing-format",
    ],
)
def test_accepted_inline_payload_is_preserved(docx, tmp_path, payload):
    parts = {"word/_rels/document.xml.rels": LINKS, "word/media/pixel.png": PNG}
    a = docx("tracked.docx", p(BOOKMARK + payload) + p(insert("new")), parts)
    b = docx("accepted.docx", p(BOOKMARK + payload) + p(run("new")), parts)
    hashes = digest(a), digest(b)
    out = tmp_path / "out.docx"
    color_revisions(a, b, out)
    assert xml_tree(xml_part(out).find(W + "body/" + W + "p")) == xml_tree(
        xml_part(b).find(W + "body/" + W + "p")
    )
    assert (
        compare(b, out, allowed={("word/document.xml", 1, i) for i in range(3)})[0][
            "overall"
        ]
        == "PASS"
    )
    assert (digest(a), digest(b)) == hashes
    with ZipFile(b) as accepted, ZipFile(out) as colored:
        assert accepted.namelist() == colored.namelist()
        for name in accepted.namelist():
            if name != "word/document.xml":
                assert accepted.read(name) == colored.read(name)


@pytest.mark.parametrize(
    "name,kind,container",
    [
        ("header-A", "hdr", None),
        ("footer-A", "ftr", None),
        ("footnotes", "footnotes", "footnote"),
        ("endnotes", "endnotes", "endnote"),
        ("comments", "comments", "comment"),
        ("notes/research", "footnotes", "footnote"),
    ],
)
def test_story_insertions_and_boundaries(docx, tmp_path, name, kind, container):
    path = f"word/{name}.xml"
    content_a = p(run("old ") + insert("new"))
    content_b = p(run("old ") + run("new"))
    if container:
        content_a = f'<w:{container} w:id="1">{content_a}</w:{container}>'
        content_b = f'<w:{container} w:id="1">{content_b}</w:{container}>'
    relation = {"hdr": "header", "ftr": "footer"}.get(kind, kind)
    rels = relationships([("story", relation, name + ".xml", False)])
    body = p(run("body"))
    if container:
        body += p(f'<w:r><w:{container}Reference w:id="1"/></w:r>')
    a = docx(
        "tracked.docx",
        body,
        {path: story(kind, content_a), "word/_rels/document.xml.rels": rels},
    )
    b = docx(
        "accepted.docx",
        body,
        {path: story(kind, content_b), "word/_rels/document.xml.rels": rels},
    )
    before = digest(a), digest(b)
    out = tmp_path / "out.docx"
    result = color_revisions(a, b, out)
    # Comments are preserved opaque parts in the frozen Phase 6 contract.
    allowed = set() if kind == "comments" else {(path, 0, i) for i in range(4, 7)}
    assert result["coloring"]["characters_colored"] == len(allowed)
    assert (
        compare(
            b,
            out,
            allowed=allowed,
            mutable_parts=set() if kind == "comments" else {path},
        )[0]["overall"]
        == "PASS"
    )
    assert (digest(a), digest(b)) == before


@pytest.mark.parametrize(
    "boundary", ["paragraph", "cell", "merged-cell", "section", "numbering"]
)
def test_accepted_block_properties_and_resources(docx, tmp_path, boundary):
    payload = field(" REF target ", run("kept")) + fraction() + image_run()
    body = p(BOOKMARK + payload)
    if boundary in {"cell", "merged-cell"}:
        span = '<w:gridSpan w:val="2"/>' if boundary == "merged-cell" else ""
        body = (
            '<w:tbl><w:tblPr><w:tblW w:w="2000" w:type="dxa"/></w:tblPr><w:tblGrid><w:gridCol w:w="1000"/><w:gridCol w:w="1000"/></w:tblGrid><w:tr><w:tc><w:tcPr>'
            + span
            + "</w:tcPr>"
            + body
            + "</w:tc></w:tr></w:tbl>"
        )
    elif boundary == "section":
        body = p(payload, '<w:sectPr><w:type w:val="nextPage"/></w:sectPr>')
    elif boundary == "numbering":
        body = p(
            payload,
            '<w:pStyle w:val="Normal"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>',
        )
    parts = {
        "word/_rels/document.xml.rels": LINKS,
        "word/media/pixel.png": PNG,
        "word/media/orphan.png": PNG + b"orphan",
        "word/data.bin": b"opaque",
        "word/media/_rels/pixel.png.rels": relationships(
            [("data", "custom", "../data.bin", False)]
        ),
        "customXml/item1.xml": "<metadata>opaque</metadata>",
        "word/styles.xml": story(
            "styles", '<w:style w:styleId="Normal"><w:rPr><w:b/></w:rPr></w:style>'
        ),
        "word/numbering.xml": story(
            "numbering", '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
        ),
        "word/settings.xml": story("settings", '<w:zoom w:percent="179"/>'),
        "word/comments.xml": story(
            "comments",
            '<w:comment w:id="1">' + p(run("orphan comment")) + "</w:comment>",
        ),
        "word/commentsExtended.xml": '<records><record id="1" parent="2"/></records>',
    }
    a = docx("tracked.docx", body + p(insert("new")), parts)
    b = docx("accepted.docx", body + p(run("new")), parts)
    out = tmp_path / "out.docx"
    result = color_revisions(a, b, out)
    assert result["coloring"]["characters_colored"] == 3
    assert xml_tree(xml_part(out).find(W + "body")[0]) == xml_tree(
        xml_part(b).find(W + "body")[0]
    )
    assert (
        compare(b, out, allowed={("word/document.xml", 1, i) for i in range(3)})[0][
            "overall"
        ]
        == "PASS"
    )
    with ZipFile(b) as accepted, ZipFile(out) as colored:
        assert accepted.namelist() == colored.namelist()
        for name in accepted.namelist():
            if name != "word/document.xml":
                assert accepted.read(name) == colored.read(name)
            x, y = accepted.getinfo(name), colored.getinfo(name)
            assert (x.date_time, x.compress_type, x.external_attr) == (
                y.date_time,
                y.compress_type,
                y.external_attr,
            )
