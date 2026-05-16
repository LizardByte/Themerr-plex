# standard imports
import os

contributes_to = [
    'tv.plex.agents.movie',  # new movie agent
    'tv.plex.agents.series',  # new tv show agent
]

guid_map = dict(
    imdb='imdb',
    tmdb='themoviedb',
    tvdb='thetvdb'
)

metadata_type_map = dict(
    album='Albums',
    artist='Artists',
    collection='Collections',
    movie='Movies',
    show='TV Shows'
)

# the explicit IPv4 address is used because `localhost` can resolve to ::1, which `websocket` rejects
plex_url = 'http://127.0.0.1:32400'  # TODO: this needs to be a configuration option
plex_token = os.environ.get('PLEXTOKEN')  # TODO: this needs to be a configuration option

plex_section_type_settings_map = dict(
    album=9,
    artist=8,
    movie=1,
    photo=13,
    show=2,
)

# issue url constants
base_url = 'https://github.com/LizardByte/ThemerrDB/issues/new?assignees='
issue_label = 'request-theme'
issue_template = 'theme.yml'
url_name = 'database_url'
title_prefix = dict(
    movies='[MOVIE]: ',
    movie_collections='[MOVIE COLLECTION]: ',
    tv_shows='[TV SHOW]: ',
)
url_prefix = dict(
    movies='https://www.themoviedb.org/movie/',
    movie_collections='https://www.themoviedb.org/collection/',
    tv_shows='https://www.themoviedb.org/tv/',
)

# two additional strings to fill in later, item title and item url
issue_urls = dict(
    movies=f'{base_url}'
           f'&labels={issue_label}'
           f'&template={issue_template}'
           f'&title={title_prefix['movies']}{'{}'}'
           f'&{url_name}={url_prefix['movies']}{'{}'}',
    movie_collections=f'{base_url}'
                      f'&labels={issue_label}'
                      f'&template={issue_template}'
                      f'&title={title_prefix['movie_collections']}{'{}'}'
                      f'&{url_name}={url_prefix['movie_collections']}{'{}'}',
    tv_shows=f'{base_url}'
             f'&labels={issue_label}'
             f'&template={issue_template}'
             f'&title={title_prefix['tv_shows']}{'{}'}'
             f'&{url_name}={url_prefix['tv_shows']}{'{}'}',
)

media_type_dict = dict(
    art=dict(
        method=lambda item: item.uploadArt,
        type='art',
        name='art',
        themerr_data_key='art_url',
        remove_pref='BOOL_REMOVE_UNUSED_ART',
        plex_field='art',
    ),
    posters=dict(
        method=lambda item: item.uploadPoster,
        type='posters',
        name='poster',
        themerr_data_key='poster_url',
        remove_pref='BOOL_REMOVE_UNUSED_POSTERS',
        plex_field='thumb',
    ),
    themes=dict(
        method=lambda item: item.uploadTheme,
        type='themes',
        name='theme',
        themerr_data_key='youtube_theme_url',
        remove_pref='BOOL_REMOVE_UNUSED_THEMES',
        plex_field='theme',
    ),
)
