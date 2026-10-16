"""Synthetic fault injection into completed output; never mutate private inputs."""

from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from helpers.corpus import R, cell, field, ins, p, package, run, table
from helpers.fidelity import M, W, compare, parse


def fixture(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    props = '<w:rStyle w:val="Audit"/><w:rFonts w:ascii="Cambria"/><w:b/><w:i/><w:color w:val="123456"/><w:sz w:val="24"/><w:u w:val="single"/><w:vertAlign w:val="superscript"/>'
    image = '<w:r><w:drawing><a:blip xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" r:embed="image"/></w:drawing></w:r>'
    complex_content = (
        '<w:bookmarkStart w:id="1" w:name="target"/>'
        + field()
        + '<w:hyperlink r:id="link">'
        + run("link")
        + '</w:hyperlink><w:bookmarkEnd w:id="1"/>'
        + '<w:commentRangeStart w:id="0"/>'
        + run("commented")
        + '<w:commentRangeEnd w:id="0"/>'
        + '<w:r><w:commentReference w:id="0"/><w:footnoteReference w:id="1"/><w:endnoteReference w:id="1"/></w:r>'
        + "<m:oMath><m:r><m:t>x²</m:t></m:r></m:oMath>"
        + image
        + '<w:sdt><w:sdtPr><w:tag w:val="audit"/></w:sdtPr><w:sdtContent>'
        + run("control")
        + "</w:sdtContent></w:sdt>"
    )
    tail = (
        p(complex_content)
        + table("<w:tr>" + cell(p(run("cellA"))) + cell(p(run("cellB"))) + "</w:tr>", 2)
        + p(run("é e\u0301 中文"))
        + '<w:sectPr><w:headerReference w:type="default" r:id="header"/><w:footerReference w:type="default" r:id="footer"/><w:pgSz w:w="11906" w:h="16838"/></w:sectPr>'
    )
    extras = {
        "word/media/image.bin": b"synthetic-opaque-image",
        "word/styles.xml": f'<w:styles xmlns:w="{W[1:-1]}"><w:style w:type="character" w:styleId="Audit"><w:name w:val="Audit"/></w:style></w:styles>',
        "word/numbering.xml": f'<w:numbering xmlns:w="{W[1:-1]}"><w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0"><w:start w:val="1"/></w:lvl></w:abstractNum><w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num></w:numbering>',
    }
    relations = [
        ("link", "hyperlink", "https://example.invalid/", True),
        ("image", "image", "media/image.bin", False),
        ("styles", "styles", "styles.xml", False),
        ("numbering", "numbering", "numbering.xml", False),
    ]
    for name, root, child, content in [
        ("header", "hdr", None, "header"),
        ("footer", "ftr", None, "footer"),
        ("comments", "comments", "comment", "comment"),
        ("footnotes", "footnotes", "footnote", "footnote"),
        ("endnotes", "endnotes", "endnote", "endnote"),
    ]:
        payload = p(run(content))
        if child:
            payload = f'<w:{child} w:id="{0 if child == "comment" else 1}">{payload}</w:{child}>'
        extras[f"word/{name}.xml"] = (
            f'<w:{root} xmlns:w="{W[1:-1]}">{payload}</w:{root}>'
        )
        relations.append(
            (
                name,
                name if name not in {"header", "footer"} else name,
                f"{name}.xml",
                False,
            )
        )
    extras["word/_rels/document.xml.rels"] = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="{ident}" Type="{R}/{kind}" Target="{target}"'
            + (' TargetMode="External"' if external else "")
            + "/>"
            for ident, kind, target, external in relations
        )
        + "</Relationships>"
    )
    para_props = '<w:pStyle w:val="Normal"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>'
    tracked = package(
        directory / "tracked.docx",
        p(run("keep ", props) + ins("new", props=props), para_props) + tail,
        extras,
    )
    accepted = package(
        directory / "accepted.docx",
        p(run("keep new", props), para_props) + tail,
        extras,
    )
    return tracked, accepted, {("word/document.xml", 0, i) for i in range(5, 8)}


MUTATIONS = (
    "text_remove",
    "text_duplicate",
    "text_reorder",
    "space_remove",
    "unicode_normalize",
    "paragraph_remove",
    "paragraph_merge",
    "cell_remove",
    "table_property",
    "font",
    "size",
    "bold",
    "italic",
    "underline",
    "superscript",
    "paragraph_property",
    "style_reference",
    "numbering_reference",
    "section",
    "math",
    "image_bytes",
    "drawing",
    "field_instruction",
    "field_result",
    "hyperlink",
    "bookmark",
    "comment_anchor",
    "comments_part",
    "footnotes_part",
    "endnotes_part",
    "header_part",
    "footer_part",
    "content_control",
    "styles_part",
    "numbering_part",
    "content_types",
    "relationship",
    "member_add",
    "member_remove",
    "invalid_xml",
    "invalid_zip",
    "unchanged_color",
    "wrong_inserted_color",
    "duplicate_color",
    "space_attribute",
)


