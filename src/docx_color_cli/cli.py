"""Convert DOCX tracked text changes into permanent colors using OOXML and lxml.

Does not require MS Word or docx-revisions. Changes are accepted in the copy.
Unsupported revisions are rejected before publication, including with --no-strict.
"""
import argparse
import json
import re
from itertools import combinations
from collections import Counter
from copy import copy
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import ZipFile

from lxml import etree

from .package import read_xml_parts, discover_stories, validate_package, retained_content, retained_structure
from .revisions import preflight, HISTORY, active_nodes, M
from .structure import accept_structure
from .resources import explicit_references, prune_images
from .comments import reference_ids, prune_comments

NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
W = '{' + NS + '}'
PROPS = HISTORY
REMOVE = {'del', 'moveFrom', 'moveFromRangeStart', 'moveFromRangeEnd',
          'delText', 'delInstrText'}
UNWRAP = {'ins', 'moveTo'}
MARKERS = {'moveToRangeStart', 'moveToRangeEnd'}


def paint_run(run, rgb):
    props = run.find(W + 'rPr')
    if props is None:
        props = etree.Element(W + 'rPr')
        run.insert(1 if run.tag == M + 'r' and run.find(M + 'rPr') is not None else 0, props)
    color = props.find(W + 'color')
    if color is None:
        color = etree.Element(W + 'color')
        props.insert(0, color)
    color.set(W + 'val', rgb.upper())
    for key in ('themeColor', 'themeTint', 'themeShade'):
        color.attrib.pop(W + key, None)


def _has_ancestor(node, tags):
    return any(a.tag in tags for a in node.iterancestors())


def modify(root, stats, original='000000', added='FF0000', strict=True):
    """Modify one Word XML part in place; abort on unhandled structural revisions."""
    preflight(root)
    from .math_revisions import deleted_objects, emptied_containers
    removed_math = deleted_objects(root)
    empty_math = emptied_containers(root, removed_math)
    stats['removed_empty_math_containers'] += len(empty_math)
    removed_nodes = removed_math | empty_math
    for node in list(root.iter()):
        if node in removed_nodes and not any(a in removed_nodes for a in node.iterancestors()):
            node.getparent().remove(node)
            if node in removed_math:
                stats['deleted_math_objects'] += 1
    # Drop historical snapshots whole before inspecting current paragraph/row properties.
    for node in list(active_nodes(root)):
        if node.tag in {W + name for name in HISTORY} and node.getparent() is not None:
            node.getparent().remove(node)
            stats['removed_or_accepted_' + etree.QName(node).localname] += 1
    from .math_revisions import inserted_controls
    for control in inserted_controls(root):
        if _has_ancestor(control, {W + 'del', W + 'moveFrom'}):
            continue
        insertion = control.find(W + 'ins')
        for props in list(insertion):
            control.append(props)
        control.remove(insertion)
        paint_run(control, added)
        stats['accepted_math_control_ins'] += 1
    # Normalize validated whole-run chains before generic subtree deletion; an
    # inner deletion removes the mathematical run, not just its text wrapper.
    for run in list(root.iter(M + 'r')):
        if _has_ancestor(run, {W + 'del', W + 'moveFrom'}):
            continue
        outer = next((c for c in run if c.tag in {W + 'ins', W + 'del'}), None)
        if outer is None:
            continue
        chain, payload = [], outer
        while payload.tag in {W + 'ins', W + 'del'}:
            chain.append(payload)
            child = next((c for c in payload if c.tag in {W + 'ins', W + 'del'}), None)
            if child is None:
                break
            payload = child
        if any(c.tag == W + 'del' for c in chain):
            run.getparent().remove(run)
            stats['removed_or_accepted_del'] += 1
        elif len(chain) > 1:
            for child in list(payload):
                outer.append(child)
            outer.remove(chain[1])
            stats['accepted_ins'] += len(chain) - 1
    # Delete outer content subtrees before accepting descendants. A later insertion
    # inside a deleted range cannot resurrect content or contribute accepted counts.
    def discard_content(parent):
        for child in list(parent):
            if child.tag in {W + 'del', W + 'moveFrom'} and parent.tag not in {W + 'rPr', W + 'trPr', M + 'r'}:
                parent.remove(child)
                stats['removed_or_accepted_' + etree.QName(child).localname] += 1
            else:
                discard_content(child)
    discard_content(root)
    accept_structure(root, stats)

    inserted_math = set()
    for run in list(root.iter(M + 'r')):
        deletion = run.find(W + 'del')
        insertion = run.find(W + 'ins')
        if deletion is not None:
            run.getparent().remove(run)
            stats['removed_or_accepted_del'] += 1
        elif insertion is not None:
            for child in list(insertion):
                run.append(child)
            run.remove(insertion)
            inserted_math.add(run)
            stats['accepted_ins'] += 1

    for run in root.iter(W + 'r', M + 'r'):
        if _has_ancestor(run, {W + 'del', W + 'moveFrom'}):
            continue
        inserted = run in inserted_math or _has_ancestor(run, {W + 'ins', W + 'moveTo'})
        paint_run(run, added if inserted else original)
        stats['inserted_runs' if inserted else 'unchanged_runs'] += 1

    # Descendants first. Remove deletions, unwrap insertions in-place.
    for node in list(root.iter())[::-1]:
        parent = node.getparent()
        if parent is None:
            continue
        if node.tag in {W + t for t in REMOVE | PROPS | MARKERS}:
            stats['removed_or_accepted_' + etree.QName(node).localname] += 1
            parent.remove(node)
        elif node.tag in {W + t for t in UNWRAP}:
            stats['accepted_' + etree.QName(node).localname] += 1
            pos = parent.index(node)
            for child in list(node):
                node.remove(child)
                parent.insert(pos, child)
                pos += 1
            parent.remove(node)
    return root


