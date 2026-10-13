import pytest
from docx_color_cli.cli import convert
from helpers.assertions import assert_integrity, assert_segments, paragraphs, xml_part
from helpers.fixtures import W, p, revision, run


@pytest.mark.parametrize('ancestor', ['ins', 'del'])
@pytest.mark.parametrize('location', ['moveFrom', 'moveTo'])
def test_move_inside_text_revision(docx, tmp_path, ancestor, location):
    def moved(kind, ident):
        payload = revision(kind, run('moved'))
        if kind == location:
            payload = revision(ancestor, payload)
        return f'<w:{kind}RangeStart w:id="{ident}" w:name="move"/>' + payload + f'<w:{kind}RangeEnd w:id="{ident}"/>'
    body = p(moved('moveFrom', '1') + run('stay') + moved('moveTo', '2'))
    target = tmp_path / 'out.docx'
    convert(docx('in.docx', body), target)
    expected = [('stay', '000000')]
    if not (ancestor == 'del' and location == 'moveTo'):
        expected.append(('moved', 'FF0000'))
    assert_segments(xml_part(target), expected)
    assert_integrity(target)


def test_merge_retains_following_section_boundary(docx, tmp_path):
    body = p(run('A'), '<w:rPr><w:del w:id="1"/></w:rPr>') + p(run('B'), '<w:sectPr><w:type w:val="nextPage"/></w:sectPr>') + p(run('C'))
    target = tmp_path / 'out.docx'
    convert(docx('in.docx', body), target)
    assert paragraphs(target) == ['AB', 'C']
    root = xml_part(target)
    assert root.find('.//' + W + 'pPr/' + W + 'sectPr/' + W + 'type').get(W + 'val') == 'nextPage'
    assert_segments(root, [('ABC', '000000')])
    assert_integrity(target)
