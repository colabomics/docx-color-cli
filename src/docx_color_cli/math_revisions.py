"""Accept control insertions and conservatively remove deleted math objects.

A deleted control alone never proves its arguments can be discarded. This policy
requires every run and every nested object's control to be independently deleted.
"""

from lxml import etree

from .revisions import M, W, active_nodes, fail

OBJECTS = {
    "d": {"e"},
    "f": {"num", "den"},
    "sSub": {"e", "sub"},
    "sSup": {"e", "sup"},
    "nary": {"sub", "sup", "e"},
    "func": {"fName", "e"},
    "eqArr": {"e"},
    "acc": {"e"},
    "bar": {"e"},
    "borderBox": {"e"},
    "box": {"e"},
    "groupChr": {"e"},
    "limLow": {"e", "lim"},
    "limUpp": {"e", "lim"},
    "phant": {"e"},
    "rad": {"deg", "e"},
    "sPre": {"e", "sub", "sup"},
    "sSubSup": {"e", "sub", "sup"},
    "m": {"mr"},
}


def fully_deleted(node):
    """Read-only proof over known carriers; unknown/non-text payload is not empty."""
    name = etree.QName(node).localname
    if node.tag != M + name or name not in OBJECTS:
        return False
    props = node.find(M + name + "Pr")
    control = props.find(M + "ctrlPr") if props is not None else None
    deletion = control_deletion(control)
    if deletion is None:
        return False
    # Preserve bookmarks, fields, drawings, relationships and unknown extensions,
    # even if a text-only inspection would incorrectly regard them as empty.
    for n in active_nodes(node):
        if not isinstance(n.tag, str):
            return False
        if any(
            etree.QName(a).namespace
            == "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
            for a in n.attrib
        ):
            return False
        if n.tag in {W + "rPr", M + "rPr"} or any(
            a.tag in {W + "rPr", M + "rPr"} for a in n.iterancestors()
        ):
            continue
        if n.tag.startswith(W) and n.tag not in {W + "ins", W + "del"}:
            return False

    def empty_argument(arg):
        for child in arg:
            if arg.tag == M + "mr" and child.tag == M + "e":
                if not empty_argument(child):
                    return False
            elif child.tag == M + "r":
                payload = next(
                    (c for c in child if c.tag in {W + "ins", W + "del"}), None
                )
                if payload is None or any(
                    c is not payload and c.tag not in {W + "rPr", M + "rPr"}
                    for c in child
                ):
                    return False
                while payload.tag == W + "ins" and len(payload) == 1:
                    payload = payload[0]
                if payload.tag != W + "del":
                    return False
            elif not fully_deleted(child):
                return False
        return True

    return all(
        c is props or c.tag in {M + a for a in OBJECTS[name]} and empty_argument(c)
        for c in node
    )


def deleted_objects(root):
    """Validate control revisions and return only objects eligible for removal."""
    result = set()
    for control in active_nodes(root):
        if control.tag != M + "ctrlPr":
            continue
        if not any(c.tag in {W + "ins", W + "del"} for c in control):
            continue
        if control.find(W + "ins") is not None and control_deletion(control) is None:
            validate_insertion(control)
            continue
        props = control.getparent()
        obj = props.getparent() if props is not None else None
        if obj is None or props.tag != obj.tag + "Pr" or not fully_deleted(obj):
            fail(
                control,
                "mathematical control deletion has surviving or unsupported content",
            )
        result.add(obj)
    return result


CONTROL_OBJECTS = {
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
}
CONTROL_ARGUMENTS = {"deg", "den", "e", "fName", "lim", "num", "sub", "sup"}


def validate_insertion(control):
    """A control insertion owns control formatting, not its argument runs."""
    parent = control.getparent()
    object_property = (
        parent is not None
        and parent.tag in {M + n + "Pr" for n in CONTROL_OBJECTS}
        and parent.getparent() is not None
        and parent.getparent().tag == parent.tag[:-2]
    )
    argument_property = parent is not None and parent.tag in {
        M + n for n in CONTROL_ARGUMENTS
    }
    if not (object_property or argument_property):
        fail(control, "unsupported mathematical control insertion location")
    if len(control) != 1 or control[0].tag != W + "ins":
        fail(control, "conflicting mathematical control properties")
    insertion = control[0]
    if len(insertion) > 1 or any(c.tag != W + "rPr" for c in insertion):
        fail(control, "unsupported mathematical control insertion payload")
    return insertion


def inserted_controls(root):
    controls = []
    for node in active_nodes(root):
        if (
            node.tag == M + "ctrlPr"
            and node.find(W + "ins") is not None
            and control_deletion(node) is None
        ):
            validate_insertion(node)
            controls.append(node)
    return controls


def control_deletion(control):
    """Word also writes a control inserted and subsequently deleted as ins/del."""
    if control is None or len(control) != 1:
        return None
    mark = control[0]
    if mark.tag == W + "ins" and len(mark) == 1:
        mark = mark[0]
    if (
        mark.tag == W + "del"
        and len(mark) <= 1
        and all(c.tag == W + "rPr" for c in mark)
    ):
        return mark
    return None


def emptied_containers(root, removed_objects):
    """Predict only containers made empty by supported deletion acceptance.

    Pre-existing empty containers/arguments, whitespace runs and unknown nodes are
    not deletion evidence. Display properties disappear only with their container.
    """
    result = set()

    def vanishes(node):
        if node in removed_objects or node in result or node.tag == W + "del":
            return True
        if node.tag == W + "ins":
            return bool(len(node)) and all(vanishes(c) for c in node)
        if node.tag == M + "r":
            mark = next((c for c in node if c.tag in {W + "ins", W + "del"}), None)
            while mark is not None:
                if mark.tag == W + "del":
                    return True
                mark = next((c for c in mark if c.tag in {W + "ins", W + "del"}), None)
        return False

    for node in reversed(list(active_nodes(root))):
        if (
            node.tag not in {M + "oMath", M + "oMathPara"}
            or node.attrib
            or (node.text or "").strip()
        ):
            continue
        props = node.find(M + "oMathParaPr")
        if props is not None and (
            props.attrib
            or any(
                c.tag != M + "jc" or len(c) or set(c.attrib) - {M + "val"}
                for c in props
            )
        ):
            continue
        payload = [c for c in node if c.tag != M + "oMathParaPr"]
        if payload and all(vanishes(c) and not (c.tail or "").strip() for c in payload):
            result.add(node)
    return result
