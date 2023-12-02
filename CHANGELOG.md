# Changelog

## [0.3.1] - 2023-12-02
**Unreleased**

## [0.3.0] - 2023-11-29
**Added**
- Option to enable/disable support for Plex Movie agent - (enabled by default)
- Option to update themes on a schedule - (enabled by default)
- Option to download themes for collections - (enabled by default)
- Option to update collection metadata (art, poster, and summary) -
  (enabled by default for legacy agents, disabled for Plex Movie agent)
- Options to remove unused media (themes, art, posters) on update -
  (enabled by default for themes, disabled for art and posters)
- Themerr icon
- Version is now printed to the log on startup
- Version is now displayed in the Plex plugin menu
- Web UI which shows the completion percentage of theme songs in the Plex libraries
- Option to add YouTube cookies to workaround EU consent issue

**Fixed**
- Themerr-plex will now skip upload of media if the existing media is the same
- Themerr-plex is now categorized as a Utility plugin instead of Music
- Refactored code to use common methods where possible
- Use TMDB api to convert IMDB ids to TMDB ids
- Fix AlertListener on IPv6-aware hosts
- Fix error handling around update_plex_item to prevent plugin hanging
- youtube-dl messages are now logged to Themerr-plex plugin log
- Disable plexapi auto-reload
- Use correct types for plex item typehints
- Ensure themes added by Themerr-plex are unlocked
- Don't update metadata/fields which are locked
- Disable restricted python in Plex plugin framework
- Remove unused YouTube parameters

**Dependencies**
- Bump peter-evans/create-pull-request from 4 to 5
- Bump actions/checkout from 3 to 4
- Use plexapi-backport and bump to 4.15.6
- Use plexhints from pypi and bump to 0.1.3
- Bump youtube-dl to 00ef748

**Misc**
- Update LizardByte workflows
- Improve CI/CD testing
- Add CodeQL analysis

## [0.2.0] - 2023-07-31
**Added**
- Add option to prefer MPEG AAC audio codec over Opus

**Fixed**
- Fix issue where most theme songs would not play on Apple devices.
- Remove tests directory from release package

## [0.1.4] - 2023-04-20
**Fixed**
- Updated youtube_dl, fixing an issue where plugin would fail to get themes in some cases

**Misc**
- LinuxServer.io images now support mods with multi-digest layers (https://github.com/linuxserver/docker-mods/pull/577)

## [0.1.3] - 2023-01-28
**Added**
- Max Retries setting added, allowing you to specify how many times to retry a failed upload

**Fixed**
- Improve error handling and logging when theme song does not exist in ThemerrDB

## [0.1.2] - 2023-01-23
**Added**
- Process items from Plex Movie agent with a queue
- Allow specifying number of simultaneous items to process for Plex Movie agent

**Fixed**
- Fixed issue where plugin would be unresponsive to changes from Plex Movie agent after 30 minutes

## [0.1.1] - 2023-01-19
**Fixed**
- Fixed `plexapi.utils` import, causing plugin to hang

## [0.1.0] - 2023-01-18
**Added**
- Added support for new Plex Movie agent

## [0.0.8] - 2023-01-02
**Fixed**
- Fixed Read the Docs build error for epub

## [0.0.7] - 2022-12-28
**Fixed**
- Fixed readme status badge

## [0.0.6] - 2022-12-28
**Changed**
- Plex token is now automatically fetched from the Plex python environment

## [0.0.5] - 2022-10-15
**Fixed**
- changing timeout no longer requires a Plex Media Server restart

## [0.0.4] - 2022-10-14
**Fixed**
- issue with timeout not being respected
- agent info formatting corrected
- documentation corrected, it is not required to re-match movies/items

**Changed**
- default timeout is now 180 seconds

## [0.0.3] - 2022-10-09
**Fixed**
- use try/except/else for plexhints import
- docker build was missing some plugin files
- dockerignore file was not being respected
- issue with special characters being replaced in plist file

**Changed**
- move plugin to `Music` category

## [0.0.2] - 2022-10-04
**Fixed**
- `plexhints` import error on Docker
- Reduced release bundle size

## [0.0.1] - 2022-10-03
**Added**
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
[0.1.2]: https://github.com/lizardbyte/themerr-plex/releases/tag/v0.1.2
[0.1.3]: https://github.com/lizardbyte/themerr-plex/releases/tag/v0.1.3
[0.1.4]: https://github.com/lizardbyte/themerr-plex/releases/tag/v0.1.4
[0.2.0]: https://github.com/lizardbyte/themerr-plex/releases/tag/v0.2.0
