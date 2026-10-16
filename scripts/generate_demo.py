"""Render verified public examples; not a Word screen recording.

Run from a development checkout:
    uv run --with pillow python scripts/generate_demo.py

Pillow is a demo-only dependency. CLI runs, frames, and reports stay in a
TemporaryDirectory; only the final GIF is saved. No document is repaired here.
"""

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile

from lxml import etree
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
WIDTH, HEIGHT, FPS = 1000, 560, 12
BG, INK, MUTED = "#111820", "#f7f8fa", "#a8b3c2"
COMMAND = (
    "$ docx-color \\\n"
    "    examples/change_tracked.docx \\\n"
    "    examples/change_accepted.docx \\\n"
    "    examples/change_colored.docx"
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def xml(path):
    with ZipFile(path) as archive:
        return etree.fromstring(
            archive.read("word/document.xml"),
            etree.XMLParser(resolve_entities=False, no_network=True),
        )


def units(paragraph, *, include_deletions=False):
    result = []
    for n in paragraph.iter():
        if n.tag not in {W + "t", W + "delText", M + "t"}:
            continue
        ancestors = list(n.iterancestors())
        deleted = any(a.tag in {W + "del", W + "moveFrom"} for a in ancestors)
        inserted = any(a.tag == W + "ins" for a in ancestors)
        if deleted and not include_deletions:
            continue
        kind = "deleted" if deleted else "inserted" if inserted else "unchanged"
        result.extend((char, kind) for char in n.text or "")
    return result


def verified_excerpt(work):
    """Read literal revision ancestry; never use alignment to author truth."""
    sys.path.insert(0, str(ROOT / "tests"))
    from helpers.fidelity import compare, requested_color

    originals = [
        ROOT / "examples" / f"change_{s}.docx" for s in ("tracked", "accepted")
    ]
    hashes = [digest(p) for p in originals]
    (work / "examples").mkdir()
    for p in originals:
        shutil.copy2(p, work / "examples" / p.name)
    command = [
        "docx-color",
        "examples/change_tracked.docx",
        "examples/change_accepted.docx",
        "examples/change_colored.docx",
    ]
    run = subprocess.run(command, cwd=work, text=True, capture_output=True, check=True)
    output = work / command[-1]
    source = list(xml(originals[0]).iter(W + "p"))
    target = list(xml(originals[1]).iter(W + "p"))
    truth = set()
    for pi, (a, b) in enumerate(zip(source, target, strict=True)):
        left, right = units(a), units(b)
        assert "".join(c for c, _ in left) == "".join(c for c, _ in right)
        truth.update(
            ("word/document.xml", pi, i)
            for i, (_, kind) in enumerate(left)
            if kind == "inserted"
        )
    result, before, after = compare(originals[1], output, allowed=truth)
    assert result["overall"] == "PASS", result
    pi = 37  # Authored example's short table caption, stable structural coordinate.
    inserted = {k for k in truth if k[1] == pi}
    assert inserted and all(
        after[k].color == requested_color("FF0000") for k in inserted
    )
    assert all(
        after[k].color == before[k].color
        for k in after
        if k[1] == pi and k not in truth
    )
    excerpt = [
        (c.text, "red" if c.color == requested_color("FF0000") else "unchanged")
        for k, c in after.items()
        if k[0] == "word/document.xml" and k[1] == pi
    ]
    assert [digest(p) for p in originals] == hashes
    assert all(after[k].color == requested_color("FF0000") for k in truth)
    assert "Status:\n  SUCCESS" in run.stdout
    # Fail rather than render success or stale numbers after a regression.
    assert f"Inserted characters colored:\n  {len(truth)}\n" in run.stdout
    assert "Remaining uncolored candidates:\n  0\n" in run.stdout
    return units(source[pi], include_deletions=True), excerpt, run.stdout, run.stderr


def font(size, *, mono=False, bold=False):
    family = "Courier New" if mono else "Arial"
    suffix = " Bold" if bold else ""
    windows = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    linux = "DejaVuSansMono" if mono else "DejaVuSans"
    candidates = [
        Path(f"/System/Library/Fonts/Supplemental/{family}{suffix}.ttf"),
        windows / ("cour.ttf" if mono else "arialbd.ttf" if bold else "arial.ttf"),
        Path(f"/usr/share/fonts/truetype/dejavu/{linux}{'-Bold' if bold else ''}.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    raise RuntimeError(
        "Install Arial/Courier New or DejaVu Sans/Mono to render the demo"
    )


def label(draw, xy, value, size=24, fill=INK, **kwargs):
    draw.text(xy, value, font=font(size, **kwargs), fill=fill)


def centered(draw, y, value, size=30, fill=INK, bold=False):
    f = font(size, bold=bold)
    draw.text(
        ((WIDTH - draw.textlength(value, font=f)) / 2, y), value, font=f, fill=fill
    )


def base(step, title):
    frame = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(frame)
    draw.rounded_rectangle((34, 30, 40, 69), radius=3, fill="#ff555e")
    label(draw, (54, 30), title, 34, bold=True)
    label(draw, (905, 43), f"0{step} / 05", 17, MUTED)
    return frame, draw


def footer(draw, text):
    centered(draw, 522, text, 16, MUTED)


def terminal(draw):
    draw.rounded_rectangle(
        (34, 115, 966, 492), radius=17, fill="#1c2530", outline="#344051"
    )
    for x, color in [(60, "#fa706b"), (81, "#e8ba60"), (102, "#78bd92")]:
        draw.ellipse((x, 133, x + 10, 143), fill=color)
    label(draw, (136, 128), "docx-color  /  local terminal", 17, MUTED)
    draw.line((35, 159, 965, 159), fill="#344051")


def rich_text(draw, items, x, y, width):
    f = font(28)
    content = "".join(c for c, _ in items)
    pos, start_x = 0, x
    for match in re.finditer(r"\S+\s*|\s+", content):
        word = match.group()
        size = sum(draw.textlength(c, font=f) for c in word.rstrip())
        if x > start_x and x + size > start_x + width:
            x, y = start_x, y + 37
        for c in word:
            kind = items[pos][1]
            color = {"inserted": "#2362a5", "deleted": "#798390", "red": "#ff0000"}.get(
                kind, "#202935"
            )
            advance = draw.textlength(c, font=f)
            draw.text((x, y), c, font=f, fill=color)
            if kind in {"inserted", "deleted"} and not c.isspace():
                offset = 29 if kind == "inserted" else 17
                draw.line((x, y + offset, x + advance, y + offset), fill=color, width=1)
            x += advance
            pos += 1
    assert y + 33 < 472, "Excerpt exceeds card bounds"


def render(scene, t, before, after, stdout):
    titles = [
        "docx-color-cli",
        "Two documents. One command.",
        "Actual CLI result",
        "See the change.",
        "docx-color-cli",
    ]
    frame, d = base(scene + 1, titles[scene])
    if scene == 0:
        label(d, (62, 139), "Highlight manuscript revisions.", 43, bold=True)
        label(d, (62, 198), "Without the manual work.", 36, MUTED)
        for x, name, badge, accent in [
            (62, "change_tracked.docx", "TRACKED CHANGES", "#2563a6"),
            (514, "change_accepted.docx", "ACCEPTED IN WORD", "#28775b"),
        ]:
            d.rounded_rectangle((x, 303, x + 424, 445), radius=15, fill="#f6f8fb")
            d.rounded_rectangle((x + 20, 323, x + 25, 425), radius=2, fill=accent)
            label(d, (x + 45, 327), badge, 17, accent, bold=True)
            label(d, (x + 45, 365), name, 25, "#192535", bold=True)
            label(d, (x + 45, 407), "Public example document", 17, "#606d7e")
        footer(d, "Free  •  Open source  •  Runs locally")
    elif scene == 1:
        terminal(d)
        count = min(len(COMMAND), int(t / 2.4 * len(COMMAND)))
        typed = COMMAND[:count]
        for i, line in enumerate(typed.split("\n")):
            label(d, (61, 190 + i * 48), line, 23, mono=True)
        lines = typed.split("\n")
        if int(t * 3) % 2 == 0:
            x = 61 + d.textlength(lines[-1], font=font(23, mono=True))
            d.rectangle(
                (
                    x + 3,
                    193 + (len(lines) - 1) * 48,
                    x + 13,
                    219 + (len(lines) - 1) * 48,
                ),
                fill="#ff747c",
            )
        footer(d, "This exact command was executed on the public examples.")
    elif scene == 2:
        terminal(d)
        for i, line in enumerate(stdout.rstrip().splitlines()):
            color = "#8de0ac" if "SUCCESS" in line else INK
            label(d, (61, 174 + i * 35), line, 23, color, mono=True)
        footer(d, "Validated DOCX published. No unresolved insertion candidates.")
    elif scene == 3:
        label(
            d,
            (54, 81),
            "A verified excerpt from the public example documents",
            19,
            MUTED,
        )
        for x, heading, items in [
            (34, "Before — Tracked Changes", before),
            (514, "After — Added Text in Red", after),
        ]:
            d.rounded_rectangle((x, 123, x + 452, 477), radius=15, fill="#ffffff")
            label(d, (x + 24, 143), heading, 21, "#3a4655", bold=True)
            d.line((x + 24, 182, x + 428, 182), fill="#dfe4eb")
            rich_text(d, items, x + 24, 201, 404)
        label(d, (58, 488), "Blue underline: inserted   •   Strike: deleted", 17, MUTED)
        label(d, (538, 488), "Red: verified output color (FF0000)", 17, MUTED)
        footer(
            d,
            "Rendered DOCX preview, not a Word screenshot. Actual CLI status: SUCCESS.",
        )
    else:
        centered(d, 165, "One command.", 54, bold=True)
        centered(d, 237, "No manual highlighting.", 42)
        centered(d, 329, "docx-color-cli", 28, "#ff747c", bold=True)
        centered(d, 386, "Free  •  Open source  •  Runs locally", 22, MUTED)
        footer(d, "Always review your document before sharing it.")
    return frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "assets/demo.gif")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="docx-demo-") as temp:
        before, after, stdout, stderr = verified_excerpt(Path(temp))
        print(stdout, end="")
        print(stderr, end="", file=sys.stderr)
        frames = []
        lengths = [1.5, 3, 2.5, 6, 2]
        previous = None
        for scene, seconds in enumerate(lengths):
            for tick in range(round(seconds * FPS)):
                frame = render(scene, tick / FPS, before, after, stdout)
                if previous is not None and tick < 3:
                    frame = Image.blend(previous, frame, (tick + 1) / 3)
                frames.append(frame)
            previous = frame
        # Fade the final scene back to the opening for a natural infinite loop.
        for i in range(3):
            frames[-3 + i] = Image.blend(previous, frames[0], (i + 1) / 3)
        contact = Image.new("RGB", (WIDTH, HEIGHT * 5))
        for i, frame_index in enumerate([9, 48, 72, 120, 168]):
            contact.paste(frames[frame_index], (0, HEIGHT * i))
        palette = contact.quantize(colors=256).getpalette()
        pal = Image.new("P", (1, 1))
        pal.putpalette(palette)
        frames = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        frames[0].save(
            args.output,
            save_all=True,
            append_images=frames[1:],
            duration=[80, 80, 90] * (len(frames) // 3),
            loop=0,
            optimize=True,
            disposal=1,
        )
        print(
            f"GIF: {args.output}; {WIDTH}x{HEIGHT}; {sum(lengths):g} seconds; {args.output.stat().st_size} bytes"
        )


if __name__ == "__main__":
    main()
