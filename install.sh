#!/usr/bin/env bash
set -Eeuo pipefail

REPO="sarox-dev/Nodecast"
TTY="/dev/tty"
[[ -r "$TTY" ]] || TTY="/dev/stdin"
BLUE='\033[38;5;75m'; GREEN='\033[38;5;78m'; DIM='\033[2m'; RESET='\033[0m'

title() {
  printf "\n${BLUE}╭────────────────────────────────────────────╮\n"
  printf "│              NODECAST SETUP                │\n"
  printf "╰────────────────────────────────────────────╯${RESET}\n"
  printf "${DIM}Local-first memory for you and your agents.${RESET}\n\n"
}
step() { printf "${BLUE}●${RESET} %s\n" "$1"; }
ok() { printf "${GREEN}✓${RESET} %s\n" "$1"; }
fail() { printf "Error: %s\n" "$1" >&2; exit 1; }
ask() { local prompt="$1" default="$2" answer; read -r -p "$prompt" answer <"$TTY"; printf '%s' "${answer:-$default}"; }

command -v curl >/dev/null || fail "curl is required"
command -v unzip >/dev/null || fail "unzip is required"

title
OS="$(uname -s)"
[[ "$OS" == "Linux" || "$OS" == "Darwin" ]] || fail "Use install.ps1 on Windows."

MODE="${NODECAST_MODE:-}"
if [[ -z "$MODE" ]]; then
  printf "  ${BLUE}1${RESET}  Docker  ${DIM}isolated, easiest to maintain${RESET}\n"
  printf "  ${BLUE}2${RESET}  Host    ${DIM}native Python service, lighter runtime${RESET}\n\n"
  choice="$(ask "Install method [1]: " "1")"
  [[ "$choice" == "2" ]] && MODE="host" || MODE="docker"
fi

AUTO_UPDATE="${NODECAST_AUTO_UPDATE:-}"
if [[ -z "$AUTO_UPDATE" ]]; then
  answer="$(ask "Enable automatic updates? [Y/n]: " "Y")"
  [[ "$answer" =~ ^[Nn]$ ]] && AUTO_UPDATE="false" || AUTO_UPDATE="true"
fi

DEFAULT_DIR="${HOME}/Nodecast"
INSTALL_DIR="${NODECAST_INSTALL_DIR:-}"
[[ -n "$INSTALL_DIR" ]] || INSTALL_DIR="$(ask "Install directory [$DEFAULT_DIR]: " "$DEFAULT_DIR")"
INSTALL_DIR="${INSTALL_DIR/#\~/$HOME}"

if [[ "$MODE" == "docker" ]]; then
  command -v docker >/dev/null || fail "Docker is required for Docker mode."
  docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is required."
else
  command -v python3 >/dev/null || fail "Python 3 is required for Host mode."
  python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' || fail "Python 3.11 or newer is required."
fi

step "Downloading the latest GitHub release"
LATEST_TAG="$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)"
[[ -n "$LATEST_TAG" ]] || fail "Could not determine the latest release."
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
curl -fsSL "https://github.com/$REPO/archive/refs/tags/$LATEST_TAG.zip" -o "$TMP_DIR/release.zip"
unzip -q "$TMP_DIR/release.zip" -d "$TMP_DIR/extract"
SOURCE_DIR="$(find "$TMP_DIR/extract" -mindepth 1 -maxdepth 1 -type d | head -1)"
[[ -f "$SOURCE_DIR/app/version.json" ]] || fail "Downloaded release is incomplete."

mkdir -p "$INSTALL_DIR"
if command -v rsync >/dev/null; then
  rsync -a --delete --exclude='.env' --exclude='contents/' --exclude='.venv/' --exclude='.git/' "$SOURCE_DIR/" "$INSTALL_DIR/"
else
  (cd "$SOURCE_DIR" && tar --exclude='.env' --exclude='contents' --exclude='.venv' --exclude='.git' -cf - .) | (cd "$INSTALL_DIR" && tar -xf -)
fi
mkdir -p "$INSTALL_DIR/contents"

