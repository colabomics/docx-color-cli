"""Structured failures without document text in diagnostic context."""

from contextlib import contextmanager
from zipfile import BadZipFile

from lxml import etree


class ConversionError(ValueError):
    """Conversion failure; optional part, element and cause metadata are public.

    ValueError compatibility is retained for callers handling validation failures.
    XML context includes only the element name, XPath and source line, not content.
    """

    def __init__(
        self, message, *, part=None, node=None, revision_type=None, cause_type=None
    ):
        super().__init__(message)
        self.message = message
        self.part = part
        self.revision_type = revision_type
        self.element = node.tag if node is not None else None
        self.xpath = node.getroottree().getpath(node) if node is not None else None
        self.line = node.sourceline if node is not None else None
        self.cause_type = cause_type

    def __str__(self):
        context = [self.part, self.cause_type]
        if self.revision_type:
            context.append("revision=" + self.revision_type)
        if self.xpath:
            context.append(self.xpath)
        if self.line:
            context.append(f"line {self.line}")
        return ": ".join([value for value in context if value] + [self.message])


class UnsupportedRevisionError(ConversionError):
    """A revision or associated structure cannot be accepted safely."""


class PublicationError(ConversionError):
    """Publication failed; output_published identifies a partial two-file result."""

    def __init__(
        self, message, *, destination, output_published=False, cause_type=None
    ):
        super().__init__(message, cause_type=cause_type)
        self.destination = str(destination)
        self.output_published = output_published


@contextmanager
def conversion_context(*, part=None):
    """Add a known part and translate expected input/I/O failures, preserving causes."""
    try:
        yield
    except ConversionError as exc:
        if exc.part is None:
            exc.part = part
        raise
    except (ValueError, OSError, BadZipFile, etree.XMLSyntaxError) as exc:
        raise ConversionError(
            str(exc), part=part, cause_type=type(exc).__name__
        ) from exc
