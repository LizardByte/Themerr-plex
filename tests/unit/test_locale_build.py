"""Locale compilation must work before the application has compiled translations."""

# standard imports
import gettext
import os
from pathlib import Path
import shutil
import subprocess
import sys


def build_tree(tmp_path):
    """Copy build inputs and fail if the application package is initialized."""
    root = Path(__file__).resolve().parents[2]
    (tmp_path / 'scripts').mkdir()
    common = tmp_path / 'src' / 'common'
    common.mkdir(parents=True)
    shutil.copyfile(root / 'scripts' / '_locale.py', tmp_path / 'scripts' / '_locale.py')
    shutil.copyfile(root / 'src' / 'common' / 'definitions.py', common / 'definitions.py')
    (common / '__init__.py').write_text("raise RuntimeError('Application initialized during locale compilation')\n")
    return tmp_path / 'scripts' / '_locale.py'


def test_locale_help_needs_no_application_or_dependencies(tmp_path):
    script = build_tree(tmp_path)
    result = subprocess.run([sys.executable, '-S', str(script), '--help'], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert '--compile' in result.stdout


def test_locale_compile_works_without_existing_translations(tmp_path):
    script = build_tree(tmp_path)
    messages = tmp_path / 'locale' / 'en' / 'LC_MESSAGES'
    messages.mkdir(parents=True)
    (messages / 'themerr-plex.po').write_text(
        'msgid ""\nmsgstr ""\n"Language: en\\n"\n"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
        'msgid "Theme"\nmsgstr "A theme"\n', encoding='utf-8',
    )
    environment = {**os.environ, 'PATH': str(Path(sys.executable).parent) + os.pathsep + os.environ.get('PATH', '')}
    result = subprocess.run([sys.executable, str(script), '--compile'], env=environment,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    with (messages / 'themerr-plex.mo').open('rb') as catalog:
        assert gettext.GNUTranslations(catalog).gettext('Theme') == 'A theme'
