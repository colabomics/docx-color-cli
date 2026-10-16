"""Color inserted content on a user-supplied Word-accepted DOCX."""

from .api import color_revisions
from .errors import ColoringError

__all__ = ["ColoringError", "color_revisions"]
