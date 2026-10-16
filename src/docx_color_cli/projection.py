"""Bounded text projection, not an implementation of Accept All Changes."""

from collections import defaultdict
from dataclasses import dataclass, field

from lxml import etree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
HISTORY = {
    W + s
    for s in (
        "rPrChange",
        "pPrChange",
        "sectPrChange",
        "tblPrChange",
        "trPrChange",
        "tcPrChange",
        "tblGridChange",
        "tblPrExChange",
        "numberingChange",
    )
}
STORIES = {W + s for s in ("document", "hdr", "ftr", "footnotes", "endnotes")}
REVISION_NAMES = {"ins", "del", "moveFrom", "moveTo", "cellIns", "cellDel", "cellMerge"}


def revision_node(n):
    if not isinstance(n.tag, str):
        return False
    q = etree.QName(n)
    return (
        q.namespace == W[1:-1]
        or (q.namespace or "").startswith("http://schemas.microsoft.com/office/word/")
    ) and (
        q.localname in REVISION_NAMES
        or q.localname.endswith("Change")
        or "Range" in q.localname
        and q.localname.startswith(("move", "customXml"))
        or "conflict" in q.localname.lower()
    )


def active(n):
    yield n
    if n.tag in HISTORY:
        return
    for c in n:
        if isinstance(c.tag, str):
            yield from active(c)


@dataclass
class Paragraph:
    part: str
    index: int
    context: tuple
    node: object
    text: str = ""
    origins: list = field(default_factory=list)
    locations: list = field(default_factory=list)
    unresolved: set = field(default_factory=set)


def context(p, root):
    """Part-local stories and explicit table topology; no inferred cell ownership."""
    result = []
    tables = list(root.iter(W + "tbl"))
    for a in reversed(list(p.iterancestors())):
        if a.tag in {W + "footnote", W + "endnote"}:
            result.append((etree.QName(a).localname, a.get(W + "id")))
        if a.tag == W + "tbl":
            # Formatting siblings do not identify cells, but logical-grid
            # properties do: equal physical cell counts alone are insufficient.
            shape = tuple(
                (
                    grid_properties(r, "trPr", {"gridBefore", "gridAfter"}),
                    tuple(
                        grid_properties(c, "tcPr", {"gridSpan", "vMerge", "hMerge"})
                        for c in r.findall(W + "tc")
                    ),
                )
                for r in a.findall(W + "tr")
            )
            result.append(("table", tables.index(a), shape))
        elif a.tag in {W + "tr", W + "tc"}:
            # Word may add tblPrEx/trPr before cells or tblPr/tblGrid before
            # rows. Count only siblings of the same content-bearing kind.
            result.append(
                (etree.QName(a).localname, a.getparent().findall(a.tag).index(a))
            )
        elif a.tag == W + "txbxContent":
            result.append(("textbox", list(root.iter(W + "txbxContent")).index(a)))
    return tuple(result)


def grid_properties(node, property_tag, names):
    props = node.find(W + property_tag)
    if props is None:
        return ()
    return tuple(
        (n.tag, tuple(sorted(n.attrib.items())))
        for n in props
        if n.tag in {W + name for name in names}
    )


def range_paragraphs(nodes, active_all):
    """Quarantine each paired range, never the envelope of unrelated ranges.

    Duplicate, missing or reversed endpoints fail closed for the entire part.
    This only bounds uncertainty; it does not interpret or accept a move.
    """
    endpoints = defaultdict(lambda: {"Start": [], "End": []})
    positions = {n: i for i, n in enumerate(active_all)}
    for n in active_all:
        if not revision_node(n) or "Range" not in etree.QName(n).localname:
            continue
        suffix = "Start" if n.tag.endswith("Start") else "End"
        if not n.tag.endswith(suffix) or n.get(W + "id") is None:
            return set(nodes)
        endpoints[n.tag.removesuffix(suffix), n.get(W + "id")][suffix].append(
            positions[n]
        )
    intervals = []
    for pair in endpoints.values():
        if len(pair["Start"]) != 1 or len(pair["End"]) != 1:
            return set(nodes)
        low, high = pair["Start"][0], pair["End"][0]
        if low >= high:
            return set(nodes)
        intervals.append((low, high))
    unsafe = set()
    for p in nodes:
        inside = [positions[n] for n in active(p) if n in positions]
        if inside and any(
            min(inside) <= high and max(inside) >= low for low, high in intervals
        ):
            unsafe.add(p)
    return unsafe


