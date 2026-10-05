"""Adapt Doxygen's generic property spacing for the pinned Sphinx C# domain."""

# standard imports
import re

# lib imports
from breathe.renderer.sphinxrenderer import CSharpProperty, DomainDirectiveFactory


class _GenericProperty(CSharpProperty):
    """Preserve type references when Doxygen inserts spaces inside generic types."""

    def handle_signature(self, sig, signode):
        """Normalize generic brackets before the upstream property parser runs."""
        compact = re.sub(r'<\s*|\s*>', lambda match: match.group().strip(), sig)
        return super().handle_signature(compact, signode)


def setup(app):
    """Register the property adapter without modifying the pinned dependency."""
    app.setup_extension('sphinx_csharp')
    # Breathe constructs C# directives through its own factory instead of Sphinx's registry.
    DomainDirectiveFactory.cs_classes['property'] = (
        _GenericProperty,
        'property',
    )
    return {
        'parallel_read_safe': True,
        'parallel_write_safe': True,
    }
