# -*- coding: utf-8 -*-

# standard imports

# plex debugging
try:
    import plexhints  # noqa: F401
except ImportError:
    pass
else:  # the code is running outside of Plex
    from plexhints.prefs_kit import Prefs  # prefs kit

# imports from Libraries\Shared
from typing import Optional
import youtube_dl


def process_youtube(url):
    # type: (str) -> Optional[str]
    """
    Process URL using `youtube_dl`

    Parameters
    ----------
    url : str
       The URL of the YouTube video.

    Returns
    -------
    Optional[str]
       The URL of the audio object.

    Examples
    --------
    >>> process_youtube(url='https://www.youtube.com/watch?v=dQw4w9WgXcQ')
    ...
    """
    youtube_dl_params = dict(
        outmpl='%(id)s.%(ext)s',
        youtube_include_dash_manifest=False,
        username=Prefs['str_youtube_user'] if Prefs['str_youtube_user'] else None,
        password=Prefs['str_youtube_passwd'] if Prefs['str_youtube_passwd'] else None,
    )

    ydl = youtube_dl.YoutubeDL(params=youtube_dl_params)

    with ydl:
        result = ydl.extract_info(
            url=url,
            download=False  # We just want to extract the info
        )
        if 'entries' in result:
            # Can be a playlist or a list of videos
            video_data = result['entries'][0]
        else:
            # Just a video
            video_data = result

    size = 0
    audio_url = None
    if video_data:
        for fmt in video_data['formats']:  # loop through formats, select largest audio size for better quality
            if 'audio only' in fmt['format']:
                filesize = int(fmt['filesize'])
                if filesize > size:
                    size = filesize
                    audio_url = fmt['url']

    return audio_url  # return None or url found
