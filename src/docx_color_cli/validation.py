"""Independent per-character formatting and package-preservation checks."""

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

from .projection import XML_SPACE, M, W


def digest(path):
    with Path(path).open("rb") as stream:
        h = sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
        return h.hexdigest()


def distinct_paths(paths):
    paths = [Path(p) for p in paths if p is not None]
    for i, a in enumerate(paths):
        for b in paths[i + 1 :]:
            if (
                a.resolve() == b.resolve()
                or a.exists()
                and b.exists()
                and a.samefile(b)
            ):
                raise ValueError(
                    "Input, output and report paths must differ, including aliases"
                )


def key(n):
    if not isinstance(n.tag, str):
        return ("xml", etree.tostring(n, with_tail=False))
    return (
        n.tag,
        tuple(sorted(n.attrib.items())),
        n.text or "",
        tuple((key(c), c.tail or "") for c in n),
    )


def events(root, selected=None, rgb="FF0000", math_controls=None):
    """Erase only safe run segmentation, retaining exact per-character properties.

    This implementation deliberately does not call the coloring/splitting helpers.
    Only xml:space and insignificant indentation may change with splitting.
    """
    selected = selected or {}
    out = []

    def expected_math(n):
        clone = deepcopy(n)
        pairs = list(zip(n.iter(), clone.iter(), strict=True))

        def property_color(parent, after_math_props=False):
            props = parent.find(W + "rPr")
            if props is None:
                props = etree.Element(W + "rPr")
                parent.insert(
                    int(after_math_props and parent.find(M + "rPr") is not None), props
                )
            for c in list(props):
                if c.tag == W + "color":
                    props.remove(c)
            # Independently enforce w:rPr schema order for inserted color.
            prior = {
                W + s
                for s in [
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
                ]
            }
            index = max(
                (i + 1 for i, c in enumerate(props) if c.tag in prior), default=0
            )
            props.insert(index, etree.Element(W + "color", {W + "val": rgb}))

        for original, copied in pairs:
            if original.tag == M + "r" and any(
                t in selected for t in original.findall(M + "t")
            ):
                assert all(
                    i in selected.get(t, ())
                    for t in original.findall(M + "t")
                    for i in range(len(t.text or ""))
                )
                property_color(copied, True)
            if original in (math_controls or {}):
                tag = math_controls[original]
                if tag is None:
                    property_color(copied)
                    continue
                props = copied.find(tag)
                assert props is not None
                ctrl = props.find(M + "ctrlPr")
                assert ctrl is not None
                property_color(ctrl)
        return key(clone)

    def visit(n):
        if not isinstance(n.tag, str):
            out.append(key(n))
            return
        if n.tag == M + "oMath":
            out.append(
                ("omml", expected_math(n) if selected or math_controls else key(n))
            )
            return
        plain = (
            n.tag == W + "r"
            and all(
                c.tag in {W + "rPr", W + "t", W + "lastRenderedPageBreak"} for c in n
            )
            and len(n.findall(W + "rPr")) <= 1
        )
        if plain:
            props = n.find(W + "rPr")
            properties = (
                tuple(key(c) for c in props if c.tag != W + "color")
                if props is not None
                else ()
            )
            prop_attrs = (
                tuple(sorted(props.attrib.items())) if props is not None else ()
            )
            colors = (
                tuple(key(c) for c in props if c.tag == W + "color")
                if props is not None
                else ()
            )
            payload = [c for c in n if c.tag != W + "rPr"]
            if not payload or not any(
                t.text or t.tag == W + "lastRenderedPageBreak" for t in payload
            ):
                out.append(("empty-run", key(n)))
            for text in payload:
                if text.tag == W + "lastRenderedPageBreak":
                    out.append(
                        (
                            "page-break",
                            tuple(sorted(n.attrib.items())),
                            key(props) if props is not None else None,
                            key(text),
                        )
                    )
                    continue
                attrs = tuple(
                    sorted((k, v) for k, v in text.attrib.items() if k != XML_SPACE)
                )
                for i, char in enumerate(text.text or ""):
                    color = (
                        ((W + "color", ((W + "val", rgb),), "", ()),)
                        if i in selected.get(text, ())
                        else colors
                    )
                    out.append(
                        (
                            "character",
                            tuple(sorted(n.attrib.items())),
                            prop_attrs,
                            properties,
                            color,
                            attrs,
                            char,
                            "uncertain-edge-space"
                            if char.isspace()
                            and text.get(XML_SPACE) != "preserve"
                            and (
                                i < len(text.text) - len(text.text.lstrip())
                                or i >= len(text.text.rstrip())
                            )
                            else "literal",
                        )
                    )
            return
        out.append(("start", n.tag, tuple(sorted(n.attrib.items())), n.text or ""))
        for c in n:
            visit(c)
            if (c.tail or "").strip():
                out.append(("tail", c.tail))
        out.append(("end", n.tag))

    visit(root)
    return out


def expected_events(package, selected, rgb, math_controls=None):
    return {
        name: events(root, selected, rgb, math_controls)
        for name, root in package.xml.items()
    }


def validate_output(path, original, expected, changed):
    with ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("Output ZIP checksum failed")
        if (
            archive.namelist() != list(original.data)
            or archive.comment != original.comment
        ):
            raise ValueError("Output package members or archive comment changed")
        original_infos = {i.filename: i for i in original.infos}
        roots = {}
        for name in archive.namelist():
            data = archive.read(name)
            if name not in changed and data != original.data[name]:
                raise ValueError("Unrelated ZIP member changed: " + name)
            a, b = original_infos[name], archive.getinfo(name)
            if (a.date_time, a.compress_type, a.external_attr) != (
                b.date_time,
                b.compress_type,
                b.external_attr,
            ):
                raise ValueError("ZIP entry metadata changed: " + name)
            if name.endswith((".xml", ".rels")):
                root = etree.fromstring(
                    data, etree.XMLParser(resolve_entities=False, no_network=True)
                )
                roots[name] = root
                if events(root) != expected[name]:
                    raise ValueError(
                        "Text, formatting or structural invariant failed: " + name
                    )
        from docx_color_cli.package import validate_package

        validate_package(archive, roots)
    return {
        "zip_valid": True,
        "xml_valid": True,
        "accepted_text_preserved": True,
        "unchanged_character_formatting_preserved": True,
        "unrelated_zip_members_unchanged": True,
        "relationships_unchanged": True,
        "complex_objects_preserved": True,
        "unresolved_integrity_differences": 0,
        "unexpected_character_edits_against_plan": 0,
    }
