"""Read-only structural evidence for text correspondence, never OOXML acceptance."""

import re
from collections import Counter, defaultdict
from pathlib import PurePosixPath

from .projection import HISTORY, M, W, active, revision_node

PARA_ID = "{http://schemas.microsoft.com/office/word/2010/wordml}paraId"
SOFT_REASONS = {"complex", "mathematical", "structural paragraph boundary"}
MOVE_MARKERS = {
    W + side + "Range" + edge
    for side in ("moveFrom", "moveTo")
    for edge in ("Start", "End")
}


def opaque_inline(n):
    """Zero projected text, not an attempt to equate two images' contents.

    The accepted object stays authoritative. Only its type and text boundary
    participate in correspondence; nested text stories are never flattened.
    """
    return n.tag in {W + "drawing", W + "pict"} and not any(
        c.tag
        in {
            W + "p",
            W + "tbl",
            W + "t",
            M + "t",
            W + "tab",
            W + "br",
            W + "cr",
            W + "fldChar",
            W + "instrText",
            W + "delInstrText",
        }
        or revision_node(c)
        for c in n.iter()
    )


def closed_deletions(p):
    """A deleted container may not leave a field or structure open outside it."""

    def check(containers):
        stack = []

        def visit(n):
            if n.tag in HISTORY or n.tag == W + "rPr" or opaque_inline(n):
                return True
            if n.tag == W + "fldChar":
                kind = n.get(W + "fldCharType")
                if kind == "begin":
                    stack.append(False)
                elif kind == "separate" and stack and not stack[-1]:
                    stack[-1] = True
                elif kind == "end" and stack:
                    stack.pop()
                else:
                    return False
            elif n.tag in {W + "instrText", W + "delInstrText"}:
                if not stack or stack[-1]:
                    return False
            elif n.tag not in {
                W + s
                for s in (
                    "del",
                    "ins",
                    "r",
                    "t",
                    "delText",
                    "tab",
                    "br",
                    "cr",
                    "lastRenderedPageBreak",
                )
            }:
                return False
            return all(visit(c) for c in n)

        return all(visit(container) for container in containers) and not stack

    if all(
        check([n])
        for n in active(p.node)
        if n.tag == W + "del" and n.getparent().tag not in {W + "rPr", W + "pPr"}
    ):
        return True

    # Word can split one wholly deleted field across adjacent revision authors
    # and w:ins/w:del wrappers in an otherwise empty paragraph. Validate the
    # combined deleted payload only when NOTHING survives in that paragraph.
    # Never balance a deleted field against live content or another paragraph.
    containers = []

    def deleted_only(n):
        if n.tag in HISTORY or n.tag == W + "pPr":
            return True
        if n.tag == W + "del":
            containers.append(n)
            return True
        if n is p.node or n.tag == W + "ins":
            return all(deleted_only(c) for c in n)
        return False

    return (
        not p.text and deleted_only(p.node) and bool(containers) and check(containers)
    )


def usable_projection(p, *, allow_moves=False):
    allowed = SOFT_REASONS | {"complex deletion"}
    if allow_moves:
        # MOVED insertions themselves remain non-eligible and masked. Their
        # presence must not suppress a separately proven insertion outside.
        allowed |= {"move revision", "revision range", "unsupported revision", "moved"}
    return p.unresolved <= allowed and (
        "complex deletion" not in p.unresolved or closed_deletions(p)
    )


def protected_move_offsets(source):
    """Read-only exclusion masks; bad endpoints quarantine the affected part.

    Do not infer a move's accepted text. Always protect source ranges and move
    wrappers. A uniquely paired destination *container* does not turn a separate
    ordinary w:ins into moved content (ISO 29500, moveToRangeStart vs moveTo).
    Unknown/unpaired/overlapping destination containers remain quarantined.
    """
    groups, result = defaultdict(list), {}
    for i, p in enumerate(source):
        if p.unresolved & {"move revision", "revision range"}:
            groups[p.part].append((i, p))
    for group in groups.values():
        nodes = list(active(group[0][1].node.getroottree().getroot()))
        positions = {n: i for i, n in enumerate(nodes)}
        pairs = defaultdict(lambda: {"Start": [], "End": []})
        valid = True
        for n in nodes:
            if not revision_node(n) or "Range" not in n.tag:
                continue
            suffix = "Start" if n.tag.endswith("Start") else "End"
            if not n.tag.endswith(suffix) or n.get(W + "id") is None:
                valid = False
                break
            pairs[n.tag.removesuffix(suffix), n.get(W + "id")][suffix].append(
                positions[n]
            )
        intervals = []
        for (kind, _), pair in pairs.items():
            if (
                len(pair["Start"]) != 1
                or len(pair["End"]) != 1
                or pair["Start"][0] >= pair["End"][0]
            ):
                valid = False
                break
            lo, hi = pair["Start"][0], pair["End"][0]
            intervals.append((kind, lo, hi, nodes[lo].get(W + "name")))
        source_names = Counter(
            name for kind, _, _, name in intervals if kind == W + "moveFromRange"
        )
        target_names = Counter(
            name for kind, _, _, name in intervals if kind == W + "moveToRange"
        )
        quarantined = []
        for kind, lo, hi, name in intervals:
            paired_destination = (
                kind == W + "moveToRange"
                and name
                and source_names[name] == target_names[name] == 1
                and not any(
                    k == kind
                    and other_lo != lo
                    and max(lo, other_lo) < min(hi, other_hi)
                    for k, other_lo, other_hi, _ in intervals
                )
            )
            if not paired_destination:
                quarantined.append((lo, hi))
        protected = {
            n
            for n, pos in positions.items()
            if any(lo <= pos <= hi for lo, hi in quarantined)
        }
        for i, p in group:
            result[i] = {
                j
                for j, (n, _) in enumerate(p.locations)
                if not valid
                or n not in positions
                or n in protected
                or any(
                    a.tag in {W + "moveFrom", W + "moveTo"} for a in n.iterancestors()
                )
            }
    return result


