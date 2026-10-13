import pytest
from docx_color_cli.cli import convert
from helpers.fixtures import p, revision, W, M
from helpers.assertions import xml_part, assert_integrity


@pytest.mark.parametrize('display',[False,True])
def test_removed_payload_cleans_math_container(docx,tmp_path,display):
    math='<m:oMath><m:r>'+revision('del','<m:t>gone</m:t>')+'</m:r></m:oMath>'
    if display:math='<m:oMathPara><m:oMathParaPr><m:jc m:val="center"/></m:oMathParaPr>'+math+'</m:oMathPara>'
    target=tmp_path/'out.docx';convert(docx('in.docx',p(math)),target)
    root=xml_part(target)
    assert not list(root.iter(M+'oMath'))
    assert not list(root.iter(M+'oMathPara'))
    assert len(list(root.iter(W+'p')))==1
    assert_integrity(target)


@pytest.mark.parametrize('math',[
 '<m:oMath/>',
 '<m:oMathPara><m:oMath/></m:oMathPara>',
 '<m:oMath><m:f><m:num/><m:den/></m:f></m:oMath>',
 '<m:oMath><m:r><m:t xml:space="preserve"> </m:t></m:r></m:oMath>',
 '<m:oMath><m:r>'+revision('del','<m:t>gone</m:t>')+'</m:r><m:r><m:t>keep</m:t></m:r></m:oMath>',
])
def test_preexisting_empty_placeholder_or_retained_content_kept(docx,tmp_path,math):
    target=tmp_path/'out.docx';convert(docx('in.docx',p(math)),target)
    assert len(list(xml_part(target).iter(M+'oMath')))==1
    assert_integrity(target)
