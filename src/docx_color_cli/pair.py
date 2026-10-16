"""Conservative input-pair preflight, separate from insertion correspondence."""

from collections import defaultdict

from .errors import ColoringError


def validate_pair(source, accepted):
    """Check ordered story text containment without creating insertion labels.

    Projection may retain move-source copies. This linear check tolerates those
    extra copies, without accepting/removing them. Structural alignment still
    controls all coloring. A matching text projection cannot certify history.
    """
    left, right = defaultdict(list), defaultdict(list)
    for p in source:
        left[p.part].append(p.text)
    for p in accepted:
        right[p.part].append(p.text)
    for part, chunks in right.items():
        a, b = "".join(left.get(part, ())), "".join(chunks)
        if not b:
            compatible = not a
        else:
            cursor = 0
            for char in a:
                if char == b[cursor]:
                    cursor += 1
                    if cursor == len(b):
                        break
            compatible = cursor == len(b)
        if not compatible:
            raise ColoringError(
                "INVALID_DOCUMENT_PAIR",
                "Accepted text is not compatible with the tracked projection. Supply the corresponding Word-accepted copy without further edits; recalculated fields or unsupported revisions may also require review.",
            )
    return {
        "status": "PASS",
        "method": "ordered story-text containment",
        "provenance_certified": False,
    }
