"""Read-only OPC checks. These checks do not prove Microsoft Word equivalence."""
import posixpath
from collections import Counter
from urllib.parse import unquote, urlsplit

from lxml import etree

W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
W = '{' + W_NS + '}'
R_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
R = '{' + R_NS + '}'
PKG = '{http://schemas.openxmlformats.org/package/2006/relationships}'
CT = '{http://schemas.openxmlformats.org/package/2006/content-types}'
STORIES = {'document', 'hdr', 'ftr', 'footnotes', 'endnotes', 'comments', 'glossaryDocument'}
STORY_TYPES = {'officeDocument': 'document', 'header': 'hdr', 'footer': 'ftr',
               'footnotes': 'footnotes', 'endnotes': 'endnotes', 'comments': 'comments',
               'glossaryDocument': 'glossaryDocument'}


def read_xml_parts(archive):
    names = archive.namelist()
    if len(names) != len(set(names)):
        raise ValueError('Duplicate ZIP members')
    if 'word/document.xml' not in names:
        raise ValueError('Missing word/document.xml: not a valid DOCX')
    roots = {}
    for name in names:
        if name.endswith(('.xml', '.rels')):
            try:
                root = etree.fromstring(archive.read(name), etree.XMLParser(resolve_entities=False, no_network=True))
            except etree.XMLSyntaxError as exc:
                if name == 'word/document.xml':
                    raise
                raise ValueError(f'{name}: XMLSyntaxError: {exc}') from exc
            if root.getroottree().docinfo.doctype:
                raise ValueError(f'{name}: DTD is unsupported')
            from .namespaces import canonical_namespaces
            root = canonical_namespaces(root)
            roots[name] = root
    if roots['word/document.xml'].tag != W + 'document':
        raise ValueError('word/document.xml: expected Word document root')
    if roots['word/document.xml'].find(W + 'body') is None:
        raise ValueError('word/document.xml: missing body')
    return roots


def relationship_source(name):
    if name == '_rels/.rels':
        return ''
    directory, filename = posixpath.split(name)
    if not directory.endswith('/_rels') or not filename.endswith('.rels'):
        raise ValueError(f'Invalid relationship part path: {name}')
    return posixpath.join(directory[:-6], filename[:-5])


def relationship_target(source, target):
    url = urlsplit(target)
    if url.scheme or url.netloc or url.query or url.fragment or '\\' in target:
        raise ValueError(f'Unsupported internal relationship target: {target}')
    target = unquote(url.path)
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source), target)) if not target.startswith('/') else posixpath.normpath(target[1:])
    if resolved.startswith('../') or resolved in ('', '.', '..'):
        raise ValueError(f'Relationship target escapes package: {target}')
    return resolved


def discover_stories(roots):
    """Discover by XML roots and verify relationship-declared story roots."""
    stories = {name: root for name, root in roots.items() if root.tag in {W + s for s in STORIES}}
    for name, root in roots.items():
        if not name.endswith('.rels'):
            continue
        source = relationship_source(name)
        for rel in root:
            kind = rel.get('Type', '')
            expected = STORY_TYPES.get(kind.removeprefix(R_NS + '/')) if kind.startswith(R_NS + '/') else None
            if expected:
                if rel.get('TargetMode') == 'External':
                    raise ValueError(f'{name}: external story is unsupported')
                dest = relationship_target(source, rel.get('Target', ''))
                if dest not in roots or roots[dest].tag != W + expected:
                    raise ValueError(f'{name}: invalid {expected} story target {dest}')
    return stories


