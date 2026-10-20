"""The upstream C# domain renders connector signatures and dependency links."""

# standard imports
from io import StringIO
from pathlib import Path
import runpy

# lib imports
import pytest


@pytest.fixture(scope='module')
def connector_docs(tmp_path_factory):
    """Build C# signatures with the project's external link configuration."""
    application = pytest.importorskip('sphinx.application', reason='Requires the docs extra')
    extrefs = pytest.importorskip('sphinx_csharp.extrefs', reason='Requires the docs extra')
    root = Path(__file__).resolve().parents[2]
    config = runpy.run_path(str(root / 'docs/dockle_sphinx.py'), init_globals={
        'dockle_project_root': root,
        'extensions': [],
    })
    source = tmp_path_factory.mktemp('connector-docs')
    (source / 'conf.py').write_text("extensions = ['sphinx_csharp', 'breathe']\n", encoding='utf-8')
    (source / 'index.rst').write_text('\n'.join([
        'Connector signatures',
        '====================',
        '',
        '.. cs:class:: OwnershipEntry',
        '',
        '.. cs:property:: DbSet< OwnershipEntry > Entries',
        '',
        '.. cs:property:: Dictionary< string, List< OwnershipEntry > > NestedEntries',
        '',
        '.. cs:property:: DbSet<  OwnershipEntry  > SpacedEntries',
        '',
        '.. cs:property:: string Name',
        '',
        f'.. cs:property:: string {" " * 100_000}LongWhitespace',
        '',
        ':cs:type:`Guid` :cs:type:`CancellationToken` :cs:type:`Task`',
        r':cs:type:`ActionResult\<OwnershipEntry>` :cs:type:`ILogger\<OwnershipEntry>`',
        r':cs:type:`DbContextOptions\<OwnershipEntry>` :cs:type:`ModelSnapshot`',
        r':cs:type:`IApplicationPaths` :cs:type:`BasePlugin\<OwnershipEntry>`',
        ':cs:type:`ILibraryManager` :cs:type:`BasePluginConfiguration` :cs:type:`IXmlSerializer`',
        '',
    ]), encoding='utf-8')
    settings = {name: value for name, value in config.items() if name.startswith('sphinx_csharp_')}
    warnings = StringIO()
    with pytest.MonkeyPatch.context() as patch:
        # Keep external services out of the build while exercising link checking.
        patch.setattr(extrefs, 'link_status', lambda url: 200)
        app = application.Sphinx(
            srcdir=source,
            confdir=source,
            outdir=source / 'html',
            doctreedir=source / 'doctrees',
            buildername='html',
            confoverrides=settings,
            status=StringIO(),
            warning=warnings,
            freshenv=True,
        )
        app.build(force_all=True)
    assert warnings.getvalue() == ''
    return app.env.get_and_resolve_doctree('index', app.builder, tags=app.tags)


@pytest.mark.parametrize('expected', [
    'DbSet<OwnershipEntry>Entries',
    'Dictionary<string,List<OwnershipEntry>>NestedEntries',
    'DbSet<OwnershipEntry>SpacedEntries',
    'stringName',
    'stringLongWhitespace',
])
def test_property_signatures_render_without_adapter(connector_docs, expected):
    from sphinx import addnodes

    signatures = [
        ''.join(node.astext().split())
        for node in connector_docs.findall(addnodes.desc_signature)
    ]
    assert expected in signatures


@pytest.mark.parametrize('url_suffix', [
    '/dotnet/api/Microsoft.EntityFrameworkCore.DbSet-1?view=efcore-10.0',
    '/dotnet/api/Microsoft.EntityFrameworkCore.DbContextOptions-1?view=efcore-10.0',
    '/dotnet/api/Microsoft.EntityFrameworkCore.Infrastructure.ModelSnapshot?view=efcore-10.0',
    '/dotnet/api/Microsoft.AspNetCore.Mvc.ActionResult-1?view=aspnetcore-10.0',
    '/dotnet/api/Microsoft.Extensions.Logging.ILogger-1?view=net-10.0',
    '/dotnet/api/System.Guid?view=net-10.0',
    '/dotnet/api/System.Threading.CancellationToken?view=net-10.0',
    '/dotnet/api/System.Threading.Tasks.Task?view=net-10.0',
    '/MediaBrowser.Common/Configuration/IApplicationPaths.cs',
    '/MediaBrowser.Common/Plugins/BasePluginOfT.cs',
    '/MediaBrowser.Controller/Library/ILibraryManager.cs',
    '/MediaBrowser.Model/Plugins/BasePluginConfiguration.cs',
    '/MediaBrowser.Model/Serialization/IXmlSerializer.cs',
])
def test_dependency_type_links_keep_namespaces_and_generic_arity(connector_docs, url_suffix):
    from docutils import nodes

    links = [node['refuri'] for node in connector_docs.findall(nodes.reference) if 'refuri' in node]
    assert any(link.endswith(url_suffix) for link in links)
