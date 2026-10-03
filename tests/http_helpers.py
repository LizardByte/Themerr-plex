"""Inspect and seed real signed ASGI session cookies in functional tests."""

# standard imports
from base64 import b64decode, b64encode
import json

# lib imports
from itsdangerous import TimestampSigner


def get_session(client) -> dict:
    """Decode the same signed cookie format used by Starlette's session middleware."""
    cookie = client.cookies.get('session')
    if not cookie:
        return {}
    data = TimestampSigner(client.app.state.secret_key).unsign(cookie.encode(), max_age=12 * 60 * 60)
    return json.loads(b64decode(data))


def set_session(client, values: dict, *, host: str | None = None) -> None:
    """Seed a browser session without introducing a test endpoint into the application."""
    data = b64encode(json.dumps(values).encode())
    cookie = TimestampSigner(client.app.state.secret_key).sign(data).decode()
    client.cookies.clear()
    domain = host or client.base_url.host
    if '.' not in domain and ':' not in domain:
        domain += '.local'
    client.cookies.set('session', cookie, domain=domain, path='/')
