"""Build an original, synthetic Nature-inspired DOCX using only the stdlib.

Run from any directory: python examples/nature-style/generate.py
No manuscript, journal text, template or publisher branding is copied.
"""
from itertools import count
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
M = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
IDS = count(1)


def run(text, props=''):
    return f'<w:r><w:rPr>{props}</w:rPr><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def edit(kind, text):
    content = run(text)
    if kind == 'del':
        content = content.replace('w:t', 'w:delText')
    return (f'<w:{kind} w:id="{next(IDS)}" w:author="Demo Editor" '
            f'w:date="2026-01-01T12:00:00Z">{content}</w:{kind}>')


def para(content, style='Normal'):
    return f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr>{content}</w:p>'


def field(code, result):
    return ('<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            f'<w:r><w:instrText xml:space="preserve">{escape(code)}</w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r>' + result +
            '<w:r><w:fldChar w:fldCharType="end"/></w:r>')


def build(path):
    global IDS
    IDS = count(1)
    body = [para(run('RESEARCH ARTICLE  |  SYNTHETIC DEMONSTRATION'), 'Label'),
            para(run('Buffered signals stabilize a synthetic gene circuit'), 'Title'),
            para(run('Alex Example¹ & Rowan Demo¹'), 'Authors'),
            para(run('¹Example Institute for Synthetic Systems, Fictional City. All data are simulated.'), 'Small')]
    body += [para(run('Cellular responses depend on both signal strength and temporal variability. ')
                  + run('Here we show, in a synthetic model, that a buffering step ')
                  + edit('del', 'slightly improves') + edit('ins', 'reduces variability in')
                  + run(' the response of a minimal gene circuit. We compare ')
                  + edit('del', '24') + edit('ins', '48')
                  + run(' simulated trajectories and retain the same mean input in each condition. ')
                  + edit('ins', 'The effect persists across two independent parameter settings. ')
                  + run('This miniature manuscript demonstrates revision handling; it reports no experimental discovery.'), 'Summary')]
    cite = field(' ADDIN ZOTERO_ITEM CSL_CITATION {"citationID":"demo-1","citationItems":[]} ',
                 run('1', '<w:vertAlign w:val="superscript"/>'))
    body += [para(run('Synthetic circuits provide a controlled setting for studying variation') + cite
                  + run('. In this demonstration, all observations are generated from a fixed numerical sequence. ')
                  + edit('del', 'The circuit was measured in living cells. ')
                  + run('No patient, animal or unpublished research data are used.'))]
    body += [para(run('Buffering reduces response variability'), 'Heading1'),
             para(run('The baseline coefficient of variation was ') + edit('del', '0.42') + edit('ins', '0.38')
                  + run(', compared with 0.21 after buffering (Table 1). ')
                  + edit('ins', 'The mean response remained approximately constant. ')
                  + run('These illustrative values are chosen to make replacements and insertions easy to inspect.'))]
    equation = ('<m:oMath><m:r><m:t>CV = </m:t></m:r><m:f><m:fPr><m:type m:val="bar"/></m:fPr>'
                '<m:num><m:r><m:t>σ</m:t></m:r></m:num>'
                '<m:den><m:r><m:t>μ</m:t></m:r></m:den></m:f></m:oMath>')
    body += [para(run('We summarize variation as ') + equation + run(', where σ and μ denote the standard deviation and mean.')),
             para(run('References'), 'Heading1'),
             para(run('1. Example, A. & Demo, R. A minimal model of buffered signals. Synthetic reference for software testing (2026).'), 'Small'),
             para(run('Table 1 | Illustrative response statistics'), 'Heading1')]
    rows = [('Condition', 'Trajectories', 'Mean', 'CV'),
            ('Baseline', '48', '1.00', '0.38'), ('Buffered', '48', '1.02', '0.21')]
    table = '<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/><w:tblBorders>'
    table += ''.join(f'<w:{edge} w:val="single" w:sz="6" w:color="B8B8B8"/>' for edge in ['top','bottom','insideH'])
    table += '</w:tblBorders></w:tblPr><w:tblGrid>' + '<w:gridCol w:w="2300"/>' * 4 + '</w:tblGrid>'
    for index, row in enumerate(rows):
        table += '<w:tr>'
        for col, value in enumerate(row):
            content = run(value, '<w:b/>' if index == 0 else '')
            if index == 2 and col == 3:
                content = edit('del', '0.25') + edit('ins', '0.21')
            table += '<w:tc><w:tcPr><w:tcW w:w="2300" w:type="dxa"/></w:tcPr>' + para(content, 'TableText') + '</w:tc>'
        table += '</w:tr>'
    body += [table + '</w:tbl>', para(run('Values are synthetic and are not evidence for a biological effect.'), 'Small')]
    body += [para('<w:r><w:br w:type="page"/></w:r>'),
             para(run('Methods'), 'Heading1'),
             para(run('Simulation design. ', '<w:b/>') + run('Two fixed sets of synthetic trajectories represent baseline and buffered responses. ')
                  + edit('del', 'A random sample was selected for analysis. ')
                  + edit('ins', 'Every trajectory was included in the summary. ')
                  + run('The example deliberately contains ordinary replacements, adjacent revisions, a revised table cell, an OMML fraction and editable Word fields.')),
             para(run('Data availability'), 'Heading1'),
             para(run('All values are fabricated for this software example. No external dataset is required.')),
             para(run('Code availability'), 'Heading1'),
             para(run('The converter is available at ') + field(' HYPERLINK "https://github.com/lzj1769/docx-color-cli" \\h ',
                  run('github.com/lzj1769/docx-color-cli', '<w:u w:val="single"/>')) + run('.')),
             para(run('Acknowledgements'), 'Heading1'), para(run('This example was created for the docx-color-cli README.')),
             para(run('Author contributions'), 'Heading1'), para(run('A.E. and R.D. are fictional names used only in this demonstration.')),
             para(run('Competing interests'), 'Heading1'), para(run('This is not a published paper or an official Nature template.'))]
    body += ['<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="850" w:right="1000" w:bottom="850" w:left="1000" w:header="400" w:footer="400"/></w:sectPr>']
    styles = f'<w:styles xmlns:w="{W}"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:sz w:val="22"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="264" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
    definitions = {'Normal': ('',''), 'Title': ('<w:keepNext/><w:spacing w:before="100" w:after="180"/>','<w:b/><w:sz w:val="40"/>'),
                   'Label': ('<w:keepNext/>','<w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:sz w:val="17"/>'),
                   'Authors': ('<w:keepNext/>','<w:sz w:val="23"/>'),
                   'Small': ('<w:spacing w:after="100"/>','<w:sz w:val="18"/>'),
                   'Summary': ('<w:spacing w:before="100" w:after="180"/>','<w:b/>'),
                   'Heading1': ('<w:keepNext/><w:spacing w:before="160" w:after="80"/><w:outlineLvl w:val="0"/>','<w:b/><w:sz w:val="24"/>'),
                   'TableText': ('<w:spacing w:before="60" w:after="60"/>','<w:sz w:val="20"/>')}
    for name, (pp, rp) in definitions.items():
        styles += f'<w:style w:type="paragraph" w:styleId="{name}"'+(' w:default="1"' if name=='Normal' else '')+f'><w:name w:val="{name}"/>'
        if name != 'Normal': styles += '<w:basedOn w:val="Normal"/>'
        styles += f'<w:pPr>{pp}</w:pPr><w:rPr>{rp}</w:rPr></w:style>'
    styles += '</w:styles>'
    relns = 'http://schemas.openxmlformats.org/package/2006/relationships'
    parts = {'word/document.xml': f'<w:document xmlns:w="{W}" xmlns:r="{R}" xmlns:m="{M}"><w:body>{"".join(body)}</w:body></w:document>',
             'word/styles.xml': styles,
             'word/settings.xml': f'<w:settings xmlns:w="{W}"><w:revisionView w:markup="1" w:insDel="1"/><w:trackRevisions/></w:settings>',
             '_rels/.rels': f'<Relationships xmlns="{relns}"><Relationship Id="rId1" Type="{R}/officeDocument" Target="word/document.xml"/></Relationships>',
             'word/_rels/document.xml.rels': f'<Relationships xmlns="{relns}"><Relationship Id="rId1" Type="{R}/styles" Target="styles.xml"/><Relationship Id="rId2" Type="{R}/settings" Target="settings.xml"/></Relationships>'}
    ct = '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
    for name, kind in [('document','document.main'),('styles','styles'),('settings','settings')]:
        ct += f'<Override PartName="/word/{name}.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.{kind}+xml"/>'
    parts['[Content_Types].xml'] = ct + '</Types>'
    with ZipFile(path,'w') as archive:
        for name, content in sorted(parts.items()):
            info = ZipInfo(name, date_time=(2026,1,1,0,0,0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'+content)
    print(path)


if __name__ == '__main__':
    build(Path(__file__).with_name('tracked.docx'))
