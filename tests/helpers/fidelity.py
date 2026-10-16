"""Independent stdlib XML/ZIP comparison and observed-color accuracy metrics.

No POC extractor, paragraph projector, alignment, painter or validator is used.
The comparison normalizes a DOM into single-character plain runs; every other
element remains structural. Color authorization is a separate, explicit result.
"""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
SPACE = "{http://www.w3.org/XML/1998/namespace}space"
TEXT = {W + "t", M + "t"}
CONTROLS = {W + "tab": "\t", W + "br": "\n", W + "cr": "\n"}


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def parse(data):
    if b"<!DOCTYPE" in data.upper():
        raise ValueError("DTD_NOT_ALLOWED")
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True))
    return ET.fromstring(data, parser=parser)


def read_package(path):
    with ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or archive.testzip() is not None:
            raise ValueError("INVALID_ZIP_MEMBERS_OR_CRC")
        data = {name: archive.read(name) for name in names}
        roots = {
            name: parse(raw)
            for name, raw in data.items()
            if name.endswith((".xml", ".rels"))
        }
        if (
            not {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}
            <= data.keys()
        ):
            raise ValueError("MISSING_REQUIRED_PART")
        return data, roots, archive.comment


def raw_tree(node):
    tag = node.tag if isinstance(node.tag, str) else str(node.tag)
    return (
        tag,
        tuple(sorted(node.attrib.items())),
        node.text or "",
        tuple((raw_tree(c), c.tail or "") for c in node),
    )


def color_of(run):
    if run is None or run.tag not in {W + "r", M + "r", M + "ctrlPr"}:
        return ()
    return tuple(
        raw_tree(c)
        for props in run.findall(W + "rPr")
        for c in props.findall(W + "color")
    )


def requested_color(rgb):
    return ((W + "color", ((W + "val", rgb.upper()),), "", ()),)


MATH_OBJECT_NAMES = [
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
]
MATH_OBJECTS = {M + s for s in MATH_OBJECT_NAMES}
MATH_OBJECT_PROPS = {M + s + "Pr" for s in MATH_OBJECT_NAMES}


def math_form(node, parent_tag=None):
    """Exact OMML tree except direct font color on runs/control properties.

    Math runs are NOT atomized: splitting or changing their properties fails.
    A new empty w:rPr after removing its only color has no residual properties.
    ctrlPr and object-property containers remain exact, including their presence:
    absent and explicit control formatting can have different inheritance.
    Object arguments, parameters, ordering and all other attributes stay exact.
    """
    children = []
    color_props = node.tag == W + "rPr" and parent_tag in {M + "r", M + "ctrlPr"}
    for c in node:
        if color_props and c.tag == W + "color":
            continue
        value = math_form(c, node.tag)
        if value is not None:
            children.append((value, c.tail or ""))
    if (
        not node.attrib
        and not (node.text or "").strip()
        and not children
        and color_props
    ):
        return None
    return (
        node.tag,
        tuple(sorted(node.attrib.items())),
        node.text or "",
        tuple(children),
    )


def math_control_colors(roots):
    """Coordinates count objects, independent of optional formatting wrappers."""
    result = {}
    for part, root in roots.items():
        for ei, eq in enumerate(root.iter(M + "oMath")):
            parents = {c: n for n in eq.iter() for c in n}
            objects = [
                n
                for n in eq.iter()
                if n.tag in MATH_OBJECTS
                or n.tag == M + "ctrlPr"
                and parents[n].tag not in MATH_OBJECT_PROPS
            ]
            for oi, obj in enumerate(objects):
                ctrl = (
                    obj
                    if obj.tag == M + "ctrlPr"
                    else obj.find(obj.tag + "Pr/" + M + "ctrlPr")
                )
                result[part, ei, oi] = color_of(ctrl)
    return result


