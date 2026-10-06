"""Installed translation catalogs determine settings choices and runtime locale selection."""

# standard imports
from pathlib import Path

# lib imports
import babel
import polib
import pytest

# local imports
from common import config, locales


def test_discover_catalogs(tmp_path, monkeypatch):
    monkeypatch.setattr(locales.Paths, 'LOCALE_DIR', str(tmp_path))
    for locale_id, filename in [
        ('ko', 'themerr.po'),
        ('pt_BR', 'themerr.po'),
        ('pt_BR', 'themerr.mo'),
        ('zh_TW', 'themerr.mo'),
        ('fr', 'other.po'),
    ]:
        messages = tmp_path / locale_id / 'LC_MESSAGES'
        messages.mkdir(parents=True, exist_ok=True)
        (messages / filename).touch()
    (tmp_path / 'themerr.po').touch()
    (tmp_path / 'de' / 'LC_MESSAGES').mkdir(parents=True)
    (tmp_path / 'es' / 'LC_MESSAGES' / 'themerr.po').mkdir(parents=True)

    assert locales.get_supported_locales() == ['en', 'ko', 'pt_BR', 'zh_TW']


def test_discover_missing_catalog_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(locales.Paths, 'LOCALE_DIR', str(tmp_path / 'missing'))
    assert locales.get_supported_locales() == ['en']


def test_repository_catalogs_are_settings_options_and_valid_locales():
    root = Path(__file__).resolve().parents[3] / 'locale'
    catalog_codes = {catalog.parent.parent.name for catalog in root.glob('*/LC_MESSAGES/themerr.po')}
    options = config._CONFIG_SPEC_DICT['General']['LOCALE']
    assert set(options['options']) == catalog_codes | {'en'}
    assert options['options'] == locales.supported_locales
    assert len(options['option_names']) == len(options['options'])
    for locale_id, name in zip(options['options'], options['option_names']):
        locale = babel.Locale.parse(locale_id)
        assert name == f'{locale.get_display_name("en")} ({locale.get_display_name()})'


@pytest.mark.parametrize('locale_id', locales.supported_locales)
def test_settings_locale_is_accepted_at_runtime(locale_id, monkeypatch):
    monkeypatch.setattr(config, 'CONFIG', {'General': {'LOCALE': locale_id}})
    assert locales.get_locale() == locale_id


@pytest.mark.parametrize('locale_id', locales.supported_locales)
def test_settings_locale_survives_config_validation(locale_id, tmp_path, monkeypatch):
    filename = tmp_path / 'config.ini'
    filename.write_text(f'[General]\nLOCALE = {locale_id}\n', encoding='utf-8')
    monkeypatch.setattr(config, 'CONFIG', None)
    result = config.create_config(str(filename))
    assert result['General']['LOCALE'] == locale_id


@pytest.mark.parametrize('value', [None, {'General': {'LOCALE': 'unsupported'}}])
def test_unavailable_locale_falls_back_to_english(value, monkeypatch):
    monkeypatch.setattr(config, 'CONFIG', value)
    assert locales.get_locale() == 'en'


def test_new_catalog_has_display_name_and_runtime_support(tmp_path, monkeypatch):
    messages = tmp_path / 'ko' / 'LC_MESSAGES'
    messages.mkdir(parents=True)
    (messages / 'themerr.po').touch()
    monkeypatch.setattr(locales.Paths, 'LOCALE_DIR', str(tmp_path))
    monkeypatch.setattr(locales, 'supported_locales', locales.get_supported_locales())
    monkeypatch.setattr(config, 'CONFIG', {'General': {'LOCALE': 'ko'}})
    assert locales.get_locale() == 'ko'
    assert locales.get_locale_names() == ['English (English)', 'Korean (한국어)']


def write_catalog(path, **messages):
    path.parent.mkdir(parents=True, exist_ok=True)
    catalog = polib.POFile()
    catalog.metadata = {'Content-Type': 'text/plain; charset=UTF-8',
                        'Plural-Forms': 'nplurals=2; plural=(n != 1);'}
    for message, translation in messages.items():
        catalog.append(polib.POEntry(msgid=message, msgstr=translation))
    catalog.save(str(path))
    return catalog


def test_source_catalog_overrides_stale_mo_and_reloads_edits(tmp_path, monkeypatch):
    monkeypatch.setattr(locales.Paths, 'LOCALE_DIR', str(tmp_path))
    path = tmp_path / 'fr' / 'LC_MESSAGES' / 'themerr.po'
    old = write_catalog(path, Settings='Ancien')
    old.save_as_mofile(str(path.with_suffix('.mo')))
    write_catalog(path, Settings='Paramètres')
    assert locales.get_translation('fr').gettext('Settings') == 'Paramètres'
    write_catalog(path, Settings='Nouveaux paramètres')
    assert locales.get_translation('fr').gettext('Settings') == 'Nouveaux paramètres'


def test_english_uses_root_source_without_an_english_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(locales.Paths, 'LOCALE_DIR', str(tmp_path))
    write_catalog(tmp_path / 'themerr.po', Greeting='Default greeting')
    write_catalog(tmp_path / 'en' / 'LC_MESSAGES' / 'themerr.po', Greeting='Old greeting')
    assert locales.get_translation('en').gettext('Greeting') == 'Default greeting'
    (tmp_path / 'en' / 'LC_MESSAGES' / 'themerr.po').unlink()
    assert locales.get_translation('en').gettext('Greeting') == 'Default greeting'
    assert locales.get_translation('en').gettext('Missing') == 'Missing'
    assert locales.get_translation('en_US').gettext('Greeting') == 'Default greeting'


def test_dynamic_translator_follows_setting_and_regional_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(locales.Paths, 'LOCALE_DIR', str(tmp_path))
    write_catalog(tmp_path / 'fr' / 'LC_MESSAGES' / 'themerr.po', Settings='Paramètres')
    monkeypatch.setattr(config, 'CONFIG', {'General': {'LOCALE': 'fr'}})
    translate = locales.get_text()
    assert translate('Settings') == 'Paramètres'
    config.CONFIG['General']['LOCALE'] = 'en'
    assert translate('Settings') == 'Settings'
    assert locales.get_translation('fr_CA').gettext('Settings') == 'Paramètres'


def test_plural_fuzzy_and_untranslated_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(locales.Paths, 'LOCALE_DIR', str(tmp_path))
    path = tmp_path / 'fr' / 'LC_MESSAGES' / 'themerr.po'
    catalog = write_catalog(path, Missing='')
    catalog.append(polib.POEntry(msgid='Fuzzy', msgstr='Unreviewed', flags=['fuzzy']))
    catalog.append(polib.POEntry(msgid='item', msgid_plural='items', msgstr_plural={0: 'objet', 1: 'objets'}))
    catalog.save(str(path))
    language = locales.get_translation('fr')
    assert language.gettext('Missing') == 'Missing'
    assert language.gettext('Fuzzy') == 'Fuzzy'
    assert language.ngettext('item', 'items', 1) == 'objet'
    assert language.ngettext('item', 'items', 2) == 'objets'
    assert not path.with_suffix('.mo').exists()
