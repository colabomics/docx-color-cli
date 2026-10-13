"""Optional local user-supplied Word pair; never distribute the manuscript here.

The user identifies the reference as Word-accepted. Word version/provenance have
not been independently authenticated. These tests do not fabricate references.
"""
from collections import Counter
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile

from lxml import etree
import pytest

from docx_color_cli.cli import convert, modify
from helpers.content import validate_docx
from helpers.fixtures import W, M

ROOT = Path(__file__).parent / 'fixtures/academic'
ORIGINAL = ROOT / 'complex_tracked.docx'
REFERENCE = ROOT / 'complex_tracked_reference.docx'
PARA_ID = '{http://schemas.microsoft.com/office/word/2010/wordml}paraId'
pytestmark = [pytest.mark.word_reference, pytest.mark.skipif(
    not (ORIGINAL.is_file() and REFERENCE.is_file()), reason='Local academic Word pair is not present')]


def read_root(path):
    with ZipFile(path) as archive:
        return etree.fromstring(archive.read('word/document.xml'))


def visible_text(root):
    pieces = []
    for node in root.iter():
        if node.tag in {W+'t', M+'t'}:
            pieces.append(node.text or '')
        elif node.tag == W+'tab':
            pieces.append('\t')
        elif node.tag in {W+'br', W+'cr'}:
            pieces.append('\n')
    return ''.join(pieces)


def deleted_mark(paragraph):
    return paragraph is not None and (paragraph.find(W+'pPr/'+W+'rPr/'+W+'del') is not None
                                     or paragraph.find(W+'pPr/'+W+'rPr/'+W+'moveFrom') is not None)


def test_academic_isolated_nested_paragraph_text_matches_word():
    """Partial text evidence only: explicitly exclude paragraphs requiring merging/moves."""
    source, reference = read_root(ORIGINAL), read_root(REFERENCE)
    expected = {p.get(PARA_ID): p for p in reference.iter(W+'p') if p.get(PARA_ID)}
    checked = 0
    for paragraph in source.iter(W+'p'):
        if paragraph.get(PARA_ID) not in expected:
            continue
        if deleted_mark(paragraph) or deleted_mark(paragraph.getprevious()):
            continue
        if any(isinstance(n.tag,str) and etree.QName(n).namespace == W[1:-1] and etree.QName(n).localname.startswith(('moveFrom','moveTo')) for n in paragraph.iter()):
            continue
        if not any(n.tag in {W+'ins',W+'del'} and any(a.tag in {W+'ins',W+'del'} for a in n.iterancestors()) for n in paragraph.iter()):
            continue
        converted = deepcopy(paragraph)
        modify(converted, Counter())
        assert visible_text(converted) == visible_text(expected[paragraph.get(PARA_ID)]), paragraph.get(PARA_ID)
        checked += 1
    assert checked > 0, 'No independently comparable nested paragraphs were found'


@pytest.mark.xfail(strict=True, raises=AssertionError, reason='VAL001: strict reference differs in link representation and metadata; see docs/code_audit.md')
def test_academic_complete_word_reference(tmp_path):
    source_hash = sha256(ORIGINAL.read_bytes()).digest()
    reference_hash = sha256(REFERENCE.read_bytes()).digest()
    output = tmp_path / 'output.docx'
    try:
        convert(ORIGINAL, output)
        result = validate_docx(output, REFERENCE)
        assert result.ok, '\n'.join(result.issues)
    finally:
        assert sha256(ORIGINAL.read_bytes()).digest() == source_hash
        assert sha256(REFERENCE.read_bytes()).digest() == reference_hash


def test_academic_all_move_ranges_validate():
    from docx_color_cli.revisions import active_nodes, check_moves
    root=read_root(ORIGINAL)
    assert root.findall('.//'+W+'moveFromRangeStart')
    check_moves(list(active_nodes(root)))


def test_academic_deleted_math_controls_have_no_retained_payload():
    from docx_color_cli.math_revisions import fully_deleted
    root=read_root(ORIGINAL)
    controls=[c for c in root.iter(M+'ctrlPr') if c.find(W+'del') is not None]
    assert controls
    assert all(fully_deleted(c.getparent().getparent()) for c in controls)


def test_academic_revision_preflight_passes_math_controls():
    from docx_color_cli.revisions import preflight
    preflight(read_root(ORIGINAL))



def test_academic_all_paragraph_text_and_properties_match_word(tmp_path):
    output=tmp_path/'output.docx'
    convert(ORIGINAL,output)
    actual,expected=read_root(output),read_root(REFERENCE)
    left,right=list(actual.iter(W+'p')),list(expected.iter(W+'p'))
    assert len(left)==len(right)
    assert [p.get(PARA_ID) for p in left]==[p.get(PARA_ID) for p in right]
    assert [visible_text(p) for p in left]==[visible_text(p) for p in right]
    def property_key(n):
        if n is None or n.tag==W+'color':return ()
        children=tuple(k for c in n if (k:=property_key(c)))
        if n.tag in {W+'pPr',W+'rPr'} and not children and not n.attrib:return ()
        return n.tag,tuple(sorted(n.attrib.items())),n.text or '',children
    assert [property_key(p.find(W+'pPr')) for p in left]==[property_key(p.find(W+'pPr')) for p in right]
    def blocks(root):
        tags={W+x for x in ['p','tbl','tr','tc']}
        return [(event,node.tag) for event,node in etree.iterwalk(root,events=('start','end')) if node.tag in tags]
    assert blocks(actual)==blocks(expected)



def test_academic_math_structure_and_comment_parts_match_reference(tmp_path):
    from helpers.content import _Package
    output=tmp_path/'output.docx'
    convert(ORIGINAL,output)
    actual,expected=_Package(output),_Package(REFERENCE)
    part='word/document.xml'
    def equations(package):
        root=package.xml[part]
        result=[]
        try:
            for math in root.iter(M+'oMath'):
                package.xml[part]=math
                result.append(package.canonical(part))
        finally:package.xml[part]=root
        return result
    assert equations(actual)==equations(expected)
    assert [name for name,root in actual.stories.items() if root.tag==W+'comments']==[name for name,root in expected.stories.items() if root.tag==W+'comments']
    for tag in ['commentRangeStart','commentRangeEnd','commentReference']:
        assert [n.get(W+'id') for n in actual.xml[part].iter(W+tag)]==[n.get(W+'id') for n in expected.xml[part].iter(W+tag)]


def test_academic_body_matches_with_documented_hyperlink_equivalence(tmp_path):
    output=tmp_path/'output.docx'
    convert(ORIGINAL,output)
    comparison=validate_docx(output,REFERENCE,semantic=True)
    assert comparison.reference_compared
    assert 'word/document.xml' in comparison.checked_parts
    assert not [issue for issue in comparison.issues if issue.startswith('word/document.xml:')]
    assert any('hyperlink visit-history switch' in warning for warning in comparison.warnings)
