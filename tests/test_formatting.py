import pytest
from lxml import etree

from docx_color_cli.cli import convert
from helpers.assertions import assert_integrity, assert_segments, xml_part
from helpers.fixtures import W, insert, p, run


def test_FMT001_run_properties_preserved(docx, tmp_path):
    props = '<w:rFonts w:ascii="Cambria"/><w:b/><w:i/><w:color w:val="123456" w:themeColor="accent1"/><w:sz w:val="24"/><w:vertAlign w:val="superscript"/>'
    source = docx('source.docx', p(run('old', props) + '<w:ins w:id="1">' + run('new', props) + '</w:ins>'))
    target = tmp_path / 'out.docx'
    convert(source, target)
    before, after = xml_part(source), xml_part(target)
    for tag in ('rFonts', 'b', 'i', 'sz', 'vertAlign'):
        assert [etree.tostring(n) for n in before.iter(W + tag)] == [etree.tostring(n) for n in after.iter(W + tag)]
    assert_segments(after, [('old', '000000'), ('new', 'FF0000')])
    assert all(n.get(W + 'themeColor') is None for n in after.iter(W + 'color'))
    assert_integrity(target)


@pytest.mark.parametrize('props,container', [
    ('rPr', 'r'), ('pPr', 'p'), ('tblPr', 'tbl'), ('trPr', 'tr'), ('tcPr', 'tc')
], ids=['FMT002-run','FMT003-paragraph','FMT004-table','FMT005-row','FMT006-cell'])
def test_current_format_survives_history_removal(docx, tmp_path, props, container):
    if props == 'rPr':
        body = p('<w:r><w:rPr><w:b/><w:rPrChange w:id="1"><w:rPr><w:i/></w:rPr></w:rPrChange></w:rPr><w:t>text</w:t></w:r>')
        current = 'b'
    elif props == 'pPr':
        body = p(run('text'), '<w:pStyle w:val="Heading1"/><w:pPrChange w:id="1"><w:pPr><w:pStyle w:val="Normal"/></w:pPr></w:pPrChange>')
        current = 'pStyle'
    else:
        current = {'tblPr':'tblW', 'trPr':'cantSplit', 'tcPr':'gridSpan'}[props]
        current_xml = {'tblPr': '<w:tblW w:w="2400" w:type="dxa"/>', 'trPr': '<w:cantSplit/>', 'tcPr': '<w:gridSpan w:val="1"/>'}[props]
        properties = f'<w:{props}>{current_xml}<w:{props}Change w:id="1"><w:{props}/></w:{props}Change></w:{props}>'
        body = '<w:tbl>' + (properties if container == 'tbl' else '') + '<w:tr>' + (properties if container == 'tr' else '') + '<w:tc>' + (properties if container == 'tc' else '') + p(run('text')) + '</w:tc></w:tr></w:tbl>'
    target = tmp_path / 'out.docx'
    convert(docx('source.docx', body), target)
    root = xml_part(target)
    assert root.find('.//' + W + current) is not None
    assert not root.findall('.//' + W + props + 'Change')
    assert_segments(root, [('text', '000000')])
    assert_integrity(target)


def test_CF015_historical_revision_not_current(docx, tmp_path):
    body = p(run('keep'), '<w:pPrChange w:id="1"><w:pPr><w:rPr><w:del w:id="2"/></w:rPr></w:pPr></w:pPrChange>')
    target = tmp_path / 'out.docx'
    convert(docx('source.docx', body), target)
    assert_segments(xml_part(target), [('keep', '000000')])
    assert_integrity(target)


def test_CF013_table_exception_history_removed(docx, tmp_path):
    body = '<w:tbl><w:tr><w:tblPrEx><w:tblW w:w="2400" w:type="dxa"/><w:tblPrExChange w:id="1"><w:tblPrEx/></w:tblPrExChange></w:tblPrEx><w:tc>' + p(run('text')) + '</w:tc></w:tr></w:tbl>'
    target = tmp_path / 'out.docx'
    convert(docx('source.docx', body), target)
    assert not xml_part(target).findall('.//' + W + 'tblPrExChange')
    assert xml_part(target).find('.//' + W + 'tblPrEx/' + W + 'tblW').get(W + 'w') == '2400'
    assert_segments(xml_part(target), [('text', '000000')])
    assert_integrity(target)


def test_CF017_color_property_order(docx, tmp_path):
    target = tmp_path / 'out.docx'
    convert(docx('source.docx', p(run('text', '<w:rFonts w:ascii="Cambria"/><w:b/><w:sz w:val="24"/>'))), target)
    tags = [etree.QName(n).localname for n in xml_part(target).find('.//' + W + 'rPr')]
    assert tags == ['rFonts', 'b', 'color', 'sz']
