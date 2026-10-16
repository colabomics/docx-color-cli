"""Conditional Level B evidence from literal whole-equation XML payloads.

Independent stdlib implementation: no production extractor, paragraph alignment,
math signature or painter imports. It retains every run boundary, parameter
and formatting property. Only insertion wrappers are transparent for equality.
Deleted/moved/history-containing equations abstain. This is NOT human truth.
"""

from collections import defaultdict

from helpers.fidelity import M, W, characters, read_package


def corroborate_math(tracked, accepted):
    _, a, _ = read_package(tracked)
    _, b, _ = read_package(accepted)

    def inventory(roots, source):
        result = defaultdict(list)
        for part, root in roots.items():
            parents = {c: n for n in root.iter() for c in n}

            def lineage(n, parents=parents):
                while n is not None:
                    yield n
                    n = parents.get(n)

            def inserted(n):
                return any(x.tag == W + "ins" for x in lineage(n))

            def payload(n):
                children = tuple(v for c in n for v in payload(c))
                if n.tag == W + "ins":
                    return children
                return (
                    (
                        n.tag,
                        tuple(sorted(n.attrib.items())),
                        n.text or "",
                        children,
                        n.tail or "",
                    ),
                )

            for ordinal, eq in enumerate(root.iter(M + "oMath")):
                nodes = list(eq.iter()) + list(lineage(eq))
                if any(
                    n.tag in {W + "del", W + "moveTo", W + "moveFrom"}
                    or isinstance(n.tag, str)
                    and n.tag.endswith("Change")
                    for n in nodes
                ):
                    continue
                texts = list(eq.iter(M + "t"))
                controls = list(eq.iter(M + "ctrlPr"))
                whole = (
                    bool(texts)
                    and all(inserted(n) for n in texts)
                    and all(
                        inserted(c) or any(inserted(n) for n in c.iter(W + "rPr"))
                        for c in controls
                    )
                )
                # This corroborator deliberately requires explicit controls in
                # complex source formulas; it never infers their provenance.
                if source and any(
                    n.tag
                    in {
                        M + "f",
                        M + "nary",
                        M + "rad",
                        M + "d",
                        M + "acc",
                        M + "sSub",
                        M + "sSup",
                        M + "sSubSup",
                        M + "m",
                    }
                    and n.find(n.tag + "Pr/" + M + "ctrlPr") is None
                    and not inserted(n)
                    for n in eq.iter()
                ):
                    whole = False
                result[part, payload(eq)].append((eq, ordinal, whole))
        return result

    sources, targets = inventory(a, True), inventory(b, False)
    coords = defaultdict(list)
    for k, char in characters(b).items():
        coords[char.node].append(k)
    labels, equations = {}, []
    for key, matches in targets.items():
        origins = sources.get(key, [])
        if (
            len(origins) != len(matches)
            or not origins
            or not all(whole for _, _, whole in origins)
        ):
            continue
        for eq, ordinal, _ in matches:
            for t in eq.iter(M + "t"):
                labels.update((k, "INSERTED") for k in coords[t])
            equations.append(
                {
                    "part": key[0],
                    "accepted_equation_ordinal": ordinal,
                    "characters": sum(len(t.text or "") for t in eq.iter(M + "t")),
                    "explicit_controls": len(list(eq.iter(M + "ctrlPr"))),
                }
            )
    return labels, {
        "evidence": "B_CONDITIONAL_LITERAL_EQUATION_XML",
        "independent_human_truth": False,
        "labeled_inserted_characters": len(labels),
        "corroborated_whole_equations": len(equations),
        "equations": equations,
    }
