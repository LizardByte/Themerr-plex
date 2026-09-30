<div align="center">
  <img
    src="https://raw.githubusercontent.com/LizardByte/Themerr-plex/refs/heads/master/web/images/icon-default.png"
    alt="Themerr-plex icon"
    width="256"
  />
  <h1 align="center">Themerr-plex</h1>
  <h4 align="center">Standalone theme song manager for Plex using ThemerrDB.</h4>
</div>

<div align="center">
  <a href="https://github.com/LizardByte/Themerr-plex/actions/workflows/CI.yml?query=branch%3Amaster"><img src="https://img.shields.io/github/actions/workflow/status/lizardbyte/themerr-plex/CI.yml.svg?branch=master&label=build&logo=github&style=for-the-badge" alt="GitHub Workflow Status"></a>
  <a href="https://github.com/LizardByte/Themerr-plex/releases/latest"><img src="https://img.shields.io/github/downloads/lizardbyte/themerr-plex/total?style=for-the-badge&logo=github" alt="GitHub Releases"></a>
  <a href="https://hub.docker.com/r/lizardbyte/themerr-plex"><img src="https://img.shields.io/docker/pulls/lizardbyte/themerr-plex?style=for-the-badge&logo=docker" alt="Docker"></a>
  <a href="https://codecov.io/gh/LizardByte/Themerr-plex"><img src="https://img.shields.io/codecov/c/gh/LizardByte/Themerr-plex?token=1LYYVYWY9D&style=for-the-badge&logo=codecov" alt="Codecov"></a>
  <a href="https://themerr-plex.readthedocs.io/"><img src="https://img.shields.io/readthedocs/themerr-plex?label=docs&style=for-the-badge&logo=readthedocs" alt="Read the Docs"></a>
</div>

## ℹ️ About

Themerr-plex adds theme music to Plex movies and TV shows from [ThemerrDB](https://github.com/LizardByte/ThemerrDB).
It listens for Plex library updates and can also scan supported libraries on a schedule. YouTube audio streams are
resolved with `yt-dlp`.

It works with the Plex Movie (`tv.plex.agents.movie`) and Plex Series (`tv.plex.agents.series`) agents. Install and
configure the application separately from Plex; no Plex plug-in directory is used.

Application state and Plex sign-in are stored in `config/themerr-plex.db` (`/config/themerr-plex.db` in Docker).
Existing JSON state is imported automatically on first use; the old files are retained as backups.

LizardByte has the full documentation hosted on [Read the Docs](https://themerr-plex.readthedocs.io/).
