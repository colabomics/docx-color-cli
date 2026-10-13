import pytest
from docx_color_cli.cli import convert
from helpers.assertions import assert_integrity, assert_rejects_without_output, assert_segments, xml_part
from helpers.fixtures import W, insert, p, run


@pytest.mark.parametrize('kind', ['Ins', 'Del'])
@pytest.mark.parametrize('wrapper', ['customXml', 'sdt'])
def test_complete_custom_markup_range(docx, tmp_path, kind, wrapper):
    payload = run('old') + insert('new')
    if wrapper == 'customXml':
        payload = '<w:customXml w:element="item" w:uri="urn:synthetic">' + payload + '</w:customXml>'
    else:
        payload = '<w:sdt><w:sdtPr><w:tag w:val="item"/></w:sdtPr><w:sdtContent>' + payload + '</w:sdtContent></w:sdt>'
    body = p(f'<w:customXml{kind}RangeStart w:id="1"/>' + payload + f'<w:customXml{kind}RangeEnd w:id="1"/>')
    source = docx('in.docx', body)
    before = source.read_bytes()
    target = tmp_path / 'out.docx'
    convert(source, target)
    root = xml_part(target)
    assert bool(list(root.iter(W + wrapper))) == (kind == 'Ins')
    assert_segments(root, [('old', '000000'), ('new', 'FF0000')])
    assert_integrity(target)
    assert source.read_bytes() == before


def test_partial_custom_markup_range_remains_rejected(docx, tmp_path):
    body = p('<w:customXmlDelRangeStart w:id="1"/><w:customXml w:element="item">' + run('keep') + '<w:customXmlDelRangeEnd w:id="1"/></w:customXml>')
    assert_rejects_without_output(convert, docx('in.docx', body), tmp_path / 'out.docx')