def validate_package(archive, roots, *, accepted=False):
    """Check publication prerequisites; not a full OOXML schema/Word validator."""
    from .revisions import is_revision

    names = set(archive.namelist())
    if archive.testzip() is not None:
        raise ValueError('Invalid ZIP checksum')
    types = roots.get('[Content_Types].xml')
    if types is None or types.tag != CT + 'Types':
        raise ValueError('Missing or invalid Content Types')
    defaults, overrides = {}, {}
    for node in types:
        if node.tag == CT + 'Default':
            mapping, key = defaults, node.get('Extension')
        elif node.tag == CT + 'Override':
            mapping, key = overrides, unquote(node.get('PartName', '')).lstrip('/')
        else:
            raise ValueError('Invalid Content Types entry')
        if not key or key in mapping or not node.get('ContentType'):
            raise ValueError('Missing or duplicate Content Types entry')
        mapping[key] = node.get('ContentType')
    if overrides.get('word/document.xml') != 'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml':
        raise ValueError('Incorrect main document Content Type')
    for name in names:
        if name.endswith('/') or name == '[Content_Types].xml':
            continue
        if name not in overrides and name.rsplit('.', 1)[-1] not in defaults:
            raise ValueError(f'{name}: missing Content Type')
    for name in overrides:
        if name not in names:
            raise ValueError(f'{name}: Content Type points to absent part')
    story_mimes = {f'application/vnd.openxmlformats-officedocument.wordprocessingml.{kind}+xml': tag
                   for kind, tag in STORY_TYPES.items() if kind != 'officeDocument'}
    story_mimes['application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'] = 'document'
    for name, mime in overrides.items():
        expected_root = story_mimes.get(mime)
        if expected_root and (name not in roots or roots[name].tag != W + expected_root):
            raise ValueError(f'{name}: Content Type and story root disagree')

    links = {}
    for name, root in roots.items():
        if not name.endswith('.rels'):
            continue
        if root.tag != PKG + 'Relationships':
            raise ValueError(f'{name}: invalid relationships root')
        source = relationship_source(name)
        if source and source not in names:
            raise ValueError(f'{name}: relationship source missing')
        rels = links.setdefault(source, {})
        for rel in root:
            ident, kind, target = rel.get('Id'), rel.get('Type'), rel.get('Target')
            mode = rel.get('TargetMode', 'Internal')
            if rel.tag != PKG + 'Relationship' or not ident or not kind or not target or ident in rels or mode not in {'Internal', 'External'}:
                raise ValueError(f'{name}: invalid or duplicate relationship')
            destination = target if mode == 'External' else relationship_target(source, target)
            if mode == 'Internal' and destination not in names:
                raise ValueError(f'{name}: missing relationship target {destination}')
            rels[ident] = (kind, destination, mode)
    main = [value for value in links.get('', {}).values() if value[0] == R_NS + '/officeDocument']
    if main != [(R_NS + '/officeDocument', 'word/document.xml', 'Internal')]:
        raise ValueError('Missing or ambiguous main document relationship')
    for name, root in roots.items():
        for node in root.iter():
            if not isinstance(node.tag, str):
                continue
            if accepted and is_revision(node):
                raise ValueError(f'{name}: residual unsupported revision {etree.QName(node).localname}')
            for attribute, value in node.attrib.items():
                if attribute.startswith(R) and value not in links.get(name, {}):
                    raise ValueError(f'{name}: missing relationship {value}')
            for kind in ('footnote', 'endnote', 'comment'):
                if node.tag == W + kind + 'Reference':
                    targets = [r for r in links.get(name, {}).values() if r[0] == R_NS + '/' + kind + 's' and r[2] == 'Internal']
                    # Header/textbox references may use the main document's note part.
                    if not targets:
                        targets = [r for r in links.get('word/document.xml', {}).values() if r[0] == R_NS + '/' + kind + 's' and r[2] == 'Internal']
                    if len(targets) != 1 or targets[0][1] not in roots or not any(n.get(W + 'id') == node.get(W + 'id') for n in roots[targets[0][1]].iter(W + kind)):
                        raise ValueError(f'{name}: dangling {kind} reference')
        if accepted and root.tag in {W + s for s in STORIES}:
            validate_story(root, name)


def validate_story(root, name):
    """Validate retained fields and ranges in each independent text story."""
    containers = {W + n for n in ('body', 'hdr', 'ftr', 'footnote', 'endnote', 'comment', 'txbxContent', 'docPartBody', 'fldSimple')}
    from .compatibility import BRANCHES
    from .math_revisions import OBJECTS
    from .revisions import M
    from .tables import validate_grid
    containers |= BRANCHES
    def check(container):
        stack = []
        starts, ends = {}, set()
        def walk(node):
            if node is not container and node.tag in containers:
                check(node)
                return
            if node.tag == W + 'fldChar':
                kind = node.get(W + 'fldCharType')
                if kind == 'begin':
                    stack.append(False)
                elif kind == 'separate' and stack and not stack[-1]:
                    stack[-1] = True
                elif kind == 'end' and stack:
                    stack.pop()
                else:
                    raise ValueError(f'{name}: broken Word field boundary')
            if node.tag == W + 'instrText' and (not stack or stack[-1]):
                raise ValueError(f'{name}: field instruction outside code region')
            if node.tag == W + 'bookmarkStart':
                ident = node.get(W + 'id')
                if ident is None or ident in starts:
                    raise ValueError(f'{name}: duplicate/missing bookmark identity')
                starts[ident] = node.get(W + 'name')
            if node.tag == W + 'bookmarkEnd':
                ident = node.get(W + 'id')
                if ident not in starts or ident in ends:
                    raise ValueError(f'{name}: orphan bookmark end')
                ends.add(ident)
            if node.tag == '{http://schemas.openxmlformats.org/officeDocument/2006/math}f':
                ns = '{http://schemas.openxmlformats.org/officeDocument/2006/math}'
                if len(node.findall(ns + 'num')) != 1 or len(node.findall(ns + 'den')) != 1:
                    raise ValueError(f'{name}: incomplete mathematical fraction')
            if node.tag.startswith(M) and etree.QName(node).localname in OBJECTS:
                kind = etree.QName(node).localname
                for argument in OBJECTS[kind]:
                    count = len(node.findall(M + argument))
                    repeatable = kind in {'d', 'eqArr', 'm'}
                    if count == 0 or not repeatable and count != 1:
                        raise ValueError(f'{name}: malformed OMML {kind}/{argument} cardinality')
            if node.tag == W + 'tbl':
                validate_grid(node)
            if node.tag == W + 'tc' and node.find(W + 'p') is None and node.find(W + 'sdt') is None:
                raise ValueError(f'{name}: table cell has no paragraph')
            for child in node:
                if isinstance(child.tag, str):
                    walk(child)
        walk(container)
        if stack:
            raise ValueError(f'{name}: unclosed Word field')
        if set(starts) != ends:
            raise ValueError(f'{name}: unclosed bookmark')
    check(root)


