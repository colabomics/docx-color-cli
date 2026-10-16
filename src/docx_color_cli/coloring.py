"""Color only mapped text; split plain text runs without touching complex runs."""

from collections import defaultdict
from copy import deepcopy

from lxml import etree

from .projection import XML_SPACE, M, W

PREDECESSORS = {
    W + n
    for n in (
        "rStyle",
        "rFonts",
        "b",
        "bCs",
        "i",
        "iCs",
        "caps",
        "smallCaps",
        "strike",
        "dStrike",
        "outline",
        "shadow",
        "emboss",
        "imprint",
        "noProof",
        "snapToGrid",
        "vanish",
        "webHidden",
    )
}


def simple_run(run):
    return (
        run is not None
        and run.tag == W + "r"
        and len(run.findall(W + "rPr")) <= 1
        and all(
            c.tag in {W + "rPr", W + "t"} and not (c.tail or "").strip() for c in run
        )
        and all(not len(t) for t in run.findall(W + "t"))
    )


def simple_math_run(run):
    return (
        run is not None
        and run.tag == M + "r"
        and len(run.findall(W + "rPr")) <= 1
        and len(run.findall(M + "rPr")) <= 1
        and bool(run.findall(M + "t"))
        and all(c.tag in {M + "rPr", W + "rPr", M + "t"} for c in run)
        and all(not len(t) for t in run.findall(M + "t"))
    )


def page_break_run(run):
    """Only text and empty rendered-page markers; no fields or other objects."""
    return (
        run is not None
        and run.tag == W + "r"
        and not (run.text or "").strip()
        and len(run.findall(W + "rPr")) <= 1
        and bool(run.findall(W + "lastRenderedPageBreak"))
        and all(
            c.tag in {W + "rPr", W + "t", W + "lastRenderedPageBreak"}
            and not (c.tail or "").strip()
            for c in run
        )
        and all(t.text and not len(t) for t in run.findall(W + "t"))
        and all(
            not len(n) and not n.text for n in run.findall(W + "lastRenderedPageBreak")
        )
    )


def color_page_break_run(run, selected, rgb):
    """Preserve each marker at its exact text boundary with its OLD properties."""
    pieces = []
    props = run.find(W + "rPr")
    for node in run:
        if node.tag == W + "rPr":
            continue
        text = node.text or ""
        flags = [i in selected.get(node, ()) for i in range(len(text))]
        boundaries = (
            [0]
            + [i for i in range(1, len(flags)) if flags[i] != flags[i - 1]]
            + [len(text)]
        )
        segments = (
            [(0, 0)]
            if node.tag == W + "lastRenderedPageBreak"
            else zip(boundaries, boundaries[1:], strict=False)
        )
        for start, end in segments:
            piece = etree.Element(run.tag, dict(run.attrib), nsmap=run.nsmap)
            if props is not None:
                piece.append(deepcopy(props))
            payload = deepcopy(node)
            if node.tag == W + "t":
                payload.text = text[start:end]
                if payload.text[:1].isspace() or payload.text[-1:].isspace():
                    payload.set(XML_SPACE, "preserve")
            piece.append(payload)
            if node.tag == W + "t" and flags[start]:
                paint(piece, rgb)
            pieces.append(piece)
    parent, at = run.getparent(), run.getparent().index(run)
    for i, piece in enumerate(pieces):
        parent.insert(at + i, piece)
    pieces[-1].tail = run.tail
    parent.remove(run)


def paint(run, rgb):
    props = run.find(W + "rPr")
    if props is None:
        props = etree.Element(W + "rPr")
        run.insert(
            1 if run.tag == M + "r" and run.find(M + "rPr") is not None else 0, props
        )
    for old in list(props.findall(W + "color")):
        props.remove(old)
    color = etree.Element(W + "color", {W + "val": rgb})
    props.insert(
        max((i + 1 for i, c in enumerate(props) if c.tag in PREDECESSORS), default=0),
        color,
    )


