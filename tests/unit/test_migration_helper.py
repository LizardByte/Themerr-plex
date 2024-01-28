# -*- coding: utf-8 -*-

# standard imports
import os

# lib imports
import pytest

# local imports
from Code import migration_helper
from Code import plex_api_helper

migration_helper_object = migration_helper.MigrationHelper()


@pytest.fixture(scope='function')
def migration_helper_fixture():
    return migration_helper_object


@pytest.fixture(scope='function')
def migration_status_file(migration_helper_fixture):
    migration_status_file = migration_helper_fixture.migration_status_file

    # delete the migration status file if it exists
    if os.path.isfile(migration_status_file):
        os.remove(migration_status_file)

    # yield the migration status file
    yield

    # delete the migration status file if it exists
    if os.path.isfile(migration_status_file):
        os.remove(migration_status_file)


@pytest.mark.parametrize('key, raise_exception, expected_return, expected_raise', [
    (migration_helper_object.LOCKED_THEMES, False, True, None),
    (migration_helper_object.LOCKED_THEMES, True, True, None),
    (migration_helper_object.LOCKED_COLLECTION_FIELDS, False, True, None),
    (migration_helper_object.LOCKED_COLLECTION_FIELDS, True, True, None),
    ('invalid', False, False, None),
    ('invalid', True, False, AttributeError),
])
def test_validate_migration_key(migration_helper_fixture, key, raise_exception, expected_return, expected_raise):
    if expected_raise is not None:
        with pytest.raises(expected_raise):
            migration_helper_fixture._validate_migration_key(key=key, raise_exception=raise_exception)
    else:
        validated = migration_helper_fixture._validate_migration_key(key=key, raise_exception=raise_exception)
        assert validated == expected_return, 'Expected {} but got {}'.format(expected_return, validated)


@pytest.mark.parametrize('key, expected', [
    (migration_helper_object.LOCKED_THEMES, None),
    (migration_helper_object.LOCKED_COLLECTION_FIELDS, None),
    pytest.param('invalid', None, marks=pytest.mark.xfail(raises=AttributeError)),
])
def test_get_migration_status(migration_helper_fixture, migration_status_file, key, expected):
    migration_status = migration_helper_fixture.get_migration_status(key=key)
    assert migration_status == expected, 'Expected {} but got {}'.format(expected, migration_status)


@pytest.mark.parametrize('key', [
    migration_helper_object.LOCKED_THEMES,
    migration_helper_object.LOCKED_COLLECTION_FIELDS,
    pytest.param('invalid', marks=pytest.mark.xfail(raises=AttributeError)),
])
def test_set_migration_status(migration_helper_fixture, migration_status_file, key):
    # perform the test twice, to load an existing migration file
    for _ in range(2):
        migration_helper_fixture.set_migration_status(key=key)
        migration_status = migration_helper_fixture.get_migration_status(key=key)
        assert migration_status is True, 'Migration status was not set to True'


@pytest.mark.parametrize('key', [
    migration_helper_object.LOCKED_THEMES,
    migration_helper_object.LOCKED_COLLECTION_FIELDS,
])
def test_perform_migration(migration_helper_fixture, migration_status_file, key):
    # perform the migration twice, should return early on the second run
    for _ in range(2):
        migration_helper_fixture.perform_migration(key=key)
        migration_status = migration_helper_fixture.get_migration_status(key=key)
        assert migration_status is True, 'Migration status was not set to True'


def test_migrate_locked_themes(movies):
    field = 'theme'

    # lock all is not working
    # movies.lockAllField(field=field, libtype='movie')
    # movies.reload()

    for movie in movies.all():
        plex_api_helper.change_lock_status(item=movie, field=field, lock=True)
        assert movie.isLocked(field=field) is True, '{} for movie is not locked'.format(field)

    migration_helper_object.migrate_locked_themes()
    movies.reload()

    for movie in movies.all():
        assert movie.isLocked(field=field) is False, '{} for movie is still locked'.format(field)


@pytest.mark.parametrize('field', [
    'art',
    'summary',
    'thumb',
])
def test_migrate_locked_collection_fields(field, movies):
    # lock all is not working, so lock manually
    for item in movies.collections():
        plex_api_helper.change_lock_status(item=item, field=field, lock=True)
        assert item.isLocked(field=field) is True, '{} for collection is not locked'.format(field)

    migration_helper_object.migrate_locked_collection_fields()
    movies.reload()

    for item in movies.collections():
        assert item.isLocked(field=field) is False, '{} for collection is still locked'.format(field)
