"""References must not silently outlive a bookmark removed by acceptance."""
import pytest

from docx_color_cli.cli import convert
from helpers.assertions import assert_integrity, assert_rejects_without_output, xml_part
from helpers.fixtures import W, field, p, revision, run

BOOKMARK = '<w:bookmarkStart w:id="1" w:name="target"/>' + run('target') + '<w:bookmarkEnd w:id="1"/>'

@pytest.mark.parametrize('reference', [
    field(' REF target \\h ', run('target')),
    field(' PAGEREF "target" ', run('1')),
    '<w:fldSimple w:instr="REF target">' + run('target') + '</w:fldSimple>',
    '<w:hyperlink w:anchor="target">' + run('target') + '</w:hyperlink>',
    field(' HYPERLINK \\l "target" ', run('target')),
    field(' HYPERLINK \\h \\l "target" ', run('target')),
    field(' HYPERLINK "" \\o "tip" \\l "target" ', run('target')),
    field(' REF target ', run('target')).replace('REF target', 'REF tar</w:instrText></w:r><w:r><w:instrText>get'),
])
def test_CF009_CF010_deleted_target_rejected(docx, tmp_path, reference):
    source = docx('source.docx', p(revision('del', BOOKMARK) + reference))
    assert_rejects_without_output(convert, source, tmp_path / 'out.docx')


def test_cross_paragraph_field_and_target_preserved(docx, tmp_path):
    code = field(' REF target ', run('result')).replace('<w:r><w:fldChar w:fldCharType="separate"', '</w:p><w:p><w:r><w:fldChar w:fldCharType="separate"')
    source = docx('source.docx', p(BOOKMARK) + p(code))
    output = tmp_path / 'output.docx'
    convert(source, output)
    assert [n.text for n in xml_part(output).iter(W + 'instrText')] == [' REF target ']
    assert len(list(xml_part(output).iter(W + 'p'))) == 3
    assert_integrity(output)


def test_external_hyperlink_anchor_is_not_local(docx, tmp_path):
    source = docx('source.docx', p(field(' HYPERLINK "https://example.org" \\l "target" ', run('link'))))
    output = tmp_path / 'output.docx'
    convert(source, output)
    assert_integrity(output)


def test_dynamic_reference_cannot_silently_lose_bookmarks(docx, tmp_path):
    dynamic = ('<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
               '<w:r><w:instrText> REF </w:instrText></w:r>' + field(' DOCVARIABLE target_name ', run('target')) +
               '<w:r><w:fldChar w:fldCharType="separate"/></w:r>' + run('result') +
               '<w:r><w:fldChar w:fldCharType="end"/></w:r>')
    source = docx('in.docx', p(revision('del', BOOKMARK) + dynamic))
    assert_rejects_without_output(convert, source, tmp_path / 'out.docx')
