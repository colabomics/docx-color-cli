"""Accepted XML is authoritative, replacing obsolete opaque-acceptance expectations.

The original 46 scenarios are retained. Expected accepted structures are
authored here; no converter accepts revisions to construct the reference.
"""

import pytest
from helpers.assertions import xml_part, xml_tree, xml_without_font_colors
from helpers.fixtures import M, W, insert, p, revision, run, story

from docx_color_cli import color_revisions

MATH_OBJECTS = {
    "d": ("e",),
    "f": ("num", "den"),
    "sSub": ("e", "sub"),
    "sSup": ("e", "sup"),
    "nary": ("sub", "sup", "e"),
    "func": ("fName", "e"),
    "eqArr": ("e",),
    "acc": ("e",),
    "bar": ("e",),
    "borderBox": ("e",),
    "box": ("e",),
    "groupChr": ("e",),
    "limLow": ("e", "lim"),
    "limUpp": ("e", "lim"),
    "phant": ("e",),
    "rad": ("deg", "e"),
    "sPre": ("e", "sub", "sup"),
    "sSubSup": ("e", "sub", "sup"),
    "m": ("mr",),
}


@pytest.mark.parametrize("kind,args", MATH_OBJECTS.items())
@pytest.mark.parametrize("edit", ["ins", "del"])
def test_accepted_math_structure_is_authoritative(docx, tmp_path, kind, args, edit):
    props = '<w:rPr><w:color w:val="123456"/></w:rPr>'

    def equation(tracked):
        control = revision(edit, props) if tracked else props
        text = "<m:t>x</m:t>"
        payload = "<m:r>" + (revision(edit, text) if tracked else text) + "</m:r>"
        arguments = "".join(
            f"<m:{a}>"
            + ("<m:e>" + payload + "</m:e>" if a == "mr" else payload)
            + f"</m:{a}>"
            for a in args
        )
        return f"<m:oMath><m:{kind}><m:{kind}Pr><m:ctrlPr>{control}</m:ctrlPr></m:{kind}Pr>{arguments}</m:{kind}></m:oMath>"

    tracked = docx("tracked.docx", p(equation(True)) + p(insert("independent")))
    accepted = docx(
        "accepted.docx",
        p(equation(False) if edit == "ins" else "") + p(run("independent")),
    )
    original = [f.read_bytes() for f in (tracked, accepted)]
    output = tmp_path / "output.docx"
    result = color_revisions(tracked, accepted, output)
    assert xml_without_font_colors(xml_part(accepted)) == xml_without_font_colors(
        xml_part(output)
    )
    assert len(list(xml_part(output).iter(M + "oMath"))) == (1 if edit == "ins" else 0)
    assert (
        xml_part(output)
        .find(W + "body")
        .findall(W + "p")[-1]
        .find(".//" + W + "color")
        .get(W + "val")
        == "FF0000"
    )
    assert result["integrity"]["accepted_text_preserved"]
    assert [f.read_bytes() for f in (tracked, accepted)] == original


OPAQUE = [
    ("<w14:conflictIns>" + insert("conflict") + "</w14:conflictIns>", run("conflict")),
    (
        '<w:sdt><w:sdtPr><w:tag w:val="control"/></w:sdtPr><w:sdtContent>'
        + insert("control")
        + "</w:sdtContent></w:sdt>",
        '<w:sdt><w:sdtPr><w:tag w:val="control"/></w:sdtPr><w:sdtContent>'
        + run("control")
        + "</w:sdtContent></w:sdt>",
    ),
    (
        "<w:customXml>" + insert("custom") + "</w:customXml>",
        "<w:customXml>" + run("custom") + "</w:customXml>",
    ),
    (
        '<m:oMath><m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>A</m:t>'
        + revision("ins", "<m:t>B</m:t>")
        + revision("del", "<m:t>C</m:t>")
        + "</m:r></m:oMath>",
        '<m:oMath><m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>AB</m:t></m:r></m:oMath>',
    ),
    (
        '<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"><mc:Choice Requires="w14">'
        + insert("choice")
        + "</mc:Choice><mc:Fallback>"
        + insert("fallback")
        + "</mc:Fallback></mc:AlternateContent>",
        '<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"><mc:Choice Requires="w14">'
        + run("choice")
        + "</mc:Choice><mc:Fallback>"
        + run("fallback")
        + "</mc:Fallback></mc:AlternateContent>",
    ),
]


@pytest.mark.parametrize("source_xml,accepted_xml", OPAQUE)
def test_accepted_complex_content_and_independent_text(
    docx, tmp_path, source_xml, accepted_xml
):
    a = docx("tracked.docx", p(source_xml) + p(insert("independent")))
    b = docx("accepted.docx", p(accepted_xml) + p(run("independent")))
    out = tmp_path / "out.docx"
    color_revisions(a, b, out)
    assert xml_without_font_colors(xml_part(b)) == xml_without_font_colors(
        xml_part(out)
    )
    assert (
        xml_part(out)
        .find(W + "body")
        .findall(W + "p")[-1]
        .find(".//" + W + "color")
        .get(W + "val")
        == "FF0000"
    )


def test_merged_paragraphs_keep_the_accepted_boundaries(docx, tmp_path):
    a = docx(
        "tracked.docx",
        p(insert("first"), '<w:rPr><w:del w:id="1"/></w:rPr>')
        + p(insert("second"))
        + p(insert("third")),
    )
    b = docx("accepted.docx", p(run("firstsecond")) + p(run("third")))
    out = tmp_path / "out.docx"
    color_revisions(a, b, out)
    assert xml_without_font_colors(xml_part(b)) == xml_without_font_colors(
        xml_part(out)
    )
    assert len(xml_part(out).find(W + "body").findall(W + "p")) == 2
    assert (
        xml_part(out)
        .find(W + "body")
        .findall(W + "p")[-1]
        .find(".//" + W + "color")
        .get(W + "val")
        == "FF0000"
    )


@pytest.mark.parametrize(
    "bad",
    [
        '<w:moveFromRangeStart w:id="1"/>',
        '<w:moveFromRangeEnd w:id="1"/><w:moveFromRangeStart w:id="1"/>',
    ],
)
def test_unresolved_source_range_preserves_accepted_story(docx, tmp_path, bad):
    a = docx(
        "tracked.docx",
        p(bad + insert("uncertain")),
        {"word/header1.xml": story("hdr", p(insert("independent")))},
    )
    b = docx(
        "accepted.docx",
        p(run("uncertain")),
        {"word/header1.xml": story("hdr", p(run("independent")))},
    )
    out = tmp_path / "out.docx"
    result = color_revisions(a, b, out)
    assert xml_tree(xml_part(b)) == xml_tree(xml_part(out))
    assert xml_without_font_colors(
        xml_part(b, "word/header1.xml")
    ) == xml_without_font_colors(xml_part(out, "word/header1.xml"))
    assert (
        xml_part(out, "word/header1.xml").find(".//" + W + "color").get(W + "val")
        == "FF0000"
    )
    assert result["coloring_status"] == "PARTIAL"
