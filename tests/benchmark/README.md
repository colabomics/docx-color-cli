# Public synthetic benchmark

Thirty-six independently authored scenarios cover ordinary text, formatting, elementary
mathematics, generic fields and hyperlinks, tables, headers, notes, Unicode,
ambiguous mapping and incompatible inputs. They are synthetic OOXML packages,
not Microsoft Word reference documents. No private-document data is used.

```bash
uv run python tests/benchmark/run.py --output .benchmark-output
uv run python tests/benchmark/run.py --original --output .benchmark-output/original
uv run pytest -q tests/test_benchmark.py
```

The ignored output directory contains each input pair, explicit expected labels,
two colored outputs per valid case, and aggregate results. The manifest and helper
sources define truth at `(part, paragraph ordinal, code-point offset)` and separate
mathematical-control coordinates. The fixture definitions import no converter or
alignment code. Unsupported insertions retain their INSERTED labels.

The independent stdlib XML/ZIP checker observes actual color changes against the
Accepted input. It checks content, non-color formatting and untouched package
parts. A fresh control color makes originally red inserted text observable; the
default-red no-op count is reported separately. The invalid pair must be refused
without publication and has no valid cross-document provenance denominator.

Metrics apply only to these authored scenarios. They are not universal accuracy
or Word-rendering guarantees. Mathematical controls are counted separately from
characters. Private inputs and generated outputs are never included in archives.

The original 30 scenarios retain their authored truth. Six additional table cases
exercise property siblings, replacements, repeated values, merged and nested
cells. Use `--original` to compare the unchanged corpus; expanded totals have a
different denominator and are reported separately.
