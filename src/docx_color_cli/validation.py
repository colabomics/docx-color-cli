"""Conservative content comparison, independent of revision conversion.

Never accepts revisions or imports the converter. The caller supplies a reference
saved after accepting all revisions in Microsoft Word. Equality here is a bounded
OOXML content comparison, not a proof of rendered layout or reference provenance.
"""
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import PurePosixPath
import posixpath
from urllib.parse import unquote
from zipfile import BadZipFile, ZipFile

from lxml import etree


W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
W = '{' + W_NS + '}'
M = '{http://schemas.openxmlformats.org/officeDocument/2006/math}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
STORIES = {W + x for x in ('document', 'hdr', 'ftr', 'footnotes', 'endnotes', 'comments', 'glossaryDocument')}
REVISION_NAMES = {
    'ins', 'del', 'moveFrom', 'moveTo', 'delText', 'delInstrText',
    'rPrChange', 'pPrChange', 'tblPrChange', 'trPrChange', 'tcPrChange',
    'sectPrChange', 'tblGridChange', 'tblPrExChange', 'numberingChange',
    'cellIns', 'cellDel', 'cellMerge',
}
IGNORED_ELEMENTS = {W + x for x in ('proofErr', 'lastRenderedPageBreak')}
SETTING_METADATA = {W + x for x in ('rsids', 'proofState', 'trackRevisions', 'revisionView')}
STORY_BOUNDARIES = {W + x for x in ('body', 'hdr', 'ftr', 'footnote', 'endnote', 'comment', 'txbxContent', 'docPartBody')} | {'{http://schemas.openxmlformats.org/markup-compatibility/2006}' + n for n in ('Choice', 'Fallback')}


@dataclass
class ValidationResult:
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checked_parts: list[str] = field(default_factory=list)
    reference_compared: bool = False

    @property
    def ok(self):
        return not self.issues

    def to_dict(self):
        return {'ok': self.ok, **asdict(self)}

    def require(self):
        if not self.ok:
            raise ValueError('Content validation failed: ' + '; '.join(self.issues))


def parse_xml(data):
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    root = etree.fromstring(data, parser)
    if root.getroottree().docinfo.doctype:
        raise ValueError('DOCTYPE is not supported in OOXML')
    from .namespaces import canonical_namespaces
    return canonical_namespaces(root)


def is_revision(node):
    if not isinstance(node.tag, str):
        return False
    q = etree.QName(node)
    word_namespace = q.namespace == W_NS or (q.namespace or '').startswith('http://schemas.microsoft.com/office/word/')
    return word_namespace and (
        q.localname in REVISION_NAMES or q.localname.startswith(('moveFromRange', 'moveToRange'))
        or ('customXml' in q.localname and 'Range' in q.localname)
        or 'conflict' in q.localname.lower()
    )


def field_issues(root):
    """Check field nesting independently in each story, including text boxes.

    Fields may span paragraphs, but may not cross into another story. Nested
    complex fields and simple fields retain independent boundary accounting.
    """
    issues = []

    def story(container):
        stack = []

        def visit(node):
            if node is not container and (node.tag in STORY_BOUNDARIES or node.tag == W + 'fldSimple'):
                story(node)
                return
            if node.tag == W + 'fldChar':
                kind = node.get(W + 'fldCharType')
                if kind == 'begin':
                    stack.append(False)
                elif kind == 'separate':
                    if not stack or stack[-1]:
                        issues.append('unmatched/duplicate field separator')
                    else:
                        stack[-1] = True
                elif kind == 'end':
                    if not stack:
                        issues.append('unmatched field end')
                    else:
                        stack.pop()
                else:
                    issues.append('invalid field character type')
            if node.tag == W + 'instrText' and (not stack or stack[-1]):
                issues.append('field instruction outside field code region')
            for child in node:
                visit(child)

        visit(container)
        if stack:
            issues.append('unclosed field at story boundary')

    story(root)
    return issues


