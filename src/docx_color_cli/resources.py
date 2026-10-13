"""Prune image relationships lost during revision acceptance, conservatively.

This is not general ZIP garbage collection: pre-existing orphans and implicit or
unknown relationships are retained. Every remaining package relationship pins
its target, even from an otherwise unreachable or opaque source part.
"""

import posixpath
from urllib.parse import unquote

from lxml import etree

from .package import CT, R_NS, R, relationship_source, relationship_target

VML_RELID = "{urn:schemas-microsoft-com:office:office}relid"


def explicit_references(root):
    return {
        value
        for node in root.iter()
        for key, value in node.attrib.items()
        if key.startswith(R) or key == VML_RELID
    }


def prune_images(roots, names, before_references, stats):
    """Mutate planned rels/Content Types; return exact removed and changed parts.

    Only references actually removed from converted XML qualify. No live image is
    recompressed, renamed or deduplicated. Publication validates this explicit plan.
    """
    names = set(names)
    types = roots["[Content_Types].xml"]
    defaults = {
        n.get("Extension"): n.get("ContentType")
        for n in types
        if n.tag == CT + "Default"
    }
    overrides = {
        unquote(n.get("PartName")).lstrip("/"): n.get("ContentType")
        for n in types
        if n.tag == CT + "Override"
    }

    def image_part(name):
        return overrides.get(
            name, defaults.get(name.rsplit(".", 1)[-1], "")
        ).startswith("image/")

    candidates, changed = set(), set()
    for name, rels in roots.items():
        if not name.endswith(".rels"):
            continue
        source = relationship_source(name)
        if source not in before_references:
            continue
        # Unknown/custom attributes carrying an ID are also conservatively kept.
        after = {
            value for node in roots[source].iter() for value in node.attrib.values()
        }
        vanished = before_references[source] - after
        for rel in list(rels):
            if (
                rel.get("Id") not in vanished
                or rel.get("Type") != R_NS + "/image"
                or rel.get("TargetMode") == "External"
            ):
                continue
            target = relationship_target(source, rel.get("Target"))
            if not image_part(target):
                continue
            rels.remove(rel)
            candidates.add(target)
            changed.add(name)
            stats["removed_image_relationships"] += 1
    pinned = set()
    for name, rels in roots.items():
        if name.endswith(".rels"):
            for rel in rels:
                if rel.get("TargetMode") != "External":
                    pinned.add(
                        relationship_target(
                            relationship_source(name), rel.get("Target")
                        )
                    )
    # Legacy/custom XML can use literal paths (for example VML src) instead of
    # relationship IDs. Filename mentions conservatively pin a candidate; false
    # retention is preferable to deleting a resource with an unmodelled use.
    mentions = []
    for name, root in roots.items():
        if name.endswith(".rels") or name == "[Content_Types].xml":
            continue
        for node in root.iter():
            mentions.extend(unquote(v) for v in node.attrib.values())
            if node.text:
                mentions.append(unquote(node.text))
    for candidate in candidates:
        if any(posixpath.basename(candidate) in value for value in mentions):
            pinned.add(candidate)
    # Do not remove compound resources with their own relationship parts.
    removed = {
        name
        for name in candidates - pinned
        if posixpath.join(
            posixpath.dirname(name), "_rels", posixpath.basename(name) + ".rels"
        )
        not in names
    }
    if removed:
        remaining = names - removed
        extensions = {
            name.rsplit(".", 1)[-1]
            for name in remaining
            if "." in name and not name.endswith("/")
        }
        removed_extensions = {name.rsplit(".", 1)[-1] for name in removed}
        for node in list(types):
            if (
                node.tag == CT + "Override"
                and unquote(node.get("PartName")).lstrip("/") in removed
                or node.tag == CT + "Default"
                and node.get("Extension") in removed_extensions - extensions
            ):
                types.remove(node)
                changed.add("[Content_Types].xml")
    stats["removed_media_parts"] += len(removed)
    return removed, {
        name: etree.tostring(
            roots[name], encoding="UTF-8", xml_declaration=True, standalone=True
        )
        for name in changed
    }