if [[ ! -f "$INSTALL_DIR/.env" ]]; then cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"; fi
if grep -q '^AUTO_UPDATE_DEFAULT=' "$INSTALL_DIR/.env"; then
  sed -i.bak "s/^AUTO_UPDATE_DEFAULT=.*/AUTO_UPDATE_DEFAULT=$AUTO_UPDATE/" "$INSTALL_DIR/.env" && rm -f "$INSTALL_DIR/.env.bak"
else
  printf '\nAUTO_UPDATE_DEFAULT=%s\n' "$AUTO_UPDATE" >> "$INSTALL_DIR/.env"
fi
APP_PORT="$(sed -n 's/^APP_PORT=//p' "$INSTALL_DIR/.env" | tail -1)"; APP_PORT="${APP_PORT:-5000}"

if [[ "$MODE" == "docker" ]]; then
  step "Building the Docker installation"
  (cd "$INSTALL_DIR" && docker compose up -d --build)
else
  step "Creating the native Python environment"
  python3 -m venv "$INSTALL_DIR/.venv"
  "$INSTALL_DIR/.venv/bin/pip" install --disable-pip-version-check -q -r "$INSTALL_DIR/requirements.txt"
  if [[ "$OS" == "Linux" ]] && command -v systemctl >/dev/null; then
    mkdir -p "$HOME/.config/systemd/user"
    SERVICE="$HOME/.config/systemd/user/nodecast.service"
    printf '[Unit]\nDescription=Nodecast\nAfter=network-online.target\n\n[Service]\nType=simple\nWorkingDirectory=%s\nEnvironment=NODECAST_INSTALL_MODE=host\nEnvironment=AUTO_UPDATE_DEFAULT=%s\nExecStart=%s/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port %s\nRestart=on-failure\n\n[Install]\nWantedBy=default.target\n' "$INSTALL_DIR" "$AUTO_UPDATE" "$INSTALL_DIR" "$APP_PORT" > "$SERVICE"
    systemctl --user daemon-reload
    systemctl --user enable --now nodecast.service
  elif [[ "$OS" == "Darwin" ]]; then
    PLIST="$HOME/Library/LaunchAgents/dev.nodecast.app.plist"; mkdir -p "$(dirname "$PLIST")"
    printf '<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd"><plist version="1.0"><dict><key>Label</key><string>dev.nodecast.app</string><key>ProgramArguments</key><array><string>%s/.venv/bin/uvicorn</string><string>app.main:app</string><string>--host</string><string>127.0.0.1</string><string>--port</string><string>%s</string></array><key>WorkingDirectory</key><string>%s</string><key>EnvironmentVariables</key><dict><key>NODECAST_INSTALL_MODE</key><string>host</string><key>AUTO_UPDATE_DEFAULT</key><string>%s</string></dict><key>RunAtLoad</key><true/><key>KeepAlive</key><true/></dict></plist>' "$INSTALL_DIR" "$APP_PORT" "$INSTALL_DIR" "$AUTO_UPDATE" > "$PLIST"
    launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
    launchctl bootstrap "gui/$(id -u)" "$PLIST"
  else
    fail "No supported service manager found."
  fi
fi

step "Installing the host-side update service"
NODECAST_INSTALL_DIR="$INSTALL_DIR" NODECAST_MODE="$MODE" NODECAST_APP_PORT="$APP_PORT" bash "$INSTALL_DIR/scripts/install-updater.sh"
[[ "$AUTO_UPDATE" == "true" ]] || printf "${DIM}  Update checks are installed but remain inactive until the admin enables them in Settings.${RESET}\n"

printf "\n${GREEN}╭────────────────────────────────────────────╮\n"
printf "│  Nodecast %s is ready                    \n" "$LATEST_TAG"
printf "╰────────────────────────────────────────────╯${RESET}\n"
printf "  Mode:      %s\n  Address:   http://localhost:%s\n  Directory: %s\n\n" "$MODE" "$APP_PORT" "$INSTALL_DIR"
