from zipfile import ZipFile
import pytest
from lxml import etree
from docx_color_cli.cli import convert
from helpers.fixtures import PNG, W, p, run, revision, image_run, relationships, story
from helpers.assertions import assert_integrity, xml_part


def image(rid):
    return image_run().replace('image1',rid).replace('<w:r>', '<w:r xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">', 1)


def source_doc(docx,extra=None,body=None):
    parts={'word/media/keep.png':PNG,'word/media/gone.png':PNG+b'gone',
           'word/_rels/document.xml.rels':relationships([('keep','image','media/keep.png',False),('gone','image','media/gone.png',False)])}
    parts.update(extra or {})
    return docx('in.docx',body if body is not None else p(image('keep')+revision('del',image('gone'))),parts)


def test_deleted_image_resource_and_relationship_removed(docx,tmp_path):
    source=source_doc(docx);before=source.read_bytes();target=tmp_path/'out.docx'
    stats=convert(source,target)
    with ZipFile(target) as z:
        assert 'word/media/gone.png' not in z.namelist()
        assert z.read('word/media/keep.png')==PNG
        assert [r.get('Id') for r in etree.fromstring(z.read('word/_rels/document.xml.rels'))]==['keep']
    assert stats['removed_media_parts']==1
    assert source.read_bytes()==before
    assert_integrity(target)


@pytest.mark.parametrize('owner', ['header1','footer1','footnotes','endnotes','comments','chart1'])
def test_other_parts_pin_shared_media(docx,tmp_path,owner):
    if owner=='chart1':
        content='<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><c:externalData r:id="shared"/></c:chartSpace>'
    elif owner in ['footnotes','endnotes','comments']:
        singular={'footnotes':'footnote','endnotes':'endnote','comments':'comment'}[owner]
        content=story(owner,f'<w:{singular} w:id="1">'+p(image('shared'))+f'</w:{singular}>')
    else:content=story('hdr' if owner=='header1' else 'ftr',p(image('shared')))
    source=source_doc(docx,{f'word/{owner}.xml':content,f'word/_rels/{owner}.xml.rels':relationships([('shared','image','media/gone.png',False)])})
    target=tmp_path/'out.docx';convert(source,target)
    with ZipFile(target) as z:assert z.read('word/media/gone.png')==PNG+b'gone'
    assert 'gone' not in [r.get('Id') for r in xml_part(target,'word/_rels/document.xml.rels')]
    assert_integrity(target)


def test_shared_id_kept_when_one_use_survives(docx,tmp_path):
    source=source_doc(docx,body=p(image('gone')+revision('del',image('gone'))+image('keep')))
    target=tmp_path/'out.docx';convert(source,target)
    with ZipFile(target) as z:assert z.read('word/media/gone.png')==PNG+b'gone'
    assert len(xml_part(target,'word/_rels/document.xml.rels'))==2


def test_preexisting_orphan_and_unknown_relationship_preserved(docx,tmp_path):
    source=source_doc(docx,{'word/media/orphan.png':PNG+b'orphan','word/custom.bin':b'opaque',
      'word/_rels/custom.bin.rels':relationships([('implicit','image','media/gone.png',False)])})
    target=tmp_path/'out.docx';convert(source,target)
    with ZipFile(target) as z:
        assert z.read('word/media/orphan.png')==PNG+b'orphan'
        assert z.read('word/media/gone.png')==PNG+b'gone'
        assert z.read('word/custom.bin')==b'opaque'
    assert_integrity(target)


def test_deleted_vml_image_reference(docx,tmp_path):
    vml='<w:r><w:pict xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office"><v:shape><v:imagedata o:relid="gone"/></v:shape></w:pict></w:r>'
    source=source_doc(docx,body=p(image('keep')+revision('del',vml)))
    target=tmp_path/'out.docx';convert(source,target)
    with ZipFile(target) as z:assert 'word/media/gone.png' not in z.namelist()
    assert_integrity(target)


def test_content_types_remove_only_deleted_overrides_and_unused_defaults(docx,tmp_path):
    from helpers.fixtures import rewrite
    source=source_doc(docx,body=p(revision('del',image('gone'))))
    # Keep image relationship is pre-existing unused: preserve it and its resource.
    with ZipFile(source) as z:root=etree.fromstring(z.read('[Content_Types].xml'))
    ns='{http://schemas.openxmlformats.org/package/2006/content-types}'
    etree.SubElement(root,ns+'Override',PartName='/word/media/gone.png',ContentType='image/png')
    rewrite(source,{'[Content_Types].xml':etree.tostring(root)})
    target=tmp_path/'out.docx';convert(source,target)
    ct=xml_part(target,'[Content_Types].xml')
    assert not any(n.get('PartName')=='/word/media/gone.png' for n in ct)
    assert any(n.get('Extension')=='png' for n in ct)
    assert_integrity(target)