def inject(source, destination, mutation):
    with ZipFile(source) as z:
        data = {name: z.read(name) for name in z.namelist()}
    root = parse(data["word/document.xml"])

    def first(tag):
        return next(root.iter(tag))

    texts = list(root.iter(W + "t"))
    if mutation == "text_remove":
        texts[0].text = texts[0].text[1:]
    elif mutation == "text_duplicate":
        texts[0].text *= 2
    elif mutation == "text_reorder":
        texts[0].text = texts[0].text[::-1]
    elif mutation == "space_remove":
        texts[0].text = texts[0].text.replace(" ", "")
    elif mutation == "unicode_normalize":
        texts[-1].text = texts[-1].text.replace("e\u0301", "é")
    elif mutation in {"paragraph_remove", "paragraph_merge"}:
        body = first(W + "body")
        if mutation == "paragraph_merge":
            body[0].extend(list(body[1]))
        body.remove(body[1])
    elif mutation == "cell_remove":
        row = first(W + "tr")
        row.remove(row[-1])
    elif mutation == "table_property":
        first(W + "gridCol").set(W + "w", "10")
    elif mutation in {
        "font",
        "size",
        "underline",
        "superscript",
        "style_reference",
        "numbering_reference",
        "section",
        "paragraph_property",
        "content_control",
        "bookmark",
    }:
        tag, attr, value = {
            "font": ("rFonts", "ascii", "Arial"),
            "size": ("sz", "val", "48"),
            "underline": ("u", "val", "double"),
            "superscript": ("vertAlign", "val", "subscript"),
            "style_reference": ("rStyle", "val", "Other"),
            "numbering_reference": ("numId", "val", "2"),
            "section": ("pgSz", "w", "100"),
            "paragraph_property": ("pStyle", "val", "Other"),
            "content_control": ("tag", "val", "changed"),
            "bookmark": ("bookmarkStart", "name", "changed"),
        }[mutation]
        first(W + tag).set(W + attr, value)
    elif mutation in {"bold", "italic"}:
        first(W + ("b" if mutation == "bold" else "i")).set(W + "val", "0")
    elif mutation == "math":
        first(M + "t").text = "y²"
    elif mutation == "drawing":
        first(W + "drawing").set("changed", "true")
    elif mutation == "field_instruction":
        first(W + "fldSimple").set(W + "instr", "ADDIN ZOTERO_ITEM changed")
    elif mutation == "field_result":
        next(first(W + "fldSimple").iter(W + "t")).text = "[2]"
    elif mutation == "hyperlink":
        first(W + "hyperlink").set("{" + R + "}id", "missing")
    elif mutation == "comment_anchor":
        first(W + "commentRangeEnd").set(W + "id", "9")
    elif mutation == "unchanged_color":
        first(W + "color").set(W + "val", "FF0000")
    elif mutation == "wrong_inserted_color":
        next(c for c in root.iter(W + "color") if c.get(W + "val") == "FF0000").set(
            W + "val", "00FF00"
        )
    elif mutation == "duplicate_color":
        props = first(W + "rPr")
        props.append(deepcopy(props.find(W + "color")))
    elif mutation == "space_attribute":
        texts[0].attrib.pop("{http://www.w3.org/XML/1998/namespace}space", None)
    data["word/document.xml"] = ET.tostring(
        root, encoding="utf-8", xml_declaration=True
    )
    if mutation.endswith("_part"):
        name = "word/" + mutation.removesuffix("_part") + ".xml"
        r = parse(data[name])
        if mutation == "styles_part":
            next(r.iter(W + "name")).set(W + "val", "ChangedStyle")
        elif mutation == "numbering_part":
            next(r.iter(W + "start")).set(W + "val", "9")
        else:
            text = next(r.iter(W + "t"))
            text.text += " changed"
        data[name] = ET.tostring(r)
    if mutation == "image_bytes":
        data["word/media/image.bin"] += b"changed"
    elif mutation == "content_types":
        data["[Content_Types].xml"] = data["[Content_Types].xml"].replace(
            b"application/xml", b"text/plain"
        )
    elif mutation == "relationship":
        data["word/_rels/document.xml.rels"] = data[
            "word/_rels/document.xml.rels"
        ].replace(b"example.invalid", b"changed.invalid")
    elif mutation == "member_add":
        data["unexpected.bin"] = b"new"
    elif mutation == "member_remove":
        del data["customXml/unchanged.xml"]
    elif mutation == "invalid_xml":
        data["word/document.xml"] = b"<broken>"
    if mutation == "invalid_zip":
        Path(destination).write_bytes(b"not a zip")
    else:
        with ZipFile(destination, "w") as z:
            for name, value in data.items():
                z.writestr(name, value)


def evaluate_mutations(directory):
    from docx_color_cli.engine import convert

    directory = Path(directory)
    tracked, accepted, allowed = fixture(directory)
    colored = directory / "colored.docx"
    convert(tracked, accepted, colored)
    baseline, _, _ = compare(accepted, colored, allowed=allowed)
    assert baseline["overall"] == "PASS", baseline["errors"]
    results = []
    for name in MUTATIONS:
        mutant = directory / (name + ".docx")
        inject(colored, mutant, name)
        report, _, _ = compare(accepted, mutant, allowed=allowed)
        results.append(
            {
                "mutation": name,
                "detected": report.get("overall") == "FAIL"
                or report["content_fidelity"] == "FAIL",
                "errors": report["errors"],
            }
        )
    neutral = directory / "reserialized.docx"
    inject(colored, neutral, "neutral_reserialization")
    neutral_report, _, _ = compare(accepted, neutral, allowed=allowed)
    return {
        "mutations": results,
        "detected": sum(r["detected"] for r in results),
        "total": len(results),
        "neutral_reserialization_passes": neutral_report["overall"] == "PASS",
    }
