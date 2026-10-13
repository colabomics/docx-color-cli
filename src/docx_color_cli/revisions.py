"""Explicit revision policy and preflight, separate from XML mutation.

Unsupported content changes are errors even with the legacy --no-strict option.
Historical property snapshots are opaque, not active document content.
"""
from lxml import etree

from .package import W, W_NS

HISTORY = {'rPrChange', 'pPrChange', 'tblPrChange', 'trPrChange', 'tcPrChange',
           'sectPrChange', 'tblGridChange', 'tblPrExChange', 'numberingChange'}
EDIT = {'ins', 'del', 'moveFrom', 'moveTo'}
RANGES = {kind + 'Range' + end for kind in ('moveFrom', 'moveTo') for end in ('Start', 'End')}
M = '{http://schemas.openxmlformats.org/officeDocument/2006/math}'


def is_revision(node):
    if not isinstance(node.tag, str):
        return False
    q = etree.QName(node)
    word_ns = q.namespace == W_NS or (q.namespace or '').startswith('http://schemas.microsoft.com/office/word/')
    return word_ns and (q.localname in EDIT | HISTORY | RANGES | {'cellIns', 'cellDel', 'cellMerge', 'delText', 'delInstrText'}
                        or q.localname.endswith('Change') or q.localname.startswith(('customXml', 'conflict')) and ('Range' in q.localname or 'conflict' in q.localname))


def active_nodes(root):
    yield root
    if root.tag in {W + name for name in HISTORY}:
        return
    for child in root:
        if isinstance(child.tag, str):
            yield from active_nodes(child)


def fail(node, message):
    raise ValueError(f'Unsupported revision at {node.getroottree().getpath(node)}: {message}')


def scope(node):
    from .compatibility import BRANCHES
    for parent in node.iterancestors():
        if parent.tag in BRANCHES:
            return parent
        if parent.tag in {W + name for name in ('body', 'hdr', 'ftr', 'footnote', 'endnote', 'comment', 'txbxContent', 'docPartBody')}:
            return parent
    return node.getroottree().getroot()


def logical_nodes(node):
    """Paragraph properties precede runs in XML, but their mark follows the runs."""
    yield node
    if node.tag in {W + n for n in HISTORY}:
        return
    for child in node:
        if child.tag != W + 'pPr':
            yield from logical_nodes(child)
    if node.tag == W + 'p':
        props = node.find(W + 'pPr')
        if props is not None:
            yield from logical_nodes(props)


def check_moves(nodes):
    """Pair named ranges in story order, including paragraph-end revisions."""
    ordered = list(logical_nodes(nodes[0]))
    positions = {n: i for i, n in enumerate(ordered)}
    moves = {n for n in nodes if n.tag in {W + 'moveFrom', W + 'moveTo'}}
    covered = set()
    by_kind = {}
    def cell(node):
        return next((a for a in node.iterancestors() if a.tag == W + 'tc'), None)
    for kind in ('moveFrom', 'moveTo'):
        starts = [n for n in nodes if n.tag == W + kind + 'RangeStart']
        ends = [n for n in nodes if n.tag == W + kind + 'RangeEnd']
        pairs, ids, used_ends = {}, set(), set()
        for start in starts:
            ident, name = start.get(W + 'id'), start.get(W + 'name')
            key, idkey = (scope(start), name), (scope(start), ident)
            if not ident or not name or key in pairs or idkey in ids:
                fail(start, 'duplicate or missing move range identity')
            ids.add(idkey)
            matches = [e for e in ends if e.get(W + 'id') == ident and scope(e) is scope(start)]
            if len(matches) != 1:
                fail(start, 'unpaired move range')
            end = matches[0]
            a, b = positions[start], positions[end]
            if b <= a or cell(start) is not cell(end):
                fail(start, 'reversed or cross-cell move range')
            contents = ordered[a + 1:b]
            selected = {n for n in contents if n.tag == W + kind}
            if selected & covered:
                fail(start, 'overlapping move content')
            if not selected:
                fail(start, 'move range has no matching move containers')
            for n in contents:
                if scope(n) is not scope(start) or cell(n) is not cell(start):
                    fail(start, 'move range crosses a story or cell boundary')
                if n.tag in {W + 'tbl', W + 'sectPr'}:
                    fail(start, 'move range crosses a table or section boundary')
                if n.tag in {W + 'r', M + 'r', W + 'hyperlink', W + 'fldSimple'}:
                    if not any(parent.tag in {W + kind, W + 'ins', W + 'del'} for parent in n.iterancestors()):
                        fail(n, 'untracked content in move range')
                if n in moves and n.tag != W + kind:
                    fail(n, 'mixed source and destination move range')
            covered.update(selected)
            used_ends.add(end)
            pairs[key] = start
        if len(used_ends) != len(ends):
            raise ValueError('Unpaired move range end')
        by_kind[kind] = pairs
    if by_kind['moveFrom'].keys() != by_kind['moveTo'].keys():
        raise ValueError('Unpaired move source/destination names in story')
    if moves != covered:
        raise ValueError('Unpaired or unsupported move container / paragraph mark')


