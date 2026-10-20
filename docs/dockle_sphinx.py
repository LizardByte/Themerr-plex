"""Project Sphinx settings added to Dockle's generated configuration."""

# standard imports
import sys
import runpy

_MICROSOFT_SEARCH_URL = 'https://learn.microsoft.com/en-us/search/?scope=.NET&terms=%s'
_JELLYFIN_SEARCH_URL = 'https://github.com/jellyfin/jellyfin/search?q=%s&type=code'
_ASPNETCORE_MVC_NAMESPACE = 'Microsoft.AspNetCore.Mvc'
_EXTENSIONS_LOGGING_NAMESPACE = 'Microsoft.Extensions.Logging'
_ENTITY_FRAMEWORK_CORE_NAMESPACE = 'Microsoft.EntityFrameworkCore'

# Add the standalone source tree for autodoc.
sys.path.insert(0, str(dockle_project_root / 'src'))  # noqa: F821 - injected by Dockle

extensions.extend(  # noqa: F821 - injected by Dockle
    [
        'sphinx_csharp',
        'breathe',
        'numpydoc',
        'sphinx.ext.autosectionlabel',
        'sphinx.ext.intersphinx',
        'sphinx.ext.todo',
        'sphinx.ext.viewcode',
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
compatibility = runpy.run_path(
    str(dockle_project_root / 'src/jellyfin/compatibility.py'),  # noqa: F821 - injected by Dockle
)
profile = compatibility['PROFILES'][compatibility['DEFAULT_SERIES']]
framework = profile['ConnectorFramework']
dotnet_version = framework.removeprefix('net')
jellyfin_version = profile['JellyfinMinimumVersion']
jellyfin_tag = jellyfin_version.removesuffix('.0') if int(jellyfin_version.split('.')[0]) >= 12 else jellyfin_version
jellyfin_source = f'https://github.com/jellyfin/jellyfin/blob/v{jellyfin_tag}'
efcore_version = profile['ConnectorEfCoreVersion']
efcore_doc_version = '.'.join(efcore_version.split('.')[:2])

breathe_default_project = 'Themerr.Connector'
breathe_projects = {
    breathe_default_project: str(dockle_project_root / '_site' / 'connector' / 'xml'),  # noqa: F821
}
breathe_domain_by_extension = {'cs': 'cs'}
sphinx_csharp_multi_language = True
sphinx_csharp_check_external_links = True
sphinx_csharp_external_search_pages = {
    'msdn': (
        f'https://learn.microsoft.com/en-us/dotnet/api/%s?view=net-{dotnet_version}',
        _MICROSOFT_SEARCH_URL,
    ),
    _ASPNETCORE_MVC_NAMESPACE: (
        f'https://learn.microsoft.com/en-us/dotnet/api/%s?view=aspnetcore-{dotnet_version}',
        _MICROSOFT_SEARCH_URL,
    ),
    _EXTENSIONS_LOGGING_NAMESPACE: (
        f'https://learn.microsoft.com/en-us/dotnet/api/%s?view=net-{dotnet_version}',
        _MICROSOFT_SEARCH_URL,
    ),
    _ENTITY_FRAMEWORK_CORE_NAMESPACE: (
        f'https://learn.microsoft.com/en-us/dotnet/api/%s?view=efcore-{efcore_doc_version}',
        _MICROSOFT_SEARCH_URL,
    ),
    'Jellyfin.Common.Configuration': (
        f'{jellyfin_source}/MediaBrowser.Common/Configuration/%s.cs',
        _JELLYFIN_SEARCH_URL,
    ),
    'Jellyfin.Common.Plugins': (
        f'{jellyfin_source}/MediaBrowser.Common/Plugins/%s.cs',
        _JELLYFIN_SEARCH_URL,
    ),
    'Jellyfin.Controller.Library': (
        f'{jellyfin_source}/MediaBrowser.Controller/Library/%s.cs',
        _JELLYFIN_SEARCH_URL,
    ),
    'Jellyfin.Model.Plugins': (
        f'{jellyfin_source}/MediaBrowser.Model/Plugins/%s.cs',
        _JELLYFIN_SEARCH_URL,
    ),
    'Jellyfin.Model.Serialization': (
        f'{jellyfin_source}/MediaBrowser.Model/Serialization/%s.cs',
        _JELLYFIN_SEARCH_URL,
    ),
}
sphinx_csharp_external_type_map = {
    _ASPNETCORE_MVC_NAMESPACE: {
        _ASPNETCORE_MVC_NAMESPACE: [
            'ActionResult-1',
            'ControllerBase',
        ],
    },
    _EXTENSIONS_LOGGING_NAMESPACE: {_EXTENSIONS_LOGGING_NAMESPACE: ['ILogger-1']},
    _ENTITY_FRAMEWORK_CORE_NAMESPACE: {
        _ENTITY_FRAMEWORK_CORE_NAMESPACE: [
            'DbContext',
            'DbContextOptions-1',
            'DbSet-1',
            'ModelBuilder',
        ],
        'Microsoft.EntityFrameworkCore.Infrastructure': ['ModelSnapshot'],
        'Microsoft.EntityFrameworkCore.Migrations': [
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
    'BasePlugin': 'BasePluginOfT',
}
