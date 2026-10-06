"""Run connector unit tests and produce separate coverage and JUnit reports for each Jellyfin ABI."""

# standard imports
import argparse
import os
from pathlib import Path
import subprocess

# local imports
from build_connector import PROFILES, ROOT


def test(dotnet='dotnet', output=None, series=None):
    """Run the native test suite against each supported series' minimum SDK."""
    output = Path(output or ROOT / 'coverage').resolve()
    failed = False
    profiles = [profile for profile in PROFILES if not series or profile in series]
    for profile in profiles:
        directory = output / (f'connector-{profile}')
        directory.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [
                dotnet,
                'test',
                str(ROOT / 'connectors/jellyfin.tests/Connector.Tests.csproj'),
                '--configuration',
                'Release',
                f'-p:JellyfinSeries={profile}',
                f'-p:RestoreConfigFile={ROOT / "connectors/jellyfin/NuGet.Config"}',
                '-p:CollectCoverage=true',
                f'-p:CoverletOutput={directory.as_posix()}/',
                '-p:CoverletOutputFormat=opencover',
                '-p:Include=[Themerr.Connector]*',
                '--logger',
                f'junit;LogFilePath={directory / "junit.xml"}',
                '--logger',
                'console;verbosity=normal',
                '--results-directory',
                str(directory),
            ],
            check=False,
        )
        failed |= result.returncode != 0
    github_output = os.environ.get('GITHUB_OUTPUT')
    if github_output:
        with open(github_output, 'a', encoding='utf-8') as stream:
            for name, filename in {
                'coverage_files': 'coverage.opencover.xml',
                'test_files': 'junit.xml',
            }.items():
                files = ','.join(str(output / f'connector-{profile}' / filename) for profile in profiles)
                stream.write(f'{name}={files}\n')
    if failed:
        raise SystemExit('Jellyfin connector tests failed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dotnet', default='dotnet')
    parser.add_argument('--output', help='Directory for coverage and test results.')
    parser.add_argument('--series', action='append', choices=PROFILES, help='Test only the selected series.')
    arguments = parser.parse_args()
    test(arguments.dotnet, arguments.output, arguments.series)
