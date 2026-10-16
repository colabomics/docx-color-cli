"""Level B: conservative retained-run identity corroboration, not gold truth.

Uses rsidR + complete run attributes/text/current non-color properties + wrapper
role, uniquely present on BOTH sides. No paragraph IDs, paragraph text anchors,
LCS, joined gaps, POC projection or POC mapping functions. Merged/split runs and
competing identities abstain. rsidR is not a cryptographic identity: agreement
is explicitly conditional algorithmic evidence, never human verification.
"""

from collections import defaultdict
from copy import deepcopy

from helpers.fidelity import M, W, characters, raw_tree, read_package


def run_inventory(roots):
    inventory = defaultdict(list)
    for part, root in roots.items():
        parents = {c: p for p in root.iter() for c in p}
        paths = {root: ()}
        for parent in root.iter():
            for i, child in enumerate(parent):
                paths[child] = (*paths[parent], i)
        for run in root.iter(W + "r"):
            stamp = run.get(W + "rsidR")
            if (
                not stamp
                or stamp == "00000000"
                or any(c.tag not in {W + "t", W + "rPr"} for c in run)
            ):
                continue
            ancestors, node = [], parents.get(run)
            while node is not None:
                ancestors.append(node)
                node = parents.get(node)
            if any(
                isinstance(n.tag, str)
                and (n.tag.endswith("Change") or n.tag in {W + "del", W + "moveFrom"})
                for n in ancestors
            ):
                continue
            text = "".join(n.text or "" for n in run.findall(W + "t"))
            if not text:
                continue
            props = run.find(W + "rPr")
            clean = deepcopy(props) if props is not None else None
            if clean is not None:
                for child in list(clean):
                    if child.tag == W + "color" or child.tag.endswith("Change"):
                        clean.remove(child)
            properties = (
                raw_tree(clean)
                if clean is not None and (len(clean) or clean.attrib or clean.text)
                else None
            )
            wrappers = tuple(
                (n.tag, tuple(sorted(n.attrib.items())))
                for n in reversed(ancestors)
                if n.tag
                in {
                    W + "hyperlink",
                    W + "fldSimple",
                    W + "footnote",
                    W + "endnote",
                    W + "sdtContent",
                    W + "txbxContent",
                }
            )
            topology = tuple(
                n.tag
                for n in reversed(ancestors)
                if n.tag in {W + "tbl", W + "tr", W + "tc"}
            )
            key = (
                part,
                tuple(sorted(run.attrib.items())),
                text,
                properties,
                wrappers,
                topology,
            )
            uncertain = any(
                n.tag == W + "moveTo" or isinstance(n.tag, str) and n.tag.startswith(M)
                for n in ancestors
            )
            for table in (n for n in ancestors if n.tag == W + "tbl"):
                if any(
                    isinstance(x.tag, str)
                    and (
                        x.tag.endswith("Change")
                        or x.tag in {W + "cellDel", W + "cellIns", W + "cellMerge"}
                        or x.tag in {W + "ins", W + "del"}
                        and parents.get(x) is not None
                        and parents[x].tag in {W + "trPr", W + "tcPr"}
                    )
                    for x in table.iter()
                ):
                    uncertain = True
            label = (
                None
                if uncertain
                else "INSERTED"
                if any(n.tag == W + "ins" for n in ancestors)
                else "UNCHANGED"
            )
            inventory[key].append((run, label, paths[run]))
    return inventory


def corroborate(tracked_path, accepted_path):
    _, source, _ = read_package(tracked_path)
    _, target, _ = read_package(accepted_path)
    a, b = run_inventory(source), run_inventory(target)
    positions = defaultdict(list)
    for coord, char in characters(target).items():
        positions[char.run].append(coord)
    labels, witnesses = {}, {}
    matched_runs = 0
    for key, candidates in a.items():
        if len(candidates) != 1 or len(b.get(key, ())) != 1:
            continue
        _, label, source_path = candidates[0]
        if label is None:
            continue
        run = b[key][0][0]
        matched_runs += 1
        for coord in positions[run]:
            labels[coord] = label
            witnesses[coord] = {
                "source_run_child_path": list(source_path),
                "method": "UNIQUE_RETAINED_RSID_RUN",
            }
    return (
        labels,
        witnesses,
        {
            "evidence_level": "B_CONDITIONAL_ALGORITHMIC_CORROBORATION",
            "independent_human_truth": False,
            "matched_unique_runs": matched_runs,
            "labeled_characters": len(labels),
            "inserted_characters": sum(x == "INSERTED" for x in labels.values()),
            "unchanged_characters": sum(x == "UNCHANGED" for x in labels.values()),
        },
    )
