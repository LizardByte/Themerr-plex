# -*- coding: utf-8 -*-
# local imports
from Code import youtube_dl_helper


def test_process_youtube():
    # test valid urls
    valid_urls = [
        'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
        'https://www.youtube.com/watch?v=Wb8j8Ojd4YQ&list=PLMYr5_xSeuXAbhxYHz86hA1eCDugoxXY0&pp=iAQB',  # playlist test
    ]
    for url in valid_urls:
        audio_url = youtube_dl_helper.process_youtube(url=url)
        assert audio_url is not None
        assert audio_url.startswith('https://')


def test_process_youtube_invalid():
    # test invalid urls
    invalid_urls = [
        'https://www.youtube.com/watch?v=notavideoid',
        'https://blahblahblah',
    ]
    for url in invalid_urls:
        audio_url = youtube_dl_helper.process_youtube(url=url)
        assert audio_url is None