def retained_content(root):
    """Ordered payload inventory for the supported transformations.

This invariant catches lost/duplicated/reordered retained payload. It deliberately
ignores paragraph and row boundaries (checked separately), and is NOT a reference
DOCX comparison or an independent implementation of Word revision semantics.
"""
    from .revisions import HISTORY
    from .tables import deleted_cell, deleted_row
    from .math_revisions import deleted_objects, emptied_containers
    from .math_runs import mixed, split_mixed_runs
    if any(mixed(n) for n in root.iter('{http://schemas.openxmlformats.org/officeDocument/2006/math}r')):
        from copy import deepcopy
        root = deepcopy(root)
        split_mixed_runs(root)
    removed_math = deleted_objects(root)
    removed_math |= emptied_containers(root, removed_math)

    math = '{http://schemas.openxmlformats.org/officeDocument/2006/math}'
    atoms = {W + n for n in ('t', 'instrText', 'tab', 'br', 'cr', 'sym', 'noBreakHyphen', 'softHyphen',
                             'fldChar', 'fldSimple', 'hyperlink', 'footnoteReference', 'endnoteReference',
                             'commentReference', 'bookmarkStart', 'bookmarkEnd', 'drawing', 'pict', 'object')}
    events = []
    def visit(node):
        if node in removed_math:
            return
        if not isinstance(node.tag, str):
            return
        if node.tag in {W + n for n in HISTORY | {'del', 'moveFrom', 'delText', 'delInstrText'}}:
            return
        if node.tag == W + 'tc' and deleted_cell(node):
            return
        if node.tag == W + 'tr' and deleted_row(node):
            return
        if node.tag == math + 'r':
            # Only a chain of whole-run edits can delete the run itself. A
            # deletion in a historical property snapshot is not active content.
            payload = next((c for c in node if c.tag in {W + 'ins', W + 'del'}), None)
            while payload is not None:
                if payload.tag == W + 'del':
                    return
                payload = next((c for c in payload if c.tag in {W + 'ins', W + 'del'}), None)
        if node.tag in atoms or node.tag.startswith(math) or any(a.startswith(R) for a in node.attrib):
            events.append((node.tag, tuple(sorted(node.attrib.items())), node.text if node.tag in {W + 't', W + 'instrText', math + 't'} else None))
        for child in node:
            visit(child)
    visit(root)
    return tuple(events)


def retained_structure(root):
    """Count retained blocks before paragraph merging, independent of node moves."""
    from .revisions import HISTORY
    from .tables import deleted_cell, deleted_row

    counts = Counter()
    def visit(node):
        if not isinstance(node.tag, str) or node.tag in {W + n for n in HISTORY | {'del', 'moveFrom'}}:
            return
        if node.tag == W + 'tc' and deleted_cell(node):
            return
        if node.tag == W + 'tr' and deleted_row(node):
            return
        if node.tag == W + 'tbl':
            rows = node.findall(W + 'tr')
            if rows and all(deleted_row(r) for r in rows):
                return
        if node.tag in {W + n for n in ('p', 'tbl', 'tr', 'tc')}:
            counts[etree.QName(node).localname] += 1
        for child in node:
            visit(child)
    visit(root)
    return counts
