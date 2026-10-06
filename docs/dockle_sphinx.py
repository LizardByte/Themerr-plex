"""Project Sphinx settings added to Dockle's generated configuration."""

# standard imports
import sys
import xml.etree.ElementTree as ET

# Add the standalone source tree for autodoc.
sys.path.insert(0, str(dockle_project_root / 'src'))  # noqa: F821 - injected by Dockle
sys.path.insert(0, str(dockle_project_root / 'third-party' / 'sphinx-csharp'))  # noqa: F821
sys.path.insert(0, str(dockle_project_root / 'docs'))  # noqa: F821

extensions.extend(  # noqa: F821 - injected by Dockle
    [
        'breathe',
        'connector_docs',
        'numpydoc',
        'sphinx.ext.autosectionlabel',
        'sphinx.ext.intersphinx',
        'sphinx.ext.todo',
        'sphinx.ext.viewcode',
        'sphinx_csharp',
    ]
)

autodoc_preserve_defaults = True
autosectionlabel_prefix_document = True
todo_include_todos = True
numpydoc_validation_checks = {
    'all',
    'SA01',
}
numpydoc_validation_exclude = {
    # Sphinx 9 exposes imported library objects through automodule; their
    # upstream docstrings are outside this project's NumPy style contract.
    r'^(?:common(?:\.[^.]+)?|main)\.(?:Union|ConfigObj|ValidateError|Validator|datetime|timedelta|'
    r'quote|quote_plus|unquote|unquote_plus|QueueHandler|QueueListener|Icon|Menu|MenuItem|'
    r'APIRouter|Depends|FastAPI|Request|HTTPException|'
    r'Response|JSONResponse|PlainTextResponse|StreamingResponse|FileResponse|ClientDisconnect|FormData|'
    r'SessionMiddleware|StaticFiles|run_in_threadpool|MutableHeaders|Jinja2Templates|URLSafeTimedSerializer|'
    r'BadSignature|Event|Path|secure_filename|lru_cache)$',
}
numpydoc_show_class_members = True
numpydoc_show_inherited_class_members = False
numpydoc_class_members_toctree = False
numpydoc_xref_param_type = True
suppress_warnings = ['epub.unknown_project_files']

python_version = f'{sys.version_info.major}.{sys.version_info.minor}'
intersphinx_mapping = {
    'python': (
        f'https://docs.python.org/{python_version}/',
        None,
    ),
    'plexapi': (
        'https://python-plexapi.readthedocs.io/en/latest/',
        None,
    ),
}

# Match public dependency links to the connector's default Jellyfin build.
connector_project = ET.parse(
    dockle_project_root / 'connectors' / 'jellyfin' / 'Themerr.Connector.csproj',  # noqa: F821 - injected by Dockle
).getroot()
framework = connector_project.findtext('./PropertyGroup/ConnectorFramework')
dotnet_version = framework.removeprefix('net')
jellyfin_version = connector_project.findtext('./PropertyGroup/JellyfinVersion')
jellyfin_tag = jellyfin_version.removesuffix('.0') if int(jellyfin_version.split('.')[0]) >= 12 else jellyfin_version
jellyfin_source = f'https://github.com/jellyfin/jellyfin/blob/v{jellyfin_tag}'
efcore_version = next(
    package.attrib['Version']
    for package in connector_project.iter('PackageReference')
    if package.attrib['Include'] == 'Microsoft.EntityFrameworkCore.Sqlite'
    and framework in package.attrib.get('Condition', '')
)
efcore_doc_version = '.'.join(efcore_version.split('.')[:2])

breathe_default_project = 'Themerr.Connector'
breathe_projects = {
    breathe_default_project: str(dockle_project_root / '_site' / 'connector' / 'xml'),  # noqa: F821
}
breathe_domain_by_extension = {'cs': 'cs'}
sphinx_csharp_multi_language = True
sphinx_csharp_test_links = True
sphinx_csharp_ext_search_pages = {
    'msdn': (f'https://learn.microsoft.com/en-us/dotnet/api/%s?view=net-{dotnet_version}',),
    'System': (f'https://learn.microsoft.com/en-us/dotnet/api/system.%s?view=net-{dotnet_version}',),
    'Microsoft.AspNetCore.Mvc': (
        f'https://learn.microsoft.com/en-us/dotnet/api/microsoft.aspnetcore.mvc.%s?view=aspnetcore-{dotnet_version}',
    ),
    'Microsoft.Extensions.Logging': (
        f'https://learn.microsoft.com/en-us/dotnet/api/microsoft.extensions.logging.%s?view=net-{dotnet_version}',
    ),
    'Microsoft.EntityFrameworkCore': (
        'https://learn.microsoft.com/en-us/dotnet/api/'
        f'microsoft.entityframeworkcore.%s?view=efcore-{efcore_doc_version}',
    ),
    'Jellyfin.Common.Configuration': (f'{jellyfin_source}/MediaBrowser.Common/Configuration/%s.cs',),
    'Jellyfin.Common.Plugins': (f'{jellyfin_source}/MediaBrowser.Common/Plugins/%s.cs',),
    'Jellyfin.Controller.Library': (f'{jellyfin_source}/MediaBrowser.Controller/Library/%s.cs',),
    'Jellyfin.Model.Plugins': (f'{jellyfin_source}/MediaBrowser.Model/Plugins/%s.cs',),
    'Jellyfin.Model.Serialization': (f'{jellyfin_source}/MediaBrowser.Model/Serialization/%s.cs',),
}
sphinx_csharp_ext_type_map = {
    'System': {
        '': [
            'Exception',
            'Guid',
        ],
        'IO': ['Stream'],
        'Threading': ['CancellationToken'],
        'Threading.Tasks': ['Task'],
    },
    'Microsoft.AspNetCore.Mvc': {
        '': [
            'ActionResult',
            'ControllerBase',
        ],
    },
    'Microsoft.Extensions.Logging': {'': ['ILogger']},
    'Microsoft.EntityFrameworkCore': {
        '': [
            'DbContext',
            'DbContextOptions',
            'DbSet',
            'ModelBuilder',
        ],
        'Infrastructure': ['ModelSnapshot'],
        'Migrations': [
            'Migration',
            'MigrationBuilder',
        ],
    },
    'Jellyfin.Common.Configuration': {'': ['IApplicationPaths']},
    'Jellyfin.Common.Plugins': {'': ['BasePlugin']},
    'Jellyfin.Controller.Library': {'': ['ILibraryManager']},
    'Jellyfin.Model.Plugins': {'': ['BasePluginConfiguration']},
    'Jellyfin.Model.Serialization': {'': ['IXmlSerializer']},
}
sphinx_csharp_external_type_rename = {
    'ActionResult': 'ActionResult-1',
    'DbContextOptions': 'DbContextOptions-1',
    'DbSet': 'DbSet-1',
    'ILogger': 'ILogger-1',
    'BasePlugin': 'BasePluginOfT',
}
