"""Read-only OPC checks. These checks do not prove Microsoft Word equivalence."""

import posixpath
from urllib.parse import unquote, urlsplit

from .errors import ColoringError, ConversionError, conversion_context

# Bound advertised archive expansion before any member is decompressed. These
# are resource limits, not schema/Word compatibility or insertion heuristics.
MAX_ZIP_MEMBERS = 4096
MAX_ZIP_BYTES = 256 * 1024 * 1024
MAX_XML_BYTES = 32 * 1024 * 1024
MAX_COMPRESSION_RATIO = 1000


def validate_archive_directory(infos):
    """Reject unsafe package names and excessive declared expansion before reads."""
    if len(infos) > MAX_ZIP_MEMBERS or sum(i.file_size for i in infos) > MAX_ZIP_BYTES:
        raise ColoringError(
            "UNSUPPORTED_CONTENT", "DOCX exceeds the archive resource budget."
        )
    for info in infos:
        name = info.filename
        parts = (name[:-1] if name.endswith("/") else name).split("/")
        if (
            info.orig_filename != name
            or "\\" in name
            or ":" in parts[0]
            or any(part in {"", ".", ".."} for part in parts)
        ):
            raise ValueError("Noncanonical or unsafe ZIP member name")
        if (
            name.endswith((".xml", ".rels"))
            and info.file_size > MAX_XML_BYTES
            or info.file_size >= 1024 * 1024
            and info.file_size > MAX_COMPRESSION_RATIO * max(1, info.compress_size)
        ):
            raise ColoringError(
                "UNSUPPORTED_CONTENT",
                "DOCX exceeds the XML or compression resource budget.",
            )


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = "{" + W_NS + "}"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
R = "{" + R_NS + "}"
PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"
CT = "{http://schemas.openxmlformats.org/package/2006/content-types}"
STORY_TYPES = {
    "officeDocument": "document",
    "header": "hdr",
    "footer": "ftr",
    "footnotes": "footnotes",
    "endnotes": "endnotes",
    "comments": "comments",
    "glossaryDocument": "glossaryDocument",
}


def relationship_source(name):
    if name == "_rels/.rels":
        return ""
    directory, filename = posixpath.split(name)
    if not directory.endswith("/_rels") or not filename.endswith(".rels"):
        raise ValueError(f"Invalid relationship part path: {name}")
    return posixpath.join(directory[:-6], filename[:-5])


def relationship_target(source, target):
    url = urlsplit(target)
    if url.scheme or url.netloc or url.query or url.fragment or "\\" in target:
        raise ValueError(f"Unsupported internal relationship target: {target}")
    target = unquote(url.path)
    resolved = (
        posixpath.normpath(posixpath.join(posixpath.dirname(source), target))
        if not target.startswith("/")
        else posixpath.normpath(target[1:])
    )
    if resolved.startswith("../") or resolved in ("", ".", ".."):
        raise ValueError(f"Relationship target escapes package: {target}")
    return resolved


def validate_package(archive, roots):
    """Check publication prerequisites; not a full OOXML schema/Word validator."""
    names = set(archive.namelist())
    if archive.testzip() is not None:
        raise ValueError("Invalid ZIP checksum")
    types = roots.get("[Content_Types].xml")
    if types is None or types.tag != CT + "Types":
        raise ConversionError(
            "Missing or invalid Content Types", part="[Content_Types].xml"
        )
    defaults, overrides = {}, {}
    for node in types:
        if node.tag == CT + "Default":
            mapping, key = defaults, node.get("Extension")
        elif node.tag == CT + "Override":
            mapping, key = overrides, unquote(node.get("PartName", "")).lstrip("/")
        else:
            raise ConversionError(
                "Invalid Content Types entry", part="[Content_Types].xml"
            )
        if not key or key in mapping or not node.get("ContentType"):
            raise ConversionError(
                "Missing or duplicate Content Types entry", part="[Content_Types].xml"
            )
        mapping[key] = node.get("ContentType")
    if (
        overrides.get("word/document.xml")
        != "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
    ):
        raise ConversionError(
            "Incorrect main document Content Type", part="[Content_Types].xml"
        )
    for name in names:
        if name.endswith("/") or name == "[Content_Types].xml":
            continue
        if name not in overrides and name.rsplit(".", 1)[-1] not in defaults:
            raise ConversionError("missing Content Type", part=name)
    for name in overrides:
        if name not in names:
            raise ConversionError("Content Type points to absent part", part=name)
    story_mimes = {
        f"application/vnd.openxmlformats-officedocument.wordprocessingml.{kind}+xml": tag
        for kind, tag in STORY_TYPES.items()
        if kind != "officeDocument"
    }
    story_mimes[
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
    ] = "document"
    for name, mime in overrides.items():
        expected_root = story_mimes.get(mime)
        if expected_root and (
            name not in roots or roots[name].tag != W + expected_root
        ):
            raise ConversionError("Content Type and story root disagree", part=name)

    links = {}
    for name, root in roots.items():
        if not name.endswith(".rels"):
            continue
        if root.tag != PKG + "Relationships":
            raise ConversionError("invalid relationships root", part=name)
        source = relationship_source(name)
        if source and source not in names:
            raise ConversionError("relationship source missing", part=name)
        rels = links.setdefault(source, {})
        for rel in root:
            ident, kind, target = rel.get("Id"), rel.get("Type"), rel.get("Target")
            mode = rel.get("TargetMode", "Internal")
            if (
                rel.tag != PKG + "Relationship"
                or not ident
                or not kind
                or not target
                or ident in rels
                or mode not in {"Internal", "External"}
            ):
                raise ConversionError("invalid or duplicate relationship", part=name)
            with conversion_context(part=name):
                destination = (
                    target
                    if mode == "External"
                    else relationship_target(source, target)
                )
            if mode == "Internal" and destination not in names:
                raise ConversionError(
                    f"missing relationship target {destination}", part=name
                )
            rels[ident] = (kind, destination, mode)
    main = [
        value
        for value in links.get("", {}).values()
        if value[0] == R_NS + "/officeDocument"
    ]
    if main != [(R_NS + "/officeDocument", "word/document.xml", "Internal")]:
        raise ConversionError(
            "Missing or ambiguous main document relationship", part="_rels/.rels"
        )
    for name, root in roots.items():
        for node in root.iter():
            if not isinstance(node.tag, str):
                continue
            for attribute, value in node.attrib.items():
                if attribute.startswith(R) and value not in links.get(name, {}):
                    raise ConversionError(
                        f"missing relationship {value}", part=name, node=node
                    )
            for kind in ("footnote", "endnote", "comment"):
                if node.tag == W + kind + "Reference":
                    targets = [
                        r
                        for r in links.get(name, {}).values()
                        if r[0] == R_NS + "/" + kind + "s" and r[2] == "Internal"
                    ]
                    # Header/textbox references may use the main document's note part.
                    if not targets:
                        targets = [
                            r
                            for r in links.get("word/document.xml", {}).values()
                            if r[0] == R_NS + "/" + kind + "s" and r[2] == "Internal"
                        ]
                    if (
                        len(targets) != 1
                        or targets[0][1] not in roots
                        or not any(
                            n.get(W + "id") == node.get(W + "id")
                            for n in roots[targets[0][1]].iter(W + kind)
                        )
                    ):
                        raise ConversionError(
                            f"dangling {kind} reference", part=name, node=node
                        )
