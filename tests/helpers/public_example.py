"""Literal provenance for the public pair, independent of production alignment."""

from helpers.fidelity import M, W, compare, read_package, requested_color

PART = "word/document.xml"
TABLE_RANGES = [
    (23, 2),
    (24, 4),
    (25, 4),
    (27, 2),
    (29, 4),
    (31, 2),
    (32, 4),
    (33, 4),
    (36, 4),
    (37, 4),
]


def insertion_coordinates(tracked, accepted):
    """Require matching paragraph/cell order; label literal surviving w:ins only.

    This intentionally limited oracle does not resolve moves or structural
    revisions. It does not search strings or use converter mappings.
    """
    result = set()

    def text_units(p, parents):
        units = []

        def visit(n, inserted=False):
            if n.tag == W + "del" or n.tag.endswith("PrChange"):
                return
            assert n.tag not in {W + "moveFrom", W + "moveTo"}
            if n is not p and n.tag == W + "p":
                return
            inserted = inserted or n.tag == W + "ins"
            if n.tag in {W + "t", M + "t"}:
                units.extend((c, inserted) for c in n.text or "")
            elif n.tag in {W + "tab", W + "br", W + "cr"}:
                units.append(("\t" if n.tag == W + "tab" else "\n", inserted))
            for child in n:
                visit(child, inserted)

        assert not any(a.tag in {W + "ins", W + "del"} for a in ancestors(p, parents))
        visit(p)
        return units

    def ancestors(n, parents):
        while n in parents:
            n = parents[n]
            yield n

    def address(p, root, parents):
        chain = []
        for n in ancestors(p, parents):
            if n.tag == W + "tbl":
                chain.append((n.tag, list(root.iter(W + "tbl")).index(n)))
            elif n.tag in {W + "tr", W + "tc"}:
                chain.append((n.tag, list(parents[n].iterfind(n.tag)).index(n)))
        return tuple(chain)

    left, right = list(tracked.iter(W + "p")), list(accepted.iter(W + "p"))
    assert len(left) == len(right)
    lp = {c: p for p in tracked.iter() for c in p}
    rp = {c: p for p in accepted.iter() for c in p}
    for pi, (a, b) in enumerate(zip(left, right, strict=True)):
        assert address(a, tracked, lp) == address(b, accepted, rp)
        source, target = text_units(a, lp), text_units(b, rp)
        assert "".join(c for c, _ in source) == "".join(c for c, _ in target)
        result.update(
            (PART, pi, i) for i, (_, inserted) in enumerate(source) if inserted
        )
    return result


def verify_public_example(tracked, accepted, output, report):
    for field in ("publication_status", "coloring_status", "overall_status"):
        assert report[field] == "SUCCESS", field
    assert report["publication"]["docx_published"] is True
    assert report["coloring"]["characters_colored"] == 3075
    assert all(
        report["completeness"][k] == 0
        for k in (
            "eligible_characters_uncolored",
            "ordinary_characters_uncolored",
            "other_projected_candidates_uncolored",
        )
    )
    source, reference = read_package(tracked)[1], read_package(accepted)[1]
    truth = insertion_coordinates(source[PART], reference[PART])
    assert len(truth) == 3075
    checked, before, after = compare(accepted, output, allowed=truth)
    assert checked["overall"] == "PASS", checked
    assert all(after[k].color == requested_color("FF0000") for k in truth)
    assert all(after[k].color == before[k].color for k in before if k not in truth)
    output_root = read_package(output)[1][PART]
    for tag in (W + "tbl", M + "oMath"):
        assert (
            len(list(output_root.iter(tag))) == len(list(reference[PART].iter(tag))) > 0
        )
    for ordinal, length in TABLE_RANGES:
        for offset in range(length):
            key = PART, ordinal - 1, offset
            assert key in truth and after[key].color == requested_color("FF0000")
    assert sum(length for _, length in TABLE_RANGES) == 34
    return checked
