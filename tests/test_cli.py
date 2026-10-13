from collections import Counter

import pytest
from lxml import etree

from docx_color_cli.cli import W, modify


def test_color_and_accept():
    xml = f'''<w:document xmlns:w="{W[1:-1]}"><w:body><w:p>
    <w:r><w:t>Old </w:t></w:r>
    <w:del><w:r><w:delText>gone</w:delText></w:r></w:del>
    <w:ins><w:r><w:t>NEW</w:t></w:r></w:ins>
    </w:p></w:body></w:document>'''
    root = etree.fromstring(xml)
    modify(root, Counter())
    assert "gone" not in etree.tostring(root).decode()
    assert [
        r.find(W + "rPr").find(W + "color").get(W + "val")
        for r in root.findall(".//" + W + "r")
    ] == ["000000", "FF0000"]
    assert not root.findall(".//" + W + "ins")


def test_structural_revisions_fail_closed():
    xml = f'''<w:document xmlns:w="{W[1:-1]}"><w:body><w:p><w:pPr><w:rPr><w:del/></w:rPr></w:pPr></w:p></w:body></w:document>'''
    with pytest.raises(ValueError, match="paragraph mark"):
        modify(etree.fromstring(xml), Counter())
