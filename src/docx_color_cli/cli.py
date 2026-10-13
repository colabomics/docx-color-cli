"""Convert DOCX tracked text changes into permanent colors using OOXML and lxml.

Does not require MS Word or docx-revisions. Changes are accepted in the copy.
Complex structural revisions are rejected in strict mode rather than silently mangled.
"""
import argparse
import json
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
from collections import Counter
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import ZipFile

from lxml import etree

NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
W = '{' + NS + '}'
PART = re.compile(r'^word/(document|footnotes|endnotes|comments|header\d*|footer\d*)\.xml$')
PROPS = {'rPrChange', 'pPrChange', 'tblPrChange', 'trPrChange', 'tcPrChange',
         'sectPrChange', 'tblGridChange', 'numberingChange'}
REMOVE = {'del', 'moveFrom', 'moveFromRangeStart', 'moveFromRangeEnd',
          'customXmlDelRangeStart', 'customXmlDelRangeEnd', 'delText', 'delInstrText'}
UNWRAP = {'ins', 'moveTo'}
MARKERS = {'moveToRangeStart', 'moveToRangeEnd', 'customXmlInsRangeStart',
           'customXmlInsRangeEnd'}
STRUCTURAL = {'cellIns', 'cellDel', 'cellMerge'}


def paint_run(run, rgb):
    props = run.find(W + 'rPr')
    if props is None:
        props = etree.Element(W + 'rPr')
        run.insert(0, props)
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
    unsupported = []
    for node in root.iter():
        if node.tag == W + 'trPr':
            if node.find(W + 'del') is not None or node.find(W + 'ins') is not None:
                unsupported.append('inserted/deleted table row')
        if node.tag == W + 'pPr':
            rpr = node.find(W + 'rPr')
            if rpr is not None and (rpr.find(W + 'del') is not None or rpr.find(W + 'ins') is not None):
                unsupported.append('deleted/inserted paragraph mark')
        if node.tag in {W + t for t in STRUCTURAL}:
            unsupported.append(etree.QName(node).localname)
    if unsupported:
        stats['unsupported_structural_revisions'] += len(unsupported)
        if strict:
            raise ValueError('Unsupported structural revisions detected: ' + ', '.join(sorted(set(unsupported))) + '. Original unchanged; use --no-strict only after reviewing output.')

    for run in root.iter(W + 'r'):
        if _has_ancestor(run, {W + 'del', W + 'moveFrom'}):
            continue
        inserted = _has_ancestor(run, {W + 'ins', W + 'moveTo'})
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


def convert(source, target, *, strict=True, black='000000', red='FF0000'):
    source, target = Path(source), Path(target)
    if source.resolve() == target.resolve():
        raise ValueError('Input and output paths must differ')
    if not source.is_file():
        raise FileNotFoundError(source)
    if not all(re.fullmatch('[0-9A-Fa-f]{6}', x) for x in (black, red)):
        raise ValueError('Colors must be six hexadecimal digits')
    stats = Counter()
    target.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(source) as zin:
        replacements = {}
        for name in zin.namelist():
            if PART.fullmatch(name):
                xml = etree.fromstring(zin.read(name))
                modify(xml, stats, black, red, strict)
                replacements[name] = etree.tostring(xml, encoding='UTF-8', xml_declaration=True, standalone=True)
                stats['processed_parts'] += 1
        if 'word/document.xml' not in replacements:
            raise ValueError('Missing word/document.xml: not a valid DOCX')
        # Atomic-ish output: leave no partial result if input fails or conversion throws.
        with NamedTemporaryFile(dir=target.parent, suffix='.docx', delete=False) as f:
            temp = Path(f.name)
        try:
            with ZipFile(temp, 'w') as zout:
                for info in zin.infolist():
                    zout.writestr(info, replacements.get(info.filename, zin.read(info.filename)))
            with ZipFile(temp) as check:
                bad = check.testzip()
                if bad:
                    raise ValueError('Invalid output ZIP member: ' + bad)
            temp.replace(target)
        finally:
            temp.unlink(missing_ok=True)
    return dict(stats)


def export_pdf(docx_path, pdf_path):
    """Render an already-colored DOCX as a PDF with LibreOffice.

    Conversion happens in an isolated temporary directory/profile to avoid
    clobbering an existing document and to prevent LO instance collisions.
    """
    executable = shutil.which('libreoffice') or shutil.which('soffice')
    if executable is None:
        raise RuntimeError(
            'PDF output requires LibreOffice (soffice). '
            'Install it and ensure libreoffice/soffice is on your PATH.'
        )
    docx_path, pdf_path = Path(docx_path), Path(pdf_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='docx-color-pdf-') as tmp:
        tmp_dir = Path(tmp)
        profile = tmp_dir / 'lo-profile'
        out_dir = tmp_dir / 'pdf'
        out_dir.mkdir()
        cmd = [
            executable,
            '-env:UserInstallation=' + profile.as_uri(),
            '--headless', '--convert-to', 'pdf:writer_pdf_Export',
            '--outdir', str(out_dir), str(docx_path.resolve()),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError('LibreOffice PDF conversion timed out after 180 seconds') from exc
        if result.returncode != 0:
            raise RuntimeError('LibreOffice conversion failed: ' + (result.stderr or result.stdout).strip())
        generated = out_dir / (docx_path.stem + '.pdf')
        if not generated.is_file() or generated.stat().st_size == 0:
            raise RuntimeError('LibreOffice returned without producing a PDF: ' + (result.stderr or result.stdout).strip())
        # Only replace requested PDF after successful generation.
        generated.replace(pdf_path)


def convert_output(source, target, *, strict=True, black='000000', red='FF0000'):
    """Write color-coded DOCX, or render it directly into PDF."""
    target = Path(target)
    if target.suffix.lower() == '.docx':
        return convert(source, target, strict=strict, black=black, red=red)
    if target.suffix.lower() != '.pdf':
        raise ValueError('Output must end in .docx or .pdf')
    # A transient DOCX ensures the exported PDF contains accepted edits and
    # actual font colors, not Word review markup.
    with TemporaryDirectory(prefix='docx-color-stage-') as tmp:
        stage = Path(tmp) / 'colored.docx'
        stats = convert(source, stage, strict=strict, black=black, red=red)
        export_pdf(stage, target)
    return stats


def main(argv=None):
    parser = argparse.ArgumentParser(description='Accept DOCX text revisions: inserted red, unchanged black, deleted omitted.')
    parser.add_argument('input', type=Path)
    parser.add_argument('output', nargs='?', type=Path)
    parser.add_argument('--red', default='FF0000', help='Inserted text RGB hex')
    parser.add_argument('--black', default='000000', help='Other text RGB hex')
    parser.add_argument('--report', type=Path, help='Write JSON summary')
    parser.add_argument('--format', choices=('docx', 'pdf'), help='Output format (used for the default filename, or validated against output extension)')
    parser.add_argument('--no-strict', action='store_true', help='Allow unsupported structural revisions to remain; review document')
    args = parser.parse_args(argv)
    selected_format = args.format or (args.output.suffix.lower().lstrip('.') if args.output else 'docx')
    if selected_format not in ('docx', 'pdf'):
        parser.error('Output must be a .docx or .pdf file')
    destination = args.output or args.input.with_name(args.input.stem + '_colored.' + selected_format)
    if destination.suffix.lower() != '.' + selected_format:
        parser.error('--format must match the output filename extension')
    stats = convert_output(args.input, destination, strict=not args.no_strict, black=args.black, red=args.red)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Saved: {destination}')
    print(json.dumps(stats, indent=2))


if __name__ == '__main__':
    main()
