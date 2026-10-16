"""Malformed OPC regressions now exercise the supported two-input API."""

import warnings
from zipfile import ZipFile

import pytest
from helpers.content import inspect_docx
from helpers.fixtures import p, paragraph, relationships, rewrite

from docx_color_cli import ColoringError, color_revisions


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
        accepted = docx("accepted.docx", paragraph("keep"))
        target = tmp_path / "out.docx"
        target.write_bytes(b"previous")
        before = source.read_bytes(), accepted.read_bytes()
        with pytest.raises(ColoringError) as error:
            color_revisions(source, accepted, target)
        assert error.value.code == "INVALID_DOCX"
        assert target.read_bytes() == b"previous"
        assert (source.read_bytes(), accepted.read_bytes()) == before
