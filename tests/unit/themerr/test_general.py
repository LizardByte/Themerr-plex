# standard imports
import os
import shutil

# lib imports
import pytest

# local imports
from themerr import constants
from themerr import general


def test_get_metadata_path(section):
    test_items = [
        section.all()[0]
    ]

    for item in test_items:
        metadata_path = general._get_metadata_path(item=item)
        assert metadata_path.endswith('.bundle')
        assert os.path.isdir(metadata_path)


@pytest.mark.parametrize('item_agent, item_type, expected', [
    ('tv.plex.agents.movie', 'movie', True),
    ('tv.plex.agents.series', 'show', True),
    ('invalid', 'invalid', False),
])
def test_continue_update(item_agent, item_type, expected):
    assert general.continue_update(item_agent=item_agent) is expected


@pytest.mark.parametrize('media_type', ['art', 'posters', 'themes'])
def test_get_media_upload_path(section, media_type):
    test_items = [
        section.all()[0]
    ]

    for item in test_items:
        media_upload_path = general.get_media_upload_path(item=item, media_type=media_type)
        assert media_upload_path.endswith(os.path.join('.bundle', 'Uploads', media_type))
        # todo - test collections, with art and posters
        if media_type == 'themes':
            assert os.path.isdir(media_upload_path)


def test_get_theme_provider(section):
    test_items = [
        section.all()[0]
    ]

    for item in test_items:
        theme_provider = general.get_theme_provider(item=item)
        assert theme_provider
        assert isinstance(theme_provider, str)
        assert theme_provider == 'themerr'


def test_get_media_upload_path_invalid(section):
    test_items = [
        section.all()[0]
    ]

    with pytest.raises(ValueError):
        general.get_media_upload_path(item=test_items[0], media_type='invalid')


def test_get_themerr_json_path(section):
    test_items = [
        section.all()[0]
    ]

    for item in test_items:
        themerr_json_path = general.get_themerr_json_path(item=item)
        assert themerr_json_path.endswith('{}.json'.format(item.ratingKey))
        assert os.path.join('Plex Media Server', 'Plug-in Support', 'Data', constants.plugin_identifier,
                            'DataItems') in themerr_json_path


def test_get_themerr_json_data(section):
    test_items = [
        section.all()[0]
    ]

    for item in test_items:
        themerr_json_data = general.get_themerr_json_data(item=item)
        assert isinstance(themerr_json_data, dict)
        assert 'youtube_theme_url' in themerr_json_data.keys()


def test_get_themerr_settings_hash():
    themerr_settings_hash = general.get_themerr_settings_hash()
    assert themerr_settings_hash
    assert isinstance(themerr_settings_hash, str)

    # ensure hash is 256 bits long
    assert len(themerr_settings_hash) == 64


def test_remove_uploaded_media(section):
    test_items = [
        section.all()[0]
    ]

    for item in test_items:
        for media_type in ['themes']:  # todo - test art and posters
            # backup current directory
            current_directory = general.get_media_upload_path(item=item, media_type=media_type)
            assert os.path.isdir(current_directory)
            shutil.copytree(current_directory, '{}.bak'.format(current_directory))
            assert os.path.isdir('{}.bak'.format(current_directory))

            general.remove_uploaded_media(item=item, media_type=media_type)
            assert not os.path.isdir(current_directory)

            # restore backup
            shutil.move('{}.bak'.format(current_directory), current_directory)
            assert os.path.isdir(current_directory)


def test_remove_uploaded_media_error_handler():
    # just try to execute the error handler function
    general.remove_uploaded_media_error_handler(
        func=test_remove_uploaded_media_error_handler,
        path=os.getcwd(),
        exc_info=OSError
    )


def test_update_themerr_data_file(section):
    test_items = [
        section.all()[0]
    ]

    new_themerr_data = {
        'pytest': 'test'
    }

    for item in test_items:
        general.update_themerr_data_file(item=item, new_themerr_data=new_themerr_data)
        themerr_json_data = general.get_themerr_json_data(item=item)
        assert themerr_json_data['pytest'] == 'test'

        for key in general.legacy_keys:
            assert key not in themerr_json_data
