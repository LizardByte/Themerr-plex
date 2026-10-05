"""Generic C# property signatures retain their type links in the public documentation."""

# standard imports
from pathlib import Path
import runpy

# lib imports
import pytest


@pytest.mark.parametrize('signature, expected', [
    (
        'DbSet< OwnershipEntry > Entries',
        'DbSet<OwnershipEntry> Entries',
    ),
    (
        'Dictionary< string, List< OwnershipEntry > > Entries',
        'Dictionary<string, List<OwnershipEntry>> Entries',
    ),
    (
        '  DbSet<\tOwnershipEntry\n>  Entries  ',
        '  DbSet<OwnershipEntry>  Entries  ',
    ),
    (
        'string Name',
        'string Name',
    ),
    (
        f'string {" " * 100_000}Name',
        f'string {" " * 100_000}Name',
    ),
], ids=[
    'generic-property',
    'nested-generics',
    'outer-spacing',
    'simple-property',
    'long-whitespace-without-brackets',
])
def test_property_signatures_preserve_spacing_outside_generic_brackets(monkeypatch, signature, expected):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(root / 'third-party/sphinx-csharp')
    from breathe.renderer.sphinxrenderer import CSharpProperty

    adapter = runpy.run_path(str(root / 'docs/connector_docs.py'))
    signode = object()

    def capture_signature(self, sig, node):
        assert node is signode
        return sig

    monkeypatch.setattr(CSharpProperty, 'handle_signature', capture_signature)
    property_type = adapter['_GenericProperty']
    directive = property_type.__new__(property_type)
    assert directive.handle_signature(signature, signode) == expected
