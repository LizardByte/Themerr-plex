# -*- coding: utf-8 -*-

# standard imports
import os
import shutil

# lib imports
import pytest

# local imports
from Code import constants
from Code import general_helper


def test_get_media_upload_path(movies):
    test_items = [
        movies.all()[0]
    ]

    media_types = ['art', 'posters', 'themes']

    for item in test_items:
        for media_type in media_types:
            media_upload_path = general_helper.get_media_upload_path(item=item, media_type=media_type)
            assert media_upload_path.endswith(os.path.join('.bundle', 'Uploads', media_type))
            # todo - test collections, with art and posters
            if media_type == 'themes':
                assert os.path.isdir(media_upload_path)


def test_get_media_upload_path_invalid(movies):
    test_items = [
        movies.all()[0]
    ]

    with pytest.raises(ValueError):
        general_helper.get_media_upload_path(item=test_items[0], media_type='invalid')


def test_get_themerr_json_path(movies):
    test_items = [
        movies.all()[0]
    ]

    for item in test_items:
        themerr_json_path = general_helper.get_themerr_json_path(item=item)
        assert themerr_json_path.endswith('{}.json'.format(item.ratingKey))
        assert os.path.join('Plex Media Server', 'Plug-in Support', 'Data', constants.plugin_identifier,
                            'DataItems') in themerr_json_path


def test_get_themerr_json_data(movies):
    test_items = [
        movies.all()[0]
    ]

    for item in test_items:
        themerr_json_data = general_helper.get_themerr_json_data(item=item)
        assert isinstance(themerr_json_data, dict)
        assert 'youtube_theme_url' in themerr_json_data.keys()


@pytest.mark.parametrize('ip_address', [(None, None), ('8.8.8.8', 'US'), ('193.110.81.0', 'FR')])
def test_get_user_country_code(ip_address):
    user_country_code = general_helper.get_user_country_code(ip_address=ip_address[0])
    assert user_country_code
    assert isinstance(user_country_code, str)

    # ensure country code is 2 characters long
    assert len(user_country_code) == 2

    if ip_address[1]:
        assert user_country_code == ip_address[1]


@pytest.mark.parametrize('ip_address', [(None, None), ('8.8.8.8', False), ('193.110.81.0', True)])
def test_is_user_in_eu(ip_address):
    is_user_in_eu = general_helper.is_user_in_eu(ip_address=ip_address[0])
    assert isinstance(is_user_in_eu, bool)

    if ip_address[1] is not None:
        assert is_user_in_eu == ip_address[1]


def test_get_themerr_settings_hash():
    themerr_settings_hash = general_helper.get_themerr_settings_hash()
    assert themerr_settings_hash
    assert isinstance(themerr_settings_hash, str)

    # ensure hash is 256 bits long
    assert len(themerr_settings_hash) == 64


def test_remove_uploaded_media(movies):
    test_items = [
        movies.all()[0]
    ]

    for item in test_items:
        for media_type in ['themes']:  # todo - test art and posters
            # backup current directory
            current_directory = general_helper.get_media_upload_path(item=item, media_type=media_type)
            assert os.path.isdir(current_directory)
            shutil.copytree(current_directory, '{}.bak'.format(current_directory))
            assert os.path.isdir('{}.bak'.format(current_directory))

            general_helper.remove_uploaded_media(item=item, media_type=media_type)
            assert not os.path.isdir(current_directory)

            # restore backup
            shutil.move('{}.bak'.format(current_directory), current_directory)
            assert os.path.isdir(current_directory)


def test_remove_uploaded_media_error_handler():
    # just try to execute the error handler function
    general_helper.remove_uploaded_media_error_handler(
        func=test_remove_uploaded_media_error_handler,
        path=os.getcwd(),
        exc_info=OSError
    )


def test_update_themerr_data_file(movies):
    test_items = [
        movies.all()[0]
    ]

    new_themerr_data = {
        'pytest': 'test'
    }

    for item in test_items:
        general_helper.update_themerr_data_file(item=item, new_themerr_data=new_themerr_data)
        themerr_json_data = general_helper.get_themerr_json_data(item=item)
        assert themerr_json_data['pytest'] == 'test'

        for key in general_helper.legacy_keys:
            assert key not in themerr_json_data
