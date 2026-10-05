"""Verify Jellyfin's lossless Opus remux and temporary-file lifecycle."""

from fractions import Fraction
import hashlib
from pathlib import Path

import av
import pytest

from jellyfin.audio import theme_file
from youtube.youtube_dl import AudioFile, validate_audio


def test_opus_is_remuxed_to_ogg_without_changing_audio(tmp_path):
    path = tmp_path / 'download.webm'
    with av.open(str(path), 'w', format='webm') as output:
        stream = output.add_stream('libopus', rate=48000)
        stream.layout = 'stereo'
        for index in range(50):
            frame = av.AudioFrame(format='fltp', layout='stereo', samples=960)
            for plane in frame.planes:
                plane.update(bytes(plane.buffer_size))
            frame.sample_rate = 48000
            frame.time_base = Fraction(1, 48000)
            frame.pts = index * 960
            for packet in stream.encode(frame):
                output.mux(packet)
        for packet in stream.encode():
            output.mux(packet)
    audio = AudioFile(str(path), 'opus', False, hashlib.sha256(path.read_bytes()).hexdigest(),
                      validate_audio(str(path), 1, 'opus'), path.stat().st_size)
    with av.open(str(path)) as source:
        packets = [bytes(packet) for packet in source.demux(audio=0) if packet.size]
    with theme_file(audio) as remuxed:
        result = Path(remuxed.path)
        assert result.exists()
        assert remuxed.sha256 == hashlib.sha256(result.read_bytes()).hexdigest()
        assert remuxed.codec == 'opus'
        assert remuxed.duration == pytest.approx(audio.duration, abs=0.001)
        with av.open(str(result)) as container:
            assert container.format.name == 'ogg'
            assert container.streams.audio[0].codec_context.name == 'opus'
            assert [bytes(packet) for packet in container.demux(audio=0) if packet.size] == packets
    assert not result.exists()
    assert path.exists()


def test_aac_keeps_original_validated_file(tmp_path):
    path = tmp_path / 'download.m4a'
    path.write_bytes(b'validated by the shared downloader')
    audio = AudioFile(str(path), 'mp4a', True, 'digest', 1, path.stat().st_size)
    with theme_file(audio) as prepared:
        assert prepared is audio
    assert path.exists()
