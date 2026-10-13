"""Accept cell revisions using the current grid and explicit vertical merge state.

ECMA-376 cellDel removes the cell, not just its text; cellMerge.vMerge is the
revised state (cont/rest). Ambiguous merge ownership is never inferred.
"""
from lxml import etree

from .package import W
from .revisions import fail

CELL_EDITS = {'cellIns', 'cellDel', 'cellMerge'}


def deleted_cell(cell):
    return cell.find(W + 'tcPr/' + W + 'cellDel') is not None


def deleted_row(row):
    cells = row.findall(W + 'tc')
    return row.find(W + 'trPr/' + W + 'del') is not None or bool(cells) and all(deleted_cell(c) for c in cells)


def check_marker(node):
    parent = node.getparent()
    if parent is None or parent.tag != W + 'tcPr' or parent.getparent().tag != W + 'tc' or len(node):
        fail(node, 'misplaced or nonempty ' + etree.QName(node).localname)
    marks = [n for n in parent if n.tag in {W + n for n in CELL_EDITS}]
    if len(marks) != 1:
        fail(node, 'conflicting cellIns/cellDel/cellMerge revisions')
    if node.tag == W + 'cellMerge':
        for attr in ('vMerge', 'vMergeOrig'):
            if node.get(W + attr) not in {None, 'cont', 'rest'}:
                fail(node, 'invalid cellMerge ' + attr)
        if node.get(W + 'vMerge') is None and node.get(W + 'vMergeOrig') is not None:
            fail(node, 'cellMerge lacks explicit revised state')


def integer(node, name, default):
    element = node.find(name)
    if element is None:
        return default
    try:
        result = int(element.get(W + 'val'))
    except (TypeError, ValueError) as exc:
        raise ValueError('Invalid table grid value') from exc
    if result < (1 if name.endswith('gridSpan') else 0):
        raise ValueError('Invalid table grid span/offset')
    return result


def validate_grid(table):
    """Verify current retained grid and merge continuity after structural changes."""
    columns = table.findall(W + 'tblGrid/' + W + 'gridCol')
    previous = set()
    for row in table.findall(W + 'tr'):
        at = integer(row, W + 'trPr/' + W + 'gridBefore', 0)
        current, horizontal = set(), False
        for cell in row.findall(W + 'tc'):
            span = integer(cell, W + 'tcPr/' + W + 'gridSpan', 1)
            key = (at, span)
            at += span
            for kind in ('hMerge', 'vMerge'):
                merge = cell.find(W + 'tcPr/' + W + kind)
                if merge is None:
                    if kind == 'hMerge':
                        horizontal = False
                    continue
                value = merge.get(W + 'val', 'continue')
                if value not in {'restart', 'continue'}:
                    fail(merge, 'invalid merge state')
                if kind == 'hMerge':
                    if value == 'continue' and not horizontal:
                        fail(merge, 'horizontal merge has no restart')
                    horizontal = True
                else:
                    if value == 'continue' and key not in previous:
                        fail(merge, 'vertical merge has no surviving owner with matching grid span')
                    current.add(key)
        at += integer(row, W + 'trPr/' + W + 'gridAfter', 0)
        if columns and at > len(columns):
            fail(row, 'retained cells exceed current table grid')
        previous = current



def has_live_content(cell):
    """Only a single plain empty paragraph is proof of an empty continuation.

    Unknown/non-text nodes, numbering and extra paragraph boundaries are content;
    never use a plain-text-only test to justify a merge.
    """
    payload = [n for n in cell if n.tag != W + 'tcPr']
    if len(payload) != 1 or payload[0].tag != W + 'p':
        return True
    for child in payload[0]:
        if child.tag == W + 'r' and all(n.tag == W + 'rPr' for n in child):
            continue
        if child.tag == W + 'pPr' and not len(child):
            continue
        return True
    return False


def accept_cells(root, stats):
    touched = set()
    for cell in list(root.iter(W + 'tc')):
        props = cell.find(W + 'tcPr')
        if props is None:
            continue
        marks = [n for n in props if n.tag in {W + n for n in CELL_EDITS}]
        if not marks:
            continue
        row = cell.getparent()
        if row.tag != W + 'tr' or row.getparent().tag != W + 'tbl':
            fail(cell, 'wrapped cell revision')
        touched.add(row.getparent())
        marker = marks[0]
        check_marker(marker)
        if marker.tag == W + 'cellDel':
            retained = [c for c in row.findall(W + 'tc') if not deleted_cell(c)]
            if retained and row.find(W + 'trPr/' + W + 'del') is None:
                columns = row.getparent().findall(W + 'tblGrid/' + W + 'gridCol')
                width = sum(integer(c, W + 'tcPr/' + W + 'gridSpan', 1) for c in retained)
                width += integer(row, W + 'trPr/' + W + 'gridBefore', 0)
                width += integer(row, W + 'trPr/' + W + 'gridAfter', 0)
                if not columns or width != len(columns):
                    fail(cell, 'cellDel requires explicit final grid/span reconciliation')
            row.remove(cell)
            stats['deleted_cells'] += 1
        else:
            if marker.tag == W + 'cellMerge' and marker.get(W + 'vMerge') is not None:
                value = {'cont': 'continue', 'rest': 'restart'}[marker.get(W + 'vMerge')]
                if value == 'continue' and has_live_content(cell):
                    fail(cell, 'cellMerge continuation contains live content requiring independent Word evidence')
                merge = props.find(W + 'vMerge')
                if merge is None:
                    merge = etree.Element(W + 'vMerge')
                    props.insert(props.index(marker), merge)
                merge.set(W + 'val', value)
            props.remove(marker)
        stats['accepted_' + etree.QName(marker).localname] += 1
    for table in touched:
        for row in list(table.findall(W + 'tr')):
            if not row.findall(W + 'tc'):
                table.remove(row)
                stats['deleted_rows'] += 1
        if not table.findall(W + 'tr'):
            table.getparent().remove(table)
            stats['deleted_tables'] += 1
    return touched
