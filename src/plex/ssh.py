"""Remove Plex uploads through SFTP with explicit host identity and root containment."""

# standard imports
import base64
from contextlib import contextmanager
import errno
import hashlib
import hmac
import io
import ipaddress
import json
import ntpath
import posixpath
import re
import stat

# lib imports
import paramiko
from sqlalchemy.orm import Session

# local imports
from common import credentials, logger
from common.path_policy import validate_relative_path
from media_servers.base import MediaServerError
from plex import servers
from plex.constants import metadata_type_map
from themerr import storage


log = logger.get_logger(__name__)
_MEDIA_DIRECTORIES = {
    'art': 'art',
    'posters': 'posters',
    'themes': 'themes',
}
_CONNECTION_ERROR = 'Unable to connect through SSH. Check the host fingerprint, credentials and SFTP permissions.'
_PATH_ERROR = 'SSH cleanup refused an unsafe or inaccessible Plex upload path.'
_DIRECTORY_ERROR = 'Enter an absolute Plex data directory, using a Windows drive path or an SFTP path.'


def _setting_id(server_id):
    return f'plex_ssh:{server_id}'


def _credential_id(server_id):
    return f'{servers.credential_id(server_id)}:ssh'


def settings(server_id: str) -> dict:
    """Read public SSH settings without exposing authentication secrets.

    Parameters
    ----------
    server_id : str
        Saved Plex machine identifier.

    Returns
    -------
    dict
        Non-secret connection settings, or an empty dictionary when SSH is disabled.
    """
    with Session(storage.engine()) as session:
        row = session.get(storage.AppSetting, _setting_id(server_id))
        return json.loads(row.value) if row else {}


def remove_settings(server_id: str) -> None:
    """Disable SSH cleanup and erase its saved credentials.

    Parameters
    ----------
    server_id : str
        Saved Plex machine identifier.
    """
    credentials.delete_token(_credential_id(server_id))
    with Session(storage.engine()) as session:
        row = session.get(storage.AppSetting, _setting_id(server_id))
        if row:
            session.delete(row)
        session.commit()


def _directory_path(value):
    """Convert an administrator-selected Windows root without collapsing unsafe components."""
    if re.match(r'^[A-Za-z]:[\\/]', value):
        value = value.replace('\\', '/')
        value = f'/{value[0].upper()}{value[1:]}'
    if not value.startswith('/') or value.startswith('//') or '\\' in value:
        raise MediaServerError(_DIRECTORY_ERROR, 400)
    drive_path = re.match(r'^/[A-Za-z]:/', value)
    relative = value[4:] if drive_path else value[1:]
    try:
        if relative:
            validate_relative_path(relative.removesuffix('/'))
    except ValueError as error:
        raise MediaServerError(_DIRECTORY_ERROR, 400) from error
    if drive_path:
        return f'/{value[1].upper()}:/{relative.removesuffix("/")}'
    return f'/{relative.removesuffix("/")}'


def _validate(values):
    if not isinstance(values, dict):
        raise MediaServerError('SSH settings must be an object.', 400)
    public = {}
    for field in (
        'host',
        'username',
        'data_directory',
        'host_fingerprint',
        'auth_type',
    ):
        value = values.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > 4096 or any(
                ord(character) < 32 or ord(character) == 127 for character in value):
            raise MediaServerError('Complete all SSH connection fields with valid values.', 400)
        public[field] = value.strip()
    try:
        ipaddress.ip_address(public['host'])
    except ValueError:
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9.-]{0,252}', public['host']):
            raise MediaServerError('Enter an SSH hostname or IP address, without a URL or path.', 400)
    if len(public['username']) > 256:
        raise MediaServerError('SSH username is too long.', 400)
    port = values.get('port', 22)
    if type(port) is not int or not 1 <= port <= 65535:
        raise MediaServerError('SSH port must be between 1 and 65535.', 400)
    public['port'] = port
    if public['auth_type'] not in (
        'key',
        'password',
    ):
        raise MediaServerError('Choose private-key or password authentication.', 400)
    fingerprint = public['host_fingerprint']
    if not re.fullmatch(r'SHA256:[A-Za-z0-9+/]{43}=?', fingerprint):
        raise MediaServerError('Enter the SSH server host fingerprint in SHA256 format.', 400)
    public['host_fingerprint'] = fingerprint.rstrip('=')
    # This is an explicit administrator-selected SFTP root, never a file-resource path.
    public['data_directory'] = _directory_path(public['data_directory'])
    return public


