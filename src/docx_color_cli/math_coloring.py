"""Exact OMML correspondence and insertion evidence; never accept math revisions.

Only insertion wrappers are transparent for comparison. Any deletion/move or
unknown payload inside a candidate equation refuses it. Accepted nodes alone
are selected; no source equation is copied into the output.
"""

from collections import Counter

from .anchors import PARA_ID, deleted_mark, exact_structural_pair
from .projection import HISTORY, M, W, revision_node

# These OMML objects permit a trailing ctrlPr in their object properties.
OBJECTS = {
    M + name: M + name + "Pr"
    for name in (
        "acc",
        "bar",
        "borderBox",
        "box",
        "d",
        "eqArr",
        "f",
        "func",
        "groupChr",
        "limLow",
        "limUpp",
        "m",
        "nary",
        "phant",
        "rad",
        "sPre",
        "sSub",
        "sSubSup",
        "sSup",
    )
}
SUPPORTED = (
    set(OBJECTS)
    | set(OBJECTS.values())
    | {
        M + name
        for name in [
            "oMath",
            "r",
            "t",
            "rPr",
            "ctrlPr",
            "e",
            "num",
            "den",
            "deg",
            "sub",
            "sup",
            "lim",
            "fName",
            "mr",
            "mcs",
            "mc",
            "mcPr",
            "count",
            "mcJc",
            "chr",
            "begChr",
            "endChr",
            "sepChr",
            "grow",
            "shp",
            "limLoc",
            "subHide",
            "supHide",
            "degHide",
            "type",
            "pos",
            "vertJc",
            "baseJc",
            "aln",
            "brk",
            "lit",
            "nor",
            "scr",
            "sty",
        ]
    }
)


def inserted(node):
    ancestors = [node, *node.iterancestors()]
    return any(n.tag == W + "ins" for n in ancestors) and not any(
        n.tag in HISTORY | {W + "del", W + "moveFrom", W + "moveTo"} for n in ancestors
    )


def description(equation):
    """Structural event stream plus original text coordinates, not rebuilt XML.

    Adjacent m:r boundaries may differ, but character math properties and every
    argument/object boundary must agree. Word formatting is target-authoritative.
    """
    positions = []

    def expanded(n):
        for c in n:
            if c.tag == W + "ins":
                yield from expanded(c)
            elif c.tag == W + "rPr":
                continue
            else:
                yield c

    for n in equation.iter():
        if any(a.tag in HISTORY or a.tag == W + "rPr" for a in n.iterancestors()):
            continue
        if revision_node(n) and n.tag != W + "ins":
            raise ValueError("math deletion/move/unknown revision")
        if not isinstance(n.tag, str) or n.tag not in SUPPORTED | {
            W + "ins",
            W + "rPr",
        }:
            raise ValueError("unsupported math payload")
    if any(
        a.tag in HISTORY | {W + "del", W + "moveFrom", W + "moveTo"}
        for a in equation.iterancestors()
    ):
        raise ValueError("equation in deleted/moved scope")

    def visit(n):
        if n.tag == M + "ctrlPr":
            return ()  # Formatting only, source provenance checked separately.
        children = list(expanded(n))
        if n.tag == M + "r":
            if any(c.tag not in {M + "rPr", M + "t"} for c in children):
                raise ValueError("complex math run")
            props = tuple(visit(c) for c in children if c.tag == M + "rPr")
            result = []
            for t in children:
                if t.tag != M + "t":
                    continue
                for i, char in enumerate(t.text or ""):
                    positions.append((t, i))
                    result.append(("math-character", props, char))
            return tuple(result)
        payload = tuple(event for c in children for event in visit(c))
        if (
            n.tag in OBJECTS.values()
            and not payload
            and not n.attrib
            and not (n.text or "").strip()
        ):
            return ()  # Absent/empty object formatting is equivalent for mapping.
        return (
            ("start", n.tag, tuple(sorted(n.attrib.items())), n.text or ""),
            *payload,
            ("end", n.tag),
        )

    return visit(equation), positions


def whole_insertion(equation, positions):
    if not positions or not all(inserted(n) for n, _ in positions):
        return False
    if inserted(equation):
        return True
    if any(
        not inserted(ctrl) and not any(inserted(n) for n in ctrl.iter(W + "rPr"))
        for ctrl in equation.iter(M + "ctrlPr")
    ):
        return False
    # All text being new does not prove the fraction bar/operator is new.
    for obj in equation.iter():
        if obj.tag not in OBJECTS:
            continue
        ctrl = obj.find(OBJECTS[obj.tag] + "/" + M + "ctrlPr")
        if not inserted(obj) and (
            ctrl is None
            or not any(inserted(n) for n in ctrl.iter() if n.tag == W + "rPr")
        ):
            return False
    return True


def inserted_controls(equation):
    count = 0
    for obj in equation.iter():
        if obj.tag not in OBJECTS:
            continue
        ctrl = obj.find(OBJECTS[obj.tag] + "/" + M + "ctrlPr")
        if (
            inserted(obj)
            or ctrl is not None
            and any(inserted(n) for n in ctrl.iter() if n.tag == W + "rPr")
        ):
            count += 1
    return count + sum(
        ctrl.getparent().tag not in OBJECTS.values()
        and (inserted(ctrl) or any(inserted(n) for n in ctrl.iter(W + "rPr")))
        for ctrl in equation.iter(M + "ctrlPr")
    )


