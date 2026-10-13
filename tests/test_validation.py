import pytest

from helpers.fixtures import W_NS as W, R_NS as R
from helpers.fixtures import paragraph, run


def validate(output, reference):
    from helpers.content import validate_docx
    return validate_docx(output, reference)


@pytest.mark.parametrize('actual,expected', [
    (paragraph('A') + paragraph('B'), paragraph('AB')),
    (paragraph('AB'), paragraph('BA')),
    (paragraph('A B'), paragraph('AB')),
    (paragraph('A') + paragraph('A'), paragraph('A')),
    ('<w:tbl><w:tr><w:tc>' + paragraph('gone') + '</w:tc></w:tr></w:tbl>', '<w:tbl/>'),
    ('<w:p><w:hyperlink w:anchor="wrong">' + run('link') + '</w:hyperlink></w:p>', '<w:p><w:hyperlink w:anchor="right">' + run('link') + '</w:hyperlink></w:p>'),
    ('<w:p><w:fldSimple w:instr="ADDIN ZOTERO_ITEM wrong">' + run('same citation') + '</w:fldSimple></w:p>', '<w:p><w:fldSimple w:instr="ADDIN ZOTERO_ITEM right">' + run('same citation') + '</w:fldSimple></w:p>'),
    ('<w:p><m:oMath><m:sSup><m:e><m:r><m:t>x</m:t></m:r></m:e><m:sup><m:r><m:t>2</m:t></m:r></m:sup></m:sSup></m:oMath></w:p>', '<w:p><m:oMath><m:r><m:t>x2</m:t></m:r></m:oMath></w:p>'),
    ('<w:p><w:r><w:rPr><w:vanish/></w:rPr><w:t>text</w:t></w:r></w:p>', paragraph('text')),
    ('<w:p><w:r><w:t>A</w:t><w:br/><w:t>B</w:t></w:r></w:p>', paragraph('A B')),
    ('<w:p><w:r><w:t>A</w:t><w:tab/><w:t>B</w:t></w:r></w:p>', paragraph('A B')),
    ('<w:tbl><w:tr><w:tc>' + paragraph('A') + '</w:tc><w:tc>' + paragraph('B') + '</w:tc></w:tr></w:tbl>', '<w:tbl><w:tr><w:tc>' + paragraph('AB') + '</w:tc></w:tr></w:tbl>'),
])
def test_semantic_differences_rejected(docx, actual, expected):
    output, reference = docx('actual.docx', actual), docx('expected.docx', expected)
    # Ensure a negative comparison is caused by the mutation, not an unrelated
    # malformed fixture that would also reject an unchanged document.
    assert validate(output, output).ok
    assert validate(reference, reference).ok
    result = validate(output, reference)
    assert not result.ok
    assert result.issues
    assert any('mismatch' in issue for issue in result.issues)


def test_colors_run_splits_and_rsid_are_ignored(docx):
    actual = '<w:p w:rsidR="123"><w:r><w:rPr><w:color w:val="FF0000"/></w:rPr><w:t>Hello</w:t></w:r>' + run(' world') + '</w:p>'
    assert validate(docx('actual.docx', actual), docx('expected.docx', paragraph('Hello world'))).ok


def test_hyperlink_relationship_ids_resolved(docx):
    def package(name, rid, url):
        rels = f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="{rid}" Type="{R}/hyperlink" Target="{url}" TargetMode="External"/></Relationships>'
        return docx(name, f'<w:p><w:hyperlink r:id="{rid}">{run("link")}</w:hyperlink></w:p>', {'word/_rels/document.xml.rels': rels})
    ref = package('ref.docx', 'rId9', 'https://example.com/right')
    assert validate(package('same.docx', 'rId1', 'https://example.com/right'), ref).ok
    assert not validate(package('wrong.docx', 'rId1', 'https://example.com/wrong'), ref).ok


def test_unaccepted_reference_is_invalid(docx):
    result = validate(docx('actual.docx', paragraph('text')), docx('ref.docx', '<w:p><w:ins>' + run('text') + '</w:ins></w:p>'))
    assert not result.ok
    assert any('revision' in issue for issue in result.issues)


@pytest.mark.parametrize('part,root', [('header1','hdr'), ('footer1','ftr'), ('footnotes','footnotes'), ('endnotes','endnotes'), ('comments','comments')])
def test_all_stories_compared(docx, part, root):
    def extra(text):
        return {f'word/{part}.xml': f'<w:{root} xmlns:w="{W}">{paragraph(text)}</w:{root}>'}
    assert not validate(docx('actual.docx', paragraph('same'), extra('wrong')), docx('ref.docx', paragraph('same'), extra('right'))).ok


