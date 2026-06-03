# Docker preview package

This folder is an experimental containerized Easy Dune Admin build. It lives
inside the main project folder so the normal app and Docker preview package can be
uploaded together, while Docker-specific files stay grouped in one place.

## What The Container Mounts

- `/data` stores `users.db`, logs, and other local runtime state.
- `/redblink` should be your host RedBlink stack directory.
- `/var/run/docker.sock` lets Easy Dune Admin and RedBlink scripts talk to the
  host Docker daemon.
- The image installs the official static Docker CLI so `docker exec` and
  RedBlink helper scripts can use that mounted host Docker socket.
- If `ENABLE_HOST_SHELL=1`, the browser shell opens inside this Easy Dune Admin
  container, not the Linux host. The entrypoint links the mounted RedBlink
  helper to `/usr/local/bin/dune` so commands such as `dune status` and
  `dune manager` work from the container shell.

The container does **not** bundle RedBlink. It expects the host stack to already
exist and be mounted.

## Persistent Webadmin Data

`docker-compose.test.yml` mounts the named volume `easy-dune-admin-data` at
`/data`. Easy Dune Admin stores `users.db` at `/data/users.db` and logs under
`/data/logs`, so normal image rebuilds should preserve webadmin users and roles.

Do not run `docker compose -f docker-compose.test.yml down -v` unless you want
to delete that named volume and reset the webadmin setup. Plain
`docker compose -f docker-compose.test.yml down` leaves the volume intact.

## Login Installation Profile

The Docker preview package defaults to the `RedBlink Docker Container` login
profile. The login page also offers `Linux Host` and experimental `Hyper-V via
SSH`. Hyper-V mode requires `EASY_DUNE_HYPERV_SSH_TARGET` and
`EASY_DUNE_HYPERV_DUNE_ROOT` in `.env`; leave them blank unless the webadmin
needs to SSH into a Hyper-V Linux VM.

## Quick Test

```bash
cd docker-preview
cp .env.docker.example .env
nano .env
docker compose -f docker-compose.test.yml up --build
```

Or use the included helper:

```bash
bash fix_shell_scripts.sh
chmod +x rebuild_docker.sh
./rebuild_docker.sh
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
