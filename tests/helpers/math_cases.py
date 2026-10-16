"""Fresh elementary math fixtures with explicitly authored character/control truth."""

from html import escape

from .corpus import Case, ins, p, run
from .field_cases import frame

NEW, OLD = "INSERTED", "UNCHANGED"
FONT = '<w:rFonts w:ascii="Cambria Math"/><w:color w:val="3355AA"/><w:sz w:val="22"/>'


def mr(text, new=False, props=FONT):
    payload = "<w:rPr>" + props + "</w:rPr><m:t>" + escape(text) + "</m:t>"
    return (
        "<m:r>"
        + ('<w:ins w:id="47">' + payload + "</w:ins>" if new else payload)
        + "</m:r>"
    )


def eq(content):
    return "<m:oMath>" + content + "</m:oMath>"


def whole(content):
    return '<w:ins w:id="48">' + eq(content) + "</w:ins>"


def control(new=False):
    content = "<w:rPr>" + FONT + "</w:rPr>"
    return (
        "<m:ctrlPr>"
        + ('<w:ins w:id="49">' + content + "</w:ins>" if new else content)
        + "</m:ctrlPr>"
    )


def fraction(a, b, *, explicit=True):
    return (
        "<m:f>"
        + ("<m:fPr>" + control() + "</m:fPr>" if explicit else "")
        + "<m:num>"
        + a
        + "</m:num><m:den>"
        + b
        + "</m:den></m:f>"
    )


def cases():
    rows = []

    def add(name, source, target, spans, controls=(), missed=0, missed_controls=0):
        rows.append(
            (
                Case(name, name.replace("_", " "), source, target, spans),
                set(controls),
                missed,
                missed_controls,
            )
        )

    add("math_whole", frame(whole(mr("q=7"))), frame(eq(mr("q=7"))), [[("q=7", NEW)]])
    add(
        "math_variable",
        frame(eq(mr("u+") + mr("κ", True) + mr("v"))),
        frame(eq(mr("u+") + mr("κ") + mr("v"))),
        [[("u+", OLD), ("κ", NEW), ("v", OLD)]],
    )
    add(
        "math_separate_edits",
        frame(eq(mr("q") + mr("+", True) + mr("8", True))),
        frame(eq(mr("q") + mr("+") + mr("8"))),
        [[("q", OLD), ("+8", NEW)]],
    )
    f = fraction(mr("7"), mr("t"))
    add("math_fraction", frame(whole(f)), frame(eq(f)), [[("7t", NEW)]], [(0, 0)])
    add(
        "math_partial_fraction",
        frame(eq(fraction(mr("κ", True) + mr("u"), mr("v")))),
        frame(eq(fraction(mr("κ") + mr("u"), mr("v")))),
        [[("κ", NEW), ("uv", OLD)]],
    )
    for name, kind, args in [
        ("math_radical", "rad", [("deg", "4"), ("e", "q")]),
        ("math_scripts", "sSubSup", [("e", "v"), ("sub", "j"), ("sup", "7")]),
        ("math_sum", "nary", [("sub", "j=0"), ("sup", "m"), ("e", "b")]),
    ]:
        properties = '<m:chr m:val="∑"/>' if kind == "nary" else ""
        content = (
            f"<m:{kind}><m:{kind}Pr>{properties}"
            + control()
            + f"</m:{kind}Pr>"
            + "".join(f"<m:{tag}>" + mr(value) + f"</m:{tag}>" for tag, value in args)
            + f"</m:{kind}>"
        )
        add(
            name,
            frame(whole(content)),
            frame(eq(content)),
            [[("".join(value for _, value in args), NEW)]],
            [(0, 0)],
        )
    matrix = (
        "<m:m><m:mPr>"
        + control()
        + "</m:mPr><m:mr><m:e>"
        + mr("a")
        + "</m:e><m:e>"
        + mr("b")
        + "</m:e></m:mr><m:mr><m:e>"
        + mr("c")
        + "</m:e><m:e>"
        + mr("d")
        + "</m:e></m:mr></m:m>"
    )
    add(
        "math_matrix",
        frame(whole(matrix)),
        frame(eq(matrix)),
        [[("abcd", NEW)]],
        [(0, 0)],
    )
    add("math_original", frame(eq(f)), frame(eq(f)), [[("7t", OLD)]])
    add(
        "math_same_objects",
        frame(eq(mr("q")) + whole(mr("q"))),
        frame(eq(mr("q")) * 2),
        [[("q", OLD), ("q", NEW)]],
    )
    add(
        "math_two_fractions",
        frame(eq(f) + whole(f)),
        frame(eq(f) * 2),
        [[("7t", OLD), ("7t", NEW)]],
        [(1, 0)],
    )
    add(
        "math_ordered_objects",
        frame(eq(mr("a")) + whole(mr("b")) + eq(mr("c"))),
        frame(eq(mr("a")) + eq(mr("b")) + eq(mr("c"))),
        [[("a", OLD), ("b", NEW), ("c", OLD)]],
    )
    add(
        "math_with_prose",
        frame(run("Keep ") + whole(mr("q=7")) + ins(" done")),
        frame(run("Keep ") + eq(mr("q=7")) + run(" done")),
        [[("Keep ", OLD), ("q=7 done", NEW)]],
    )
    add(
        "math_unicode",
        frame(whole(mr("θ≤中"))),
        frame(eq(mr("θ≤中"))),
        [[("θ≤中", NEW)]],
    )
    add(
        "math_target_run_merged",
        frame(eq(mr("u") + mr("+", True) + mr("v"))),
        frame(eq(mr("u+v"))),
        [[("u", OLD), ("+", NEW), ("v", OLD)]],
        missed=1,
    )
    add(
        "math_duplicate_paragraphs",
        p(eq(mr("q"))) + p(whole(mr("q"))),
        p(eq(mr("q"))) * 2,
        [[("q", OLD)], [("q", NEW)]],
        missed=1,
    )
    add(
        "math_unknown_object",
        frame(whole("<m:unknown>" + mr("q") + "</m:unknown>")),
        frame(eq("<m:unknown>" + mr("q") + "</m:unknown>")),
        [[("q", NEW)]],
        missed=1,
    )
    add(
        "math_implicit_control",
        frame(whole(fraction(mr("7"), mr("t"), explicit=False))),
        frame(eq(fraction(mr("7"), mr("t"), explicit=False))),
        [[("7t", NEW)]],
        missed_controls=1,
    )
    red = '<w:color w:val="FF0000"/><w:i/>'
    add(
        "math_existing_red",
        frame(eq(mr("a", props=red) + mr("b", True, props=red))),
        frame(eq(mr("a", props=red) + mr("b", props=red))),
        [[("a", OLD), ("b", NEW)]],
    )
    controlled = fraction(mr("7"), mr("t"))
    add(
        "math_control_only",
        frame(eq(controlled.replace(control(), control(True)))),
        frame(eq(controlled)),
        [[("7t", OLD)]],
        missed_controls=1,
    )
    styled = (
        '<m:r><m:rPr><m:sty m:val="p"/></m:rPr><w:rPr>'
        + FONT
        + "<w:i/></w:rPr><m:t>r≤8</m:t></m:r>"
    )
    add("math_styled", frame(whole(styled)), frame(eq(styled)), [[("r≤8", NEW)]])
    return rows
