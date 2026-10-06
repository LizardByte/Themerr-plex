"""Read the code-owned Jellyfin compatibility series shared with MSBuild."""

# standard imports
from pathlib import Path
import re
import xml.etree.ElementTree as ET

_MANIFEST = ET.parse(Path(__file__).with_suffix('.props')).getroot()
DEFAULT_SERIES = _MANIFEST.findtext('./PropertyGroup/JellyfinSeries')
PROFILES = {
    group.attrib['Label']: {child.tag: child.text for child in group}
    for group in _MANIFEST.findall('PropertyGroup')
    if 'Label' in group.attrib
}


def version_parts(value):
    """Parse stable two-, three-, or four-component versions without accepting previews."""
    if not isinstance(value, str) or re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){1,3}', value) is None:
        raise ValueError('Invalid stable Jellyfin version.')
    parts = tuple(int(part) for part in value.split('.'))
    return parts + (0,) * (4 - len(parts))


def select(server_version):
    """Select a supported compatibility series using its explicit inclusive minimum and exclusive maximum."""
    version = version_parts(server_version)
    for series, values in PROFILES.items():
        if version_parts(values['JellyfinMinimumVersion']) <= version < version_parts(values['JellyfinMaximumVersion']):
            return series
    raise ValueError('Unsupported Jellyfin version.')
