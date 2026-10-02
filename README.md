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
  <a href="https://github.com/LizardByte/Themerr-plex"><img src="https://img.shields.io/github/stars/lizardbyte/Themerr-plex.svg?logo=github&style=for-the-badge" alt="GitHub stars"></a>
  <a href="https://github.com/LizardByte/Themerr-plex/releases/latest"><img src="https://img.shields.io/github/downloads/lizardbyte/Themerr-plex/total.svg?style=for-the-badge&logo=github" alt="GitHub Releases"></a>
  <a href="https://hub.docker.com/r/lizardbyte/themerr-plex"><img src="https://img.shields.io/docker/pulls/lizardbyte/themerr-plex.svg?style=for-the-badge&logo=docker" alt="Docker"></a>
  <a href="https://github.com/LizardByte/Themerr-plex/actions/workflows/ci.yml?query=branch%3Amaster"><img src="https://img.shields.io/github/actions/workflow/status/lizardbyte/Themerr-plex/ci.yml.svg?branch=master&label=build&logo=github&style=for-the-badge" alt="GitHub Workflow Status"></a>
  <a href="https://codecov.io/gh/LizardByte/Themerr-plex"><img src="https://img.shields.io/endpoint.svg?url=https%3A%2F%2Fapp.lizardbyte.dev%2Fdashboard%2Fshields%2Fcodecov%2FThemerr-plex.json&style=for-the-badge&logo=codecov" alt="Codecov"></a>
  <a href="https://sonarcloud.io/project/overview?id=LizardByte_Themerr-plex"><img src="https://img.shields.io/sonar/quality_gate/LizardByte_Themerr-plex.svg?server=https%3A%2F%2Fsonarcloud.io&style=for-the-badge&logo=sonarqubecloud&label=sonarcloud" alt="SonarCloud"></a>
</div>

# Overview

## ℹ️ About

Themerr-plex adds theme music to Plex movies and TV shows from [ThemerrDB](https://github.com/LizardByte/ThemerrDB).
It listens for Plex library updates and can also scan supported libraries on a schedule. YouTube audio streams are
resolved with `yt-dlp`.

It works with the Plex Movie (`tv.plex.agents.movie`) and Plex Series (`tv.plex.agents.series`) agents. Install and
configure the application separately from Plex; no Plex plug-in directory is used.

LizardByte has the full documentation hosted on [Read the Docs](https://themerr-plex.readthedocs.io/).
