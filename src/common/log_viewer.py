"""Read recent log files and complete current-session history in bounded batches."""

# standard imports
import os
import re
import json
import logging
import tempfile
import time

# local imports
from common import logger
from common.definitions import Paths

MAX_READ_BYTES = 1024 * 1024  # Per session batch or recent source, including rotated files.
MAX_ENTRIES = 2000
_HEADER = re.compile(
    r'^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:[.,]\d{3})?)'
    r' - (?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+:: (?P<thread>.*?) : (?P<message>.*)$',
)


class _SessionLogHandler(logging.Handler):
    """Keep masked current-session records on temporary disk storage until shutdown."""

    def __init__(self):
        self.stream = tempfile.TemporaryFile(mode='w+b')
        super().__init__()
        self.failed = False
        self.sequence = 0
        self.end = 0
        self.setFormatter(logger.PrivateFormatter('%(module)s : %(message)s'))

    def emit(self, record):
        """Append one complete record under the logging handler's shared lock."""
        if self.failed or self._closed:
            return
        source = 'backend' if record.name.split('.')[0] in ('uvicorn', 'backend') else 'themerr'
        if record.name == 'yt-dlp':
            source = 'yt-dlp'
        try:
            entry = {
                'id': f'startup:{self.sequence}', 'source': source, 'level': record.levelname,
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(record.created))
                + f'.{int(record.msecs):03d}',
                'thread': logger.redact(record.threadName), 'message': self.format(record),
            }
            self.stream.seek(0, os.SEEK_END)
            self.stream.write(json.dumps(entry, ensure_ascii=False).encode('utf-8') + b'\n')
            self.end = self.stream.tell()
            self.sequence += 1
        except Exception:
            self.failed = True
            self.handleError(record)

    def read(self, source, cursor, limit):
        """Read the next bounded batch without retaining the session in server memory."""
        with self.lock:
            if self._closed:
                return {'entries': [], 'cursor': 0, 'has_more': False,
                        'unavailable': list(logger.LOG_NAMES), 'truncated': False}
            end = self.end
            start = min(cursor, end)
            self.stream.seek(start)
            if start:
                self.stream.seek(start - 1)
                if self.stream.read(1) != b'\n':
                    self.stream.readline()  # Invalid offsets skip to the next complete record.
            entries = []
            while self.stream.tell() < end and len(entries) < limit and self.stream.tell() - start < MAX_READ_BYTES:
                entry = json.loads(self.stream.readline())
                if source == 'all' or entry['source'] == source:
                    entry['message'] = logger.redact(entry['message'])
                    entry['thread'] = logger.redact(entry['thread'])
                    entries.append(entry)
            cursor = self.stream.tell()
            return {'entries': entries, 'cursor': cursor, 'has_more': cursor < end,
                    'unavailable': list(logger.LOG_NAMES) if self.failed else [], 'truncated': False}

    def close(self):
        """Release temporary session storage when logging shuts down."""
        with self.lock:
            if not self._closed:
                self.stream.close()
            super().close()


def session_snapshot(source: str = 'all', limit: int = 1000, cursor: int = 0) -> dict:
    """Read a batch of records emitted since application logging started.

    Keep session history independently of rotating log files and reset it when the
    process restarts. Use the returned cursor to load subsequent batches or new records.

    Parameters
    ----------
    source : str, optional
        ``all``, ``themerr``, ``backend``, or ``yt-dlp``. Defaults to ``all``.
    limit : int, optional
        Maximum records in this batch, between 1 and 2000. Defaults to 1000.
    cursor : int, optional
        Offset returned by a previous batch. Zero starts at the first session record.

    Returns
    -------
    dict
        Entries, the next cursor, whether more records remain, and unavailable sources.

    Examples
    --------
    >>> data = session_snapshot(source='themerr', limit=250, cursor=0)
    >>> 'has_more' in data
    True
    """
    if source not in ('all', *logger.LOG_NAMES) or not 1 <= limit <= MAX_ENTRIES or cursor < 0:
        raise ValueError('Invalid log selection')
    if logger._session_handler is None:
        return {'entries': [], 'cursor': 0, 'has_more': False,
                'unavailable': list(logger.LOG_NAMES), 'truncated': False}
    try:
        return logger._session_handler.read(source, cursor, limit)
    except OSError:
        return {'entries': [], 'cursor': cursor, 'has_more': False,
                'unavailable': list(logger.LOG_NAMES), 'truncated': False}


def _read_file(path: str, source: str, budget: int) -> tuple[list[dict], int, bool]:
    """Read complete records from a file tail, keeping continuation lines together."""
    with open(path, 'rb') as stream:
        stat = os.fstat(stream.fileno())
        start = max(0, stat.st_size - budget)
        boundary = start == 0
        if start:
            stream.seek(start - 1)
            boundary = stream.read(1) == b'\n'
        stream.seek(start)
        data = stream.read(min(stat.st_size, budget))
    offset = start
    lines = data.splitlines(keepends=True)
    if not boundary and lines:
        # The first line may start halfway through a UTF-8 character or log header.
        offset += len(lines.pop(0))
    if lines and not lines[-1].endswith(b'\n'):
        lines.pop()  # A writer may still be appending the last line; retry on the next refresh.
    entries = []
    for line in lines:
        text = line.decode('utf-8', errors='replace').rstrip('\r\n')
        header = _HEADER.match(text)
        if header:
            entries.append({
                'id': f'{source}:{stat.st_ino}:{offset}', 'source': source, **header.groupdict(),
            })
        elif entries:
            entries[-1]['message'] += '\n' + text
        offset += len(line)
    return entries, len(data), start > 0


def snapshot(source: str = 'all', limit: int = 1000) -> dict:
    """Return recent records in chronological order with bounded disk reads.

    Parameters
    ----------
    source : str
        ``all`` or one of ``themerr``, ``backend``, and ``yt-dlp``. No paths are accepted.
    limit : int
        Maximum number of records, between 1 and 2000.

    Returns
    -------
    dict
        Entries, unavailable sources, and whether older history was omitted.
        Mask secrets again before returning data, including logs from development mode.
    """
    if source not in ('all', *logger.LOG_NAMES) or not 1 <= limit <= MAX_ENTRIES:
        raise ValueError('Invalid log selection')
    entries, unavailable = [], []
    truncated = False
    for name in logger.LOG_NAMES if source == 'all' else (source,):
        recent = []
        budget = MAX_READ_BYTES
        for index in range(logger.MAX_FILES + 1):
            path = os.path.join(Paths.LOG_DIR, f'{name}.log' + (f'.{index}' if index else ''))
            try:
                records, size, partial = _read_file(path, name, budget)
            except FileNotFoundError:
                continue  # Empty installations and rotation races are normal.
            except OSError:
                unavailable.append(name)
                break
            recent = records + recent
            budget -= size
            truncated = truncated or partial
            if len(recent) > limit or budget <= 0:
                truncated = True
                break
        entries.extend(recent[-limit:])
    entries.sort(key=lambda entry: entry['timestamp'])
    truncated = truncated or len(entries) > limit
    entries = entries[-limit:]
    for entry in entries:
        entry['message'] = logger.redact(entry['message'])
        entry['thread'] = logger.redact(entry['thread'])
    return {'entries': entries, 'unavailable': unavailable, 'truncated': truncated}
