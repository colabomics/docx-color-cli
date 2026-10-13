from pathlib import Path
from zipfile import ZipFile

import pytest

from docx_color_cli.cli import convert
from helpers.assertions import assert_integrity, assert_rejects_without_output, assert_segments, paragraphs, xml_part
from helpers.content import field_issues
from helpers.fixtures import W, delete, field, insert, p, relationships, revision, run


@pytest.mark.parametrize('revised', [False, True], ids=['F001-link', 'F002-link-revision'])
def test_hyperlink(docx, tmp_path, revised):
    content = run('link') if not revised else delete('old') + insert('link')
    body = p('<w:hyperlink r:id="link1">' + content + '</w:hyperlink>')
    rels = relationships([('link1','hyperlink','https://example.org/paper?q=1&x=2',True)])
    source = docx('source.docx', body, {'word/_rels/document.xml.rels': rels})
    target = tmp_path / 'out.docx'
    convert(source, target)
    assert_segments(xml_part(target), [('link', 'FF0000' if revised else '000000')])
    assert xml_part(target).find('.//' + W + 'hyperlink').get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id') == 'link1'
    with ZipFile(source) as original, ZipFile(target) as output:
        assert output.read('word/_rels/document.xml.rels') == original.read('word/_rels/document.xml.rels')
    assert_integrity(target)


@pytest.mark.parametrize('code,result', [
    (' REF target \\h ', 'Section 1'),
    (' ADDIN ZOTERO_ITEM CSL_CITATION {"citationID":"synthetic","citationItems":[]} ', '(Smith, 2020)'),
    (' ADDIN ZOTERO_BIBL {"uncited":[],"omitted":[],"custom":[]} CSL_BIBLIOGRAPHY ', 'Smith. A synthetic paper.'),
    (' SEQ Figure \\* ARABIC ', '1'),
], ids=['F003-cross-reference','F004-zotero-citation','F005-zotero-bibliography','F006-complex-field'])
def test_fields_remain_editable(docx, tmp_path, code, result):
    body = p('<w:bookmarkStart w:id="7" w:name="target"/>' + run('target') + '<w:bookmarkEnd w:id="7"/>' + field(code, run(result)))
    target = tmp_path / 'out.docx'
    convert(docx('source.docx', body), target)
    root = xml_part(target)
    assert paragraphs(target) == ['target' + result]
    assert [n.text for n in root.iter(W + 'instrText')] == [code]
    assert [n.get(W + 'fldCharType') for n in root.iter(W + 'fldChar')] == ['begin', 'separate', 'end']
    assert root.find('.//' + W + 'bookmarkStart').get(W + 'name') == 'target'
    assert root.find('.//' + W + 'bookmarkEnd').get(W + 'id') == '7'
    assert_segments(root, [('target' + result, '000000')])
    assert not field_issues(root)
    assert_integrity(target)


def test_F009_nested_fields_preserved(docx, tmp_path):
    nested = field(' QUOTE ', field(' AUTHOR ', run('Synthetic Author')) + insert('!'))
    target = tmp_path / 'out.docx'
    convert(docx('source.docx', p(nested)), target)
    root = xml_part(target)
    assert [n.text for n in root.iter(W + 'instrText')] == [' QUOTE ', ' AUTHOR ']
    assert [n.get(W + 'fldCharType') for n in root.iter(W + 'fldChar')] == ['begin', 'separate', 'begin', 'separate', 'end', 'end']
    assert_segments(root, [('Synthetic Author','000000'), ('!','FF0000')])
    assert_integrity(target)


def test_F007_revised_citation_result_preserves_code(docx, tmp_path):
    code = ' ADDIN ZOTERO_ITEM CSL_CITATION {"citationID":"synthetic"} '
    target = tmp_path / 'out.docx'
    convert(docx('source.docx', p(field(code, delete('(Old, 2000)') + insert('(New, 2026)')))), target)
    root = xml_part(target)
    assert [n.text for n in root.iter(W + 'instrText')] == [code]
    assert_segments(root, [('(New, 2026)', 'FF0000')])
    assert_integrity(target)


def test_F008_simple_field(docx, tmp_path):
    target = tmp_path / 'out.docx'
    body = p('<w:fldSimple w:instr="AUTHOR">' + run('Synthetic Author') + '</w:fldSimple>')
    convert(docx('source.docx', body), target)
    assert xml_part(target).find('.//' + W + 'fldSimple').get(W + 'instr') == 'AUTHOR'
    assert_segments(xml_part(target), [('Synthetic Author', '000000')])
    assert_integrity(target)


def test_CF009_field_boundary_deletion(docx, tmp_path):
    body = (Path(__file__).parent / 'fixtures/fields/broken_revision.xml').read_text(encoding='utf-8')
    assert_rejects_without_output(convert, docx('source.docx', body), tmp_path / 'out.docx')


def test_CF010_bookmark_boundary_deletion(docx, tmp_path):
    body = p(revision('del', '<w:bookmarkStart w:id="7" w:name="target"/>' + '<w:r><w:delText>gone</w:delText></w:r>') + '<w:bookmarkEnd w:id="7"/>' + field(' REF target ', run('gone')))
    assert_rejects_without_output(convert, docx('source.docx', body), tmp_path / 'out.docx')


def test_hyperlink_h_field_revision_keeps_editable_code(docx, tmp_path):
    code=' HYPERLINK "https://example.org/paper?q=1&x=2" \\h '
    source=docx('source.docx',p(field(code,run('See ')+delete('old')+insert('paper'))))
    before=source.read_bytes()
    target=tmp_path/'out.docx'
    convert(source,target)
    root=xml_part(target)
    assert [n.text for n in root.iter(W+'instrText')]==[code]
    assert [n.get(W+'fldCharType') for n in root.iter(W+'fldChar')]==['begin','separate','end']
    assert_segments(root,[('See ','000000'),('paper','FF0000')])
    assert_integrity(target)
    assert source.read_bytes()==before