def normal_form(node):
    """A tree, rather than the POC's mapping-conditioned expected event stream.

    Only pure text runs are atomized. Direct font color is removed there and
    checked separately. xml:space changes are accepted only when character
    whitespace semantics agree. Empty runs and non-text runs stay intact.
    """
    if node.tag == M + "oMath":
        return math_form(node)
    children = []
    for child in node:
        plain = (
            child.tag == W + "r"
            and len(child.findall(W + "rPr")) <= 1
            and all(
                c.tag in {W + "rPr", W + "t", W + "lastRenderedPageBreak"}
                for c in child
            )
        )
        payload = [c for c in child if c.tag != W + "rPr"] if plain else []
        if (
            plain
            and payload
            and all(
                t.tag == W + "lastRenderedPageBreak" or t.text and not len(t)
                for t in payload
            )
        ):
            props = child.find(W + "rPr")
            non_color = (
                tuple(raw_tree(c) for c in props if c.tag != W + "color")
                if props is not None
                else ()
            )
            prop_attrs = (
                tuple(sorted(props.attrib.items())) if props is not None else ()
            )
            for t in payload:
                if t.tag == W + "lastRenderedPageBreak":
                    children.append(
                        (
                            "rendered-boundary",
                            tuple(sorted(child.attrib.items())),
                            raw_tree(props) if props is not None else None,
                            raw_tree(t),
                        )
                    )
                    continue
                value = t.text
                left, right = len(value) - len(value.lstrip()), len(value.rstrip())
                for index, char in enumerate(value):
                    space = (
                        "default-edge"
                        if t.get(SPACE) != "preserve"
                        and char.isspace()
                        and (index < left or index >= right)
                        else "literal"
                    )
                    children.append(
                        (
                            "char-run",
                            tuple(sorted(child.attrib.items())),
                            prop_attrs,
                            non_color,
                            tuple(
                                sorted(
                                    (k, v) for k, v in t.attrib.items() if k != SPACE
                                )
                            ),
                            char,
                            space,
                        )
                    )
                if (t.tail or "").strip():
                    children.append(("payload-tail", t.tail))
            if (child.text or "").strip():
                children.append(("run-text", child.text))
        else:
            children.append(normal_form(child))
        if (child.tail or "").strip():
            children.append(("tail", child.tail))
    tag = node.tag if isinstance(node.tag, str) else str(node.tag)
    value = node.text or ""
    if node.tag not in TEXT and not value.strip():
        value = ""
    return tag, tuple(sorted(node.attrib.items())), value, tuple(children)


@dataclass
class Character:
    text: str
    color: tuple
    node: object
    run: object
    paragraph: object
    node_offset: int


def characters(roots):
    """Coordinates: part, zero-based XML paragraph ordinal, code-point offset.

    Paragraph/cell delimiters are structural, not characters. Instructions are
    compared as XML, not counted as displayed characters. Nested stories have
    their own paragraph, never duplicate counts in the containing paragraph.
    """
    result = {}
    for part, root in roots.items():
        parents = {c: p for p in root.iter() for c in p}
        for pi, paragraph in enumerate(root.iter(W + "p")):
            offset = 0

            def walk(node, *, paragraph=paragraph, parents=parents, part=part, pi=pi):
                nonlocal offset
                if node is not paragraph and node.tag == W + "p":
                    return
                value = (
                    node.text or "" if node.tag in TEXT else CONTROLS.get(node.tag, "")
                )
                for local, char in enumerate(value):
                    parent = parents.get(node)
                    result[part, pi, offset] = Character(
                        char, color_of(parent), node, parent, paragraph, local
                    )
                    offset += 1
                for child in node:
                    walk(child)

            walk(paragraph)
    return result


