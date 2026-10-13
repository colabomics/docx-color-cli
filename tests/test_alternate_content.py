from docx_color_cli.cli import convert
from helpers.assertions import assert_integrity, assert_segments, xml_part
from helpers.fixtures import delete, insert, p, run

MC = '{http://schemas.openxmlformats.org/markup-compatibility/2006}'


def test_alternate_branches_both_accept_revisions(docx, tmp_path):
    branch = p(run('A') + delete('gone') + insert('B'))
    body = '<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"><mc:Choice Requires="w14">' + branch + '</mc:Choice><mc:Fallback>' + branch + '</mc:Fallback></mc:AlternateContent>'
    source = docx('in.docx', body)
    target = tmp_path / 'out.docx'
    convert(source, target)
    root = xml_part(target)
    choices = list(root.iter(MC + 'Choice', MC + 'Fallback'))
    assert len(choices) == 2
    for choice in choices:
        assert_segments(choice, [('A', '000000'), ('B', 'FF0000')])
    assert choices[0].get('Requires') == 'w14'
    assert_integrity(target)


def test_malformed_alternative_cannot_publish(docx, tmp_path):
    from helpers.assertions import assert_rejects_without_output
    body = '<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"><mc:Choice Requires="missing">' + p(insert('B')) + '</mc:Choice></mc:AlternateContent>'
    assert_rejects_without_output(convert, docx('in.docx', body), tmp_path / 'out.docx')


def test_inline_alternatives_accept_text_edits(docx, tmp_path):
    content = delete('gone') + insert('new')
    body = p('<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"><mc:Choice Requires="w14">' + content + '</mc:Choice><mc:Fallback>' + content + '</mc:Fallback></mc:AlternateContent>')
    target = tmp_path / 'out.docx'
    convert(docx('in.docx', body), target)
    for branch in xml_part(target).iter(MC + 'Choice', MC + 'Fallback'):
        assert_segments(branch, [('new', 'FF0000')])


def test_conditional_bookmark_loss_cannot_be_masked_by_fallback(docx, tmp_path):
    from helpers.fixtures import field, revision
    from helpers.assertions import assert_rejects_without_output
    bookmark = '<w:bookmarkStart w:id="1" w:name="target"/>' + run('target') + '<w:bookmarkEnd w:id="1"/>'
    body = p('<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"><mc:Choice Requires="w14">' + revision('del', bookmark) + '</mc:Choice><mc:Fallback>' + bookmark + '</mc:Fallback></mc:AlternateContent>' + field(' REF target ', run('target')))
    assert_rejects_without_output(convert, docx('in.docx', body), tmp_path / 'out.docx')


def test_bookmark_ids_may_repeat_in_mutually_exclusive_branches(docx, tmp_path):
    from docx_color_cli.validation import validate_docx
    bookmark = '<w:bookmarkStart w:id="1" w:name="target"/>' + run('target') + '<w:bookmarkEnd w:id="1"/>'
    body = p('<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"><mc:Choice Requires="w14">' + bookmark + '</mc:Choice><mc:Fallback>' + bookmark + '</mc:Fallback></mc:AlternateContent>')
    target = tmp_path / 'out.docx'
    convert(docx('in.docx', body), target)
    assert_integrity(target)
    assert validate_docx(target, target).ok
