import pytest
from helpers.fixtures import p,run,field,relationships,story
from helpers.content import validate_docx


@pytest.fixture(autouse=True, params=['helper', 'production'])
def select_validator(request, monkeypatch):
    import sys
    if request.param == 'helper':
        from helpers.content import validate_docx as implementation
    else:
        from docx_color_cli.validation import validate_docx as implementation
    monkeypatch.setattr(sys.modules[__name__], 'validate_docx', implementation)


def test_bookmark_renumbering_keeps_name_pair_and_position(docx):
    def body(ident,name='target',inside='x'):
        return p(f'<w:bookmarkStart w:id="{ident}" w:name="{name}"/>'+run(inside)+f'<w:bookmarkEnd w:id="{ident}"/>')
    a=docx('a.docx',body('140'));b=docx('b.docx',body('0'))
    assert not validate_docx(a,b).ok
    assert validate_docx(a,b,semantic=True).ok
    c=docx('c.docx',body('0','changed'))
    assert not validate_docx(a,c,semantic=True).ok


def test_bookmark_range_change_not_equivalent(docx):
    a=docx('a.docx',p('<w:bookmarkStart w:id="1" w:name="t"/>'+run('A')+'<w:bookmarkEnd w:id="1"/>'+run('B')))
    b=docx('b.docx',p('<w:bookmarkStart w:id="2" w:name="t"/>'+run('AB')+'<w:bookmarkEnd w:id="2"/>'))
    assert not validate_docx(a,b,semantic=True).ok


@pytest.mark.parametrize('code,target,equal',[
 (' HYPERLINK "https://example.org" ','https://example.org',True),
 (' HYPERLINK "https://example.org" ','https://changed.example',False),
 (' HYPERLINK "https://example.org" \\h ','https://example.org',True),
 (' HYPERLINK "https://example.org" \\h ','https://changed.example',False),
 (' REF target ','https://example.org',False),
])
def test_field_hyperlink_equivalence_is_narrow(docx,code,target,equal):
    a=docx('a.docx',p(field(code,run('link'))))
    b=docx('b.docx',p('<w:hyperlink r:id="link">'+run('link')+'</w:hyperlink>'),{'word/_rels/document.xml.rels':relationships([('link','hyperlink',target,True)])})
    assert validate_docx(a,b,semantic=True).ok==equal
    assert not validate_docx(a,b).ok


def test_link_result_style_and_editability_not_ignored(docx):
    a=docx('a.docx',p(field(' HYPERLINK "https://example.org" ',run('link'))))
    plain=docx('plain.docx',p(run('link')))
    styled=docx('styled.docx',p('<w:hyperlink r:id="l">'+run('link','<w:b/>')+'</w:hyperlink>'),{'word/_rels/document.xml.rels':relationships([('l','hyperlink','https://example.org',True)])})
    assert not validate_docx(a,plain,semantic=True).ok
    assert not validate_docx(a,styled,semantic=True).ok


def test_view_zoom_equivalent_but_layout_setting_not(docx):
    a=docx('a.docx',p(run('x')),{'word/settings.xml':story('settings','<w:zoom w:percent="179"/>')})
    b=docx('b.docx',p(run('x')),{'word/settings.xml':story('settings','<w:zoom w:percent="118"/>')})
    c=docx('c.docx',p(run('x')),{'word/settings.xml':story('settings','<w:zoom w:percent="118"/><w:evenAndOddHeaders/>')})
    assert validate_docx(a,b,semantic=True).ok
    assert not validate_docx(a,c,semantic=True).ok


def test_drawing_edit_id_equivalence_never_ignores_image_bytes(docx):
    from helpers.fixtures import PNG,image_run
    def make(name,edit,data):
        body=image_run().replace('<wp:inline>','<wp:inline xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing" wp14:editId="'+edit+'">')
        return docx(name,p(body),{'word/media/pixel.png':data,'word/_rels/document.xml.rels':relationships([('image1','image','media/pixel.png',False)])})
    a=make('a.docx','00000001',PNG);b=make('b.docx','00000002',PNG);c=make('c.docx','00000002',PNG+b'changed')
    assert not validate_docx(a,b).ok
    assert validate_docx(a,b,semantic=True).ok
    assert not validate_docx(a,c,semantic=True).ok


def test_font_signature_difference_remains_failure(docx):
    def make(name,value):return docx(name,p(run('text')),{'word/fontTable.xml':story('fonts','<w:font w:name="Arial"><w:sig w:usb0="'+value+'"/></w:font>')})
    assert not validate_docx(make('a.docx','00000001'),make('b.docx','00000002'),semantic=True).ok


def test_split_hyperlink_code_and_rsid_are_equivalent(docx):
    code=field('HYPERLINK "https://example.org"',run('link')).replace('<w:r>','<w:r w:rsidR="00000001">').replace('HYPERLINK "https://example.org"','HYPERLINK </w:instrText></w:r><w:r><w:instrText>"https://example.org"')
    code=code.replace('<w:r><w:fldChar w:fldCharType="separate"/>', '<w:r><w:rPr><w:b/></w:rPr></w:r><w:r><w:fldChar w:fldCharType="separate"/>')
    a=docx('a.docx',p(code))
    b=docx('b.docx',p('<w:hyperlink r:id="l" w:history="1">'+run('link')+'</w:hyperlink>'),{'word/_rels/document.xml.rels':relationships([('l','hyperlink','https://example.org',True)])})
    assert validate_docx(a,b,semantic=True).ok


@pytest.mark.parametrize('suffix', [r'\h \l bookmark', r'\h \s location',
                                      r'\h \o tooltip', r'\h \unknown',
                                      r'\h argument', r'\hello', r'\h \h'])
def test_hyperlink_h_does_not_hide_other_switches(docx, suffix):
    a=docx('a.docx',p(field('HYPERLINK "https://example.org" '+suffix,run('link'))))
    b=docx('b.docx',p('<w:hyperlink r:id="l">'+run('link')+'</w:hyperlink>'),
           {'word/_rels/document.xml.rels':relationships([('l','hyperlink','https://example.org',True)])})
    assert not validate_docx(a,b,semantic=True).ok


@pytest.mark.parametrize('change', ['none','text','style','plain','locked'])
def test_split_h_switch_preserves_result_and_field_constraints(docx,change):
    code=field('HYPERLINK "https://example.org" \\h ',run('link'))
    code=code.replace('\\h ', '\\</w:instrText></w:r><w:r><w:instrText xml:space="preserve">h ')
    if change=='locked':
        code=code.replace('w:fldCharType="begin"','w:fldCharType="begin" w:fldLock="true"')
    a=docx('a.docx',p(code))
    result=run('changed' if change=='text' else 'link','<w:b/>' if change=='style' else '')
    body=result if change=='plain' else '<w:hyperlink r:id="l">'+result+'</w:hyperlink>'
    b=docx('b.docx',p(body),{'word/_rels/document.xml.rels':relationships([('l','hyperlink','https://example.org',True)])})
    validation=validate_docx(a,b,semantic=True)
    assert validation.ok==(change=='none')
    assert not validate_docx(a,b).ok
    if change=='none':
        assert any('hyperlink visit-history switch' in warning for warning in validation.warnings)
