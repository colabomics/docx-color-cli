"""Read an authoritative package without accepting or normalizing revisions."""

from collections import Counter
from zipfile import ZipFile

from lxml import etree

from .errors import ColoringError
from .package import validate_archive_directory
from .projection import W, paragraphs, revision_node


class Package:
    def __init__(self, path, *, accepted=False):
        with ZipFile(path) as archive:
            self.infos = archive.infolist()
            self.comment = archive.comment
            if len(self.infos) != len({i.filename for i in self.infos}):
                raise ValueError("Duplicate ZIP members")
            validate_archive_directory(self.infos)
            if archive.testzip() is not None:
                raise ValueError("ZIP checksum failure")
            self.data = {i.filename: archive.read(i) for i in self.infos}
            self.xml = {}
            for name, data in self.data.items():
                if name.endswith((".xml", ".rels")):
                    root = etree.fromstring(
                        data, etree.XMLParser(resolve_entities=False, no_network=True)
                    )
                    if root.getroottree().docinfo.doctype:
                        raise ValueError("DTD is unsupported")
                    self.xml[name] = root
            root = self.xml.get("word/document.xml")
            if (
                root is not None
                and root.tag
                == "{http://purl.oclc.org/ooxml/wordprocessingml/main}document"
            ):
                raise ColoringError(
                    "UNSUPPORTED_CONTENT",
                    "Strict OOXML is not supported by the revision-guided workflow. Save a Transitional .docx copy in Word.",
                )
            if (
                root is None
                or root.tag != W + "document"
                or root.find(W + "body") is None
            ):
                raise ValueError(
                    "Requires a Transitional OOXML Word document with body"
                )
            # This is a read-only OPC/relationship check, never a conversion call.
            from docx_color_cli.package import validate_package

            validate_package(archive, self.xml)
        if accepted and any(
            revision_node(n) for root in self.xml.values() for n in root.iter()
        ):
            raise ColoringError(
                "INVALID_DOCUMENT_PAIR",
                "Accepted input still contains tracked revisions. Accept all changes in Word and save a separate DOCX.",
            )
        self.paragraphs = paragraphs(self) if accepted else []


def summary(package):
    return dict(Counter(p.part for p in package.paragraphs))