def test_broken_field_rejected_even_when_both_documents_match(docx):
    body = '<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r>' + run('text') + '</w:p>'
    assert not validate(docx('actual.docx', body), docx('ref.docx', body)).ok


def test_dangling_relationship_rejected_even_when_both_match(docx):
    body = '<w:p><w:hyperlink r:id="missing">' + run('text') + '</w:hyperlink></w:p>'
    assert not validate(docx('actual.docx', body), docx('ref.docx', body)).ok


@pytest.mark.parametrize('element', ['footnoteReference', 'endnoteReference', 'commentReference'])
def test_dangling_story_reference_rejected(docx, element):
    body = f'<w:p><w:r><w:{element} w:id="7"/></w:r></w:p>'
    assert not validate(docx('actual.docx', body), docx('ref.docx', body)).ok


@pytest.mark.parametrize('name,one,two', [
    ('word/settings.xml', f'<w:settings xmlns:w="{W}"><w:displayBackgroundShape/></w:settings>', f'<w:settings xmlns:w="{W}"/>'),
    ('customXml/item1.xml', '<data>first</data>', '<data>second</data>'),
    ('word/styles.xml', f'<w:styles xmlns:w="{W}"><w:style w:styleId="normal"><w:rPr><w:vanish/></w:rPr></w:style></w:styles>', f'<w:styles xmlns:w="{W}"><w:style w:styleId="normal"/></w:styles>'),
])
def test_content_dependencies_compared(docx, name, one, two):
    actual = docx('actual.docx', paragraph('same'), {name: one})
    reference = docx('ref.docx', paragraph('same'), {name: two})
    assert validate(actual, actual).ok
    assert validate(reference, reference).ok
    assert not validate(actual, reference).ok


def test_xml_space_difference_is_not_ignored_for_edge_spaces(docx):
    actual = '<w:p><w:r><w:t> leading</w:t></w:r></w:p>'
    assert not validate(docx('actual.docx', actual), docx('ref.docx', paragraph(' leading'))).ok


def test_changed_image_bytes_rejected(docx):
    body = '<w:p><w:r><w:drawing><image r:embed="rId1"/></w:drawing></w:r></w:p>'
    rels = f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{R}/image" Target="media/image.png"/></Relationships>'
    def extra(data):
        return {'word/_rels/document.xml.rels': rels, 'word/media/image.png': data}
    assert not validate(docx('actual.docx', body, extra(b'changed')), docx('ref.docx', body, extra(b'original'))).ok


def test_complex_zotero_field_instructions_and_nested_results(docx):
    field = ('<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
             '<w:r><w:instrText xml:space="preserve"> ADDIN ZOTERO_ITEM CSL_CITATION {}</w:instrText></w:r>'
             '<w:r><w:fldChar w:fldCharType="separate"/></w:r>' + run('(Smith, 2020)') +
             '<w:r><w:fldChar w:fldCharType="end"/></w:r>')
    body = '<w:p>' + field + '</w:p>'
    ref = docx('ref.docx', body)
    assert validate(docx('actual.docx', body), ref).ok
    assert not validate(docx('changed.docx', body.replace('CSL_CITATION {}', 'CSL_CITATION {"id":1}')), ref).ok
    nested = '<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText> QUOTE </w:instrText></w:r>' + field + '<w:r><w:fldChar w:fldCharType="separate"/></w:r>' + run('result') + '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
    assert validate(docx('nested.docx', nested), docx('nested-ref.docx', nested)).ok


def test_fields_cannot_cross_textbox_story_boundary(docx):
    body = '<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:pict><w:txbxContent><w:p><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p></w:txbxContent></w:pict></w:r></w:p>'
    assert not validate(docx('actual.docx', body), docx('ref.docx', body)).ok


@pytest.mark.parametrize('damage', ['package-rels', 'content-types', 'math', 'bookmark'])
def test_integrity_helper_detects_specific_mutations(docx, damage):
    from helpers.content import inspect_docx
    from helpers.fixtures import fraction, p, rewrite
    source = docx('source.docx', p(fraction()))
    assert inspect_docx(source).ok
    if damage == 'package-rels':
        rewrite(source, {'_rels/.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'})
        expected = 'main document relationship'
    elif damage == 'content-types':
        rewrite(source, {'[Content_Types].xml': None})
        expected = 'Content Types'
    elif damage == 'math':
        source = docx('source.docx', p('<m:oMath><m:f><m:num><m:r><m:t>x</m:t></m:r></m:num></m:f></m:oMath>'))
        expected = 'OMML fraction'
    else:
        source = docx('source.docx', p('<w:bookmarkStart w:id="1" w:name="target"/>' + run('text')))
        expected = 'bookmark range'
    assert any(expected in issue for issue in inspect_docx(source).issues)
