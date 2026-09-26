#!/usr/bin/env bash
set -Eeuo pipefail

INSTALL_DIR="${NODECAST_INSTALL_DIR:-$(pwd)}"
MODE="${NODECAST_MODE:-docker}"
APP_PORT="${NODECAST_APP_PORT:-5000}"
STATE_DIR="${HOME}/.nodecast"
mkdir -p "$STATE_DIR"
printf 'INSTALL_DIR=%s\nMODE=%s\nAPP_PORT=%s\n' "$INSTALL_DIR" "$MODE" "$APP_PORT" > "$STATE_DIR/config"
cp "$INSTALL_DIR/scripts/update-nodecast.sh" "$STATE_DIR/update.sh"
chmod 700 "$STATE_DIR/update.sh"

if command -v systemctl >/dev/null; then
  mkdir -p "$HOME/.config/systemd/user"
  cat > "$HOME/.config/systemd/user/nodecast-update.service" <<EOF
[Unit]
Description=Update Nodecast when a release is available

[Service]
Type=oneshot
ExecStart=${STATE_DIR}/update.sh
EOF
  cat > "$HOME/.config/systemd/user/nodecast-update.timer" <<EOF
[Unit]
Description=Check for Nodecast updates

[Timer]
OnBootSec=5min
OnUnitActiveSec=30min
Persistent=true

[Install]
WantedBy=timers.target
EOF
  systemctl --user daemon-reload
  systemctl --user enable --now nodecast-update.timer
elif [[ "$(uname -s)" == "Darwin" ]]; then
  PLIST="$HOME/Library/LaunchAgents/dev.nodecast.update.plist"; mkdir -p "$(dirname "$PLIST")"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict><key>Label</key><string>dev.nodecast.update</string><key>ProgramArguments</key><array><string>${STATE_DIR}/update.sh</string></array><key>StartInterval</key><integer>1800</integer><key>RunAtLoad</key><true/></dict></plist>
EOF
  launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
else
  command -v crontab >/dev/null || { echo "No supported scheduler found." >&2; exit 1; }
  JOB="*/30 * * * * ${STATE_DIR}/update.sh"
  (crontab -l 2>/dev/null | grep -v "${STATE_DIR}/update.sh" || true; echo "$JOB") | crontab -
fi

echo "Automatic updates enabled (checks every 30 minutes)."
