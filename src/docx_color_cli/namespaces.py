"""Namespace adapter for the shared Strict/Transitional revision vocabulary.

Only expanded XML names and OPC relationship type URIs are mapped. Text, field
instructions, targets, unknown attributes and prefix-valued attributes stay exact.
This is not a general format conversion: publication restores each part's dialect.
"""

from copy import deepcopy

from lxml import etree

STRICT = {
    "http://purl.oclc.org/ooxml/wordprocessingml/main": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "http://purl.oclc.org/ooxml/officeDocument/relationships": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "http://purl.oclc.org/ooxml/officeDocument/math": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "http://purl.oclc.org/ooxml/drawingml/main": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "http://purl.oclc.org/ooxml/drawingml/wordprocessingDrawing": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "http://purl.oclc.org/ooxml/drawingml/picture": "http://schemas.openxmlformats.org/drawingml/2006/picture",
}
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"


def dialect(root):
    namespaces = set()
    for node in root.iter():
        if not isinstance(node.tag, str):
            continue
        namespaces.add(etree.QName(node).namespace)
        namespaces.update(etree.QName(key).namespace for key in node.attrib)
    for strict, transitional in STRICT.items():
        if strict in namespaces and transitional in namespaces:
            raise ValueError(
                "Mixed Strict/Transitional expanded names in one part are unsupported"
            )
    for node in root.iter(REL):
        value = node.get("Type", "")
        namespaces.update(ns for ns in STRICT if value.startswith(ns + "/"))
    return {STRICT[ns]: ns for ns in namespaces if ns in STRICT}


def remap(root, mapping):
    def name(value):
        if not value.startswith("{"):
            return value
        uri, local = value[1:].split("}", 1)
        return "{" + mapping.get(uri, uri) + "}" + local

    def visit(node):
        if not isinstance(node.tag, str):
            return deepcopy(node)
        result = etree.Element(
            name(node.tag),
            nsmap={prefix: mapping.get(uri, uri) for prefix, uri in node.nsmap.items()},
        )
        for key, value in node.attrib.items():
            if node.tag == REL and key == "Type":
                for old, new in mapping.items():
                    if value.startswith(old + "/"):
                        value = new + value[len(old) :]
                        break
            result.set(name(key), value)
        result.text, result.tail = node.text, node.tail
        for child in node:
            result.append(visit(child))
        return result

    return visit(root)


def canonical_namespaces(root):
    original = dialect(root)
    mapping = {strict: canonical for canonical, strict in original.items()}
    return remap(root, mapping) if mapping else root