def _secrets(values, saved):
    result = dict(saved)
    for field in (
        'private_key',
        'passphrase',
        'password',
    ):
        value = values.get(field, '')
        if not isinstance(value, str) or len(value) > 32768 or '\x00' in value:
            raise MediaServerError('Invalid SSH authentication field.', 400)
        if value:
            result[field] = value
    if values['auth_type'] == 'key':
        result.pop('password', None)
        if not result.get('private_key'):
            raise MediaServerError('Provide an SSH private key.', 400)
    else:
        result.pop('private_key', None)
        result.pop('passphrase', None)
        if not result.get('password'):
            raise MediaServerError('Provide an SSH password.', 400)
    _blacklist(result)
    return result


def _blacklist(secret):
    logger.blacklist_config({'SSH': {f'{field}_SECRET': value for field, value in secret.items()}})


class _PinnedHostKey(paramiko.MissingHostKeyPolicy):
    def __init__(self, fingerprint):
        self.fingerprint = fingerprint

    def missing_host_key(self, client, hostname, key):
        digest = base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode('ascii').rstrip('=')
        if not hmac.compare_digest(self.fingerprint, f'SHA256:{digest}'):
            raise paramiko.SSHException('SSH host fingerprint mismatch')


def _private_key(secret):
    for key_class in (
        paramiko.Ed25519Key,
        paramiko.ECDSAKey,
        paramiko.RSAKey,
    ):
        try:
            return key_class.from_private_key(io.StringIO(secret['private_key']), password=secret.get('passphrase'))
        except paramiko.SSHException:
            continue
    raise MediaServerError('Unable to read the SSH private key. Check its format and passphrase.', 400)


@contextmanager
def _connection(public, secret):
    _blacklist(secret)
    try:
        with paramiko.SSHClient() as client:
            # Verify the supplied fingerprint before sending credentials. Never learn keys automatically.
            client.set_missing_host_key_policy(_PinnedHostKey(public['host_fingerprint']))
            client.connect(
                hostname=public['host'],
                port=public['port'],
                username=public['username'],
                pkey=_private_key(secret) if public['auth_type'] == 'key' else None,
                password=secret.get('password') if public['auth_type'] == 'password' else None,
                allow_agent=False,
                look_for_keys=False,
                timeout=10,
                banner_timeout=10,
                auth_timeout=10,
                channel_timeout=10,
            )
            with client.open_sftp() as sftp:
                sftp.get_channel().settimeout(30)
                yield sftp
    except (
        paramiko.SSHException,
        OSError,
        EOFError,
    ) as error:
        log.warning('SSH cleanup connection failed (%s)', type(error).__name__)
        raise MediaServerError(_CONNECTION_ERROR, 502) from error


def _root(sftp, configured_root):
    canonical = sftp.normalize(configured_root)
    if not re.fullmatch(r'/[A-Za-z]:/', canonical):
        canonical = canonical.rstrip('/') or '/'
    if not canonical.startswith('/') or '\\' in canonical or any(ord(character) < 32 for character in canonical):
        raise MediaServerError(_PATH_ERROR, 409)
    if not stat.S_ISDIR(sftp.lstat(canonical).st_mode):
        raise MediaServerError(_PATH_ERROR, 409)
    return canonical


def _resolve(sftp, root, relative, *, directory=False):
    """Validate each remote component and canonical containment at the SFTP boundary."""
    validate_relative_path(relative)
    candidate = root
    for component in relative.split('/'):
        candidate = posixpath.join(candidate, component)
        attributes = sftp.lstat(candidate)
        # Treat links and Windows junctions as unsafe even when a server resolves them differently.
        normalized = sftp.normalize(candidate).rstrip('/')
        if (stat.S_ISLNK(attributes.st_mode) or normalized != candidate or
                posixpath.commonpath((
                    root,
                    normalized,
                )) != (root.rstrip('/') or '/')):
            raise MediaServerError(_PATH_ERROR, 409)
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(attributes.st_mode):
        raise MediaServerError(_PATH_ERROR, 409)
    return candidate


def configure(server_id: str, values: dict) -> dict:
    """Verify SSH identity and the Plex root before saving the connection.

    Parameters
    ----------
    server_id : str
        Saved Plex machine identifier.
    values : dict
        Public SSH settings and optional replacement authentication secrets.

    Returns
    -------
    dict
        Verified non-secret settings.

    Raises
    ------
    MediaServerError
        The settings, SSH identity, credentials or Plex root cannot be verified.
    """
    if not servers.get_server(server_id):
        raise MediaServerError('Plex server not found.', 404)
    public = _validate(values)
    previous = settings(server_id)
    # Do not send a saved secret to a newly selected host or account.
    reuse = previous and all(previous[field] == public[field] for field in (
        'host',
        'port',
        'username',
        'host_fingerprint',
        'auth_type',
    ))
    saved = credentials.get_token(_credential_id(server_id)) if reuse else ''
    secret = _secrets({
        **values,
        'auth_type': public['auth_type'],
    }, json.loads(saved) if saved else {})
    with _connection(public, secret) as sftp:
        root = _root(sftp, public['data_directory'])
        _resolve(sftp, root, 'Metadata', directory=True)
        public['data_directory'] = root
    credentials.save_token(_credential_id(server_id), json.dumps(secret))
    with Session(storage.engine()) as session:
        row = session.get(storage.AppSetting, _setting_id(server_id))
        if row is None:
            session.add(storage.AppSetting(key=_setting_id(server_id), value=json.dumps(public)))
        else:
            row.value = json.dumps(public)
        session.commit()
    return public


