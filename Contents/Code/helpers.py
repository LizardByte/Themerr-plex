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
