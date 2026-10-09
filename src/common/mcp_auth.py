"""Administrator token management and request authentication for scoped MCP credentials."""

# standard imports
from datetime import datetime, timezone
import hashlib
import hmac
import json
import secrets

# lib imports
from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import JSONResponse

# local imports
from common import admin
from common.http import read_json
from themerr import storage

router = APIRouter()
_KEY_PREFIX = 'mcp-token:'
_SCOPES = (
    'read',
    'process',
)


def create_token(scope: str, name: str = 'MCP client') -> str:
    """Issue a credential after administrator setup, persisting only its digest.

    Parameters
    ----------
    scope : str
        ``read`` for queries or ``process`` for queries, refreshes, and retries.
    name : str, optional
        Administrator label identifying the client using this token.

    Returns
    -------
    str
        Bearer token to display once in the web UI.

    Raises
    ------
    ValueError
        If the scope is invalid or administrator setup is incomplete.
    """
    if scope not in _SCOPES:
        raise ValueError('Choose the read or process MCP scope.')
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 64:
        raise ValueError('Choose a token name between 1 and 64 characters.')
    current = admin.account()
    if current is None:
        raise ValueError('Create the admin account in the browser first.')
    token = f'tmcp_{secrets.token_urlsafe(32)}'
    digest = hashlib.sha256(token.encode()).hexdigest()
    value = {
        'scope': scope,
        'name': name.strip(),
        'revision': current['revision'],
        'created': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    with Session(storage.engine()) as database:
        database.add(storage.AppSetting(key=f'{_KEY_PREFIX}{digest}', value=json.dumps(value)))
        database.commit()
    return token


def list_tokens() -> list[dict]:
    """Return token labels, scopes, dates, and validity without revealing credentials.

    Returns
    -------
    list of dict
        Management identifiers and metadata for issued tokens.
    """
    current = admin.account()
    with Session(storage.engine()) as database:
        rows = database.scalars(select(storage.AppSetting).where(
            storage.AppSetting.key.startswith(_KEY_PREFIX),
        ).order_by(storage.AppSetting.key)).all()
        tokens = []
        for row in rows:
            value = json.loads(row.value)
            tokens.append({
                'id': row.key.removeprefix(_KEY_PREFIX),
                'name': value['name'],
                'scope': value['scope'],
                'created': value['created'],
                'active': bool(current and value['revision'] == current['revision']),
            })
    return tokens


def revoke_tokens() -> None:
    """Revoke all MCP credentials for this installation."""
    with Session(storage.engine()) as database:
        database.execute(delete(storage.AppSetting).where(storage.AppSetting.key.startswith(_KEY_PREFIX)))
        database.commit()


@router.get('/api/mcp/tokens', name='mcp.tokens')
def tokens() -> dict:
    """List MCP token metadata for the signed-in administrator.

    Returns
    -------
    dict
        Issued token metadata without plaintext credentials.
    """
    return {'tokens': list_tokens()}


@router.post('/api/mcp/tokens', name='mcp.create_token', response_model=None)
def issue_token(payload=Depends(read_json)):
    """Create a named MCP credential through a CSRF-protected administrator request.

    Returns
    -------
    JSONResponse
        Newly issued token, displayed once, or a fixed validation error.
    """
    if not isinstance(payload, dict) or set(payload) != {
        'name',
        'scope',
    } or not isinstance(payload['scope'], str):
        return JSONResponse({'message': 'Supply a token name and scope.'}, status_code=400)
    try:
        token = create_token(payload['scope'], payload['name'])
    except ValueError as exc:
        return JSONResponse({'message': str(exc)}, status_code=400)
    return JSONResponse({
        'token': token,
        'tokens': list_tokens(),
    }, status_code=201)


@router.delete('/api/mcp/tokens/{token_id}', name='mcp.revoke_token', response_model=None)
def remove_token(token_id: str):
    """Revoke one credential without interrupting other MCP clients.

    Parameters
    ----------
    token_id : str
        Management identifier returned by the token list.

    Returns
    -------
    JSONResponse
        Revocation confirmation and remaining token metadata, or a fixed not-found error.
    """
    with Session(storage.engine()) as database:
        row = database.get(storage.AppSetting, f'{_KEY_PREFIX}{token_id}')
        if row is None:
            return JSONResponse({'message': 'MCP token not found.'}, status_code=404)
        database.delete(row)
        database.commit()
    return JSONResponse({
        'message': 'MCP token revoked.',
        'tokens': list_tokens(),
    })


@router.delete('/api/mcp/tokens', name='mcp.revoke_tokens')
def remove_tokens() -> dict:
    """Revoke every MCP credential through a CSRF-protected administrator request.

    Returns
    -------
    dict
        Revocation confirmation and an empty token list.
    """
    revoke_tokens()
    return {
        'message': 'All MCP tokens revoked.',
        'tokens': [],
    }


def authorize(request: Request) -> JSONResponse | None:
    """Authenticate each MCP HTTP request independently of browser cookies.

    Parameters
    ----------
    request : Request
        Request with an Authorization bearer header.

    Returns
    -------
    JSONResponse or None
        Fixed authentication failure, or no response with the scope in request state.
    """
    scheme, _, token = request.headers.get('authorization', '').partition(' ')
    if scheme.lower() == 'bearer' and 32 <= len(token) <= 256 and token.isascii():
        digest = hashlib.sha256(token.encode()).hexdigest()
        with Session(storage.engine()) as database:
            row = database.get(storage.AppSetting, f'{_KEY_PREFIX}{digest}')
        current = admin.account()
        if row and current:
            value = json.loads(row.value)
            if value.get('scope') in _SCOPES and hmac.compare_digest(value['revision'], current['revision']):
                request.state.mcp_scope = value['scope']
                return None
    return JSONResponse(
        {'message': 'A valid MCP bearer token is required.'},
        status_code=401,
        headers={'WWW-Authenticate': 'Bearer realm="Themerr MCP"'},
    )
