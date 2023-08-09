# -*- coding: utf-8 -*-

# standard imports
import plistlib
import os

# plex debugging
try:
    import plexhints  # noqa: F401
except ImportError:
    pass
else:  # the code is running outside of Plex
    from plexhints.core_kit import Core  # core kit

# get plugin directory from core kit
plugin_directory = Core.bundle_path
if plugin_directory.endswith('test.bundle'):
    # use current directory instead, to allow for testing outside of Plex
    if os.path.basename(os.getcwd()) == 'docs':
        # use parent directory if current directory is 'docs'
        plugin_directory = os.path.dirname(os.getcwd())
    else:
        plugin_directory = os.getcwd()

# get identifier and version from Info.plist file
info_file_path = os.path.join(plugin_directory, 'Contents', 'Info.plist')
try:
    info_plist = plistlib.readPlist(pathOrFile=info_file_path)
except IOError:
    info_plist = dict(
        CFBundleIdentifier='dev.lizardbyte.themerr-plex',
        PlexBundleVersion='0.0.0'
    )
plugin_identifier = info_plist['CFBundleIdentifier']
version = info_plist['PlexBundleVersion']

app_support_directory = Core.app_support_path
metadata_base_directory = os.path.join(app_support_directory, 'Metadata')
plugin_support_directory = os.path.join(app_support_directory, 'Plug-in Support')
plugin_support_data_directory = os.path.join(plugin_support_directory, 'Data')
themerr_data_directory = os.path.join(plugin_support_data_directory, plugin_identifier, 'DataItems')

contributes_to = [
    'tv.plex.agents.movie',
    'com.plexapp.agents.imdb',
    'com.plexapp.agents.themoviedb',
    # 'com.plexapp.agents.thetvdb',  # not available as movie agent
    'dev.lizardbyte.retroarcher-plex'
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

# issue url constants
base_url = 'https://github.com/LizardByte/ThemerrDB/issues/new?assignees='
issue_label = 'request-theme'
issue_template = 'theme.yml'
url_name = 'database_url'
title_prefix = dict(
    games='[GAME]: ',
    game_collections='[GAME COLLECTION]: ',
    game_franchises='[GAME FRANCHISE]: ',
    movies='[MOVIE]: ',
    movie_collections='[MOVIE COLLECTION]: ',
)
url_prefix = dict(
    games='https://www.igdb.com/games/',
    game_collections='https://www.igdb.com/collections/',
    game_franchises='https://www.igdb.com/franchises/',
    movies='https://www.themoviedb.org/movie/',
    movie_collections='https://www.themoviedb.org/collection/',
)

# two additional strings to fill in later, item title and item url
issue_urls = dict(
    games='{}&labels={}&template={}&title={}{}&{}={}{}'.format(
        base_url, issue_label, issue_template, title_prefix['games'], '{}', url_name, url_prefix['games'], '{}'),
    game_collections='{}&labels={}&template={}&title={}{}&{}={}{}'.format(
        base_url, issue_label, issue_template, title_prefix['game_collections'], '{}', url_name,
        url_prefix['game_collections'], '{}'),
    game_franchises='{}&labels={}&template={}&title={}{}&{}={}{}'.format(
        base_url, issue_label, issue_template, title_prefix['game_franchises'], '{}', url_name,
        url_prefix['game_franchises'], '{}'),
    movies='{}&labels={}&template={}&title={}{}&{}={}{}'.format(
        base_url, issue_label, issue_template, title_prefix['movies'], '{}', url_name, url_prefix['movies'], '{}'),
    movie_collections='{}&labels={}&template={}&title={}{}&{}={}{}'.format(
        base_url, issue_label, issue_template, title_prefix['movie_collections'], '{}', url_name,
        url_prefix['movie_collections'], '{}'),
)
