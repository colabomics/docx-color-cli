"""The supported three-document Python entry point."""

from .engine import convert
from .errors import ColoringError


def color_revisions(
    tracked_path, accepted_path, output_path, color="FF0000", *, report_path=None
):
    """Return a JSON-compatible result, or raise ColoringError before publication.

    Partial coverage and late auxiliary-report failures return PARTIAL with
    explicit warnings. The accepted file is the authoritative final document.
    """
    try:
        return convert(
            tracked_path,
            accepted_path,
            output_path,
            inserted_color=color,
            report_path=report_path,
        )
    except ColoringError:
        raise
    except Exception as exc:
        raise ColoringError(
            "INTERNAL_ERROR",
            "Unexpected processing failure; no successful publication receipt was returned.",
        ) from exc
