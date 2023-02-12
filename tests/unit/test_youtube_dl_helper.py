# lib imports
import pytest
from youtube_dl import DownloadError

# local imports
from Code import youtube_dl_helper


def test_process_youtube():
    # test valid urls
    valid_urls = [
        'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
    ]
    for url in valid_urls:
        audio_url = youtube_dl_helper.process_youtube(url=url)
        assert audio_url is not None
        assert audio_url.startswith('https://')

    # test invalid urls
    invalid_urls = [
        'https://www.youtube.com/watch?v=notavideoid',
        'https://blahblahblah',
    ]
    for url in invalid_urls:
        with pytest.raises(DownloadError):
            youtube_dl_helper.process_youtube(url=url)
