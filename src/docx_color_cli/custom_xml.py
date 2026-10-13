"""Accept complete custom-markup ranges, preserving their text and fields.

Partial physical-tag ranges and overlapping ranges need additional semantics;
refuse these rather than delete their text or silently change content bindings.
"""

from .revisions import W, active_nodes, fail

MARKERS = {
    "customXml" + kind + "Range" + end
    for kind in ("Ins", "Del")
    for end in ("Start", "End")
}


def plan(root):
    nodes = list(active_nodes(root))
    markers = [n for n in nodes if n.tag in {W + m for m in MARKERS}]
    result, used = [], set()
    for start in markers:
        if not start.tag.endswith("Start"):
            continue
        ident = start.get(W + "id")
        matches = [
            n
            for n in markers
            if n.tag == start.tag[:-5] + "End" and n.get(W + "id") == ident
        ]
        starts = [n for n in markers if n.tag == start.tag and n.get(W + "id") == ident]
        if (
            not ident
            or len(matches) != 1
            or len(starts) != 1
            or len(start)
            or len(matches[0])
        ):
            fail(start, "ambiguous custom XML range identity")
        end = matches[0]
        parent = start.getparent()
        if end.getparent() is not parent or parent.index(end) <= parent.index(start):
            fail(start, "partial/cross-container custom XML range")
        enclosed = list(parent)[parent.index(start) + 1 : parent.index(end)]
        covered = {n for top in enclosed for n in active_nodes(top)}
        if any(n in markers for n in covered) or covered & used:
            fail(start, "overlapping custom XML ranges")
        wrappers = [n for n in covered if n.tag in {W + "customXml", W + "sdt"}]
        if not wrappers:
            fail(start, "custom XML range contains no markup")
        for wrapper in wrappers:
            if wrapper.tag == W + "sdt" and len(wrapper.findall(W + "sdtContent")) != 1:
                fail(wrapper, "content control must have one content container")
        used |= covered | {start, end}
        result.append((start, end, wrappers))
    if any(n not in used for n in markers):
        fail(next(n for n in markers if n not in used), "unpaired custom XML range")
    return result


def accept(root, stats):
    for start, end, wrappers in plan(root):
        if start.tag == W + "customXmlDelRangeStart":
            for node in sorted(
                wrappers, key=lambda n: len(list(n.iterancestors())), reverse=True
            ):
                parent, at = node.getparent(), node.getparent().index(node)
                children = (
                    list(node.find(W + "sdtContent"))
                    if node.tag == W + "sdt"
                    else [n for n in node if n.tag != W + "customXmlPr"]
                )
                for child in children:
                    parent.insert(at, child)
                    at += 1
                parent.remove(node)
                stats["removed_custom_markup_wrappers"] += 1
        start.getparent().remove(start)
        end.getparent().remove(end)
        stats["accepted_custom_markup_ranges"] += 1
