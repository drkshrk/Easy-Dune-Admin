# Docker Test Package

This folder is an experimental containerized Easy Dune Admin build. It is kept
separate from the normal release folder so Docker packaging can be tested
without disturbing the current app layout.

## What The Container Mounts

- `/data` stores `users.db`, logs, and other local runtime state.
- `/redblink` should be your host RedBlink stack directory.
- `/var/run/docker.sock` lets Easy Dune Admin and RedBlink scripts talk to the
  host Docker daemon.
- The image installs the official static Docker CLI so `docker exec` and
  RedBlink helper scripts can use that mounted host Docker socket.

The container does **not** bundle RedBlink. It expects the host stack to already
exist and be mounted.

## Quick Test

```bash
cd easy-dune-admin-docker-test
cp .env.docker.example .env
nano .env
docker compose -f docker-compose.test.yml up --build
```

Open:

```text
http://SERVER-IP:8088
```

## Production Notes

- Change `DUNE_SECRET_KEY`.
- Keep `ENABLE_HOST_SHELL=0` unless this is a trusted LAN/VPN-only install.
- The Docker socket mount is powerful. Anyone with admin access to the panel can
  indirectly control host Docker.
- RedBlink memory/map/server controls still operate against the host stack, not
  a stack inside this image.
