from pathlib import Path
from zipfile import ZipFile

import pytest
from lxml import etree

import docx_color_cli.cli as cli
from helpers.assertions import assert_rejects_without_output
from helpers.fixtures import W, insert, p, paragraph, rewrite, run, story


@pytest.mark.parametrize('damage', ['lost', 'duplicate', 'reordered'])
def test_P0_retained_content_guard(docx, tmp_path, monkeypatch, damage):
    source = docx('source.docx', p(run('first') + insert('second')))
    target = docx('out.docx', paragraph('previous'))
    modify = cli.modify
    def broken(root, *args):
        modify(root, *args)
        para = root.find('.//' + W + 'p')
        if damage == 'lost':
            para.remove(para[-1])
        elif damage == 'duplicate':
            from copy import deepcopy
            para.append(deepcopy(para[-1]))
        else:
            para.insert(0, para[-1])
        return root
    monkeypatch.setattr(cli, 'modify', broken)
    assert_rejects_without_output(cli.convert, source, target)
    assert sorted(f.name for f in tmp_path.iterdir()) == ['out.docx', 'source.docx']


@pytest.mark.parametrize('damage', ['residual', 'broken-field', 'bad-relationship', 'missing-member', 'changed-text'])
def test_P0_validate_temporary_package_before_publication(docx, tmp_path, monkeypatch, damage):
    source = docx('source.docx', paragraph('original'))
    target = docx('out.docx', paragraph('previous'))
    write = ZipFile.writestr
    def corrupt(self, info, data, *args, **kwargs):
        name = info.filename if hasattr(info, 'filename') else info
        if name == 'word/document.xml':
            if damage == 'missing-member':
                return
            data = data.replace(b'original', b'altered') if damage == 'changed-text' else data
            nodes = {'residual': '<w:ins w:id="1"/>', 'broken-field': '<w:r><w:fldChar w:fldCharType="end"/></w:r>', 'bad-relationship': '<w:hyperlink r:id="absent"/>'}
            if damage in nodes:
                data = data.replace(b'</w:p>', nodes[damage].encode() + b'</w:p>')
        return write(self, info, data, *args, **kwargs)
    monkeypatch.setattr(ZipFile, 'writestr', corrupt)
    assert_rejects_without_output(cli.convert, source, target)
    assert sorted(f.name for f in tmp_path.iterdir()) == ['out.docx', 'source.docx']


@pytest.mark.parametrize('marker', ['cellIns', 'cellDel', 'cellMerge'])
def test_P0_no_strict_cannot_publish_unsupported_table_revision(docx, tmp_path, marker):
    body = '<w:tbl><w:tr><w:tc><w:tcPr><w:' + marker + ' w:id="1"><w:unknown/></w:' + marker + '></w:tcPr>' + paragraph('keep') + '</w:tc></w:tr></w:tbl>'
    assert_rejects_without_output(cli.convert, docx('source.docx', body), tmp_path / 'out.docx', strict=False)


def test_CF005_nonstandard_note_path(docx, tmp_path):
    from helpers.fixtures import relationships
    source = docx('source.docx', p('<w:r><w:footnoteReference w:id="1"/></w:r>'), {
        'word/notes/research.xml': story('footnotes', '<w:footnote w:id="1">' + p(insert('note')) + '</w:footnote>'),
        'word/_rels/document.xml.rels': relationships([('notes','footnotes','notes/research.xml',False)])})
    target = tmp_path / 'out.docx'
    cli.convert(source, target)
    from helpers.assertions import assert_segments, xml_part
    assert_segments(xml_part(target, 'word/notes/research.xml'), [('note', 'FF0000')])


def test_P0_revisions_in_nonstory_part_cannot_be_left_behind(docx, tmp_path):
    source = docx('source.docx', paragraph('keep'), {'word/styles.xml': story('styles', '<w:style w:styleId="normal"><w:rPr><w:rPrChange w:id="1"><w:rPr/></w:rPrChange></w:rPr></w:style>')})
    assert_rejects_without_output(cli.convert, source, tmp_path / 'out.docx')


@pytest.mark.parametrize('damage', ['paragraph', 'cell'])
def test_P0_structure_guard_detects_boundary_loss(docx, tmp_path, monkeypatch, damage):
    body = paragraph('first') + paragraph('second') if damage == 'paragraph' else '<w:tbl><w:tr><w:tc>' + paragraph('first') + '</w:tc><w:tc>' + paragraph('second') + '</w:tc></w:tr></w:tbl>'
    source = docx('source.docx', body)
    target = tmp_path / 'out.docx'
    modify = cli.modify
    def broken(root, *args):
        modify(root, *args)
        nodes = list(root.iter(W + ('p' if damage == 'paragraph' else 'tc')))
        for child in list(nodes[1]):
            nodes[0].append(child)
        nodes[1].getparent().remove(nodes[1])
        return root
    monkeypatch.setattr(cli, 'modify', broken)
    assert_rejects_without_output(cli.convert, source, target)
