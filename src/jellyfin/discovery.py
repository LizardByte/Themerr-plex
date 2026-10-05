"""Discover nearby Jellyfin addresses without transmitting credentials."""

# standard imports
import json
import socket
import time

# local imports
from jellyfin.client import base_url, identifier
from media_servers.base import MediaServerError


def discover():
    """Collect bounded Jellyfin UDP discovery replies from the application's network."""
    results = {}
    deadline = time.monotonic() + 2
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as transport:
            transport.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            transport.bind(
                (
                    '',
                    0,
                )
            )
            for address in (
                '255.255.255.255',
                '127.0.0.1',
            ):
                transport.sendto(
                    b'Who is JellyfinServer?',
                    (
                        address,
                        7359,
                    ),
                )
            while len(results) < 32 and time.monotonic() < deadline:
                transport.settimeout(max(0.001, deadline - time.monotonic()))
                try:
                    payload, _ = transport.recvfrom(4096)
                except socket.timeout:
                    break
                try:
                    data = json.loads(payload)
                    server_id = identifier(data['Id'])
                    url = base_url(data['Address'])
                    name = str(data['Name'])[:128]
                except (
                    ValueError,
                    TypeError,
                    KeyError,
                    MediaServerError,
                ):
                    continue
                results[
                    (
                        server_id,
                        url,
                    )
                ] = {
                    'id': server_id,
                    'name': name,
                    'url': url,
                }
    except OSError as exc:
        raise MediaServerError(
            'Jellyfin discovery is unavailable. Check local network access or enter an address.', 503
        ) from exc
    return sorted(
        results.values(),
        key=lambda row: (
            row['name'],
            row['url'],
        ),
    )