def bookmark_issues(root):
    """Validate each alternative separately; only one MC branch is displayed."""
    branches = {'{http://schemas.openxmlformats.org/markup-compatibility/2006}' + n
                for n in ('Choice', 'Fallback')}
    issues = []
    def check(container):
        starts, ends = set(), set()
        def walk(node):
            if node is not container and node.tag in branches:
                check(node)
                return
            if node.tag == W + 'bookmarkStart':
                ident = node.get(W + 'id')
                if ident is None or ident in starts:
                    issues.append('unbalanced/duplicate bookmark range')
                starts.add(ident)
            elif node.tag == W + 'bookmarkEnd':
                ident = node.get(W + 'id')
                if ident not in starts or ident in ends:
                    issues.append('unbalanced/duplicate bookmark range')
                ends.add(ident)
            for child in node:
                walk(child)
        walk(container)
        if starts != ends:
            issues.append('unbalanced/duplicate bookmark range')
    check(root)
    return issues


class _Package:
    def __init__(self, path):
        with ZipFile(path) as archive:
            names = archive.namelist()
            if len(set(names)) != len(names):
                raise ValueError('duplicate ZIP members')
            self.data = {name: archive.read(name) for name in names}
        if 'word/document.xml' not in self.data:
            raise ValueError('missing word/document.xml')
        self.xml = {name: parse_xml(data) for name, data in self.data.items()
                    if name.endswith(('.xml', '.rels'))}
        if self.xml['word/document.xml'].tag != W + 'document':
            raise ValueError('unsupported document namespace/root')
        self.stories = {name: root for name, root in self.xml.items() if root.tag in STORIES}
        for root in self.xml.values():
            for node in root.iter():
                if isinstance(node.tag, str) and 'purl.oclc.org/ooxml/' in node.tag:
                    raise ValueError('unsupported Strict OOXML namespace')

    def relationship(self, part, rid):
        path = PurePosixPath(part)
        rels_name = str(path.parent / '_rels' / (path.name + '.rels'))
        root = self.xml.get(rels_name)
        matches = [] if root is None else [n for n in root if n.get('Id') == rid]
        if len(matches) != 1:
            raise ValueError(f'{part}: missing or duplicate relationship {rid}')
        rel = matches[0]
        target = rel.get('Target')
        kind = rel.get('Type')
        if not target or not kind:
            raise ValueError(f'{part}: invalid relationship {rid}')
        if rel.get('TargetMode') == 'External':
            return kind, 'External', target
        target = unquote(target)
        resolved = posixpath.normpath(posixpath.join(str(path.parent), target)) if not target.startswith('/') else target.lstrip('/')
        if resolved not in self.data:
            raise ValueError(f'{part}: relationship {rid} has missing target')
        return kind, 'Internal', resolved

    def attributes(self, node, part, seen):
        attrs = []
        for key, value in node.attrib.items():
            q = etree.QName(key)
            if (q.namespace == W_NS and q.localname.startswith('rsid')) or (
                q.namespace == 'http://schemas.microsoft.com/office/word/2010/wordml'
                and q.localname in {'paraId', 'textId'}
            ):
                continue
            if key == '{http://www.w3.org/XML/1998/namespace}space':
                continue  # The text itself, including spaces, remains exact.
            if key.startswith(R) or key == '{urn:schemas-microsoft-com:office:office}relid':
                kind, mode, target = self.relationship(part, value)
                if mode == 'Internal':
                    if target in self.stories or target in seen:
                        value = (kind, mode, target)
                    elif target in self.xml:
                        value = (kind, mode, self.canonical(target, seen | {part}))
                    else:
                        value = (kind, mode, sha256(self.data[target]).hexdigest())
                else:
                    value = (kind, mode, target)
            attrs.append((key, value))
        return tuple(sorted(attrs))

    def canonical(self, part, seen=frozenset()):
        """Ordered structural events; merge text only across equivalent runs.

        Exact paragraph/table/math/field structure and all non-color run
        properties remain significant. Unknown XML is retained conservatively.
        """
        events = []

        def emit(event):
            if event[0] == 'text' and events and events[-1][:-1] == event[:-1]:
                events[-1] = (*event[:-1], events[-1][-1] + event[-1])
            else:
                events.append(event)

        def properties(node):
            if node.tag == W + 'color':
                return None
            children = tuple(p for child in node if (p := properties(child)) is not None)
            return node.tag, self.attributes(node, part, seen), (node.text or '').strip(), children

        def visit(node, style=()):
            if not isinstance(node.tag, str) or node.tag in IGNORED_ELEMENTS:
                return
            if self.xml[part].tag == W + 'settings' and node.tag in SETTING_METADATA:
                return
            if node.tag in {W + 'r', M + 'r'}:
                props = []
                for child in node:
                    if child.tag in {W + 'rPr', M + 'rPr'}:
                        for prop in child:
                            value = properties(prop)
                            if value is not None:
                                props.append(value)
                style = (self.attributes(node, part, seen), tuple(sorted(props, key=repr)))
                # An empty run has no visible content; its properties do not
                # create a boundary between surrounding equivalent text runs.
                for child in node:
                    if child.tag not in {W + 'rPr', M + 'rPr'}:
                        visit(child, style)
                return
            if node.tag in {W + 't', M + 't', W + 'instrText'}:
                text = node.text or ''
                # A missing xml:space on edge whitespace may change how Word
                # interprets it. Do not equate that with explicit preservation.
                space = node.get('{http://www.w3.org/XML/1998/namespace}space')
                uncertain_space = bool(text != text.strip() and space != 'preserve')
                emit(('text', node.tag, () if node.tag == W + 'instrText' else style, uncertain_space, text))
                return
            # Font color is intentionally replaced by the converter, including
            # math control and paragraph-mark font properties.
            if node.tag == W + 'color' and node.getparent() is not None and node.getparent().tag == W + 'rPr':
                return
            if node.tag == W + 'rPr' and not any(c.tag != W + 'color' for c in node):
                return
            emit(('start', node.tag, self.attributes(node, part, seen), style))
            if node.text and node.text.strip():
                emit(('literal', node.text))
            for child in node:
                visit(child, style)
                if child.tail and child.tail.strip():
                    emit(('literal', child.tail))
            emit(('end', node.tag))

        visit(self.xml[part])
        return tuple(events)

    def opc_issues(self):
        issues = []
        ct = self.xml.get('[Content_Types].xml')
        namespace = '{http://schemas.openxmlformats.org/package/2006/content-types}'
        if ct is None or ct.tag != namespace + 'Types':
            issues.append('missing/invalid Content Types')
        else:
            defaults = {n.get('Extension'): n.get('ContentType') for n in ct if n.tag == namespace + 'Default'}
            overrides = {n.get('PartName', '').lstrip('/'): n.get('ContentType') for n in ct if n.tag == namespace + 'Override'}
            for name in self.data:
                if name == '[Content_Types].xml' or name.endswith('/'):
                    continue
                extension = PurePosixPath(name).name.rsplit('.', 1)[-1]
                if not (overrides.get(name) or defaults.get(extension)):
                    issues.append(f'{name}: missing Content Type')
            for name in overrides:
                if name not in self.data:
                    issues.append(f'{name}: Content Type override has missing part')
            expected = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'
            if overrides.get('word/document.xml') != expected:
                issues.append('word/document.xml: incorrect main Content Type')
        if '_rels/.rels' not in self.xml:
            issues.append('missing package relationships')
        else:
            office = [n for n in self.xml['_rels/.rels'] if n.get('Type') == R[1:-1] + '/officeDocument']
            if len(office) != 1 or office[0].get('Target', '').lstrip('/') != 'word/document.xml':
                issues.append('missing/ambiguous main document relationship')
        for name, root in self.xml.items():
            if not name.endswith('.rels'):
                continue
            rel_ns = '{http://schemas.openxmlformats.org/package/2006/relationships}'
            if root.tag != rel_ns + 'Relationships':
                issues.append(f'{name}: invalid relationships root')
                continue
            ids = [n.get('Id') for n in root]
            if None in ids or len(set(ids)) != len(ids):
                issues.append(f'{name}: missing/duplicate relationship IDs')
            if name == '_rels/.rels':
                source = ''
            else:
                path = PurePosixPath(name)
                source = str(path.parent.parent / path.name[:-5])
                if source not in self.data:
                    issues.append(f'{name}: missing relationship source part')
            for node in root:
                target = node.get('Target')
                if not target or not node.get('Type'):
                    issues.append(f'{name}: malformed relationship')
                    continue
                if node.get('TargetMode') == 'External':
                    continue
                resolved = posixpath.normpath(posixpath.join(str(PurePosixPath(source).parent), unquote(target))) if not target.startswith('/') else target.lstrip('/')
                if resolved not in self.data:
                    issues.append(f'{name}: missing relationship target {resolved}')
        return issues

    def check(self, accepted=True):
        issues = self.opc_issues()
        definitions = {}
        for kind in ('footnote', 'endnote', 'comment'):
            ids = [n.get(W + 'id') for root in self.stories.values() for n in root.iter(W + kind)]
            definitions[kind] = ids
            if len(set(ids)) != len(ids) or None in ids:
                issues.append(f'duplicate/missing {kind} definition ID')
        for name, root in self.xml.items():
            if accepted and any(is_revision(n) for n in root.iter()):
                issues.append(f'{name}: residual revision markup (reference must be accepted in Word)')
            if name in self.stories:
                issues.extend(f'{name}: {issue}' for issue in field_issues(root))
                if accepted:
                    issues.extend(f'{name}: {issue}' for issue in bookmark_issues(root))
                for fraction in root.iter(M + 'f'):
                    if fraction.find(M + 'num') is None or fraction.find(M + 'den') is None:
                        issues.append(f'{name}: incomplete OMML fraction')
            for node in root.iter():
                for kind, ids in definitions.items():
                    if node.tag == W + kind + 'Reference' and node.get(W + 'id') not in ids:
                        issues.append(f'{name}: dangling {kind} reference')
                if node.tag == W + 'altChunk':
                    issues.append(f'{name}: unsupported externally imported content (altChunk)')
                if isinstance(node.tag, str):
                    try:
                        self.attributes(node, name, frozenset({name}))
                    except ValueError as exc:
                        issues.append(str(exc))
        return issues


