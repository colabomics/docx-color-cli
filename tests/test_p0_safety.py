import os
from pathlib import Path

import pytest

from docx_color_cli.cli import convert, main
from helpers.fixtures import paragraph


@pytest.mark.parametrize('alias', ['relative', 'symlink', 'hardlink'])
@pytest.mark.parametrize('collision', ['output-input', 'report-input', 'report-output'])
def test_CF001_path_aliases(docx, tmp_path, monkeypatch, alias, collision):
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
    with pytest.raises(ValueError, match='paths must differ'):
        if collision == 'output-input':
            convert(source, link)
        else:
            main([str(source), str(target), '--report', str(link)])
    assert (source.read_bytes(), target.read_bytes()) == before


def test_CF001_report_failure_preserves_existing_output(docx, tmp_path, monkeypatch):
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
    with pytest.raises(PermissionError, match='report publication'):
        main([str(source), str(target), '--report', str(report)])
    assert (source.read_bytes(), target.read_bytes()) == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ['out.docx', 'source.docx']
