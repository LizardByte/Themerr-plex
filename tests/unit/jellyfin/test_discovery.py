"""Bounded LAN discovery parses untrusted UDP replies without transmitting API keys."""

import json
import socket
from unittest.mock import Mock

import pytest

from jellyfin import discovery
from media_servers.base import MediaServerError


def test_discovery_validates_and_deduplicates_replies(monkeypatch):
    server = {'Id': '3' * 32, 'Name': '<untrusted>', 'Address': 'http://jellyfin.example:8096/'}
    transport = Mock()
    transport.__enter__ = Mock(return_value=transport)
    transport.__exit__ = Mock(return_value=False)
    replies = [b'invalid', b'[]', json.dumps({**server, 'Address': 'file:///private'}).encode(),
               json.dumps({**server, 'Id': '../private'}).encode(), json.dumps(server).encode(),
               json.dumps(server).encode()]
    transport.recvfrom.side_effect = [(reply, ('127.0.0.1', 7359)) for reply in replies] + [socket.timeout()]
    monkeypatch.setattr(discovery.socket, 'socket', Mock(return_value=transport))
    monkeypatch.setattr(discovery.time, 'monotonic', lambda: 1)
    assert discovery.discover() == [{'id': '3' * 32, 'name': '<untrusted>', 'url': 'http://jellyfin.example:8096'}]
    assert [call.args for call in transport.sendto.call_args_list] == [
        (b'Who is JellyfinServer?', ('255.255.255.255', 7359)),
        (b'Who is JellyfinServer?', ('127.0.0.1', 7359)),
    ]


def test_discovery_socket_failure_has_a_fixed_client_message(monkeypatch):
    monkeypatch.setattr(discovery.socket, 'socket', Mock(side_effect=OSError('private details')))
    with pytest.raises(MediaServerError, match='local network access') as error:
        discovery.discover()
    assert error.value.status_code == 503
    assert 'private details' not in str(error.value)