def paragraphs(package, records=None):
    from .extract import ordinary

    tracked = records is not None
    result = []
    for part, root in package.xml.items():
        if root.tag not in STORIES:
            continue
        nodes = [
            p
            for p in root.iter(W + "p")
            if not any(a.tag in HISTORY for a in p.iterancestors())
        ]
        active_all = list(active(root))
        ranged = range_paragraphs(nodes, active_all) if tracked else set()
        unsafe = set()
        for i, p in enumerate(nodes):
            props = p.find(W + "pPr")
            if (
                tracked
                and props is not None
                and any(
                    n.tag in {W + "del", W + "moveFrom", W + "moveTo"}
                    for n in active(props)
                )
            ):
                unsafe.update(nodes[i : i + 2])
        for i, p in enumerate(nodes):
            block = Paragraph(part, i, context(p, root), p)
            if p in unsafe:
                block.unresolved.add("structural paragraph boundary")
            if p in ranged:
                block.unresolved.add("revision range")
            if tracked:
                for ancestor in p.iterancestors():
                    if ancestor.tag in {
                        W + "ins",
                        W + "del",
                        W + "moveFrom",
                        W + "moveTo",
                    }:
                        block.unresolved.add("block-level revision")
                    if ancestor.tag == W + "tbl" and any(
                        n.tag
                        in {
                            W + "cellIns",
                            W + "cellDel",
                            W + "cellMerge",
                            W + "tblGridChange",
                            W + "tblPrChange",
                            W + "trPrChange",
                            W + "tcPrChange",
                            W + "tblPrExChange",
                        }
                        or n.tag in {W + "ins", W + "del"}
                        and n.getparent().tag == W + "trPr"
                        for n in active(ancestor)
                    ):
                        block.unresolved.add("table structure revision")
            chunks = []

            def visit(n, origin=None, *, p=p, block=block, chunks=chunks):
                if n is not p and n.tag == W + "p":
                    return  # Independent nested story paragraphs are indexed separately.
                if n.tag in HISTORY:
                    return
                if tracked:
                    if n.tag == W + "del":
                        if not ordinary(n):
                            block.unresolved.add("complex deletion")
                        return
                    if n.tag in {W + "moveFrom", W + "moveTo"}:
                        block.unresolved.add("move revision")
                    if n in records:
                        record = records[n]
                        if record.kind == "PARAGRAPH_MARK":
                            return
                        if record.kind != "ORDINARY":
                            block.unresolved.add(record.kind.lower())
                        origin = record.key
                    if n.tag in {W + "delText", W + "delInstrText"}:
                        return
                    if revision_node(n) and n.tag not in {W + "ins", W + "del"}:
                        block.unresolved.add("unsupported revision")
                value = None
                if n.tag in {W + "t", M + "t"}:
                    value = n.text or ""
                elif n.tag in {W + "tab", W + "br", W + "cr"}:
                    value = "\t" if n.tag == W + "tab" else "\n"
                if value is not None:
                    chunks.append(value)
                    block.origins.extend([origin] * len(value))
                    block.locations.extend((n, j) for j in range(len(value)))
                for child in n:
                    visit(child, origin)

            inherited = next(
                (records[a].key for a in p.iterancestors() if tracked and a in records),
                None,
            )
            if not tracked or not any(a.tag == W + "del" for a in p.iterancestors()):
                visit(p, inherited)
            block.text = "".join(chunks)
            result.append(block)
    return result
