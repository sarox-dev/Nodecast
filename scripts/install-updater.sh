#!/usr/bin/env bash
set -e

NODECAST_DIR="${HOME}/.nodecast"
mkdir -p "$NODECAST_DIR"

# Detect install directory
if [ -f .env ]; then
    INSTALL_DIR=$(pwd)
elif [ -d "$HOME/Nodecast" ]; then
    INSTALL_DIR="$HOME/Nodecast"
else
    read -r -p "Enter Nodecast install directory: " INSTALL_DIR
    INSTALL_DIR="${INSTALL_DIR/#\~/$HOME}"
fi

APP_PORT=$(grep "^APP_PORT=" "$INSTALL_DIR/.env" 2>/dev/null | cut -d= -f2 || echo "5000")

# Save config
cat > "$NODECAST_DIR/config" <<EOF
INSTALL_DIR=$INSTALL_DIR
APP_PORT=$APP_PORT
EOF

# Copy update script
cp "$INSTALL_DIR/scripts/update-nodecast.sh" "$NODECAST_DIR/update.sh"
chmod +x "$NODECAST_DIR/update.sh"

# Install cron job
CRON_JOB="*/15 * * * * ${NODECAST_DIR}/update.sh"
(crontab -l 2>/dev/null | grep -v "update.sh" ; echo "$CRON_JOB") | crontab -

echo "✓ Auto-updater installed (checks every 15 min)"
echo "  Config: $NODECAST_DIR/config"
echo "  Update script: $NODECAST_DIR/update.sh"