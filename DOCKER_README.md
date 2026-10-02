# Docker

## lizardbyte/themerr-plex

Before Plex sign-in, create a persistent key file outside the `/config` volume. Keep this file private and ensure the
container's `PUID` can read it. Keep the same key when recreating the container; losing it requires signing in again.

```bash
python3 -c 'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())' > themerr-plex.key
chmod 600 themerr-plex.key
```

### Using docker run
Create and run the container (substitute your `<values>`):

```bash
docker run -d \
  --name=themerr-plex \
  --restart=unless-stopped \
  -v <path to data>:/config \
  -v <absolute path to themerr-plex.key>:/run/secrets/themerr_plex_key:ro \
  -e THEMERR_PLEX_TOKEN_KEY_FILE=/run/secrets/themerr_plex_key \
  -e PUID=<uid> \
  -e PGID=<gid> \
  -e TZ=<timezone> \
  -p 9494:9494 \
  lizardbyte/themerr-plex
```

To update the container it must be removed and recreated:

```bash
# Stop the container
docker stop themerr-plex
# Remove the container
docker rm themerr-plex
# Pull the latest update
docker pull lizardbyte/themerr-plex
# Run the container with the same parameters as before
docker run -d ...
```

### Using docker-compose

Create a `docker-compose.yml` file with the following contents (substitute your `<values>`):

```yaml
version: '3'
services:
  themerr-plex:
    image: lizardbyte/themerr-plex
    container_name: themerr-plex
    restart: unless-stopped
    volumes:
      - <path to data>:/config
      - <absolute path to themerr-plex.key>:/run/secrets/themerr_plex_key:ro
    environment:
      - THEMERR_PLEX_TOKEN_KEY_FILE=/run/secrets/themerr_plex_key
      - PUID=<uid>
      - PGID=<gid>
      - TZ=<timezone>
    ports:
      - 9494:9494
```

Create and start the container (run the command from the same folder as your `docker-compose.yml` file):

```bash
docker-compose up -d
```

To update the container:
```bash
# Pull the latest update
docker-compose pull
# Update and restart the container
docker-compose up -d
```

### Parameters
You must substitute the `<values>` with your own settings.

Parameters are split into two halves separated by a colon. The left side represents the host and the right side the
container.

**Example:** `-p external:internal` - This shows the port mapping from internal to external of the container.
Therefore `-p 9494:9494` exposes port `9494` from inside the container on the host's port `9494`.
The internal port is `9494`; the host port may be changed (e.g. `-p 8080:9494`).


| Parameter                   | Function                                                                             | Example Value        | Required |
|-----------------------------|--------------------------------------------------------------------------------------|----------------------|:--------:|
| `-p <port>:9494`            | Web UI Port                                                                          | `9494`               |   True   |
| `-v <path to data>:/config` | Volume mapping                                                                       | `/home/themerr-plex` |   True   |
| `-v <path to key>:/run/secrets/themerr_plex_key:ro` | Read-only token encryption key | `/home/me/themerr-plex.key` | True |
| `-e THEMERR_PLEX_TOKEN_KEY_FILE=...` | Container path to the token encryption key | `/run/secrets/themerr_plex_key` | True |
| `-e PUID=<uid>`             | User ID                                                                              | `1001`               |  False   |
| `-e PGID=<gid>`             | Group ID                                                                             | `1001`               |  False   |
| `-e TZ=<timezone>`          | Lookup TZ value [here](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) | `America/New_York`   |   True   |

### User / Group Identifiers:

When using data volumes (-v flags) permissions issues can arise between the host OS and the container. To avoid this
issue you can specify the user PUID and group PGID. Ensure the data volume directory on the host is owned by the same
user you specify.

In this instance `PUID=1001` and `PGID=1001`. To find yours use id user as below:

```bash
$ id dockeruser
uid=1001(dockeruser) gid=1001(dockergroup) groups=1001(dockergroup)
```