def prepare(mappings, accepted):
    selected = defaultdict(set)
    claims = defaultdict(list)
    for mapping in mappings:
        if mapping.status not in {"EXACT", "ALIGNED"}:
            continue
        p = accepted[mapping.target]
        node, offset = p.locations[mapping.target_offset]
        if not (
            node.tag == W + "t"
            and (simple_run(node.getparent()) or page_break_run(node.getparent()))
            or node.tag == M + "t"
            and simple_math_run(node.getparent())
        ):
            mapping.status = "UNSUPPORTED"
            mapping.evidence = "accepted run contains a non-text object or instruction"
            continue
        claims[node, offset].append(mapping)
    # Avoid changing OMML run structure: mixed accepted math runs are a stated
    # unsupported case, not permission to paint their unchanged characters.
    math_runs = {n.getparent() for n, _ in claims if n.tag == M + "t"}
    for run in math_runs:
        positions = [
            (t, i) for t in run.findall(M + "t") for i in range(len(t.text or ""))
        ]
        if any(len(claims.get(pos, ())) != 1 for pos in positions):
            for pos in positions:
                for mapping in claims.pop(pos, ()):
                    mapping.status = "UNSUPPORTED"
                    mapping.evidence = (
                        "partial accepted math run would require OMML run splitting"
                    )
    for (node, offset), owners in claims.items():
        if len(owners) != 1:
            for mapping in owners:
                mapping.status = "AMBIGUOUS"
                mapping.evidence = (
                    "multiple insertion origins claim one accepted character"
                )
        else:
            selected[node].add(offset)
    return selected


def color(selected, rgb, math_controls=None):
    runs = {n.getparent() for n in selected}
    paragraphs = set()
    changed_parts = set()
    split_runs = 0
    marker_runs = 0
    math_runs = 0
    for run in runs:
        paragraphs.add(next((a for a in run.iterancestors() if a.tag == W + "p"), None))
        changed_parts.add(run.getroottree().getroot())
        if run.tag == M + "r":
            paint(run, rgb)
            math_runs += 1
            continue
        if page_break_run(run):
            color_page_break_run(run, selected, rgb)
            split_runs += 1
            marker_runs += 1
            continue
        nodes = run.findall(W + "t")
        flags = [
            i in selected.get(n, ()) for n in nodes for i in range(len(n.text or ""))
        ]
        if all(flags):
            paint(run, rgb)
            continue
        split_runs += 1
        boundaries = (
            [0]
            + [i for i in range(1, len(flags)) if flags[i] != flags[i - 1]]
            + [len(flags)]
        )
        parent, at = run.getparent(), run.getparent().index(run)
        props = run.find(W + "rPr")
        for start, end in zip(boundaries, boundaries[1:], strict=False):
            piece = etree.Element(run.tag, dict(run.attrib), nsmap=run.nsmap)
            if props is not None:
                piece.append(deepcopy(props))
            position = 0
            for node in nodes:
                text = node.text or ""
                left, right = max(start, position), min(end, position + len(text))
                if left < right:
                    child = deepcopy(node)
                    child.text = text[left - position : right - position]
                    if child.text[:1].isspace() or child.text[-1:].isspace():
                        child.set(XML_SPACE, "preserve")
                    piece.append(child)
                position += len(text)
            if flags[start]:
                paint(piece, rgb)
            parent.insert(at, piece)
            at += 1
        parent[at - 1].tail = run.tail
        parent.remove(run)
    for obj, prop_tag in (math_controls or {}).items():
        if prop_tag is None:
            paint(obj, rgb)
            changed_parts.add(obj.getroottree().getroot())
            continue
        props = obj.find(prop_tag)
        if props is None:
            raise ValueError("Missing accepted math control properties")
        ctrl = props.find(M + "ctrlPr")
        if ctrl is None:
            raise ValueError("Missing accepted math control container")
        paint(ctrl, rgb)
        changed_parts.add(obj.getroottree().getroot())
    return {
        "runs_split": split_runs,
        "page_break_runs_split": marker_runs,
        "paragraphs_affected": len(paragraphs - {None}),
        "characters_colored": sum(map(len, selected.values())),
        "math_runs_colored": math_runs,
        "math_controls_colored": len(math_controls or {}),
    }, changed_parts
