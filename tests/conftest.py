import pytest
from helpers.fixtures import write_docx


@pytest.fixture
def docx(tmp_path):
    """Synthetic OOXML fixtures, never represented as Word-generated oracles."""
    def create(name, body, parts=None):
        return write_docx(tmp_path / name, body, parts)
    return create
