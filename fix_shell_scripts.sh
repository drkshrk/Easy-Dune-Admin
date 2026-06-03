#!/bin/bash

# =========================================================
# Easy Dune Admin Shell Script Repair Helper
# =========================================================
#
# Use after uploading by SFTP if Linux says scripts are not executable or have
# bad interpreter errors from Windows line endings.
#
# Run from this folder:
#   bash fix_shell_scripts.sh

set -euo pipefail

cd "$(dirname "$0")"

echo "Repairing shell scripts under: $(pwd)"

find . -maxdepth 2 -type f -name "*.sh" -print0 | while IFS= read -r -d '' script; do
    # Remove CRLF carriage returns that can appear after Windows/SFTP edits.
    sed -i 's/\r$//' "$script"

    # Restore executable bit that SFTP uploads commonly lose.
    chmod +x "$script"

    echo "fixed $script"
done

echo "Shell script repair complete."
