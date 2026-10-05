"""Run connector unit tests and produce separate coverage and JUnit reports for each Jellyfin ABI."""

import argparse
from pathlib import Path
import subprocess

from build_connector import PROFILES, ROOT


def test(dotnet='dotnet', output=None):
    """Run the same native test suite against both supported server assemblies."""
    output = Path(output or ROOT / 'coverage').resolve()
    failed = False
    for profile, (abi, framework) in PROFILES.items():
        directory = output / ('connector-' + profile)
        directory.mkdir(parents=True, exist_ok=True)
        result = subprocess.run([
            dotnet, 'test', str(ROOT / 'connectors/jellyfin.tests/Connector.Tests.csproj'),
            '--configuration', 'Release', f'-p:ConnectorFramework={framework}', f'-p:JellyfinVersion={abi}',
            f'-p:RestoreConfigFile={ROOT / "connectors/jellyfin/NuGet.Config"}',
            '-p:CollectCoverage=true', f'-p:CoverletOutput={directory.as_posix()}/',
            '-p:CoverletOutputFormat=opencover', '-p:Include=[Themerr.Connector]*',
            '--logger', f'junit;LogFilePath={directory / "junit.xml"}',
            '--logger', 'console;verbosity=normal', '--results-directory', str(directory),
        ], check=False)
        failed |= result.returncode != 0
    if failed:
        raise SystemExit('Jellyfin connector tests failed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dotnet', default='dotnet')
    parser.add_argument('--output', help='Directory for coverage and test results.')
    arguments = parser.parse_args()
    test(arguments.dotnet, arguments.output)
