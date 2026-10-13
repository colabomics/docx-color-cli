"""Assertions for accepted XML, independent of the converter constants."""
from zipfile import ZipFile

from lxml import etree

from .content import inspect_docx, is_revision
from .fixtures import M, W


def xml_part(path, name='word/document.xml'):
    with ZipFile(path) as archive:
        return etree.fromstring(archive.read(name))


def text(node):
    fragments = []
    for child in node.iter():
        if child.tag in {W + 't', M + 't'}:
            fragments.append(child.text or '')
        elif child.tag == W + 'tab':
            fragments.append('\t')
        elif child.tag in {W + 'br', W + 'cr'}:
            fragments.append('\n')
    return ''.join(fragments)


def paragraphs(path):
    root = xml_part(path)
    return [text(node) for node in root.findall(W + 'body/' + W + 'p')]


def assert_segments(root, expected):
    """Compare character order and color independently of run segmentation."""
    actual = []
    for node in root.iter(W + 'r'):
        value = ''.join((n.text or '') for n in node if n.tag == W + 't')
        if not value:
            continue
        color = node.find(W + 'rPr/' + W + 'color')
        assert color is not None, 'visible run lacks explicit color'
        actual.extend((char, color.get(W + 'val')) for char in value)
    expected_chars = [(char, color) for value, color in expected for char in value]
    assert actual == expected_chars
    assert not any(is_revision(node) for node in root.iter()), 'residual revisions'


def assert_integrity(path):
    result = inspect_docx(path)
    assert result.ok, '\n'.join(result.issues)


def assert_rejects_without_output(convert, source, target, **kwargs):
    """Expect a specific safe refusal; verify artifacts even if it fails to refuse."""
    before = source.read_bytes()
    existing = target.read_bytes() if target.exists() else None
    try:
        convert(source, target, **kwargs)
    except ValueError as exc:
        assert str(exc)
    else:
        raise AssertionError('converter silently accepted unsupported content')
    assert source.read_bytes() == before
    if existing is not None:
        assert target.read_bytes() == existing
    else:
        assert not target.exists()


def xml_without_font_colors(node):
    """Compare preserved XML while allowing only the intended font-color edit."""
    from copy import deepcopy
    node = deepcopy(node)
    for color in list(node.iter(W + 'color')):
        color.getparent().remove(color)
    for props in list(node.iter(W + 'rPr')):
        if len(props) == 0 and not props.attrib:
            props.getparent().remove(props)
    etree.cleanup_namespaces(node)
    return etree.tostring(node)
