# Changelog

## [0.1.1] - 2023-01-19
### Fixed
- Fixed `plexapi.utils` import, causing plugin to hang

## [0.1.0] - 2023-01-18
### Added
- Added support for new Plex Movie agent

## [0.0.8] - 2023-01-02
### Fixed
- Fixed Read the Docs build error for epub

## [0.0.7] - 2022-12-28
### Fixed
- Fixed readme status badge

## [0.0.6] - 2022-12-28
### Changed
- Plex token is now automatically fetched from the Plex python environment

## [0.0.5] - 2022-10-15
### Fixed
- changing timeout no longer requires a Plex Media Server restart

## [0.0.4] - 2022-10-14
### Fixed
- issue with timeout not being respected
- agent info formatting corrected
- documentation corrected, it is not required to re-match movies/items
### Changed
- default timeout is now 180 seconds

## [0.0.3] - 2022-10-09
### Fixed
- use try/except/else for plexhints import
- docker build was missing some plugin files
- dockerignore file was not being respected
- issue with special characters being replaced in plist file
### Changed
- move plugin to `Music` category

## [0.0.2] - 2022-10-04
### Fixed
- `plexhints` import error on Docker
- Reduced release bundle size

## [0.0.1] - 2022-10-03
### Added
- Initial Release

[0.0.1]: https://github.com/lizardbyte/themerr-plex/releases/tag/v0.0.1
[0.0.2]: https://github.com/lizardbyte/themerr-plex/releases/tag/v0.0.2
[0.0.3]: https://github.com/lizardbyte/themerr-plex/releases/tag/v0.0.3
[0.0.4]: https://github.com/lizardbyte/themerr-plex/releases/tag/v0.0.4
[0.0.5]: https://github.com/lizardbyte/themerr-plex/releases/tag/v0.0.5
[0.0.6]: https://github.com/lizardbyte/themerr-plex/releases/tag/v0.0.6
[0.0.7]: https://github.com/lizardbyte/themerr-plex/releases/tag/v0.0.7
[0.0.8]: https://github.com/lizardbyte/themerr-plex/releases/tag/v0.0.8
[0.1.0]: https://github.com/lizardbyte/themerr-plex/releases/tag/v0.1.0
[0.1.1]: https://github.com/lizardbyte/themerr-plex/releases/tag/v0.1.1
