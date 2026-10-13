import pytest
from docx_color_cli.cli import convert
from helpers.assertions import assert_integrity, xml_part
from helpers.fixtures import M, W, p


@pytest.mark.parametrize('kind,args', [
    ('acc', ['e']), ('bar', ['e']), ('borderBox', ['e']), ('box', ['e']),
    ('groupChr', ['e']), ('limLow', ['e', 'lim']), ('limUpp', ['e', 'lim']),
    ('phant', ['e']), ('rad', ['deg', 'e']), ('sPre', ['sub', 'sup', 'e']),
    ('sSubSup', ['e', 'sub', 'sup']), ('m', ['mr']),
])
def test_wholly_deleted_math_object(docx, tmp_path, kind, args):
    deleted = '<m:r><w:del w:id="2"><m:t>gone</m:t></w:del></m:r>'
    if kind == 'm':
        deleted = '<m:e>' + deleted + '</m:e>'
    body = p('<m:oMath><m:' + kind + '><m:' + kind + 'Pr><m:ctrlPr><w:del w:id="1"/></m:ctrlPr></m:' + kind + 'Pr>' + ''.join(f'<m:{arg}>{deleted}</m:{arg}>' for arg in args) + '</m:' + kind + '><m:r><m:t>keep</m:t></m:r></m:oMath>')
    target = tmp_path / 'out.docx'
    convert(docx('in.docx', body), target)
    root = xml_part(target)
    assert [n.text for n in root.iter(M + 't')] == ['keep']
    assert not list(root.iter(M + kind))
    assert root.find('.//' + W + 'color').get(W + 'val') == '000000'
    assert_integrity(target)