def preflight(root):
    from .math_revisions import deleted_objects, inserted_controls
    from .custom_xml import MARKERS as CUSTOM_MARKERS, plan
    plan(root)
    from .compatibility import validate_alternatives
    validate_alternatives(root)
    accepted_controls = set(inserted_controls(root))
    removed_math = deleted_objects(root)
    nodes = list(active_nodes(root))
    for node in nodes:
        if not is_revision(node):
            continue
        name = etree.QName(node).localname
        if node.tag in {W + n for n in CUSTOM_MARKERS}:
            continue
        if node.tag not in {W + n for n in EDIT | HISTORY | RANGES | {'cellIns', 'cellDel', 'cellMerge', 'delText', 'delInstrText'}}:
            fail(node, name)
        if name in {'cellIns', 'cellDel', 'cellMerge'}:
            from .tables import check_marker
            check_marker(node)
            continue
        if name in HISTORY:
            # History is valid only on the corresponding current property container.
            expected = 'numPr' if name == 'numberingChange' else name[:-6]
            if node.getparent() is None or node.getparent().tag != W + expected:
                fail(node, 'misplaced historical ' + name)
            continue
        ancestors = list(node.iterancestors())
        if any(a.tag == M + 'ctrlPr' for a in ancestors):
            if any(a in removed_math or a in accepted_controls for a in ancestors):
                continue
            fail(node, 'mathematical control revision')
        if name in EDIT:
            if name in {'moveFrom', 'moveTo'} and any(a.tag in {W + 'moveFrom', W + 'moveTo'} for a in ancestors):
                fail(node, 'nested move containers')
            parent = node.getparent()
            paragraph_mark = (parent is not None and parent.tag == W + 'rPr' and parent.getparent() is not None and parent.getparent().tag == W + 'pPr' and parent.getparent().getparent() is not None and parent.getparent().getparent().tag == W + 'p')
            row_mark = parent is not None and parent.tag == W + 'trPr' and parent.getparent() is not None and parent.getparent().tag == W + 'tr'
            if paragraph_mark or (name in {'ins', 'del'} and row_mark):
                if len(node):
                    fail(node, 'structural revision marker must be empty')
                continue  # Structural policy is checked before mutation in the converter.
            if name in {'ins', 'del'} and parent is not None and parent.tag == M + 'r':
                from .math_runs import mixed, segments
                if mixed(parent):
                    segments(parent)
                    continue
                # Word extension: a whole math run's payload is inside w:ins/w:del.
                # Mixed streams were validated above; this path handles whole runs.
                if any(c is not node and c.tag not in {M + 'rPr', W + 'rPr'} for c in parent):
                    fail(node, 'mixed math run revision requires splitting')
                payload = node
                deleted_payload = node.tag == W + 'del'
                while any(c.tag in {W + 'ins', W + 'del'} for c in payload):
                    if len(payload) != 1:
                        fail(node, 'mixed nested math revision requires splitting')
                    payload = payload[0]
                    deleted_payload |= payload.tag == W + 'del'
                if any(c.tag not in ({W + 'rPr', M + 'rPr', M + 't'} if deleted_payload else {W + 'rPr', M + 't'}) for c in payload):
                    fail(node, 'unsupported math run revision payload')
                if len(parent.findall(M + 'rPr')) + len(payload.findall(M + 'rPr')) > 1 or len(parent.findall(W + 'rPr')) + len(payload.findall(W + 'rPr')) > 1:
                    fail(node, 'ambiguous math run properties')
                continue
            from .compatibility import BRANCHES
            if parent is not None and parent.tag in BRANCHES:
                parent = parent.getparent().getparent()
            math_runs = (name in {'ins', 'del'} and parent is not None and parent.tag in {M + n for n in ('oMath', 'num', 'den', 'e', 'deg', 'sub', 'sup', 'lim', 'fName')} and all(c.tag == M + 'r' for c in node))
            if not math_runs and (parent is None or parent.tag not in {W + n for n in ('p', 'hyperlink', 'fldSimple', 'sdtContent', 'smartTag', 'customXml', 'dir', 'bdo', 'ins', 'del', 'moveFrom', 'moveTo')}):
                fail(node, 'unsupported content revision context')
            if any(n.tag in {W + t for t in ('p', 'tr', 'tc', 'tbl')} for n in node.iterdescendants()):
                fail(node, 'block-level revision container')
        elif name in {'delText', 'delInstrText'}:
            if not any(a.tag in {W + 'del', W + 'moveFrom'} for a in ancestors):
                fail(node, 'deleted text outside deletion')
    check_moves(nodes)
