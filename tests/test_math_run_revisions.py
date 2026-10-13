import pytest

from docx_color_cli.cli import convert
from helpers.assertions import assert_integrity, assert_rejects_without_output, xml_part
from helpers.fixtures import M, W, p, revision


@pytest.mark.parametrize('location', ['oMath', 'numerator', 'superscript'])
@pytest.mark.parametrize('inserted', [True, False])
def test_word_math_run_revision(docx, tmp_path, location, inserted):
    props = '<w:rPr><w:rFonts w:ascii="Cambria Math"/><w:sz w:val="24"/></w:rPr>'
    edited = '<m:r><m:rPr><m:sty m:val="p"/></m:rPr>' + revision('ins' if inserted else 'del', props + '<m:t xml:space="preserve"> β &lt; 0 </m:t>') + '</m:r>'
    keep = '<m:r><m:t>x</m:t></m:r>'
    if location == 'numerator':
        content = '<m:f><m:num>' + edited + keep + '</m:num><m:den>' + keep + '</m:den></m:f>'
    elif location == 'superscript':
        content = '<m:sSup><m:e>' + keep + '</m:e><m:sup>' + edited + keep + '</m:sup></m:sSup>'
    else:
        content = edited + keep
    source = docx('source.docx', p('<m:oMath>' + content + '</m:oMath>'))
    original = source.read_bytes()
    target = tmp_path / 'out.docx'
    convert(source, target)
    root = xml_part(target)
    texts = [n.text for n in root.iter(M + 't')]
    assert (' β < 0 ' in texts) == inserted
    assert texts.count('x') == (1 if location == 'oMath' else 2)
    for run in root.iter(M + 'r'):
        value = run.find(M + 't').text
        assert run.find(W + 'rPr/' + W + 'color').get(W + 'val') == ('FF0000' if value == ' β < 0 ' else '000000')
        if value == ' β < 0 ':
            assert run.find(W + 'rPr/' + W + 'rFonts').get(W + 'ascii') == 'Cambria Math'
            assert run.find(W + 'rPr/' + W + 'sz').get(W + 'val') == '24'
            assert run.find(M + 'rPr/' + M + 'sty').get(M + 'val') == 'p'
            assert list(run)[0].tag == M + 'rPr'
    assert source.read_bytes() == original
    assert_integrity(target)


@pytest.mark.parametrize('content', [
    revision('ins', '<m:f><m:num/><m:den/></m:f>'),
    '<w:rPr><w:b/></w:rPr>' + revision('ins', '<w:rPr><w:i/></w:rPr><m:t>x</m:t>'),
])
def test_ambiguous_math_run_revision_refused(docx, tmp_path, content):
    assert_rejects_without_output(convert, docx('source.docx', p('<m:oMath><m:r>' + content + '</m:r></m:oMath>')), tmp_path / 'out.docx', strict=False)


@pytest.mark.parametrize('outer,inner,expected', [('ins','del',[]),('ins','ins',['x']),('del','ins',[]),('del','del',[])])
def test_nested_whole_math_run(docx,tmp_path,outer,inner,expected):
    content='<m:oMath><m:r>'+revision(outer,revision(inner,'<m:t>x</m:t>'))+'</m:r><m:r><m:t>keep</m:t></m:r></m:oMath>'
    target=tmp_path/'out.docx'
    convert(docx('in.docx',p(content)),target)
    root=xml_part(target)
    assert [n.text for n in root.iter(M+'t')]==expected+['keep']
    assert len(list(root.iter(M+'r')))==len(expected)+1
    for r in root.iter(M+'r'):
        assert r.find(W+'rPr/'+W+'color').get(W+'val')==('FF0000' if r.find(M+'t').text=='x' else '000000')
    assert_integrity(target)