def check_paths(*paths):
    """Reject aliases, including existing hard links, before opening any output."""
    for a, b in combinations([Path(p) for p in paths if p is not None], 2):
        if a.resolve() == b.resolve() or (a.exists() and b.exists() and a.samefile(b)):
            raise ValueError('Input, output and report paths must differ')


def convert(source, target, *, strict=True, black='000000', red='FF0000', _report=None):
    source, target = Path(source), Path(target)
    check_paths(source, target, _report)
    if not source.is_file():
        raise FileNotFoundError(source)
    if not all(re.fullmatch('[0-9A-Fa-f]{6}', x) for x in (black, red)):
        raise ValueError('Colors must be six hexadecimal digits')
    stats = Counter()
    target.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(source) as zin:
        replacements = {}
        roots = read_xml_parts(zin)
        validate_package(zin, roots)
        stories = discover_stories(roots)
        before_comments = reference_ids(roots)
        before_references = {name: explicit_references(xml) for name, xml in stories.items()}
        for name, xml in stories.items():
            expected_payload = retained_content(xml)
            expected_structure = retained_structure(xml)
            merged_before = stats['merged_paragraphs']
            modify(xml, stats, black, red, strict)
            expected_structure['p'] -= stats['merged_paragraphs'] - merged_before
            if retained_structure(xml) != expected_structure:
                raise ValueError(f'{name}: retained paragraph/table structure changed unexpectedly')
            if retained_content(xml) != expected_payload:
                raise ValueError(f'{name}: retained content changed during conversion')
            replacements[name] = etree.tostring(xml, encoding='UTF-8', xml_declaration=True, standalone=True)
            stats['processed_parts'] += 1
        removed_comments, comment_changes = prune_comments(roots, set(zin.namelist()), before_comments, stats)
        replacements.update(comment_changes)
        removed_parts, resource_changes = prune_images(roots, set(zin.namelist()) - removed_comments, before_references, stats)
        replacements.update(resource_changes)
        stats['removed_media_bytes'] = sum(zin.getinfo(name).file_size for name in removed_parts)
        removed_parts |= removed_comments
        # Stage beside the destination; publish only after all DOCX checks succeed.
        with NamedTemporaryFile(dir=target.parent, suffix='.docx', delete=False) as f:
            temp = Path(f.name)
        report_temp = None
        try:
            with ZipFile(temp, 'w') as zout:
                for info in zin.infolist():
                    if info.filename in removed_parts:
                        continue
                    # ZipFile.writestr mutates ZipInfo.header_offset; keep the input
                    # archive's directory usable for the publication comparison.
                    zout.writestr(copy(info), replacements.get(info.filename, zin.read(info.filename)))
            with ZipFile(temp) as check:
                validate_package(check, read_xml_parts(check), accepted=True)
                if check.namelist() != [name for name in zin.namelist() if name not in removed_parts]:
                    raise ValueError('Output ZIP members changed unexpectedly')
                for name in check.namelist():
                    if check.read(name) != replacements.get(name, zin.read(name)):
                        raise ValueError(f'{name}: unexpected output payload change')
            if _report is not None:
                _report = Path(_report)
                _report.parent.mkdir(parents=True, exist_ok=True)
                with NamedTemporaryFile(dir=_report.parent, suffix='.json', delete=False) as f:
                    report_temp = Path(f.name)
                report_temp.write_text(json.dumps(dict(stats), indent=2, ensure_ascii=False), encoding='utf-8')
            check_paths(source, target, _report)
            if report_temp is not None:
                report_temp.replace(_report)
            temp.replace(target)
        finally:
            temp.unlink(missing_ok=True)
            if report_temp is not None:
                report_temp.unlink(missing_ok=True)
    return dict(stats)


def convert_output(source, target, *, strict=True, black='000000', red='FF0000'):
    """Write a color-coded DOCX; no other output format is supported."""
    if Path(target).suffix.lower() != '.docx':
        raise ValueError('Output must end in .docx')
    return convert(source, target, strict=strict, black=black, red=red)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Accept DOCX text revisions: inserted red, unchanged black, deleted omitted.')
    parser.add_argument('input', type=Path)
    parser.add_argument('output', nargs='?', type=Path)
    parser.add_argument('--red', default='FF0000', help='Inserted text RGB hex')
    parser.add_argument('--black', default='000000', help='Other text RGB hex')
    parser.add_argument('--report', type=Path, help='Write JSON summary')
    parser.add_argument('--no-strict', action='store_true', help='Legacy option; unsupported revisions are still rejected')
    args = parser.parse_args(argv)
    destination = args.output or args.input.with_name(args.input.stem + '_colored.docx')
    if destination.suffix.lower() != '.docx':
        parser.error('Output must be a .docx file')
    stats = convert(args.input, destination, strict=not args.no_strict, black=args.black, red=args.red, _report=args.report)
    print(f'Saved: {destination}')
    print(json.dumps(stats, indent=2))


if __name__ == '__main__':
    main()
