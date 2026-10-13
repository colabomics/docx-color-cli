from collections import Counter

import pytest
from helpers.fixtures import W, p, paragraph, rewrite, run, story
from lxml import etree

from docx_color_cli.cli import check, convert, convert_output, modify
from docx_color_cli.errors import ConversionError, UnsupportedRevisionError


@pytest.mark.parametrize("operation", [check, convert])
@pytest.mark.parametrize(
    "part,root",
    [
        ("word/document.xml", "document"),
        ("word/header1.xml", "hdr"),
        ("word/styles.xml", "styles"),
    ],
)
def test_revision_diagnostics_identify_part_type_and_element(
    docx, tmp_path, operation, part, root
):
    body = p('<w:conflictIns w:id="7">' + run("private text") + "</w:conflictIns>")
    source = docx(
        "source.docx",
        body if root == "document" else paragraph("keep"),
        {} if root == "document" else {part: story(root, body)},
    )
    args = (source,) if operation is check else (source, tmp_path / "out.docx")
    with pytest.raises(UnsupportedRevisionError) as caught:
        operation(*args)
    error = caught.value
    assert error.part == part
    assert error.revision_type == "conflictIns"
    assert error.element == W + "conflictIns"
    assert "conflictIns" in error.xpath
    assert part in str(error)
    assert "private text" not in str(error)
    assert not (tmp_path / "out.docx").exists()


def test_direct_modify_error_has_xml_context():
    root = etree.fromstring(
        story("document", p(run("keep"), '<w:rPr><w:del w:id="1"/></w:rPr>'))
    )
    with pytest.raises(UnsupportedRevisionError) as caught:
        modify(root, Counter())
    assert caught.value.part is None
    assert caught.value.revision_type == "del"
    assert caught.value.xpath.endswith("/w:p")


@pytest.mark.parametrize("part", ["word/document.xml", "word/header1.xml"])
def test_xml_parse_errors_identify_part_and_cause(docx, tmp_path, part):
    source = docx("source.docx", paragraph("keep"))
    rewrite(source, {part: b"<broken>"})
    with pytest.raises(ConversionError) as caught:
        convert(source, tmp_path / "out.docx")
    assert caught.value.part == part
    assert caught.value.cause_type == "XMLSyntaxError"
    assert isinstance(caught.value.__cause__, etree.XMLSyntaxError)


@pytest.mark.parametrize("function", [modify, convert, convert_output])
def test_strict_parameter_removed(function):
    import inspect

    assert "strict" not in inspect.signature(function).parameters
    with pytest.raises(TypeError, match="strict"):
        function(None, None, strict=False)