def plan(source, accepted, records, mappings):
    by_key = {r.key: r for r in records.values()}
    by_location = {}
    for m in mappings:
        node, offset = source[m.source].locations[m.offset]
        if node.tag == M + "t" and by_key[m.origin].kind == "MATHEMATICAL":
            m.eligible = True
            by_location[node, offset] = m
    counts_a = Counter((p.part, p.context, p.node.get(PARA_ID)) for p in source)
    counts_b = Counter((p.part, p.context, p.node.get(PARA_ID)) for p in accepted)
    texts_a = Counter((p.part, p.context, p.text) for p in source)
    texts_b = Counter((p.part, p.context, p.text) for p in accepted)
    ids_b = {
        (p.part, p.context, p.node.get(PARA_ID)): j for j, p in enumerate(accepted)
    }
    text_b = {(p.part, p.context, p.text): j for j, p in enumerate(accepted)}
    controls, rows = {}, []
    for p in source:
        equations = [
            e
            for e in p.node.iter(M + "oMath")
            if next((a for a in e.iterancestors() if a.tag == W + "p"), None) is p.node
        ]
        if not equations:
            continue
        ident = (p.part, p.context, p.node.get(PARA_ID))
        text = (p.part, p.context, p.text)
        j = None
        if ident[-1] and counts_a[ident] == counts_b[ident] == 1:
            j = ids_b[ident]
        elif p.text and texts_a[text] == texts_b[text] == 1:
            candidate = text_b[text]
            if not ident[-1] or not accepted[candidate].node.get(PARA_ID):
                j = candidate
        paired = (
            j is not None
            and not deleted_mark(p)
            and exact_structural_pair(p, accepted[j])
        )
        targets = list(accepted[j].node.iter(M + "oMath")) if paired else []
        paired = paired and len(equations) == len(targets)
        coords = (
            {loc: k for k, loc in enumerate(accepted[j].locations)} if paired else {}
        )
        for ordinal, eq in enumerate(equations):
            row = {
                "part": p.part,
                "source_paragraph": p.index,
                "source_xpath": eq.getroottree().getpath(eq),
                "status": "UNSUPPORTED",
                "whole_insertion": False,
                "inserted_characters": 0,
                "inserted_controls": 0,
                "reason": "no exact paragraph/object correspondence",
            }
            rows.append(row)
            try:
                signature, positions = description(eq)
            except ValueError:
                row["reason"] = "deleted, moved or unsupported mathematical revision"
                continue
            row["inserted_characters"] = sum(inserted(n) for n, _ in positions)
            row["inserted_controls"] = inserted_controls(eq)
            whole = whole_insertion(eq, positions)
            row["whole_insertion"] = whole
            if not paired:
                continue
            target = targets[ordinal]
            try:
                other, destinations = description(target)
            except ValueError:
                continue
            if signature != other:
                row["reason"] = "OMML structure, parameters or math text differ"
                continue
            row.update(
                status="EXACT",
                reason="exact paragraph context and ordered OMML object/argument signature",
                target_paragraph=accepted[j].index,
                target_xpath=target.getroottree().getpath(target),
            )
            for loc, dest in zip(positions, destinations, strict=True):
                mapping = by_location.get(loc)
                if mapping is not None and inserted(loc[0]):
                    # Without an explicit control color, painting a partial
                    # object's first character can change an unchanged bar or
                    # operator through inheritance. Do not silently pin or
                    # recolor unchanged control properties to work around it.
                    implicit_control = any(
                        obj.tag in OBJECTS
                        and obj.find(
                            OBJECTS[obj.tag]
                            + "/"
                            + M
                            + "ctrlPr/"
                            + W
                            + "rPr/"
                            + W
                            + "color"
                        )
                        is None
                        for obj in dest[0].iterancestors()
                    )
                    if not whole and implicit_control:
                        mapping.evidence = (
                            "partial math object has implicit control color inheritance"
                        )
                        continue
                    mapping.status = "EXACT"
                    mapping.evidence = row["reason"]
                    mapping.target, mapping.target_offset = j, coords[dest]
            if whole:
                for obj in target.iter():
                    if obj.tag in OBJECTS:
                        # Creating ctrlPr changes the inheritance baseline from
                        # the first math character to paragraph properties.
                        # Retain absent containers without rendered evidence.
                        if obj.find(OBJECTS[obj.tag] + "/" + M + "ctrlPr") is not None:
                            controls[obj] = OBJECTS[obj.tag]
                    elif (
                        obj.tag == M + "ctrlPr"
                        and obj.getparent().tag not in OBJECTS.values()
                    ):
                        controls[obj] = (
                            None  # Existing argument-level control formatting.
                        )
    return controls, {
        "source_equations": len(rows),
        "accepted_equations": sum(
            len(list(p.node.iter(M + "oMath"))) for p in accepted
        ),
        "whole_inserted_equations": sum(r["whole_insertion"] for r in rows),
        "mapped_whole_inserted_equations": sum(
            r["whole_insertion"] and r["status"] == "EXACT" for r in rows
        ),
        "inserted_control_candidates": sum(r["inserted_controls"] for r in rows),
        "uncolored_inserted_controls": sum(r["inserted_controls"] for r in rows)
        - len(controls),
        "equations": rows,
        "word_visual_validation": "PENDING_WORD_VISUAL_VALIDATION",
    }
