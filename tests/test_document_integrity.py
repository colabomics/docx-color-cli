import warnings
from contextlib import suppress
from zipfile import ZipFile

import pytest
from helpers.assertions import assert_integrity, assert_rejects_without_output, xml_part
from helpers.content import inspect_docx
from helpers.fixtures import (
    W_NS,
    delete,
    insert,
    p,
    paragraph,
    relationships,
    rewrite,
    story,
)

from docx_color_cli.cli import convert, main


def test_DI001_unrelated_zip_members_preserved(docx, tmp_path):
    extras = {
        "word/media/pixel.bin": b"opaque-object",
        "customXml/item1.xml": "<metadata>opaque</metadata>",
    }
    source = docx("source.docx", p(delete("old") + insert("new")), extras)
    target = tmp_path / "out.docx"
    convert(source, target)
    with ZipFile(source) as original, ZipFile(target) as output:
        assert output.namelist() == original.namelist()
        assert output.testzip() is None
        for name in original.namelist():
            if name != "word/document.xml":
                assert output.read(name) == original.read(name)
            before, after = original.getinfo(name), output.getinfo(name)
            assert (before.date_time, before.compress_type, before.external_attr) == (
                after.date_time,
                after.compress_type,
                after.external_attr,
            )


def test_DI002_deterministic_content_and_counts(docx, tmp_path):
    source = docx("source.docx", p(delete("old") + insert("new")))
    a, b = tmp_path / "a.docx", tmp_path / "b.docx"
    assert convert(source, a) == convert(source, b)
    with ZipFile(a) as one, ZipFile(b) as two:
        assert {n: one.read(n) for n in one.namelist()} == {
            n: two.read(n) for n in two.namelist()
        }


@pytest.mark.parametrize("report_target", ["source", "output"])
def test_CF001_report_cannot_overwrite_document(docx, tmp_path, report_target):
    source = docx("source.docx", paragraph("keep"))
    target = tmp_path / "out.docx"
    before = source.read_bytes()
    report = source if report_target == "source" else target
    with suppress(ValueError, SystemExit):
        main([str(source), str(target), "--report", str(report)])
    assert source.read_bytes() == before
    if target.exists():
        assert_integrity(target)


def test_CF004_wrong_document_root_rejected(docx, tmp_path):
    source = docx("source.docx", p(delete("gone") + insert("keep")))
    rewrite(source, {"word/document.xml": b"<not-a-word-document/>"})
    assert_rejects_without_output(convert, source, tmp_path / "out.docx")


def test_CF005_nonstandard_header_path(docx, tmp_path):
    name = "word/header-A.xml"
    parts = {
        name: story("hdr", p(delete("gone") + insert("keep"))),
        "word/_rels/document.xml.rels": relationships(
            [("header", "header", "header-A.xml", False)]
        ),
    }
    body = (
        paragraph("body")
        + '<w:sectPr><w:headerReference w:type="default" r:id="header"/></w:sectPr>'
    )
    source = docx("source.docx", body, parts)
    target = tmp_path / "out.docx"
    convert(source, target)
    assert_integrity(target)
    assert xml_part(target, name).find(".//{" + W_NS + "}del") is None


@pytest.mark.parametrize(
    "damage",
    [
        "missing-media",
        "missing-types",
        "wrong-main-type",
        "broken-extra-xml",
        "duplicate-member",
        "missing-footnote",
        "missing-relationship",
    ],
)
def test_CF014_invalid_package_is_rejected(docx, tmp_path, damage):
    source = docx("source.docx", paragraph("keep"))
    if damage == "missing-media":
        rewrite(
            source,
            {
                "word/_rels/document.xml.rels": relationships(
                    [("image", "image", "media/missing.png", False)]
                )
            },
        )
    elif damage == "missing-types":
        rewrite(source, {"[Content_Types].xml": None})
    elif damage == "wrong-main-type":
        with ZipFile(source) as archive:
            types = archive.read("[Content_Types].xml")
        rewrite(
            source,
            {
                "[Content_Types].xml": types.replace(
                    b"wordprocessingml.document.main+xml",
                    b"wordprocessingml.header+xml",
                )
            },
        )
    elif damage == "broken-extra-xml":
        rewrite(source, {"customXml/item1.xml": b"<broken>"})
    elif damage == "duplicate-member":
        with ZipFile(source, "a") as archive:
            archive.writestr("customXml/duplicate.xml", "<a/>")
            with pytest.warns(UserWarning, match="Duplicate name"):
                archive.writestr("customXml/duplicate.xml", "<b/>")
    elif damage == "missing-footnote":
        source = docx("source.docx", p('<w:r><w:footnoteReference w:id="7"/></w:r>'))
    else:
        source = docx(
            "source.docx",
            p('<w:hyperlink r:id="missing"><w:r><w:t>link</w:t></w:r></w:hyperlink>'),
        )
    # The oracle detects the malformed input independently of conversion.
    issues = inspect_docx(source).issues
    expected = {
        "missing-media": "missing relationship target",
        "missing-types": "Content Types",
        "wrong-main-type": "incorrect main Content Type",
        "broken-extra-xml": "invalid DOCX",
        "duplicate-member": "duplicate ZIP",
        "missing-footnote": "dangling footnote",
        "missing-relationship": "missing or duplicate relationship",
    }[damage]
    assert any(expected in issue for issue in issues), issues
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message="Duplicate name:", category=UserWarning
        )
        assert_rejects_without_output(convert, source, tmp_path / "out.docx")
