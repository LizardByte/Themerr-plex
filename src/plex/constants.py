contributes_to = [
    'tv.plex.agents.movie',  # new movie agent
    'tv.plex.agents.series',  # new tv show agent
]

guid_map = dict(
    imdb='imdb',
    tmdb='themoviedb',
    tvdb='thetvdb',
    **{
        'com.plexapp.agents.imdb': 'imdb',
        'com.plexapp.agents.themoviedb': 'themoviedb',
        'com.plexapp.agents.thetvdb': 'thetvdb',
    },
)

metadata_type_map = {
    'album': 'Albums',
    'artist': 'Artists',
    'collection': 'Collections',
    'movie': 'Movies',
    'show': 'TV Shows',
}

plex_section_type_settings_map = {
    'album': 9,
    'artist': 8,
    'movie': 1,
    'photo': 13,
    'show': 2,
}

media_type_dict = {
    'art': {
        'method': lambda item: item.uploadArt,
        'type': 'art',
        'name': 'art',
        'themerr_data_key': 'art_url',
        'remove_pref': 'BOOL_REMOVE_UNUSED_ART',
        'plex_field': 'art',
    },
    'posters': {
        'method': lambda item: item.uploadPoster,
        'type': 'posters',
        'name': 'poster',
        'themerr_data_key': 'poster_url',
        'remove_pref': 'BOOL_REMOVE_UNUSED_POSTERS',
        'plex_field': 'thumb',
    },
    'themes': {
        'method': lambda item: item.uploadTheme,
        'type': 'themes',
        'name': 'theme',
        'themerr_data_key': 'youtube_theme_url',
        'remove_pref': 'BOOL_REMOVE_UNUSED_THEMES',
        'plex_field': 'theme',
    },
}