def test_last_extension_default_removed(docx,tmp_path):
    source=docx('in.docx',p(revision('del',image('gone'))),{'word/media/gone.png':PNG,'word/_rels/document.xml.rels':relationships([('gone','image','/word/media/gone.png',False)])})
    target=tmp_path/'out.docx';convert(source,target)
    assert not any(n.get('Extension')=='png' for n in xml_part(target,'[Content_Types].xml'))
    assert_integrity(target)


def test_secondary_relation_to_same_image_pins_resource(docx,tmp_path):
    source=source_doc(docx,{'word/_rels/document.xml.rels':relationships([('keep','image','media/keep.png',False),('gone','image','media/gone.png',False),('implicit','customImageUse','media/gone.png',False)])})
    target=tmp_path/'out.docx';convert(source,target)
    with ZipFile(target) as z:assert z.read('word/media/gone.png')==PNG+b'gone'
    assert [r.get('Id') for r in xml_part(target,'word/_rels/document.xml.rels')]==['keep','implicit']


def test_external_images_and_nonimage_targets_not_pruned(docx,tmp_path):
    source=source_doc(docx,{'word/_rels/document.xml.rels':relationships([('keep','image','media/keep.png',False),('gone','image','https://example.org/image.png',True)])})
    target=tmp_path/'out.docx';convert(source,target)
    assert len(xml_part(target,'word/_rels/document.xml.rels'))==2
    assert_integrity(target)


def test_cleanup_failure_preserves_existing_output(docx,tmp_path,monkeypatch):
    import docx_color_cli.cli as cli
    source=source_doc(docx);original=source.read_bytes();target=tmp_path/'out.docx';target.write_bytes(b'existing')
    def fail(*args):raise ValueError('simulated cleanup error')
    monkeypatch.setattr(cli,'prune_images',fail)
    with pytest.raises(ValueError,match='simulated cleanup'):
        convert(source,target)
    assert target.read_bytes()==b'existing'
    assert source.read_bytes()==original
    assert {p.name for p in tmp_path.iterdir()}=={'in.docx','out.docx'}


def test_post_cleanup_validation_catches_live_resource_loss(docx,tmp_path,monkeypatch):
    import docx_color_cli.cli as cli
    real=cli.prune_images
    def corrupt(*args):
        removed,changes=real(*args)
        return removed|{'word/media/keep.png'},changes
    monkeypatch.setattr(cli,'prune_images',corrupt)
    source=source_doc(docx);target=tmp_path/'out.docx';target.write_bytes(b'existing')
    with pytest.raises(ValueError,match='missing relationship target'):
        convert(source,target)
    assert target.read_bytes()==b'existing'
    assert {p.name for p in tmp_path.iterdir()}=={'in.docx','out.docx'}


def test_literal_vml_path_keeps_resource(docx,tmp_path):
    literal='<w:r><w:pict xmlns:v="urn:schemas-microsoft-com:vml"><v:shape><v:imagedata src="media/gone.png"/></v:shape></w:pict></w:r>'
    source=source_doc(docx,body=p(revision('del',image('gone'))+literal+image('keep')))
    target=tmp_path/'out.docx';convert(source,target)
    with ZipFile(target) as z:assert z.read('word/media/gone.png')==PNG+b'gone'
    assert_integrity(target)


def test_percent_encoded_image_target(docx,tmp_path):
    source=docx('in.docx',p(revision('del',image('gone'))),{'word/media/a b.png':PNG,'word/_rels/document.xml.rels':relationships([('gone','image','media/a%20b.png',False)])})
    target=tmp_path/'out.docx';convert(source,target)
    with ZipFile(target) as z:assert 'word/media/a b.png' not in z.namelist()
    assert_integrity(target)


def test_image_relationship_to_nonimage_type_preserved(docx,tmp_path):
    source=source_doc(docx,{'word/data.bin':b'opaque','word/_rels/document.xml.rels':relationships([('keep','image','media/keep.png',False),('gone','image','data.bin',False)])})
    target=tmp_path/'out.docx';convert(source,target)
    assert len(xml_part(target,'word/_rels/document.xml.rels'))==2
    with ZipFile(target) as z:assert z.read('word/data.bin')==b'opaque'


def test_compound_image_with_own_relationships_preserved(docx,tmp_path):
    source=source_doc(docx,{'word/metadata.bin':b'keep','word/media/_rels/gone.png.rels':relationships([('data','custom','../metadata.bin',False)])})
    target=tmp_path/'out.docx';convert(source,target)
    with ZipFile(target) as z:
        assert z.read('word/media/gone.png')==PNG+b'gone'
        assert z.read('word/metadata.bin')==b'keep'
    assert_integrity(target)