def compare(
    accepted_path,
    colored_path,
    *,
    allowed=None,
    rgb="FF0000",
    mutable_parts=None,
    allowed_math_controls=None,
):
    """allowed=None => provenance pending, never silently authorize all colors."""
    try:
        before, a, comment_a = read_package(accepted_path)
        after, b, comment_b = read_package(colored_path)
    except (ValueError, BadZipFile, ET.ParseError, OSError):
        return (
            {
                "content_fidelity": "FAIL",
                "color_authorization": "NOT_EVALUATED",
                "errors": ["INVALID_PACKAGE_OR_XML"],
            },
            {},
            {},
        )
    errors = []
    if before.keys() != after.keys():
        errors.append("ZIP_MEMBER_SET_CHANGED")
    if comment_a != comment_b:
        errors.append("ZIP_COMMENT_CHANGED")
    mutable_parts = (
        {"word/document.xml"} if mutable_parts is None else set(mutable_parts)
    )
    changed = [
        name for name in before.keys() & after.keys() if before[name] != after[name]
    ]
    for name in changed:
        if name not in mutable_parts:
            errors.append("UNMODIFIED_PART_BYTES_CHANGED:" + name)
        if (
            name not in a
            or name not in b
            or normal_form(a[name]) != normal_form(b[name])
        ):
            errors.append("CONTENT_OR_NONCOLOR_FORMAT_CHANGED:" + name)
    ac, bc = characters(a), characters(b)
    if ac.keys() != bc.keys() or any(
        ac[k].text != bc[k].text for k in ac.keys() & bc.keys()
    ):
        errors.append("DISPLAY_TEXT_OR_BOUNDARIES_CHANGED")
    edits = {k for k in ac.keys() & bc.keys() if ac[k].color != bc[k].color}
    wrong_color = {k for k in edits if bc[k].color != requested_color(rgb)}
    unauthorized = edits - set(allowed) if allowed is not None else set()
    if wrong_color:
        errors.append("WRONG_TARGET_COLOR")
    if unauthorized:
        errors.append("UNAUTHORIZED_COLOR_CHANGE")
    controls_a, controls_b = math_control_colors(a), math_control_colors(b)
    control_edits = {
        k
        for k in controls_a.keys() & controls_b.keys()
        if controls_a[k] != controls_b[k]
    }
    if controls_a.keys() != controls_b.keys():
        errors.append("MATH_OBJECT_SET_CHANGED")
    wrong_controls = {k for k in control_edits if controls_b[k] != requested_color(rgb)}
    control_allowed = (
        set(allowed_math_controls or ())
        if allowed is not None or allowed_math_controls is not None
        else None
    )
    unauthorized_controls = (
        control_edits - control_allowed if control_allowed is not None else set()
    )
    if wrong_controls:
        errors.append("WRONG_MATH_CONTROL_COLOR")
    if unauthorized_controls:
        errors.append("UNAUTHORIZED_MATH_CONTROL_COLOR")
    fidelity_errors = [
        e
        for e in errors
        if e
        not in {
            "WRONG_TARGET_COLOR",
            "UNAUTHORIZED_COLOR_CHANGE",
            "WRONG_MATH_CONTROL_COLOR",
            "UNAUTHORIZED_MATH_CONTROL_COLOR",
        }
    ]
    report = {
        "overall": "FAIL"
        if errors
        else "PENDING_INDEPENDENT_PROVENANCE"
        if allowed is None
        else "PASS",
        "content_fidelity": "FAIL" if fidelity_errors else "PASS",
        "color_authorization": "PENDING_INDEPENDENT_PROVENANCE"
        if allowed is None
        else "FAIL"
        if wrong_color or unauthorized or wrong_controls or unauthorized_controls
        else "PASS",
        "errors": errors,
        "actual_color_edits": len(edits),
        "math_control_color_edits": len(control_edits),
        "unauthorized_math_controls": len(unauthorized_controls)
        if control_allowed is not None
        else None,
        "wrong_target_color_characters": len(wrong_color),
        "unauthorized_color_characters": len(unauthorized)
        if allowed is not None
        else None,
        "display_characters_compared": len(ac),
        "zip_members": len(before),
        "unchanged_part_bytes": sum(before[n] == after.get(n) for n in before),
        "changed_parts": sorted(changed),
    }
    return report, ac, bc


def accuracy(before, after, truth, rgb="FF0000"):
    """Observed edits, not final RGB or converter claims, determine predictions.

    INSERTED characters already in the exact requested direct color are no-op
    observations: exclude them explicitly, never invent a TP or FN. A second
    conversion with a fresh color can test these characters' actual selection.
    """
    counts = dict(TP=0, FP=0, FN=0, TN=0, inserted_already_target_noop=0)
    for key, label in truth.items():
        a, b = before[key], after[key]
        if a.text != b.text:
            raise ValueError("METRICS_REQUIRE_IDENTICAL_TEXT")
        inserted = label == "INSERTED"
        if label not in {"INSERTED", "UNCHANGED"}:
            raise ValueError("UNKNOWN_TRUTH_LABEL")
        edited = a.color != b.color
        if inserted and a.color == b.color == requested_color(rgb):
            counts["inserted_already_target_noop"] += 1
        elif inserted:
            counts["TP" if edited and b.color == requested_color(rgb) else "FN"] += 1
        else:
            counts["FP" if edited else "TN"] += 1
    tp, fp, fn, tn = (counts[k] for k in ("TP", "FP", "FN", "TN"))

    def ratio(x, y):
        return x / y if y else None

    return {
        **counts,
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
        "false_positive_rate": ratio(fp, fp + tn),
        "false_negative_rate": ratio(fn, fn + tp),
        "labeled_characters": len(truth),
    }
