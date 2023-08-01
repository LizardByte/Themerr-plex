# -*- coding: utf-8 -*-

# standard imports
import os

# plex debugging
try:
    import plexhints  # noqa: F401
except ImportError:
    pass
else:  # the code is running outside of Plex
    from plexhints.core_kit import Core  # core kit

app_support_directory = Core.app_support_path
plugin_identifier = 'dev.lizardbyte.themerr-plex'
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


base_url = 'https://github.com/LizardByte/ThemerrDB/issues/new?assignees='
issue_labels = dict(
    game='request-game',
    movie='request-movie',
)
issue_template = dict(
    game='game-theme.yml',
    movie='movie-theme.yml',
)
title_prefix = dict(
    game='[GAME]: ',
    movie='[MOVIE]: ',
)
url_name = dict(
    game='igdb_url',
    movie='themoviedb_url',
)
url_prefix = dict(
    game='https://www.igdb.com/games/',
    movie='https://www.themoviedb.org/movie/',
)

# two additional strings to fill in later, item title and item url
issue_url_movies = '%s&labels=%s&template=%s&title=%s%s&%s=%s%s' % (base_url, issue_labels['movie'],
                                                                    issue_template['movie'], title_prefix['movie'],
                                                                    '%s', url_name['movie'], url_prefix['movie'], '%s')
issue_url_games = '%s&labels=%s&template=%s&title=%s%s&%s=%s%s' % (base_url, issue_labels['game'],
                                                                   issue_template['game'], title_prefix['game'],
                                                                   '%s', url_name['game'], url_prefix['game'], '%s')
