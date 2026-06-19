# Docker Install

Docker is the primary install path for Easy Dune Admin as of `0.8.8-beta`.

## What The Container Mounts

- `/data` stores `users.db`, logs, and other local runtime state.
- The RedBlink stack should be mounted at the same absolute path inside Easy
  Dune Admin that it uses on the Docker host, for example
  `/home/steihl/dune-awakening-selfhost-docker`.
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

Keep `DUNE_ROOT_CONTAINER` equal to `REDBLINK_HOST_DIR` in Docker mode. RedBlink
scripts launch sibling server containers through the mounted host Docker socket,
and Docker bind-mount source paths are interpreted by the host daemon. If Easy
Dune Admin sees RedBlink at `/redblink` but the host does not, commands such as
`dune restart survival` can create a Survival container that cannot find
`/opt/dune-local/run-server.sh`.

If an existing install was created with the old `/redblink` container alias,
`docker/env.repair-redblink-path.example` is a copy-ready `.env` repair template
for the `/home/steihl/easy-dune-admin` and
`/home/steihl/dune-awakening-selfhost-docker` layout.

## Persistent Webadmin Data

`docker-compose.yml` mounts the named volume `easy-dune-admin-data` at `/data`.
Easy Dune Admin stores `users.db` at `/data/users.db` and logs under
`/data/logs`, so normal image rebuilds preserve webadmin users and roles.

Do not run `docker compose down -v` unless you want to delete that named volume
and reset the webadmin setup. Plain `docker compose down` leaves the volume
intact.

Docker-mode catalog edits write through the mounted Easy Dune Admin checkout.
Current builds try to keep `data/easy-dune-item-catalog.json` owned by the same
Linux user that owns the checkout's `data` directory. If an older build saved
the catalog as `root` and SFTP/scp can no longer overwrite it, repair ownership
from the Docker host:

```bash
sudo chown "$USER:$USER" /path/to/easy-dune-admin/data
sudo chown "$USER:$USER" /path/to/easy-dune-admin/data/easy-dune-item-catalog.json
```

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
EASY_DUNE_HOST_DIR=/absolute/path/to/easy-dune-admin
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

## Clean Uninstall

The Infrastructure page includes a Clean Uninstall panel for trusted admins.
After typing `UNINSTALL EDA`, it removes the Easy Dune Admin Docker stack and
named webadmin data volume. It leaves the RedBlink stack, RedBlink database,
and this host checkout on disk. In Docker mode, a detached uninstaller removes
the Easy Dune Admin container as its final step, so the panel disconnects.

Manual clean uninstall from the Docker host:

```bash
cd /path/to/easy-dune-admin
docker compose -f docker-compose.yml down -v --remove-orphans
docker rm -f easy-dune-admin easy-dune-admin-updater easy-dune-admin-uninstaller 2>/dev/null || true
```

Optional follow-up cleanup:

```bash
docker image rm easy-dune-admin:0.8.8-beta 2>/dev/null || true
rm -rf /path/to/easy-dune-admin
```

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