def deleted_mark(p):
    return p.node.find(W + "pPr/" + W + "rPr/" + W + "del") is not None


def boundary_signature(p, *, allow_moves=False):
    """Exact offsets of field, hyperlink and math boundaries in projected text.

    Unknown objects, unbalanced fields and nested stories refuse this extra path.
    Property trees carry no displayed text. Math remains opaque: record its text
    extent, not its expression semantics or acceptance behavior.
    """
    events, stack = [], []
    offset = 0
    valid = True
    allowed = {
        W + n
        for n in (
            "p",
            "r",
            "t",
            "ins",
            "tab",
            "br",
            "cr",
            "hyperlink",
            "fldSimple",
            "fldChar",
            "instrText",
            "bookmarkStart",
            "bookmarkEnd",
            "lastRenderedPageBreak",
            "proofErr",
        )
    }

    def visit(n):
        nonlocal offset, valid
        if n.tag in HISTORY or n.tag in {W + "del", W + "pPr", W + "rPr", M + "ctrlPr"}:
            return
        if n.tag in {W + "delText", W + "delInstrText"}:
            return
        if allow_moves and n.tag in MOVE_MARKERS:
            return
        if allow_moves and n.tag == W + "moveTo":
            for child in n:
                visit(child)
            return
        if opaque_inline(n):
            events.append(("opaque-inline", n.tag, offset))
            return
        if n.tag == W + "p" and n is not p.node:
            valid = False
            return
        if not isinstance(n.tag, str) or (
            n.tag not in allowed and not n.tag.startswith(M)
        ):
            valid = False
            return
        wrapper = n.tag in {W + "hyperlink", W + "fldSimple", M + "oMath"}
        if wrapper:
            events.append(("start", n.tag, offset, tuple(sorted(n.attrib.items()))))
        if n.tag == W + "fldChar":
            kind = n.get(W + "fldCharType")
            events.append(("field", kind, offset))
            if kind == "begin":
                stack.append(False)
            elif kind == "separate" and stack and not stack[-1]:
                stack[-1] = True
            elif kind == "end" and stack:
                stack.pop()
            else:
                valid = False
        if n.tag == W + "instrText":
            events.append(("instruction", offset, n.text or ""))
        if n.tag in {W + "t", M + "t"}:
            offset += len(n.text or "")
        elif n.tag in {W + "tab", W + "br", W + "cr"}:
            events.append(("control", n.tag, offset))
            offset += 1
        for child in n:
            visit(child)
        if wrapper:
            events.append(("end", n.tag, offset))

    visit(p.node)
    return tuple(events) if valid and not stack and offset == len(p.text) else None


def exact_structural_pair(a, b, *, allow_moves=False):
    if not usable_projection(a, allow_moves=allow_moves) or a.text != b.text:
        return False
    signature = boundary_signature(a, allow_moves=allow_moves)
    return signature is not None and signature == boundary_signature(b)


