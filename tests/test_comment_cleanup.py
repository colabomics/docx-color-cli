from zipfile import ZipFile
import pytest
from docx_color_cli.cli import convert
from helpers.fixtures import W,p,run,revision,story
from helpers.assertions import xml_part,assert_integrity


def anchor(ident):return f'<w:r><w:commentReference w:id="{ident}"/></w:r>'
def definition(ident):return f'<w:comment w:id="{ident}">'+p(run('comment'))+'</w:comment>'


@pytest.mark.parametrize('keep',[False,True])
def test_deleted_comment_anchor_removes_only_its_definition_and_range(docx,tmp_path,keep):
    body=p('<w:commentRangeStart w:id="1"/>'+run('kept')+'<w:commentRangeEnd w:id="1"/>'+revision('del',anchor('1'))+(anchor('2') if keep else ''))
    source=docx('in.docx',body,{'word/comments.xml':story('comments',definition('1')+(definition('2') if keep else ''))})
    original=source.read_bytes();target=tmp_path/'out.docx';convert(source,target)
    root=xml_part(target)
    assert not list(root.iter(W+'commentRangeStart'))
    assert not list(root.iter(W+'commentRangeEnd'))
    with ZipFile(target) as z:
        assert ('word/comments.xml' in z.namelist())==keep
    if keep:assert [n.get(W+'id') for n in xml_part(target,'word/comments.xml')]==['2']
    assert source.read_bytes()==original
    assert_integrity(target)


def test_existing_orphan_and_surviving_comment_preserved(docx,tmp_path):
    body=p(anchor('1')+revision('del',anchor('1')))
    source=docx('in.docx',body,{'word/comments.xml':story('comments',definition('1')+definition('2'))})
    target=tmp_path/'out.docx';convert(source,target)
    assert [n.get(W+'id') for n in xml_part(target,'word/comments.xml')]==['1','2']
    assert_integrity(target)


def modern_parts(thread=False):
    from helpers.fixtures import relationships
    w14='http://schemas.microsoft.com/office/word/2010/wordml'
    comments=story('comments',''.join(f'<w:comment w:id="{i}"><w:p xmlns:w14="{w14}" w14:paraId="P{i}">'+run('comment')+'</w:p></w:comment>' for i in ['1','2']))
    return {'word/comments.xml':comments,
      'word/commentsIds.xml':'<w16cid:commentsIds xmlns:w16cid="http://schemas.microsoft.com/office/word/2016/wordml/cid"><w16cid:commentId w16cid:paraId="P1" w16cid:durableId="D1"/><w16cid:commentId w16cid:paraId="P2" w16cid:durableId="D2"/></w16cid:commentsIds>',
      'word/commentsExtended.xml':'<w15:commentsEx xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml"><w15:commentEx w15:paraId="P1"/><w15:commentEx w15:paraId="P2"'+(' w15:paraIdParent="P1"' if thread else '')+'/></w15:commentsEx>',
      'word/commentsExtensible.xml':'<w16cex:commentsExtensible xmlns:w16cex="http://schemas.microsoft.com/office/word/2018/wordml/cex"><w16cex:commentExtensible w16cex:durableId="D1"/><w16cex:commentExtensible w16cex:durableId="D2"/></w16cex:commentsExtensible>'}


def test_partial_modern_comment_cleanup_keeps_other_records(docx,tmp_path):
    source=docx('in.docx',p(revision('del',anchor('1'))+anchor('2')),modern_parts())
    target=tmp_path/'out.docx';convert(source,target)
    for name in ['comments.xml','commentsIds.xml','commentsExtended.xml','commentsExtensible.xml']:
        root=xml_part(target,'word/'+name)
        assert len(root)==1
        assert all(v not in ['1','P1','D1'] for v in root[0].attrib.values())
    assert_integrity(target)


def test_surviving_reply_prevents_parent_comment_deletion(docx,tmp_path):
    from helpers.assertions import assert_rejects_without_output
    source=docx('in.docx',p(revision('del',anchor('1'))+anchor('2')),modern_parts(thread=True))
    assert_rejects_without_output(convert,source,tmp_path/'out.docx')


def test_unknown_relationship_to_comments_is_not_silently_removed(docx,tmp_path):
    from helpers.fixtures import relationships
    from helpers.assertions import assert_rejects_without_output
    source=docx('in.docx',p(revision('del',anchor('1'))),{'word/comments.xml':story('comments',definition('1')),'word/_rels/document.xml.rels':relationships([('c','comments','comments.xml',False),('extra','unknown','comments.xml',False)])})
    assert_rejects_without_output(convert,source,tmp_path/'out.docx')


def test_comment_part_not_identified_by_filename(docx,tmp_path):
    from helpers.fixtures import relationships
    source=docx('in.docx',p(revision('del',anchor('1'))),{'word/other.xml':story('comments',definition('1')),'word/_rels/document.xml.rels':relationships([('c','comments','other.xml',False)])})
    target=tmp_path/'out.docx';convert(source,target)
    with ZipFile(target) as z:assert 'word/other.xml' not in z.namelist()
    assert_integrity(target)
