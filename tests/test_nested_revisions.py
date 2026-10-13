import pytest

from docx_color_cli.cli import convert
from helpers.assertions import assert_integrity, assert_segments, xml_part
from helpers.fixtures import W, field, p, revision, run


@pytest.mark.parametrize('content,expected', [
    (revision('ins', run('A') + revision('del', run('gone')) + run('B')), [('AB','FF0000')]),
    (revision('del', revision('ins', run('gone'))), []),
    (revision('ins', revision('ins', run('new'))), [('new','FF0000')]),
    (revision('del', revision('del', run('gone'))), []),
    (revision('ins', run('A') + revision('del', revision('ins', run('gone'))) + revision('ins', run('B'))), [('AB','FF0000')]),
], ids=['insert-delete','delete-insert','insert-insert','delete-delete','three-level'])
@pytest.mark.parametrize('strict', [True, False])
def test_nested_deletion_dominates(docx, tmp_path, content, expected, strict):
    source = docx('source.docx', p(run('before ') + content + run(' after')))
    original = source.read_bytes()
    target = tmp_path / 'out.docx'
    convert(source, target, strict=strict)
    assert_segments(xml_part(target), [('before ','000000'), *expected, (' after','000000')])
    assert_integrity(target)
    assert source.read_bytes() == original


def test_nested_zotero_result_keeps_field(docx, tmp_path):
    code = ' ADDIN ZOTERO_ITEM CSL_CITATION {"id":"synthetic"} '
    result = revision('ins', run('(1') + revision('del', run(', 2')) + run(')'))
    source = docx('source.docx', p(field(code, result)))
    target = tmp_path / 'out.docx'
    convert(source, target)
    root = xml_part(target)
    assert [n.text for n in root.iter(W+'instrText')] == [code]
    assert [n.get(W+'fldCharType') for n in root.iter(W+'fldChar')] == ['begin','separate','end']
    assert_segments(root, [('(1)','FF0000')])
    assert_integrity(target)


@pytest.mark.parametrize('kind,inner,expected', [
    ('moveTo', 'del', [('stay ', '000000')]),
    ('moveTo', 'ins', [('stay ', '000000'), ('moved', 'FF0000')]),
    ('moveFrom', 'ins', [('stay ', '000000'), ('moved', 'FF0000')]),
])
def test_nested_edits_inside_paired_moves(docx, tmp_path, kind, inner, expected):
    def moved(which, ident):
        payload = run('moved')
        if which == kind:
            payload = revision(inner, payload, '20')
        return f'<w:{which}RangeStart w:id="{ident}" w:name="pair"/>' + revision(which, payload, ident) + f'<w:{which}RangeEnd w:id="{ident}"/>'
    source = docx('source.docx', p(moved('moveFrom','1') + run('stay ') + moved('moveTo','2')))
    target = tmp_path / 'out.docx'
    stats = convert(source, target)
    assert_segments(xml_part(target), expected)
    if kind == 'moveFrom':
        assert stats.get('accepted_ins',0) == 0
    assert_integrity(target)