def check(server_id: str) -> None:
    """Verify the saved SSH connection without modifying any remote files.

    Parameters
    ----------
    server_id : str
        Saved Plex machine identifier.

    Raises
    ------
    MediaServerError
        SSH is not configured or verification fails.
    """
    public = settings(server_id)
    secret = credentials.get_token(_credential_id(server_id)) if public else ''
    if not secret:
        raise MediaServerError('Configure SSH cleanup for this Plex server first.', 409)
    with _connection(public, json.loads(secret)) as sftp:
        _resolve(sftp, _root(sftp, public['data_directory']), 'Metadata', directory=True)


def _upload_directory(item, media_type):
    if media_type not in _MEDIA_DIRECTORIES or item.type not in metadata_type_map:
        raise MediaServerError('Unsupported Plex upload resource.', 400)
    # Plex supplies the GUID; requests never provide filesystem names.
    digest = hashlib.sha1(item.guid.encode('utf-8'), usedforsecurity=False).hexdigest()
    return (f'Metadata/{metadata_type_map[item.type]}/{digest[0]}/{digest[1:]}.bundle/'
            f'Uploads/{_MEDIA_DIRECTORIES[media_type]}')


def _tree(sftp, root, relative):
    directory = _resolve(sftp, root, relative, directory=True)
    files = []
    directories = [relative]
    for entry in sftp.listdir_attr(directory):
        # Names come from the remote filesystem, and are validated before joining.
        validate_relative_path(entry.filename)
        if '/' in entry.filename or ntpath.isabs(entry.filename):
            raise MediaServerError(_PATH_ERROR, 409)
        child = posixpath.join(relative, entry.filename)
        if stat.S_ISDIR(entry.st_mode):
            child_files, child_directories = _tree(sftp, root, child)
            files.extend(child_files)
            directories.extend(child_directories)
        else:
            _resolve(sftp, root, child)
            files.append(child)
    return (
        files,
        directories,
    )


def _cleanup(sftp, root, relative, keep):
    try:
        files, directories = _tree(sftp, root, relative)
    except OSError as error:
        if error.errno == errno.ENOENT and not keep:
            return
        raise
    remove = []
    retained = not keep
    for filename in files:
        path = _resolve(sftp, root, filename)
        if keep:
            with sftp.open(path, 'rb') as stream:
                matches = hashlib.file_digest(stream, 'sha256').hexdigest() == keep
            if matches:
                retained = True
                continue
        remove.append(filename)
    if not retained:
        raise MediaServerError('SSH cleanup could not find the verified new upload. Existing uploads were kept.', 409)
    for filename in remove:
        sftp.remove(_resolve(sftp, root, filename))
    if not keep:
        for directory in reversed(directories):
            sftp.rmdir(_resolve(sftp, root, directory, directory=True))


def remove_uploaded_media(server_id: str, item, media_type: str, keep_sha256: str | None = None) -> None:
    """Delete only one item's Plex uploads under the configured remote root.

    Parameters
    ----------
    server_id : str
        Saved Plex machine identifier.
    item : plexapi.base.PlexPartialObject
        Item fetched from the corresponding Plex server.
    media_type : str
        Fixed upload resource: themes, art or posters.
    keep_sha256 : str or None, optional
        Keep uploads matching the verified new audio digest.

    Raises
    ------
    MediaServerError
        The connection, containment checks or verified retained upload fails.
    """
    public = settings(server_id)
    secret = credentials.get_token(_credential_id(server_id)) if public else ''
    if not secret:
        raise MediaServerError('SSH cleanup credentials are unavailable. Save the SSH settings again.', 409)
    if keep_sha256 and re.fullmatch('[a-f0-9]{64}', keep_sha256) is None:
        raise MediaServerError('Invalid verified upload digest.', 400)
    relative = _upload_directory(item, media_type)
    try:
        with _connection(public, json.loads(secret)) as sftp:
            _cleanup(sftp, _root(sftp, public['data_directory']), relative, keep_sha256)
    except ValueError as error:
        raise MediaServerError(_PATH_ERROR, 409) from error
