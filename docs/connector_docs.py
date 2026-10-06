"""Adapt Doxygen's generic property spacing for the pinned Sphinx C# domain."""

# lib imports
from breathe.renderer.sphinxrenderer import CSharpProperty, DomainDirectiveFactory


class _GenericProperty(CSharpProperty):
    """Preserve type references when Doxygen inserts spaces inside generic types."""

    def handle_signature(self, sig, signode):
        """Normalize generic brackets before the upstream property parser runs."""
        # Split on brackets so whitespace runs are visited once without regex backtracking.
        parts = sig.split('<')
        compact = '<'.join([
            parts[0],
            *(part.lstrip() for part in parts[1:]),
        ])
        parts = compact.split('>')
        compact = '>'.join([
            *(part.rstrip() for part in parts[:-1]),
            parts[-1],
        ])
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
