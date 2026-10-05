"""Resolve Jellyfin provider identifiers into ThemerrDB metadata."""

# standard imports
import re
from urllib.parse import quote_plus

# local imports
from themerr import themerr_db, tmdb
from themerr.constants import issue_urls

TYPES = {
    'Movie': (
        'movie',
        'movies',
    ),
    'Series': (
        'show',
        'tv_shows',
    ),
    'BoxSet': (
        'collection',
        'movie_collections',
    ),
}
_DECIMAL_ID = r'[0-9]+'  # NOSONAR python:S6353: provider IDs are ASCII; \d also accepts Unicode digits.
_IMDB_ID = r'tt[0-9]+'  # NOSONAR python:S6353: IMDb identifiers require ASCII decimal digits.


def _identifiers(item, kind):
    """Validate native provider IDs and preserve the ordered external-ID fallbacks."""
    providers = item.get('ProviderIds') or {}
    tmdb_id = str(providers.get('Tmdb', ''))
    if not re.fullmatch(_DECIMAL_ID, tmdb_id):
        tmdb_id = None
    imdb_id = str(providers.get('Imdb', ''))
    if not re.fullmatch(_IMDB_ID, imdb_id):
        imdb_id = None
    source_database, source_id = (
        (
            'themoviedb',
            tmdb_id,
        )
        if tmdb_id
        else (
            'imdb',
            imdb_id,
        )
    )
    if not tmdb_id and kind == 'movie' and imdb_id:
        tmdb_id = tmdb.get_tmdb_id_from_external_id(imdb_id, 'imdb', 'movie')
    if not tmdb_id and kind == 'show':
        tvdb_id = str(providers.get('Tvdb', ''))
        source_database, source_id = (
            'thetvdb',
            tvdb_id if re.fullmatch(_DECIMAL_ID, tvdb_id) else None,
        )
        tmdb_id = tmdb.get_tmdb_id_from_external_id(tvdb_id, 'tvdb', 'tv', title=item.get('Name'))
    if not tmdb_id and kind == 'collection':
        tmdb_id = tmdb.get_tmdb_id_from_collection(item.get('Name', ''))
    return (
        tmdb_id,
        imdb_id,
        source_database,
        source_id,
    )


def resolve(item):
    """Select validated provider IDs, using shared title and external-ID fallbacks."""
    kind, database_type = TYPES.get(
        item.get('Type'),
        (
            None,
            None,
        ),
    )
    tmdb_id, imdb_id, source_database, source_id = _identifiers(item, kind)
    if tmdb_id:
        database, database_id = (
            'themoviedb',
            str(tmdb_id),
        )
    elif kind == 'movie' and imdb_id:
        database, database_id = (
            'imdb',
            imdb_id,
        )
    else:
        database, database_id = (
            None,
            None,
        )
    exists = bool(
        database_type and database and database_id and themerr_db.item_exists(database_type, database, database_id)
    )
    url = issue_urls.get(database_type)
    title = item.get('Name', '')
    if kind != 'collection' and item.get('ProductionYear'):
        title = f'{title} ({item["ProductionYear"]})'
    return {
        'type': kind,
        'database_type': database_type,
        'database': database,
        'database_id': database_id,
        'source_database': source_database,
        'source_id': source_id,
        'exists': exists,
        'issue_action': 'edit' if exists else 'add',
        'issue_url': url.format(quote_plus(title), database_id) if url and database_id else None,
    }
