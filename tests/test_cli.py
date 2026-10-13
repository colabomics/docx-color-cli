from collections import Counter

import pytest
from helpers.assertions import assert_segments, xml_part
from helpers.fixtures import insert, p, run
from lxml import etree

from docx_color_cli.cli import W, main, modify


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


@pytest.mark.parametrize("position", ["before", "between", "after"])
def test_options_can_surround_positional_paths(docx, tmp_path, capsys, position):
    source = docx("source.docx", p(run("keep") + insert("new")))
    original = source.read_bytes()
    target = tmp_path / "explicit output.docx"
    options = ["--inserted-color", "123456", "--unchanged-color", "654321"]
    arguments = {
        "before": [*options, str(source), str(target)],
        "between": [str(source), *options, str(target)],
        "after": [str(source), str(target), *options],
    }[position]
    main(arguments)
    assert "Saved:" in capsys.readouterr().out
    assert_segments(xml_part(target), [("keep", "654321"), ("new", "123456")])
    assert source.read_bytes() == original
    assert set(tmp_path.iterdir()) == {source, target}