def inspect_docx(path, *, accepted=True):
    """Check accepted-document integrity, without claiming Word equivalence."""
    result = ValidationResult()
    try:
        package = _Package(path)
        result.checked_parts = sorted(package.stories)
        result.issues.extend(package.check(accepted=accepted))
    except (OSError, BadZipFile, etree.XMLSyntaxError, ValueError) as exc:
        result.issues.append(f'invalid DOCX: {exc}')
    return result


def validate_docx(output, reference, *, semantic=False):
    """Compare accepted output to an independently supplied Word reference.

    Part names and semantic IDs (bookmarks/notes/styles) are conservative: a
    Word re-save that renames them can cause a false rejection, never an
    intentional fallback to a lossy flattened-text comparison.
    """
    result = ValidationResult(reference_compared=True)
    packages = []
    for label, path in [('output', output), ('reference', reference)]:
        try:
            package = _Package(path)
            result.issues.extend(f'{label}: {issue}' for issue in package.check())
            packages.append(package)
        except (OSError, BadZipFile, etree.XMLSyntaxError, ValueError) as exc:
            result.issues.append(f'{label}: invalid DOCX: {exc}')
    if result.issues:
        return result
    actual, expected = packages
    if semantic:
        from .equivalence import normalize
        for label, package in zip(('output', 'reference'), packages):
            applied = normalize(package)
            if applied:
                result.warnings.append(label + ' bounded equivalences: ' + ', '.join(f'{k}={v}' for k,v in sorted(applied.items())))
    # Styles, numbering, fonts and themes affect symbols, list labels, hidden
    # text and equation rendering. Compare these dependencies conservatively.
    ancillary_roots = {W + 'styles', W + 'numbering', W + 'fonts', W + 'settings',
                       '{http://schemas.openxmlformats.org/drawingml/2006/main}theme'}
    parts = set(actual.stories) | set(expected.stories)
    for package in packages:
        parts.update(name for name, root in package.xml.items()
                     if root.tag in ancillary_roots or name.startswith('customXml/'))
    for name in sorted(parts):
        if name not in actual.xml or name not in expected.xml:
            result.issues.append(f'{name}: content part missing from output or reference')
            continue
        result.checked_parts.append(name)
        try:
            left, right = actual.canonical(name), expected.canonical(name)
            if left != right:
                index = next((i for i, (a, b) in enumerate(zip(left, right)) if a != b), min(len(left), len(right)))
                result.issues.append(f'{name}: content/structure mismatch at event {index} (output {len(left)} events, reference {len(right)} events)')
        except ValueError as exc:
            result.issues.append(str(exc))
    result.warnings.append('OOXML content comparison does not establish layout fidelity or verify that the reference was generated by Word.')
    return result
