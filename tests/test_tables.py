from pathlib import Path

import pytest
from lxml import etree

from docx_color_cli.cli import convert
from helpers.assertions import xml_without_font_colors, assert_integrity, assert_segments, text, xml_part
from helpers.fixtures import M, W, PNG, delete, fraction, image_run, insert, p, relationships, run


def table(content, row_props='', cell_props=''):
    return '<w:tbl><w:tblPr/><w:tblGrid><w:gridCol w:w="2000"/></w:tblGrid><w:tr>' + (f'<w:trPr>{row_props}</w:trPr>' if row_props else '') + '<w:tc>' + (f'<w:tcPr>{cell_props}</w:tcPr>' if cell_props else '') + p(content) + '</w:tc></w:tr></w:tbl>'


@pytest.mark.parametrize('content,segments', [
    (run('A') + insert('B'), [('A','000000'), ('B','FF0000')]),
    (run('A') + delete('B'), [('A','000000')]),
    (delete('old') + insert('new'), [('new','FF0000')]),
], ids=['TB001-insert', 'TB002-delete', 'TB003-replace'])
def test_cell_text_revisions(docx, tmp_path, content, segments):
    target = tmp_path / 'out.docx'
    convert(docx('source.docx', table(content)), target)
    root = xml_part(target)
    rows = root.findall('.//' + W + 'tr')
    assert len(rows) == 1
    assert len(rows[0].findall(W + 'tc')) == 1
    assert text(rows[0]) == ''.join(t for t, _ in segments)
    assert_segments(root, segments)
    assert_integrity(target)


@pytest.mark.parametrize('tag', ['ins', 'del'])
def test_TB004_row_structural_revision_accepted(docx, tmp_path, tag):
    source = docx('source.docx', table(run('row'), f'<w:{tag} w:id="1"/>'))
    target = tmp_path / 'out.docx'
    before = source.read_bytes()
    convert(source, target)
    assert source.read_bytes() == before
    assert [text(r) for r in xml_part(target).iter(W + 'tr')] == (['row'] if tag == 'ins' else [])
    assert_segments(xml_part(target), [('row', '000000')] if tag == 'ins' else [])
    assert_integrity(target)


def test_CF003_deleted_row_removed(docx, tmp_path):
    body = (Path(__file__).parent / 'fixtures/tables/deleted_row.xml').read_text(encoding='utf-8')
    target = tmp_path / 'out.docx'
    convert(docx('source.docx', body), target, strict=False)
    rows = xml_part(target).findall('.//' + W + 'tr')
    assert [text(row) for row in rows] == ['keep']


@pytest.mark.parametrize('tag', ['cellIns', 'cellDel', 'cellMerge'])
def test_TB005_cell_structural_revision_rejected(docx, tmp_path, tag):
    with pytest.raises(ValueError, match=tag):
        convert(docx('source.docx', table(run('cell'), cell_props=f'<w:{tag} w:id="1"/>')), tmp_path / 'out.docx')
    assert not (tmp_path / 'out.docx').exists()


@pytest.mark.xfail(strict=True, raises=(AssertionError, ValueError), reason='CF012: cell revisions are safely rejected; acceptance remains unsupported')
@pytest.mark.parametrize('tag', ['cellIns', 'cellDel', 'cellMerge'])
def test_CF012_cell_revisions_fully_accepted(docx, tmp_path, tag):
    target = tmp_path / 'out.docx'
    convert(docx('source.docx', table(run('cell'), cell_props=f'<w:{tag} w:id="1"/>')), target, strict=False)
    assert not xml_part(target).findall('.//' + W + tag)


def test_TB006_cross_cell_replacement_preserves_boundaries(docx, tmp_path):
    body = '<w:tbl><w:tr><w:tc>' + p(delete('old A') + insert('new A')) + '</w:tc><w:tc>' + p(delete('old B') + insert('new B')) + '</w:tc></w:tr></w:tbl>'
    target = tmp_path / 'out.docx'
    convert(docx('source.docx', body), target)
    assert [text(c) for c in xml_part(target).findall('.//' + W + 'tc')] == ['new A', 'new B']
    assert_segments(xml_part(target), [('new Anew B', 'FF0000')])
    assert_integrity(target)


def test_TB007_table_image_equation_and_merged_cells(docx, tmp_path):
    body = table(run('cell') + image_run() + fraction(), cell_props='<w:gridSpan w:val="2"/>')
    # Two grid columns for the spanned cell.
    body = body.replace('<w:gridCol w:w="2000"/>', '<w:gridCol w:w="1000"/><w:gridCol w:w="1000"/>')
    parts = {'word/_rels/document.xml.rels': relationships([('image1','image','media/pixel.png',False)]), 'word/media/pixel.png': PNG}
    source = docx('source.docx', body, parts)
    target = tmp_path / 'out.docx'
    convert(source, target)
    before, after = xml_part(source), xml_part(target)
    for tag in [W + 'drawing', M + 'oMath', W + 'gridSpan', W + 'tblGrid']:
        serialize = xml_without_font_colors if tag == M + 'oMath' else etree.tostring
        assert serialize(before.find('.//' + tag)) == serialize(after.find('.//' + tag))
    assert_integrity(target)
