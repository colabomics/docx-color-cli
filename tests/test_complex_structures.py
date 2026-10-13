from zipfile import ZipFile

import pytest
from lxml import etree

from docx_color_cli.cli import convert
from helpers.assertions import assert_integrity, assert_segments, paragraphs, xml_part
from helpers.fixtures import W, PNG, delete, image_run, insert, p, relationships, run, story


def test_CX001_image_reference_relationship_and_resource(docx, tmp_path):
    parts = {'word/_rels/document.xml.rels': relationships([('image1','image','media/pixel.png',False)]), 'word/media/pixel.png': PNG}
    source = docx('source.docx', p(run('before') + image_run() + insert('after')), parts)
    target = tmp_path / 'out.docx'
    convert(source, target)
    assert etree.tostring(xml_part(source).find('.//' + W + 'drawing')) == etree.tostring(xml_part(target).find('.//' + W + 'drawing'))
    with ZipFile(source) as zin, ZipFile(target) as zout:
        for name in parts:
            assert zin.read(name) == zout.read(name)
    assert_segments(xml_part(target), [('before','000000'), ('after','FF0000')])
    assert_integrity(target)


@pytest.mark.parametrize('name,kind,container', [
    ('header1','hdr',None), ('footer1','ftr',None), ('footnotes','footnotes','footnote'),
    ('endnotes','endnotes','endnote'), ('comments','comments','comment')
], ids=['CX002-header','CX003-footer','CX004-footnote','CX005-endnote','CX006-comment'])
def test_all_standard_stories(docx, tmp_path, name, kind, container):
    content = p(run('old ') + delete('gone') + insert('new'))
    if container:
        content = f'<w:{container} w:id="1">{content}</w:{container}>'
    parts = {f'word/{name}.xml': story(kind, content)}
    body = p(run('body'))
    if container:
        body += p(f'<w:r><w:{container}Reference w:id="1"/></w:r>')
    target = tmp_path / 'out.docx'
    convert(docx('source.docx', body, parts), target)
    assert_segments(xml_part(target, f'word/{name}.xml'), [('old ','000000'), ('new','FF0000')])
    assert_integrity(target)


def test_CX007_bookmarks_content_controls_preserved(docx, tmp_path):
    body = p('<w:bookmarkStart w:id="1" w:name="target"/><w:sdt><w:sdtPr><w:tag w:val="sample"/><w:id w:val="42"/></w:sdtPr><w:sdtContent>' + run('old') + insert('new') + '</w:sdtContent></w:sdt><w:bookmarkEnd w:id="1"/>')
    target = tmp_path / 'out.docx'
    convert(docx('source.docx', body), target)
    root = xml_part(target)
    assert root.find('.//' + W + 'bookmarkStart').get(W + 'name') == 'target'
    assert root.find('.//' + W + 'bookmarkEnd').get(W + 'id') == '1'
    assert root.find('.//' + W + 'sdtPr/' + W + 'tag').get(W + 'val') == 'sample'
    assert_segments(root, [('old','000000'), ('new','FF0000')])
    assert_integrity(target)


def test_CX008_tabs_breaks_and_symbols_preserved(docx, tmp_path):
    body = p(run('A') + '<w:r><w:tab/><w:t>B</w:t><w:br/><w:t>C</w:t><w:sym w:font="Symbol" w:char="F061"/></w:r>' + insert('!'))
    target = tmp_path / 'out.docx'
    convert(docx('source.docx', body), target)
    root = xml_part(target)
    assert paragraphs(target) == ['A\tB\nC!']
    assert root.find('.//' + W + 'sym').get(W + 'char') == 'F061'
    assert_segments(root, [('ABC','000000'), ('!','FF0000')])
    assert_integrity(target)
