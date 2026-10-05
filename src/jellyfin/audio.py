"""Prepare lossless container changes for Jellyfin's local theme-file formats."""

# standard imports
from contextlib import contextmanager
from dataclasses import replace
import hashlib
from pathlib import Path
import tempfile

# lib imports
import av

# local imports
from youtube.youtube_dl import validate_audio


@contextmanager
def theme_file(audio):
    """Remux WebM Opus into Ogg without re-encoding and verify the resulting complete audio.

    Parameters
    ----------
    audio : AudioFile
        Downloaded and validated YouTube audio.

    Yields
    ------
    AudioFile
        Validated MP4 AAC or Ogg Opus, removed when the upload finishes.
    """
    if audio.codec == 'mp4a':
        yield audio
        return
    with tempfile.TemporaryDirectory(prefix='themerr-jellyfin-audio-') as directory:
        path = Path(directory) / 'theme.opus'
        with av.open(audio.path) as source, av.open(str(path), 'w', format='ogg') as target:
            stream = source.streams.audio[0]
            output = target.add_stream_from_template(stream)
            for packet in source.demux(stream):
                if packet.dts is not None:
                    packet.stream = output
                    target.mux(packet)
        duration = validate_audio(str(path), audio.duration, 'opus')
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        yield replace(audio, path=str(path), sha256=digest, size=path.stat().st_size, duration=duration)
