"""Insertion provenance stays separate from final-text matching decisions."""

from collections import Counter
from dataclasses import dataclass, field

from lxml import etree

from .projection import HISTORY, STORIES, M, W, active, context, revision_node


@dataclass
class Insertion:
    key: str
    part: str
    revision_id: str | None
    author: str | None
    date: str | None
    kind: str
    text: str
    paragraph: int | None
    path: str
    structural_context: tuple
    before: str = ""
    after: str = ""
    spans: list = field(default_factory=list)


def ordinary(n):
    if n.tag in {W + "ins", W + "del"}:
        return all(ordinary(c) for c in n)
    return (
        n.tag == W + "r"
        and all(c.tag in {W + "rPr", W + "t", W + "delText"} for c in n)
        and not any(revision_node(c) and c.tag != W + "rPrChange" for c in active(n))
    )


def eligible_text(record, node):
    """Inline insertion provenance is a text-leaf property, not a run inventory.

    A field/line break in a sibling run does not revoke w:ins on this w:t.
    Keep the container COMPLEX so alignment still requires exact object/field
    boundaries. This admits candidates, not destinations or coloring spans.
    Math, controls, moves, historical and block insertions remain excluded.
    """
    if record.kind == "ORDINARY":
        return True
    if record.kind != "COMPLEX" or record.paragraph is None or node.tag != W + "t":
        return False
    if node.getparent().tag != W + "r":
        return False
    inline_insertion = False
    for ancestor in node.iterancestors():
        if ancestor.tag == W + "p":
            return inline_insertion
        if ancestor.tag not in {W + "r", W + "ins", W + "hyperlink", W + "fldSimple"}:
            return False
        inline_insertion |= ancestor.tag == W + "ins"
    return False


def extract(package):
    records, categories = {}, Counter()
    for part, root in package.xml.items():
        ps = list(root.iter(W + "p"))
        for ordinal, n in enumerate(root.iter(W + "ins")):
            ancestors = list(n.iterancestors())
            para = next((a for a in ancestors if a.tag == W + "p"), None)
            parent = n.getparent()
            if root.tag not in STORIES:
                kind = "UNSUPPORTED_PART"
            elif any(a.tag in HISTORY for a in ancestors):
                kind = "HISTORICAL"
            elif any(a.tag in {W + "del", W + "moveFrom"} for a in ancestors):
                kind = "DELETED"
            elif parent.tag == W + "rPr" and parent.getparent().tag == W + "pPr":
                kind = "PARAGRAPH_MARK"
            elif parent.tag in {W + "trPr", W + "tcPr"}:
                kind = "TABLE_STRUCTURE"
            elif any(
                isinstance(a.tag, str) and a.tag.startswith(M) for a in ancestors
            ) or any(isinstance(a.tag, str) and a.tag.startswith(M) for a in n.iter()):
                kind = "MATHEMATICAL"
            elif any(a.tag == W + "moveTo" for a in ancestors):
                kind = "MOVED"
            elif ordinary(n) and para is not None:
                kind = "ORDINARY"
            else:
                kind = "COMPLEX"
            text = "".join(
                c.text or ""
                for c in n.iter()
                if c.tag in {W + "t", W + "delText", M + "t"}
            )
            rec = Insertion(
                f"{part}#ins-{ordinal}",
                part,
                n.get(W + "id"),
                n.get(W + "author"),
                n.get(W + "date"),
                kind,
                text,
                ps.index(para) if para is not None else None,
                root.getroottree().getpath(n),
                context(para, root) if para is not None else (),
            )
            records[n] = rec
            categories[kind] += 1
    # Inventory revision kinds separately, including non-insertion revisions.
    inventory = Counter(
        etree.QName(n).localname
        for root in package.xml.values()
        for n in active(root)
        if revision_node(n)
    )
    return records, {
        "insertion_containers": len(records),
        "insertion_kinds": dict(categories),
        "raw_container_text_characters": sum(len(r.text) for r in records.values()),
        "active_revision_kinds": dict(inventory),
    }


def attach_offsets(records, projection):
    """Half-open paragraph/node spans retain offsets without repeating XML paths per char."""
    by_key = {r.key: r for r in records.values()}
    for p in projection:
        i = 0
        while i < len(p.origins):
            key = p.origins[i]
            if key is None:
                i += 1
                continue
            rec = by_key[key]
            node, offset = p.locations[i]
            end = i + 1
            while (
                end < len(p.origins)
                and p.origins[end] == key
                and p.locations[end] == (node, offset + end - i)
            ):
                end += 1
            if not rec.spans:
                rec.before = p.text[max(0, i - 40) : i]
            rec.after = p.text[end : end + 40]
            tree = node.getroottree()
            rec.spans.append(
                (
                    p.index,
                    i,
                    end,
                    tree.getpath(node.getparent()),
                    tree.getpath(node),
                    offset,
                    offset + end - i,
                )
            )
            i = end
