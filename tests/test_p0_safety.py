import os
from pathlib import Path

import pytest

from docx_color_cli.cli import convert, main
from helpers.fixtures import paragraph


@pytest.mark.parametrize('alias', ['relative', 'symlink', 'hardlink'])
@pytest.mark.parametrize('collision', ['output-input', 'report-input', 'report-output'])
def test_CF001_path_aliases(docx, tmp_path, monkeypatch, alias, collision, capsys):
    source = docx('source.docx', paragraph('original'))
    target = docx('out.docx', paragraph('previous output'))
    victim = target if collision == 'report-output' else source
    link = tmp_path / 'alias.docx'
    if alias == 'symlink':
        link.symlink_to(victim)
    elif alias == 'hardlink':
        os.link(victim, link)
    else:
        monkeypatch.chdir(tmp_path)
        link = Path(victim.name)
    before = source.read_bytes(), target.read_bytes()
    if collision == 'output-input':
        with pytest.raises(ValueError, match='paths must differ'):
            convert(source, link)
    else:
        with pytest.raises(SystemExit) as error:
            main([str(source), str(target), '--report', str(link)])
        assert error.value.code == 1
        assert 'paths must differ' in capsys.readouterr().err
    assert (source.read_bytes(), target.read_bytes()) == before


def test_CF001_report_failure_preserves_existing_output(docx, tmp_path, monkeypatch, capsys):
    source = docx('source.docx', paragraph('original'))
    target = docx('out.docx', paragraph('previous output'))
    report = tmp_path / 'report.json'
    before = source.read_bytes(), target.read_bytes()
    replace = Path.replace
    def fail_report(self, destination):
        if Path(destination) == report:
            raise PermissionError('report publication failed')
        return replace(self, destination)
    monkeypatch.setattr(Path, 'replace', fail_report)
    with pytest.raises(SystemExit) as error:
        main([str(source), str(target), '--report', str(report)])
    assert error.value.code == 1
    assert 'report publication' in capsys.readouterr().err
    assert (source.read_bytes(), target.read_bytes()) == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ['out.docx', 'source.docx']
