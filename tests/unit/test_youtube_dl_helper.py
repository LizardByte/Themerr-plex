# -*- coding: utf-8 -*-

# lib imports
import pytest

# local imports
from Code import youtube_dl_helper


@pytest.mark.parametrize('url', [
    'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
    'https://www.youtube.com/watch?v=Wb8j8Ojd4YQ&list=PLMYr5_xSeuXAbhxYHz86hA1eCDugoxXY0&pp=iAQB',  # playlist test
])
def test_process_youtube(url):
    # test valid urls
    audio_url = youtube_dl_helper.process_youtube(url=url)
    assert audio_url is not None
    assert audio_url.startswith('https://')


@pytest.mark.parametrize('url', [
    'https://www.youtube.com/watch?v=notavideoid',
    'https://blahblahblah',
])
def test_process_youtube_invalid(url):
    # test invalid urls
    audio_url = youtube_dl_helper.process_youtube(url=url)
    assert audio_url is None
