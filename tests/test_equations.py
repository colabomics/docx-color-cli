from pathlib import Path

import pytest
from lxml import etree

from docx_color_cli.cli import convert
from helpers.assertions import xml_without_font_colors, assert_integrity, assert_rejects_without_output, xml_part
from helpers.fixtures import M, W, fraction, p, revision


def test_EQ001_equation_structure_preserved(docx, tmp_path):
    source = docx('source.docx', p(fraction()))
    target = tmp_path / 'out.docx'
    convert(source, target)
    assert xml_without_font_colors(xml_part(source).find('.//' + M + 'oMath')) == xml_without_font_colors(xml_part(target).find('.//' + M + 'oMath'))
    assert_integrity(target)


def test_CF008_math_control_revision_rejected(docx, tmp_path):
    body = (Path(__file__).parent / 'fixtures/equations/deleted_control.xml').read_text(encoding='utf-8')
    assert_rejects_without_output(convert, docx('source.docx', body), tmp_path / 'out.docx')


@pytest.mark.parametrize('inserted,color', [(False,'000000'), (True,'FF0000')])
def test_CF016_math_run_color(docx, tmp_path, inserted, color):
    content = '<m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>x</m:t></m:r>'
    if inserted:
        content = revision('ins', content)
    source = docx('source.docx', p('<m:oMath>' + content + '</m:oMath>'))
    target = tmp_path / 'out.docx'
    convert(source, target)
    root = xml_part(target)
    color_node = root.find('.//' + M + 'r/' + W + 'rPr/' + W + 'color')
    assert color_node is not None and color_node.get(W + 'val') == color
    assert root.find('.//' + M + 'sty').get(M + 'val') == 'p'
    assert_integrity(target)
