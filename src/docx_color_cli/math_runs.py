"""Split mixed OMML text streams without flattening mathematical objects."""
from copy import deepcopy
from lxml import etree
from .revisions import M, W, fail

PROPS = {M + 'rPr', W + 'rPr'}
EDITS = {W + 'ins', W + 'del'}


def mixed(run):
    payload = [n for n in run if n.tag not in PROPS]
    if not any(n.tag in EDITS for n in run.iterdescendants()):
        return False
    while len(payload) == 1 and payload[0].tag in EDITS:
        payload = [n for n in payload[0] if n.tag not in PROPS]
    return len(payload) > 1


def segments(run):
    """Yield text leaves, inherited property blocks and insertion ancestry."""
    result = []
    def visit(container, properties, inserted=False, deleted=False):
        local = [n for n in container if n.tag in PROPS]
        if len({n.tag for n in properties + local}) != len(properties + local):
            fail(container, 'ambiguous math run properties')
        properties = properties + local
        for child in container:
            if child.tag in PROPS:
                continue
            if child.tag in EDITS:
                visit(child, properties, inserted or child.tag == W + 'ins', deleted or child.tag == W + 'del')
            elif child.tag == M + 't' and not len(child):
                if not deleted:
                    result.append((child, properties, inserted))
            else:
                fail(child, 'unsupported mixed math run payload')
    visit(run, [])
    return result


def split_mixed_runs(root, stats=None):
    for run in list(root.iter(M + 'r')):
        if not mixed(run):
            continue
        planned = segments(run)
        parent, at = run.getparent(), run.getparent().index(run)
        for leaf, props, inserted in planned:
            replacement = etree.Element(M + 'r', attrib=dict(run.attrib))
            for prop in sorted(props, key=lambda p: p.tag != M + 'rPr'):
                replacement.append(deepcopy(prop))
            replacement.append(deepcopy(leaf))
            if inserted:
                wrapper = etree.Element(W + 'ins')
                wrapper.append(replacement)
                replacement = wrapper
            parent.insert(at, replacement)
            at += 1
        parent.remove(run)
        if stats is not None:
            stats['split_math_runs'] += 1
