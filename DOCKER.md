# Docker Install

Docker is the primary install path for Easy Dune Admin as of `0.8.3-alpha`.

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

Open:

```text
http://SERVER-IP:8088
```

## Production Notes

- Change `DUNE_SECRET_KEY`.
- Set `REDBLINK_HOST_DIR` to your RedBlink stack path.
- Set `EASY_DUNE_DEVELOPER_KEY_HASH` if you use the hidden Developer page.
- Keep `ENABLE_HOST_SHELL=0` unless this is a trusted LAN/VPN-only install.
- The Docker socket mount is powerful. Anyone with admin access to the panel can
  indirectly control host Docker.
