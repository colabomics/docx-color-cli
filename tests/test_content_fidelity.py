from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from docx_color_cli.cli import convert
from helpers.content import is_revision, parse_xml, validate_docx


REFERENCE_ROOT = Path(__file__).parent / 'fixtures/complex/word'
CASES = sorted(p for p in REFERENCE_ROOT.iterdir() if p.is_dir()) if REFERENCE_ROOT.exists() else []


@pytest.mark.word_reference
@pytest.mark.parametrize('case', CASES or [None], ids=[p.name for p in CASES] or ['no-independent-Word-reference'])
def test_word_accepted_reference(case, tmp_path):
    if case is None:
        pytest.skip('No independent Microsoft Word original/reference pair; synthetic fixtures are not Word ground truth')
    original, reference = case / 'original.docx', case / 'reference.docx'
    assert original.is_file() and reference.is_file(), 'incomplete reference pair'
    provenance = json.loads((case / 'provenance.json').read_text(encoding='utf-8'))
    assert provenance['producer'] == 'Microsoft Word'
    assert provenance['accepted_all_revisions'] is True
    assert provenance['synthetic'] is False
    assert provenance['word_version']
    for role, path in [('original', original), ('reference', reference)]:
        assert sha256(path.read_bytes()).hexdigest() == provenance[role + '_sha256']
    with ZipFile(original) as archive:
        assert any(is_revision(node) for name in archive.namelist() if name.endswith('.xml')
                   for node in parse_xml(archive.read(name)).iter()), 'original has no tracked revisions'
    output = tmp_path / 'output.docx'
    original_bytes, reference_bytes = original.read_bytes(), reference.read_bytes()
    convert(original, output)
    result = validate_docx(output, reference)
    assert result.ok, '\n'.join(result.issues)
    assert original.read_bytes() == original_bytes
    assert reference.read_bytes() == reference_bytes
