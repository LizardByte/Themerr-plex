"""
src/common/locales.py

Functions related to localization.

Localization (also referred to as l10n) is the process of adapting a product or service to a specific locale.
Translation is only one of several elements in the localization process. In addition to translation, the localization
process may also include:
- Adapting design and layout to properly display translated text in the language of the locale
- Adapting sorting functions to the alphabetical order of a specific locale
- Changing formats for date and time, addresses, numbers, currencies, etc. for specific target locales
- Adapting graphics to suit the expectations and tastes of a target locale
- Modifying content to suit the tastes and consumption habits of a target locale

The aim of localization is to give a product or service the look and feel of having been created specifically for a
target market, no matter their language, cultural preferences, or location.
"""
# standard imports
import gettext
import builtins
import copy
from functools import lru_cache
from io import BytesIO as _BytesIO
import pathlib

# lib imports
import babel
from babel import localedata
import polib

# local imports
from common import config
from common.definitions import Names, Paths
from common import logger

default_domain = Names.name.lower()
default_locale = 'en'
default_timezone = 'UTC'

log = logger.get_logger(__name__)


def get_supported_locales() -> list[str]:
    """Return sorted locale codes with a PO or compiled MO catalog for this application.

    Include English as the default even when no catalogs are installed. Source templates,
    other gettext domains, and directories without catalogs do not add settings options.

    Returns
    -------
    list of str
        Available locale codes in alphabetical order, including the English default.

    Examples
    --------
    >>> get_supported_locales()
    ['aa', 'bg', ... 'en', ... 'zh_TW']
    """
    locale_dir = pathlib.Path(Paths.LOCALE_DIR)
    catalogs = set(locale_dir.glob(f'*/LC_MESSAGES/{default_domain}.po'))
    catalogs.update(locale_dir.glob(f'*/LC_MESSAGES/{default_domain}.mo'))
    return sorted({default_locale} | {catalog.parent.parent.name for catalog in catalogs if catalog.is_file()})


supported_locales = get_supported_locales()


def get_locale_names() -> list[str]:
    """Return English and native display names for supported locales.

    Names follow the order of ``supported_locales`` so each settings label matches its locale code.

    Returns
    -------
    list of str
        Settings labels containing each language's English and native display names.

    Examples
    --------
    >>> get_locale_names()
    [... 'English (English)', ... 'Korean (한국어)', ...]
    """
    names = []
    for locale_id in supported_locales:
        locale = babel.Locale.parse(locale_id)
        names.append(f'{locale.get_display_name("en")} ({locale.get_display_name()})')
    return names


def get_all_locales() -> dict:
    """
    Get a dictionary of all possible locales for use with babel.

    Dictionary keys will be `locale_id` and value with be `locale_display_name`.
    This is a shortened example of the returned value.

    .. code-block:: python

        {
          'de': 'Deutsch',
          'en': 'English',
          'en_GB': 'English (United Kingdom)',
          'en_US': 'English (United States)',
          'es': 'español',
          'fr': 'français',
          'it': 'italiano',
          'ru': 'русский'
        }

    Returns
    -------
    dict
        Dictionary of all possible locales.

    Examples
    --------
    >>> get_all_locales()
    {... 'en': 'English', ... 'en_GB': 'English (United Kingdom)', ... 'es': 'español', ... 'fr': 'français', ...}
    """
    log.debug(msg='Getting locale dictionary.')
    locale_ids = localedata.locale_identifiers()

    locales = {}

    for locale_id in locale_ids:
        locale = babel.Locale.parse(identifier=locale_id)
        locales[locale_id] = locale.get_display_name()

    return locales


def get_locale() -> str:
    """
    Verify the locale.

    Verify the locale from the config against supported locales and returns appropriate locale.

    Returns
    -------
    str
        The locale set in the config if it is valid, otherwise the default locale (en).

    Examples
    --------
    >>> get_locale()
    'en'
    """
    try:
        config_locale = config.CONFIG['General']['LOCALE']
    except (AttributeError, KeyError, TypeError):
        config_locale = None

    if config_locale in supported_locales:
        return config_locale
    else:
        return default_locale


@lru_cache(maxsize=32)
def _catalog(path: str, modified: int, size: int) -> gettext.GNUTranslations:
    """Read source catalogs in memory, retaining gettext plural and fuzzy-entry handling."""
    if path.endswith('.po'):
        return gettext.GNUTranslations(_BytesIO(polib.pofile(path).to_binary()))
    with open(path, 'rb') as stream:
        return gettext.GNUTranslations(stream)


def get_translation(locale_id: str | None = None) -> gettext.NullTranslations:
    """Load the selected source catalog without creating compiled files.

    Prefer PO over any older MO file. Cache parsing until the source changes and
    fall back to the base language for regional locales. MO-only installations
    remain supported.

    Parameters
    ----------
    locale_id : str or None, optional
        Locale to load, defaulting to the current setting.

    Returns
    -------
    gettext.NullTranslations
        Request-local gettext translations, or English message identifiers.

    Examples
    --------
    >>> get_translation('fr').gettext('Settings')
    'Paramètres'
    """
    locale_id = locale_id or get_locale()
    language = gettext.NullTranslations()
    for code in dict.fromkeys((locale_id, locale_id.split('_')[0], default_locale)):
        for extension in ('po', 'mo'):
            root = pathlib.Path(Paths.LOCALE_DIR)
            path = (root / f'{default_domain}.{extension}' if code == default_locale else
                    root / code / 'LC_MESSAGES' / f'{default_domain}.{extension}')
            if path.is_file():
                stat = path.stat()
                # Fallbacks belong to this call, never to the shared cached catalog.
                language.add_fallback(copy.copy(_catalog(str(path), stat.st_mtime_ns, stat.st_size)))
                break
    return language


def _gettext(message: str) -> str:
    """Resolve the setting when translating, including after a settings save."""
    return get_translation().gettext(message)


def get_text():
    """Install a translator that follows the current locale setting.

    Load source catalogs on demand so settings changes and catalog edits do not
    require compilation or an application restart.

    Returns
    -------
    gettext.gettext
        Callable translating through the current catalog on each invocation.

    Examples
    --------
    >>> get_text()
    <function _gettext at 0x...>
    """
    builtins._ = _gettext
    return _gettext
