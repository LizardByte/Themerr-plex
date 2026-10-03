"""Project Sphinx settings added to Dockle's generated configuration."""

# standard imports
import sys

# Add the standalone source tree for autodoc.
sys.path.insert(0, str(dockle_project_root / 'src'))  # noqa: F821 - injected by Dockle

extensions.extend([  # noqa: F821 - injected by Dockle
    'numpydoc',
    'sphinx.ext.autosectionlabel',
    'sphinx.ext.intersphinx',
    'sphinx.ext.todo',
    'sphinx.ext.viewcode',
])

autodoc_preserve_defaults = True
autosectionlabel_prefix_document = True
todo_include_todos = True
numpydoc_validation_checks = {'all', 'SA01'}
numpydoc_validation_exclude = {
    # Sphinx 9 exposes imported library objects through automodule; their
    # upstream docstrings are outside this project's NumPy style contract.
    r'^(?:common(?:\.[^.]+)?|themerr_plex)\.(?:Union|ConfigObj|ValidateError|Validator|datetime|timedelta|'
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
    'python': (f'https://docs.python.org/{python_version}/', None),
    'plexapi': ('https://python-plexapi.readthedocs.io/en/latest/', None),
}
