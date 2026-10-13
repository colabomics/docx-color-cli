"""Bounded optional equivalences on parsed copies, never conversion logic."""
from collections import Counter
import re
from lxml import etree

W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
R='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
WP='{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}'
WP14='{http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing}'
LINK='{urn:docx-color-cli:test-equivalence}hyperlink'


def normalize(package):
    counts=Counter()
    for part,root in package.xml.items():
        starts=list(root.iter(W+'bookmarkStart'))
        names=[n.get(W+'name') for n in starts]
        if all(names) and len(names)==len(set(names)):
            mapping={n.get(W+'id'):n.get(W+'name') for n in starts}
            for n in root.iter(W+'bookmarkStart',W+'bookmarkEnd'):
                if n.get(W+'id') in mapping:
                    n.set(W+'id',mapping[n.get(W+'id')]);counts['bookmark identity mapping']+=1
        if root.tag==W+'settings':
            for n in list(root.findall(W+'zoom')):
                root.remove(n);counts['view zoom']+=1
        for n in root.iter(WP+'inline',WP+'anchor'):
            if WP14+'editId' in n.attrib:
                del n.attrib[WP14+'editId'];counts['drawing edit identifier']+=1
        for n in root.iter(W+'hyperlink'):
            if R+'id' not in n.attrib or set(n.attrib)-{R+'id',W+'history'}:
                continue
            kind,mode,target=package.relationship(part,n.get(R+'id'))
            if mode!='External' or kind!=R[1:-1]+'/hyperlink':
                continue
            if n.get(W+'history') not in {None,'0','1','true','false','on','off'}:
                continue
            n.tag=LINK;n.attrib.clear();n.set('target',target)
            counts['editable hyperlink representation']+=1
        for parent in list(root.iter(W+'p')):
            i=0
            while i<len(parent):
                match=complex_link(list(parent),i)
                if match is None:i+=1;continue
                end,target,result,no_history=match
                link=etree.Element(LINK,target=target)
                nodes=list(parent)[i:end+1]
                for node in result:link.append(node)
                for node in nodes:
                    if node.getparent() is parent:parent.remove(node)
                parent.insert(i,link);counts['editable hyperlink representation']+=1;i+=1
                if no_history:counts['hyperlink visit-history switch']+=1
    return counts


def payload(run):
    if run.tag!=W+'r' or any(not k.startswith(W+'rsid') for k in run.attrib):return None
    return [c for c in run if c.tag!=W+'rPr']


def boundary(run,kind):
    children=payload(run)
    return children is not None and len(children)==1 and children[0].tag==W+'fldChar' and dict(children[0].attrib)=={W+'fldCharType':kind} and not len(children[0])


def complex_link(nodes,start):
    if not boundary(nodes[start],'begin'):return None
    code=[];i=start+1
    while i<len(nodes) and not boundary(nodes[i],'separate'):
        children=payload(nodes[i])
        if children is None or any(c.tag!=W+'instrText' for c in children):return None
        code.extend(c.text or '' for c in children);i+=1
    if i==len(nodes):return None
    # MS-OE376 2.1.509: HYPERLINK \\h suppresses visited-link history.
    # Like w:history above, this is excluded only in opt-in content comparison;
    # production retains the complete editable field and its click behavior.
    # https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oe376/233c2d46-107d-4881-86bf-c5f61f9c2a60
    # Recognize only a single documented trailing switch; never drop arbitrary
    # switches, arguments, nested fields or extra boundary attributes.
    match=re.fullmatch(r'\s*HYPERLINK\s+"(https?://[^"\s]+)"(?:\s+(\\h))?\s*',''.join(code),re.IGNORECASE)
    if match is None:return None
    result=[];i+=1
    while i<len(nodes) and not boundary(nodes[i],'end'):
        if nodes[i].tag!=W+'r' or any(n.tag in {W+'fldChar',W+'instrText'} for n in nodes[i].iter()):return None
        result.append(nodes[i]);i+=1
    if i==len(nodes) or not result:return None
    return i,match.group(1),result,bool(match.group(2))
