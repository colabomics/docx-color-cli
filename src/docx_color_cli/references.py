"""Read-only bookmark dependencies; never evaluate or rewrite editable fields.

Check dependencies that conversion breaks. Pre-existing broken references are
preserved (including their cached error/result), rather than silently repaired.
"""

import re
from collections import Counter

from .errors import ConversionError
from .package import R, W, discover_stories
from .revisions import HISTORY

STORIES = {
    W + n
    for n in (
        "body",
        "hdr",
        "ftr",
        "footnote",
        "endnote",
        "comment",
        "txbxContent",
        "docPartBody",
        "fldSimple",
    )
}
TOKEN = re.compile(r'"((?:\\"|[^"\n])*)"|([^\s"]+)')
UNRESOLVED = object()


def instruction_target(code):
    tokens = [a.replace('\\"', '"') if a else b for a, b in TOKEN.findall(code)]
    if not tokens:
        return None
    command = tokens[0].upper()
    if command in {"REF", "PAGEREF", "NOTEREF"}:
        return (
            tokens[1]
            if len(tokens) > 1 and not tokens[1].startswith("\\")
            else UNRESOLVED
        )
    if command == "HYPERLINK":
        location, bookmark, i = None, None, 1
        while i < len(tokens):
            token = tokens[i]
            if token.lower() in {"\\l", "\\o", "\\t", "\\*"}:
                if i + 1 == len(tokens):
                    return UNRESOLVED
                if token.lower() == "\\l":
                    if bookmark is not None:
                        return UNRESOLVED
                    bookmark = tokens[i + 1]
                i += 2
            elif token.lower() in {"\\h", "\\m", "\\n"}:
                i += 1
            elif token.startswith("\\") or location is not None:
                return UNRESOLVED
            else:
                location = token
                i += 1
        # Switch order does not determine locality; a file/URL operand does.
        return bookmark if not location else None
    return None


def dependencies(roots):
    """Return bookmark names and counts of literal local references per part.

    Nested fields are tracked separately; dynamic outer instructions containing a
    nested field are deliberately not guessed. Field/range balance is checked by
    package.validate_story on the accepted document.
    """
    bookmarks, refs, dynamic, conditional = Counter(), Counter(), set(), Counter()
    from .compatibility import BRANCHES

    for name, root in discover_stories(roots).items():

        def collect(code, part=name):
            target = instruction_target(code)
            if target is UNRESOLVED:
                dynamic.add(part)
            elif target and target != "_top":
                refs[part, target] += 1

        def story(container, part=name):
            stack = []

            def walk(node):
                if node.tag in {W + h for h in HISTORY}:
                    return
                if node.tag == W + "bookmarkStart":
                    target = node.get(W + "name")
                    bookmarks[target] += 1
                    branch = next(
                        (a for a in node.iterancestors() if a.tag in BRANCHES), None
                    )
                    if branch is not None:
                        conditional[
                            part, branch.getroottree().getpath(branch), target
                        ] += 1
                if node.tag == W + "hyperlink" and node.get(R + "id") is None:
                    anchor = node.get(W + "anchor")
                    if anchor and anchor != "_top":
                        refs[part, anchor] += 1
                if node is not container and node.tag in STORIES:
                    story(node)
                    return
                if node.tag == W + "fldSimple":
                    collect(node.get(W + "instr", ""))
                if node.tag == W + "fldChar":
                    kind = node.get(W + "fldCharType")
                    if kind == "begin":
                        if stack and not stack[-1]["result"]:
                            stack[-1]["dynamic"] = True
                        stack.append({"code": [], "result": False, "dynamic": False})
                    elif kind == "separate" and stack:
                        stack[-1]["result"] = True
                    elif kind == "end" and stack:
                        field = stack.pop()
                        code = "".join(field["code"])
                        if not field["dynamic"]:
                            collect(code)
                        elif re.match(
                            r"\s*(REF|PAGEREF|NOTEREF|HYPERLINK)\b", code, re.IGNORECASE
                        ):
                            dynamic.add(part)
                elif node.tag == W + "instrText" and stack and not stack[-1]["result"]:
                    stack[-1]["code"].append(node.text or "")
                for child in node:
                    walk(child)

            walk(container)

        story(root)
    return bookmarks, refs, dynamic, conditional


def validate_dependencies(before, roots):
    original_bookmarks, original_refs, _, original_conditional = before
    bookmarks, refs, dynamic, conditional = dependencies(roots)
    changed = {
        key[2]
        for key in set(original_conditional) | set(conditional)
        if original_conditional[key] != conditional[key]
    }
    if any(target in changed for _, target in refs):
        raise ValueError(
            "Conditional bookmark changes require branch-specific reference validation"
        )
    if dynamic and original_bookmarks != bookmarks:
        raise ValueError(
            "Cannot validate dynamic bookmark references after bookmark changes: "
            + ", ".join(sorted(dynamic))
        )
    for (part, target), count in refs.items():
        if bookmarks[target] == 1:
            continue
        # A pre-existing missing/ambiguous target is not created by acceptance.
        if original_bookmarks[target] != 1 and count <= original_refs[part, target]:
            continue
        raise ConversionError(
            f"acceptance leaves missing or ambiguous bookmark target {target!r}",
            part=part,
        )
