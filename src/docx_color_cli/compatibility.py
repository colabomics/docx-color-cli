"""Preserve all AlternateContent alternatives, validating each branch independently."""
from .revisions import fail

MC = '{http://schemas.openxmlformats.org/markup-compatibility/2006}'
BRANCHES = {MC + 'Choice', MC + 'Fallback'}


def validate_alternatives(root):
    for node in root.iter(MC + 'AlternateContent'):
        choices = node.findall(MC + 'Choice')
        fallbacks = node.findall(MC + 'Fallback')
        if not choices or len(fallbacks) > 1 or any(c.tag not in BRANCHES for c in node):
            fail(node, 'malformed AlternateContent branches')
        if fallbacks and node[-1] is not fallbacks[0]:
            fail(node, 'AlternateContent Fallback must follow Choices')
        for choice in choices:
            required = choice.get('Requires', '').split()
            if not required or any(prefix not in choice.nsmap for prefix in required):
                fail(choice, 'AlternateContent has missing/unbound Requires prefixes')
