from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

import pytest

import docx_color_cli.cli as cli
from helpers.fixtures import p, paragraph, rewrite, run


@pytest.mark.parametrize('case,message', [
    ('missing', 'FileNotFoundError'), ('bad-zip', 'BadZipFile'),
    ('truncated-zip', 'BadZipFile'), ('missing-document', 'Missing word/document.xml'),
    ('bad-xml', 'XMLSyntaxError'), ('same-path', 'paths must differ'),
    ('bad-color', 'six hexadecimal'), ('unsupported', 'paragraph mark'),
    ('unwritable-parent', 'FileExistsError'),
], ids=lambda v: v)
def test_cli_errors(docx, tmp_path, case, message):
    source = docx('source.docx', paragraph('keep'))
    target = tmp_path / 'out.docx'
    args = []
    if case == 'missing':
        source = tmp_path / 'missing.docx'
    elif case == 'bad-zip':
        source.write_text('not a zip')
    elif case == 'truncated-zip':
        source.write_bytes(source.read_bytes()[:30])
    elif case == 'missing-document':
        rewrite(source, {'word/document.xml': None})
    elif case == 'bad-xml':
        rewrite(source, {'word/document.xml': b'<broken>'})
    elif case == 'same-path':
        target = source
    elif case == 'bad-color':
        args = ['--inserted-color', 'not-rgb']
    elif case == 'unsupported':
        source = docx('source.docx', p(run('keep'), '<w:rPr><w:del w:id="1"/></w:rPr>'))
    else:
        blocker = tmp_path / 'not-a-directory'
        blocker.write_bytes(b'blocker')
        target = blocker / 'out.docx'
    original = source.read_bytes() if source.exists() else None
    result = subprocess.run([sys.executable, '-m', 'docx_color_cli.cli', str(source), str(target), *args], capture_output=True, text=True)
    assert result.returncode != 0
    assert message in result.stderr
    if original is not None:
        assert source.read_bytes() == original
    if target != source:
        assert not target.exists()


@pytest.mark.parametrize('failure', ['write', 'replace', 'temporary-permission'])
def test_ER010_injected_failure_preserves_original_and_existing_output(docx, tmp_path, monkeypatch, failure):
    source = docx('source.docx', paragraph('keep'))
    target = tmp_path / 'out.docx'
    target.write_bytes(b'previous complete output')
    original = source.read_bytes()
    def fail(*args, **kwargs):
        raise PermissionError('injected deterministic failure')
    if failure == 'write':
        monkeypatch.setattr(ZipFile, 'writestr', fail)
    elif failure == 'replace':
        monkeypatch.setattr(Path, 'replace', fail)
    else:
        monkeypatch.setattr(cli, 'NamedTemporaryFile', fail)
    with pytest.raises(PermissionError, match='injected'):
        cli.convert(source, target)
    assert source.read_bytes() == original
    assert target.read_bytes() == b'previous complete output'
    assert sorted(n.name for n in tmp_path.iterdir()) == ['out.docx', 'source.docx']


@pytest.mark.parametrize('color_options', [('--inserted-color', '--unchanged-color'), ('-ic', '-uc')])
def test_ER011_docx_cli_defaults_and_report(docx, tmp_path, capsys, color_options):
    source = docx('source.docx', p(run('keep') + '<w:ins w:id="1">' + run('new') + '</w:ins>'))
    report = tmp_path / 'report.json'
    cli.main([str(source), color_options[0], '00ff00', color_options[1], '112233', '--report', str(report)])
    from helpers.assertions import assert_segments, xml_part
    assert_segments(xml_part(tmp_path / 'source_colored.docx'), [('keep','112233'), ('new','00FF00')])
    assert report.exists()
    assert 'Saved:' in capsys.readouterr().out


@pytest.mark.parametrize('arguments', [['--format', 'docx'], ['--reference', 'reference.docx'], ['--strict-content'], ['--red', '0000FF'], ['--black', '112233']])
def test_ER012_only_existing_docx_cli_options(arguments, docx, tmp_path):
    source = docx('source.docx', paragraph('keep'))
    result = subprocess.run([sys.executable, '-m', 'docx_color_cli.cli', str(source), *arguments], capture_output=True, text=True)
    assert result.returncode != 0
    assert 'unrecognized arguments' in result.stderr
    assert not (tmp_path / 'source_colored.docx').exists()


def test_ER013_output_must_be_docx(docx, tmp_path):
    source = docx('source.docx', paragraph('keep'))
    with pytest.raises(ValueError, match='.docx'):
        cli.convert_output(source, tmp_path / 'out.txt')
