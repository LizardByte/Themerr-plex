# -*- coding: utf-8 -*-

# standard imports
import binascii
import os
import tempfile
from urlparse import urlparse

# lib imports
import pytest
import requests

# local imports
from Code import youtube_dl_helper

gh_url_prefix = 'https://raw.githubusercontent.com/LizardByte/ThemerrDB/gh-pages'

xfail_rate_limit = "YouTube is probably rate limiting"


# standard items setup by plexhints action
@pytest.fixture(scope='module', params=[
    pytest.param({
        'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
        'expected': True,
    }),
    pytest.param({  # playlist
        'url': 'https://www.youtube.com/watch?v=Wb8j8Ojd4YQ&list=PLMYr5_xSeuXAbhxYHz86hA1eCDugoxXY0&pp=iAQB',
        'expected': True,
    }),
    pytest.param({
        'url': '{}/movies/themoviedb/9761.json'.format(gh_url_prefix),  # Elephants Dream
        'expected': True,
    }, marks=pytest.mark.xfail(reason=xfail_rate_limit)),
    pytest.param({
        'url': '{}/movies/themoviedb/20529.json'.format(gh_url_prefix),  # Sita Sings the Blues
        'expected': True,
    }, marks=pytest.mark.xfail(reason=xfail_rate_limit)),
    pytest.param({
        'url': '{}/movies/themoviedb/10378.json'.format(gh_url_prefix),  # Big Buck Bunny
        'expected': True,
    }, marks=pytest.mark.xfail(reason=xfail_rate_limit)),
    pytest.param({
        'url': '{}/movies/themoviedb/45745.json'.format(gh_url_prefix),  # Sintel
        'expected': True,
    }, marks=pytest.mark.xfail(reason=xfail_rate_limit)),
    pytest.param({
        'url': '{}/tv_shows/themoviedb/1399.json'.format(gh_url_prefix),  # Game of Thrones
        'expected': True,
    }, marks=pytest.mark.xfail(reason=xfail_rate_limit)),
    pytest.param({
        'url': '{}/tv_shows/themoviedb/48866.json'.format(gh_url_prefix),  # The 100
        'expected': True,
    }, marks=pytest.mark.xfail(reason=xfail_rate_limit)),
    pytest.param({
        'url': 'https://www.youtube.com/watch?v=notavideoid',  # invalid A
        'expected': False,
    }),
    pytest.param({
        'url': 'https://blahblahblah',  # invalid B
        'expected': False,
    }),
])
def youtube_url(request):
    url = request.param['url']
    host = urlparse(url=url).hostname
    if host and not host.endswith(".githubusercontent.com"):
        return request.param

    # get the youtube_theme_url key from the JSON data
    response = requests.get(url=url)
    assert response.status_code == 200
    data = response.json()
    request.param['url'] = data['youtube_theme_url']
    return request.param


@pytest.fixture
def temp_file():
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        yield temp_file.name
    os.remove(temp_file.name)


def test_process_youtube(youtube_url, temp_file):
    # test valid urls
    audio_url = youtube_dl_helper.process_youtube(url=youtube_url['url'])
    if not youtube_url['expected']:
        assert audio_url is None
        return

    assert audio_url is not None
    assert audio_url.startswith('https://')

    # valid signatures dictionary with offsets
    valid_signatures = {
        "1866747970": 3,  # Mp4 container
        "6674797069736F6D": 4,  # Mp4 container
        "494433": 0,  # ID3
        "FFFB": 0,  # MPEG-1 Layer 3
        "FFF3": 0,  # MPEG-1 Layer 3
        "FFF2": 0,  # MPEG-1 Layer 3
    }

    chunk_size = 0
    for sig, offset in valid_signatures.items():
        chunk_size = max(chunk_size, len(sig) + offset)  # get the max chunk size

    # validate the format of the audio file at the URL
    # download the file
    with requests.get(audio_url, stream=True) as r:
        r.raise_for_status()
        with open(temp_file, 'wb') as f:
            for chunk in r.iter_content(chunk_size=chunk_size):
                f.write(chunk)
                break  # only download the first chunk for unit testing

    # read the file bytes
    with open(temp_file, 'rb') as f:
        file_bytes = f.read()

    # convert bytes to hex
    file_bytes_hex = binascii.hexlify(file_bytes)
    print(file_bytes_hex[:30])

    # check if the file is not WebM
    is_webm = file_bytes_hex.startswith("1A45DFA3")
    assert not is_webm, "File {} is WebM".format(temp_file)

    # check if the file is valid
    is_valid = False

    # loop through valid_signatures
    for signature, offset in valid_signatures.items():
        # remove the offset bytes
        file_bytes_hex_without_offset = file_bytes_hex[offset * 2:]

        # check if the beginning of the file_bytes_hex_without_offset matches the signature
        if file_bytes_hex_without_offset.startswith(signature):
            is_valid = True
            break

    assert is_valid, "File {} is not a valid format".format(temp_file)
