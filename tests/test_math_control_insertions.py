import pytest
from docx_color_cli.cli import convert
from helpers.fixtures import W, M, p, revision
from helpers.assertions import xml_part, assert_integrity, assert_rejects_without_output


def control(payload='<w:rPr><w:rFonts w:ascii="Cambria Math"/><w:b/><w:color w:val="123456" w:themeColor="accent1"/><w:sz w:val="24"/></w:rPr>'):
    return '<m:ctrlPr>'+revision('ins',payload)+'</m:ctrlPr>'


@pytest.mark.parametrize('kind,args', [('d',['e']),('f',['num','den']),('sSub',['e','sub']),('nary',['sub','sup','e']),('func',['fName','e']),('eqArr',['e']),('rad',['deg','e']),('sSup',['e','sup'])])
def test_inserted_control_retains_object_and_arguments(docx,tmp_path,kind,args):
    content=''.join(f'<m:{a}><m:r><m:t>keep</m:t></m:r><m:r>'+revision('ins','<m:t>new</m:t>')+f'</m:r></m:{a}>' for a in args)
    source=docx('in.docx',p(f'<m:oMath><m:{kind}><m:{kind}Pr>'+control()+f'</m:{kind}Pr>'+content+f'</m:{kind}></m:oMath>'))
    original=source.read_bytes();target=tmp_path/'out.docx';convert(source,target,red='AA0011')
    root=xml_part(target);obj=root.find('.//'+M+kind)
    assert obj is not None
    assert [n.text for n in obj.iter(M+'t')]==['keep','new']*len(args)
    props=obj.find(M+kind+'Pr/'+M+'ctrlPr/'+W+'rPr')
    assert props.find(W+'color').get(W+'val')=='AA0011'
    assert props.find(W+'color').get(W+'themeColor') is None
    assert props.find(W+'rFonts').get(W+'ascii')=='Cambria Math'
    assert props.find(W+'b') is not None
    assert props.find(W+'sz').get(W+'val')=='24'
    for r in obj.iter(M+'r'):
        assert r.find(W+'rPr/'+W+'color').get(W+'val')==('000000' if r.find(M+'t').text=='keep' else 'AA0011')
    assert source.read_bytes()==original
    assert_integrity(target)


@pytest.mark.parametrize('payload',['','<w:rPr/>'])
def test_inserted_control_without_font_properties(docx,tmp_path,payload):
    source=docx('in.docx',p('<m:oMath><m:d><m:dPr>'+control(payload)+'</m:dPr><m:e/></m:d></m:oMath>'))
    target=tmp_path/'out.docx';convert(source,target)
    assert xml_part(target).find('.//'+M+'ctrlPr/'+W+'rPr/'+W+'color').get(W+'val')=='FF0000'
    assert_integrity(target)


@pytest.mark.parametrize('payload',['<w:rPr/><w:rPr/>','<w:del/><w:rPr/>','<m:r><m:t>bad</m:t></m:r>'])
def test_ambiguous_control_insertion_refused(docx,tmp_path,payload):
    source=docx('in.docx',p('<m:oMath><m:d><m:dPr>'+control(payload)+'</m:dPr><m:e/></m:d></m:oMath>'))
    assert_rejects_without_output(convert,source,tmp_path/'out.docx',strict=False)


@pytest.mark.parametrize('survives',[False,True])
def test_inserted_then_deleted_control(docx,tmp_path,survives):
    payload='<m:r><m:t>x</m:t></m:r>' if survives else '<m:r>'+revision('del','<m:t>x</m:t>')+'</m:r>'
    content='<m:sSup><m:sSupPr>'+control('<w:del w:id="2"><w:rPr/></w:del>')+'</m:sSupPr><m:e>'+payload+'</m:e><m:sup>'+payload+'</m:sup></m:sSup>'
    source=docx('in.docx',p('<m:oMath>'+content+'</m:oMath>'));target=tmp_path/'out.docx'
    if survives:
        assert_rejects_without_output(convert,source,target)
    else:
        convert(source,target)
        assert not list(xml_part(target).iter(M+'sSup'))
        assert not list(xml_part(target).iter(M+'t'))
        assert_integrity(target)


@pytest.mark.parametrize('math_properties',[False,True])
def test_properties_in_wholly_deleted_math_run(docx,tmp_path,math_properties):
    props=('<m:rPr><m:sty m:val="p"/></m:rPr>' if math_properties else '')+'<w:rPr><w:b/></w:rPr>'
    source=docx('in.docx',p('<m:oMath><m:r>'+revision('del',props+'<m:t>gone</m:t>')+'</m:r><m:r><m:t>keep</m:t></m:r></m:oMath>'))
    target=tmp_path/'out.docx';convert(source,target)
    assert [n.text for n in xml_part(target).iter(M+'t')]==['keep']
    assert not list(xml_part(target).iter(W+'t'))
    assert_integrity(target)


@pytest.mark.parametrize('body',[
    '<m:oMath>'+control()+'</m:oMath>',
    '<m:oMath><m:d><m:dPr><m:ctrlPr><w:rPr/>'+revision('ins','<w:rPr/>')+'</m:ctrlPr></m:dPr><m:e/></m:d></m:oMath>',
])
def test_control_location_and_conflicting_properties(docx,tmp_path,body):
    assert_rejects_without_output(convert,docx('in.docx',p(body)),tmp_path/'out.docx')


def test_nested_inserted_controls_preserve_black_parameters(docx,tmp_path):
    inner='<m:sSup><m:sSupPr>'+control()+'</m:sSupPr><m:e><m:r><m:t>x</m:t></m:r></m:e><m:sup><m:r><m:t>2</m:t></m:r></m:sup></m:sSup>'
    source=docx('in.docx',p('<m:oMath><m:d><m:dPr>'+control()+'</m:dPr><m:e>'+inner+'</m:e></m:d></m:oMath>'))
    target=tmp_path/'out.docx';stats=convert(source,target)
    root=xml_part(target)
    assert stats['accepted_math_control_ins']==2
    assert [c.find(W+'rPr/'+W+'color').get(W+'val') for c in root.iter(M+'ctrlPr')]==['FF0000','FF0000']
    assert [r.find(W+'rPr/'+W+'color').get(W+'val') for r in root.iter(M+'r')]==['000000','000000']
    assert [t.text for t in root.iter(M+'t')]==['x','2']
    assert_integrity(target)
