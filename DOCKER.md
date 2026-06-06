# Docker Install

Docker is the primary install path for Easy Dune Admin as of `0.8.4-beta`.

## What The Container Mounts

- `/data` stores `users.db`, logs, and other local runtime state.
- `/redblink` should be your host RedBlink stack directory.
- `/var/run/docker.sock` lets Easy Dune Admin and RedBlink scripts talk to the
  host Docker daemon.
- The image installs the official static Docker CLI so `docker exec` and
  RedBlink helper scripts can use that mounted host Docker socket.
- If `ENABLE_HOST_SHELL=1`, the browser shell opens inside this Easy Dune Admin
  container, not directly on the Linux host. The entrypoint links the mounted
  RedBlink helper to `/usr/local/bin/dune` so commands such as `dune status`
  and `dune manager` work from the container shell.

The container does not bundle RedBlink. It expects the host stack to already
exist and be mounted.

## Persistent Webadmin Data

`docker-compose.yml` mounts the named volume `easy-dune-admin-data` at `/data`.
Easy Dune Admin stores `users.db` at `/data/users.db` and logs under
`/data/logs`, so normal image rebuilds preserve webadmin users and roles.

Do not run `docker compose down -v` unless you want to delete that named volume
and reset the webadmin setup. Plain `docker compose down` leaves the volume
intact.

## Quick Start

```bash
cp .env.docker.example .env
nano .env
chmod +x rebuild_docker.sh docker/entrypoint.sh
./rebuild_docker.sh
```

For later updates from the Linux host checkout, pull the latest source and run:

```bash
FOLLOW_LOGS=0 ./rebuild_docker.sh
```

The Infrastructure page can run the same GitHub pull + Docker rebuild flow from
Docker mode when `.env` sets:

```bash
ENABLE_SELF_UPDATE=1
EASY_DUNE_HOST_DIR=/absolute/path/to/Easy-Dune-Admin
```

Docker mode starts a detached `easy-dune-admin-updater` container from
`EASY_DUNE_UPDATER_IMAGE`. That updater mounts the host checkout, refuses dirty
Git trees, pulls GitHub, runs `FOLLOW_LOGS=0 ./rebuild_docker.sh`, and can keep
working while the webadmin container is replaced. Watch it from the host with:

```bash
docker logs -f easy-dune-admin-updater
```

`rebuild_docker.sh` stamps each image with the Git revision and dirty-state used
for the build. The normal updater refuses to run if the running image was built
from dirty source or if the running image revision does not match the mounted
host checkout. This protects uploaded/devbuild containers from being silently
replaced by an older checkout. Docker mode runs these checks as a foreground
preflight first, so the Infrastructure panel reports when the update was
aborted before any detached updater is started.

The Clean Reinstall button uses the same detached updater container, but it is
more destructive: after typing `CLEAN INSTALL`, it force-resets the Easy Dune
Admin checkout to upstream GitHub, removes untracked source/build files, keeps
`.env` plus common local runtime paths, and then rebuilds Docker.

Open:

```text
http://SERVER-IP:8089
```

## Production Notes

- Change `DUNE_SECRET_KEY`.
- Set `REDBLINK_HOST_DIR` to your RedBlink stack path.
- Set `EASY_DUNE_HOST_DIR` to this Easy Dune Admin checkout path if you want
  the Docker-mode Infrastructure update button.
- Set `EASY_DUNE_DEVELOPER_KEY_HASH` if you use the hidden Developer page.
- Keep `ENABLE_HOST_SHELL=0` unless this is a trusted LAN/VPN-only install.
- The Docker socket mount is powerful. Anyone with admin access to the panel can
  indirectly control host Docker.
