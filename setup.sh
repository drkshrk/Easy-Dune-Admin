#!/bin/bash

echo
echo "==========================================="
echo " Dune Web Admin Initial Setup"
echo "==========================================="
echo

read -p "Linux username running the web admin: " WEBADMIN_USER

if [ -z "$WEBADMIN_USER" ]; then
    echo "No username supplied."
    exit 1
fi

if ! id "$WEBADMIN_USER" >/dev/null 2>&1; then
    echo "User '$WEBADMIN_USER' does not exist."
    exit 1
fi

SUDOERS_FILE="/etc/sudoers.d/dune-web-admin"

echo
echo "Creating restricted sudoers entry for:"
echo "  $WEBADMIN_USER"
echo

APT_BIN="$(command -v apt || true)"
SYSTEMCTL_BIN="$(command -v systemctl || true)"
USERMOD_BIN="$(command -v usermod || true)"
SH_BIN="$(command -v sh || true)"

if [ -z "$APT_BIN" ] || [ -z "$SYSTEMCTL_BIN" ] || [ -z "$USERMOD_BIN" ] || [ -z "$SH_BIN" ]; then
    echo "Could not locate apt, systemctl, usermod, or sh."
    exit 1
fi

DEFAULT_REDBLINK_DIR="/home/${WEBADMIN_USER}/dune-awakening-selfhost-docker"
read -p "RedBlink stack directory for install-command.sh [$DEFAULT_REDBLINK_DIR]: " REDBLINK_DIR
REDBLINK_DIR="${REDBLINK_DIR:-$DEFAULT_REDBLINK_DIR}"
REDBLINK_INSTALL_COMMAND="${REDBLINK_DIR%/}/runtime/scripts/install-command.sh"

sudo tee "$SUDOERS_FILE" >/dev/null <<EOF
# Easy Dune Admin restricted sudo rules.
# These are only for the optional legacy Infrastructure installer buttons.
# Normal Docker-primary operation should not require passwordless sudo.

Cmnd_Alias EDA_APT = \\
    ${APT_BIN} update, \\
    ${APT_BIN} install -y git curl ca-certificates apt-transport-https software-properties-common, \\
    ${APT_BIN} install -y docker.io docker-compose-plugin, \\
    ${APT_BIN} install -y docker-compose-plugin

Cmnd_Alias EDA_DOCKER_BOOTSTRAP = \\
    ${SH_BIN} /tmp/easy-dune-admin-get-docker.sh, \\
    ${SYSTEMCTL_BIN} enable --now docker, \\
    ${USERMOD_BIN} -aG docker ${WEBADMIN_USER}

Cmnd_Alias EDA_REDBLINK_INSTALL = \\
    ${REDBLINK_INSTALL_COMMAND}

${WEBADMIN_USER} ALL=(root) NOPASSWD: EDA_APT, EDA_DOCKER_BOOTSTRAP, EDA_REDBLINK_INSTALL
EOF

sudo chmod 440 "$SUDOERS_FILE"

echo
echo "Validating sudoers configuration..."
sudo visudo -c

if [ $? -ne 0 ]; then
    echo
    echo "ERROR: sudoers validation failed."
    exit 1
fi

echo
echo "Installed:"
echo "  $SUDOERS_FILE"

echo
echo "Testing permissions..."

sudo -n "$APT_BIN" update >/dev/null && echo "apt update OK"
sudo -n "$SYSTEMCTL_BIN" enable --now docker >/dev/null 2>&1 && echo "systemctl docker OK"

echo
echo "Setup complete."
echo
echo "You may need to log out and back in after Docker group changes."
echo "The generated sudoers file intentionally does not allow NOPASSWD: ALL."
echo
