#!/usr/bin/env bash
set -euo pipefail

mkdir -p "${EDA_DATA_DIR:-/data}" "${EDA_LOG_DIR:-/data/logs}"

if [ ! -S /var/run/docker.sock ]; then
    echo "WARNING: /var/run/docker.sock is not mounted. Docker-backed admin actions will fail."
fi

if [ ! -x "${DUNE_ROOT:-/redblink}/runtime/scripts/dune" ]; then
    echo "WARNING: RedBlink dune script not found or not executable at ${DUNE_ROOT:-/redblink}/runtime/scripts/dune."
    echo "Mount your RedBlink stack directory and set DUNE_ROOT if needed."
else
    ln -sf "${DUNE_ROOT:-/redblink}/runtime/scripts/dune" /usr/local/bin/dune
    echo "Linked RedBlink dune helper at /usr/local/bin/dune."
fi

exec "$@"
