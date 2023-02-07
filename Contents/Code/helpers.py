# -*- coding: utf-8 -*-

# imports from Libraries\Shared
import requests

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


def get_json(url):
    # type: (str) -> [dict, bool]
    """
    Get JSON from a URL.

    Use ``requests`` to get JSON data from a URL.

    Parameters
    ----------
    url : str
        The URL to get JSON data from.

    Returns
    -------
    dict
        The JSON data from the URL.
    bool
        ``False`` if the URL is not valid or the data is not JSON.

    Examples
    --------
    >>> get_json('https://app.lizardbyte.dev/ThemerrDB/movies/themoviedb/10138.json')
    {}
    """
    response = requests.get(url=url)
    if response.status_code == 200 and response.headers['content-type'] == 'application/json':
        return response.json()
    else:
        return False
