"""Dashboard caching accepts overlapping libraries and repeated API page entries."""

# standard imports
from unittest.mock import Mock
from uuid import UUID

# lib imports
import pytest

# local imports
from jellyfin import backend, metadata
from themerr import storage


@pytest.mark.parametrize('overlap', [
    'libraries',
    'pages',
])
def test_dashboard_refresh_preserves_unique_items_in_each_library(configured, monkeypatch, overlap):
    first_library = '1' * 32
    second_library = '2' * 32
    shared_item = {
        'Id': '3' * 32,
        'Name': 'Shared movie',
        'Type': 'Movie',
        'ProviderIds': {'Tmdb': '42'},
    }
    other_item = {
        **shared_item,
        'Id': '4' * 32,
        'Name': 'Other movie',
    }
    libraries = [{
        'ItemId': first_library,
        'Name': 'Movies',
        'CollectionType': 'movies',
    }]
    if overlap == 'libraries':
        libraries.append({
            'ItemId': second_library,
            'Name': 'Shared library',
            'CollectionType': 'movies',
        })

    def response(method, path, *, params=None):
        if path == '/Library/VirtualFolders':
            return libraries
        assert path == '/Items'
        if params.get('HasThemeSong'):
            return {
                'Items': [],
                'TotalRecordCount': 0,
            }
        if overlap == 'pages':
            items = [
                shared_item,
                {**shared_item, 'Id': str(UUID(shared_item['Id'])).upper()},
                other_item,
            ]
            start = params['StartIndex']
            return {
                'Items': items[start:start + 1],
                'TotalRecordCount': len(items),
            }
        return {
            'Items': [shared_item] if params['ParentId'] == first_library else [
                shared_item,
                other_item,
            ],
            'TotalRecordCount': 1 if params['ParentId'] == first_library else 2,
        }

    connection = Mock()
    connection.json.side_effect = response
    monkeypatch.setattr(backend.servers, 'client', lambda _: connection)
    monkeypatch.setattr(backend.connector, 'verify', lambda _: {})
    monkeypatch.setattr(metadata.themerr_db, 'item_exists', lambda *_: True)
    server_id = f'jellyfin:{"5" * 32}'
    adapter = backend.JellyfinMediaServer(server_id)

    for _ in range(2):
        assert adapter.cache_dashboard()
        with storage.server_scope(server_id):
            snapshot = storage.get_dashboard()
        assert set(snapshot) == {library['ItemId'] for library in libraries}
        for library_id, section in snapshot.items():
            expected = [shared_item['Id']]
            if library_id == second_library or overlap == 'pages':
                expected.append(other_item['Id'])
            assert [item['rating_key'] for item in section['items']] == expected
            assert section['total_count'] == len(expected)
            assert section['media_count'] == len(expected)
            assert section['media_percent_complete'] == 0
    if overlap == 'pages':
        offsets = [
            call.kwargs['params']['StartIndex']
            for call in connection.json.call_args_list
            if call.args[1] == '/Items' and not call.kwargs['params'].get('HasThemeSong')
        ]
        assert offsets == [
            0,
            1,
            2,
            0,
            1,
            2,
        ]
    assert storage.get_dashboard() is None
