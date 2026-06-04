#!/bin/bash

# =========================================================
# Easy Dune Admin Docker Rebuild Helper
# =========================================================
#
# Run this from the Easy Dune Admin project root:
#   ./rebuild_docker.sh
#
# User-adjustable values:
# - COMPOSE_FILE: change only if you rename docker-compose.yml.
# - SERVICE_NAME: keep aligned with docker-compose.yml.
# - CONTAINER_NAME: keep aligned with docker-compose.yml container_name.
# - FOLLOW_LOGS: set to 0 to rebuild without attaching to logs.

set -euo pipefail

cd "$(dirname "$0")"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
SERVICE_NAME="${SERVICE_NAME:-easy-dune-admin}"
CONTAINER_NAME="${CONTAINER_NAME:-easy-dune-admin}"
FOLLOW_LOGS="${FOLLOW_LOGS:-1}"

if [ ! -f "${COMPOSE_FILE}" ]; then
    echo "ERROR: ${COMPOSE_FILE} not found in $(pwd)."
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: docker command not found."
    exit 1
fi

echo "Stopping existing Easy Dune Admin stack..."
docker compose -f "${COMPOSE_FILE}" down

# docker compose down removes containers from the current compose project. If
# the folder was renamed or launched under a different project name, a fixed-name
# container can remain and block the next up. Remove only this webadmin
# container; named volumes such as easy-dune-admin-data are preserved.
if docker ps -a --format '{{.Names}}' | grep -Fxq "${CONTAINER_NAME}"; then
    echo "Removing stale container: ${CONTAINER_NAME}"
    docker rm -f "${CONTAINER_NAME}"
fi

echo "Rebuilding and starting Easy Dune Admin..."
docker compose -f "${COMPOSE_FILE}" up --build -d

echo
echo "Docker rebuild complete."
echo "Open the webadmin at the port configured by EDA_PORT, usually:"
echo "  http://SERVER-IP:8088"
echo

if [ "${FOLLOW_LOGS}" = "1" ]; then
    echo "Following logs for service: ${SERVICE_NAME}"
    echo "Press Ctrl+C to stop watching logs; the container will keep running."
    docker compose -f "${COMPOSE_FILE}" logs -f "${SERVICE_NAME}"
fi
