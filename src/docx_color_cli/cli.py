"""Supported CLI: tracked DOCX + Word-accepted DOCX -> colored DOCX."""

import argparse
import sys
from importlib.metadata import version
from pathlib import Path

from .api import color_revisions
from .errors import ColoringError


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="docx-color",
        usage="%(prog)s [--color HEX] [--report PATH] TRACKED ACCEPTED OUTPUT",
        description="Color surviving insertions using a tracked DOCX and its corresponding Word-accepted copy. This tool does not accept revisions.",
        epilog="Legacy one/two-file usage is no longer supported. In Word, accept all changes and save a second DOCX, then provide TRACKED ACCEPTED OUTPUT.",
    )
    parser.add_argument(
        "--version", action="version", version="%(prog)s " + version("docx-color-cli")
    )
    parser.add_argument(
        "tracked",
        metavar="TRACKED",
        type=Path,
        help="original DOCX containing Word tracked changes",
    )
    parser.add_argument(
        "accepted",
        metavar="ACCEPTED",
        nargs="?",
        type=Path,
        help="corresponding copy saved after accepting all changes in Word",
    )
    parser.add_argument(
        "output",
        metavar="OUTPUT",
        nargs="?",
        type=Path,
        help="destination colored DOCX (existing output is replaced on success)",
    )
    parser.add_argument(
        "--color",
        default="FF0000",
        metavar="HEX",
        help="insertion color: six hex digits, without # (default: FF0000)",
    )
    parser.add_argument(
        "--report", type=Path, help="write a text-free JSON result report"
    )
    args = parser.parse_intermixed_args(argv)
    if args.accepted is None or args.output is None:
        parser.error(
            "The new workflow requires TRACKED ACCEPTED OUTPUT. Accept all changes in Word and save a second DOCX; the tool no longer accepts revisions."
        )
    try:
        result = color_revisions(
            args.tracked,
            args.accepted,
            args.output,
            args.color,
            report_path=args.report,
        )
    except ColoringError as exc:
        print(
            f"docx-color: {exc.code}: {exc}\nStatus: FAILED (DOCX not published)",
            file=sys.stderr,
        )
        return 1
    remaining = (
        result["completeness"]["eligible_characters_uncolored"]
        + result["completeness"]["other_projected_candidates_uncolored"]
    )
    # Redirected Windows/legacy terminals may not encode a Unicode filename.
    # Escape only unrepresentable display characters; never turn an already
    # published DOCX into a misleading UnicodeEncodeError failure.
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    display_output = (
        str(args.output).encode(encoding, "backslashreplace").decode(encoding)
    )
    print(
        f"Colored DOCX created:\n  {display_output}\nInserted characters colored:\n  {result['coloring']['characters_colored']}\nRemaining uncolored candidates:\n  {remaining}\nStatus:\n  {result['overall_status']}"
    )
    if result["mathematics"]["uncolored_inserted_controls"]:
        print(
            f"Unresolved mathematical control elements:\n  {result['mathematics']['uncolored_inserted_controls']}"
        )
    for warning in result["warnings"]:
        print(
            f"docx-color: {warning['code']}: {warning.get('message', 'See the publication receipt for details.')}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
