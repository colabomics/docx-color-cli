"""Accept supported paragraph-mark and table-row revisions without flattening XML."""
from lxml import etree

from .package import W
from .revisions import RANGES, fail


def accept_structure(root, stats):
    """Accept cells, then plan row and paragraph changes before publication."""
    from .tables import accept_cells, has_live_content, validate_grid
    cell_tables = accept_cells(root, stats)
    removed_rows = []
    row_markers = []
    touched_tables = set()
    for row in root.iter(W + 'tr'):
        props = row.find(W + 'trPr')
        if props is None:
            continue
        marks = [n for n in props if n.tag in {W + 'ins', W + 'del'}]
        if not marks:
            continue
        table = row.getparent()
        if len(marks) != 1 or table.tag != W + 'tbl':
            fail(row, 'conflicting or wrapped table row revision')
        if marks[0].tag == W + 'ins':
            for cell in row.findall(W + 'tc'):
                merge = cell.find(W + 'tcPr/' + W + 'vMerge')
                if merge is not None and merge.get(W + 'val', 'continue') == 'continue' and has_live_content(cell):
                    fail(row, 'inserted continuation row has live content requiring Word evidence')
        row_markers.extend(marks)
        touched_tables.add(table)
        if marks[0].tag == W + 'del':
            removed_rows.append(row)

    merges = []
    paragraph_marks = []
    for paragraph in root.iter(W + 'p'):
        if any(a in removed_rows for a in paragraph.iterancestors()):
            continue
        props = paragraph.find(W + 'pPr')
        rpr = props.find(W + 'rPr') if props is not None else None
        marks = [] if rpr is None else [n for n in rpr if n.tag in {W + 'ins', W + 'del', W + 'moveFrom', W + 'moveTo'}]
        if not marks:
            continue
        if len({n.tag for n in marks}) != len(marks) or {W + 'moveFrom', W + 'moveTo'} <= {n.tag for n in marks}:
            fail(paragraph, 'conflicting paragraph mark revisions')
        paragraph_marks.extend(marks)
        if not any(n.tag in {W + 'del', W + 'moveFrom'} for n in marks):
            continue
        following = paragraph.getnext()
        while following is not None and following.tag in {W + name for name in RANGES}:
            following = following.getnext()
        if following is None or following.tag != W + 'p':
            fail(paragraph, 'deleted paragraph mark has no adjacent paragraph in the same container')
        if props.find(W + 'sectPr') is not None:
            fail(paragraph, 'paragraph mark deletion across section boundary')
        merges.append((paragraph, following))

    for row in removed_rows:
        row.getparent().remove(row)
        stats['deleted_rows'] += 1
    for marker in row_markers + paragraph_marks:
        marker.getparent().remove(marker)
        stats['accepted_structural_' + etree.QName(marker).localname] += 1
    # Moving complete inline nodes preserves fields, links, OMML and run order.
    # The last surviving mark owns the merged paragraph and its complete pPr.
    # Do not union properties: an absent property on that mark is also significant.
    for paragraph, following in merges:
        at = 1 if following.find(W + 'pPr') is not None else 0
        for child in list(paragraph):
            if child.tag != W + 'pPr':
                following.insert(at, child)
                at += 1
        paragraph.getparent().remove(paragraph)
        stats['merged_paragraphs'] += 1
    for table in touched_tables:
        if not table.findall(W + 'tr'):
            # No remaining rows: the table itself has no final content.
            table.getparent().remove(table)
            stats['deleted_tables'] += 1

    for table in touched_tables | cell_tables:
        if table.getparent() is not None:
            validate_grid(table)