def equivalent_hyperlink_field(a, b, accepted_xml):
    """One closed HYPERLINK field vs one external hyperlink, read-only.

    Called only for a unique, matching paragraph ID and identical context.
    Require the complete displayed text, exact field/result boundaries and
    literal destination URI to agree. No switches, nested fields or URI
    normalization. The accepted hyperlink/relationship is never rewritten.
    """
    if (
        accepted_xml is None
        or (a.part, a.context) != (b.part, b.context)
        or a.text != b.text
        or deleted_mark(a)
        or a.unresolved - {"complex", "complex deletion"}
        or not usable_projection(a)
    ):
        return False
    left, right = boundary_signature(a), boundary_signature(b)
    if left is None or right is None or len(left) != 4 or len(right) != 2:
        return False
    if (
        tuple(e[0] for e in left) != ("field", "instruction", "field", "field")
        or (left[0][1], left[2][1], left[3][1]) != ("begin", "separate", "end")
        or [e[:2] for e in right]
        != [("start", W + "hyperlink"), ("end", W + "hyperlink")]
    ):
        return False
    start, end = right[0][2], right[1][2]
    if not (left[0][2] == left[1][1] == left[2][2] == start < end == left[3][2]):
        return False
    match = re.fullmatch(r'\s*HYPERLINK\s+"([^"\r\n]+)"\s*', left[1][2])
    if match is None:
        return False
    uri = match.group(1)
    if not uri.startswith(("https://", "http://")) or any(c.isspace() for c in uri):
        return False
    markers = [
        n
        for n in active(a.node)
        if n.tag == W + "fldChar"
        and not any(
            p.tag in HISTORY | {W + "del", W + "rPr", W + "pPr"}
            for p in n.iterancestors()
        )
    ]
    if len(markers) != 3 or any(
        len(n) or set(n.attrib) != {W + "fldCharType"} for n in markers
    ):
        return False
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    attrs = dict(right[0][3])
    rid = attrs.get("{" + rel_ns + "}id")
    if not rid or set(attrs) - {"{" + rel_ns + "}id", W + "history"}:
        return False
    if attrs.get(W + "history", "1") not in {"0", "1", "true", "false"}:
        return False
    part = PurePosixPath(b.part)
    rels = accepted_xml.get(str(part.parent / "_rels" / (part.name + ".rels")))
    if rels is None:
        return False
    matches = [n for n in rels if n.get("Id") == rid]
    return len(matches) == 1 and (
        matches[0].tag
        == "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"
        and matches[0].get("Type") == rel_ns + "/hyperlink"
        and matches[0].get("TargetMode") == "External"
        and matches[0].get("Target") == uri
    )


def region_signature(paragraphs, *, allow_moves=False):
    """Retain every object boundary at its absolute offset in a bounded region."""
    result, offset = [], 0
    for p in paragraphs:
        signature = boundary_signature(p, allow_moves=allow_moves)
        if signature is None:
            return None
        for event in signature:
            index = 1 if event[0] == "instruction" else 2
            shifted = list(event)
            shifted[index] += offset
            result.append(tuple(shifted))
        offset += len(p.text)
    return tuple(result)


def plain_subsequence_chain(source, accepted):
    """Bound one complete paragraph chain; never flatten an object or a cell.

    MoveFrom text remains in the source sequence for alignment, not acceptance.
    Non-text boundaries forbid this specialized path. Existing deletion
    projection must be locally closed, as for exact correspondence.
    """
    if not source or len(source) > 32 or sum(len(p.text) for p in source) > 16_000:
        return False
    if deleted_mark(source[-1]) or any(not deleted_mark(p) for p in source[:-1]):
        return False
    if any((p.part, p.context) != (accepted.part, accepted.context) for p in source):
        return False
    if not all(usable_projection(p, allow_moves=True) for p in source):
        return False

    def plain(n, root):
        if n.tag in HISTORY or n.tag in {W + "del", W + "pPr", W + "rPr"}:
            return True
        if n.tag == W + "p" and n is not root:
            return False
        allowed = {
            W + s for s in ("p", "r", "t", "delText", "ins", "moveFrom", "moveTo")
        } | MOVE_MARKERS
        return n.tag in allowed and all(plain(c, root) for c in n)

    return all(plain(p.node, p.node) for p in [*source, accepted])


def joined_gap(source, accepted, *, allow_moves=False):
    """A bounded exact stream with explicitly deleted source paragraph marks.

    No fuzzy matching across paragraph boundaries. Preserve every surviving
    delimiter and require identical text; no table/move/complex interpretation.
    """
    if not source or not accepted or max(len(source), len(accepted)) > 32:
        return False
    if not all(usable_projection(p, allow_moves=allow_moves) for p in source):
        return False
    if deleted_mark(source[-1]) or sum(len(p.text) for p in source) > 16_000:
        return False
    signature = region_signature(source, allow_moves=allow_moves)
    if signature is None or signature != region_signature(accepted):
        return False
    if "".join(p.text for p in source) != "".join(p.text for p in accepted):
        return False
    boundaries, at = [], 0
    for p in source[:-1]:
        at += len(p.text)
        if not deleted_mark(p):
            boundaries.append(at)
    target_boundaries, at = [], 0
    for p in accepted[:-1]:
        at += len(p.text)
        target_boundaries.append(at)
    return boundaries == target_boundaries
