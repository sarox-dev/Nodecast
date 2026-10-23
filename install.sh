#!/usr/bin/env bash
set -Eeuo pipefail

REPO="sarox-dev/Nodecast"
TOTAL_STEPS=8
CURRENT_STEP=0
TTY="/dev/tty"
[[ -r "$TTY" && -w "$TTY" ]] || TTY="/dev/stdin"

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  BLUE='\033[38;5;75m'; CYAN='\033[38;5;81m'; GREEN='\033[38;5;78m'
  YELLOW='\033[38;5;220m'; RED='\033[38;5;203m'; BOLD='\033[1m'; DIM='\033[2m'; RESET='\033[0m'
else
  BLUE=''; CYAN=''; GREEN=''; YELLOW=''; RED=''; BOLD=''; DIM=''; RESET=''
fi

terminal_width() {
  local width="${COLUMNS:-}"
  [[ "$width" =~ ^[0-9]+$ ]] || width="$(tput cols 2>/dev/null || printf '80')"
  printf '%s' "$width"
}

title() {
  local width; width="$(terminal_width)"
  printf '\n'
  if (( width >= 76 )); then
    printf "${BLUE}${BOLD}  _   _           _                     _   ${RESET}\n"
    printf "${BLUE}${BOLD} | \ | | ___   __| | ___  ___ __ _ ___| |_ ${RESET}\n"
    printf "${CYAN}${BOLD} |  \| |/ _ \ / _\` |/ _ \/ __/ _\` / __| __|${RESET}\n"
    printf "${CYAN}${BOLD} | |\  | (_) | (_| |  __/ (_| (_| \__ \ |_ ${RESET}\n"
    printf "${CYAN}${BOLD} |_| \_|\___/ \__,_|\___|\___\__,_|___/\__|${RESET}\n"
  elif (( width >= 50 )); then
    printf "${BLUE}╭────────────────────────────────────────────╮${RESET}\n"
    printf "${BLUE}│${RESET}              ${BOLD}NODECAST SETUP${RESET}                ${BLUE}│${RESET}\n"
    printf "${BLUE}╰────────────────────────────────────────────╯${RESET}\n"
  else
    printf "${BLUE}${BOLD}NODECAST SETUP${RESET}\n"
  fi
  printf "${DIM}Your knowledge layer. Your context. Your memory.${RESET}\n\n"
}

step() { CURRENT_STEP=$((CURRENT_STEP + 1)); printf "${BLUE}${BOLD}[%s/%s]${RESET} %s\n" "$CURRENT_STEP" "$TOTAL_STEPS" "$1"; }
ok() { printf "  ${GREEN}✓${RESET} %s\n" "$1"; }
note() { printf "  ${CYAN}i${RESET} %s\n" "$1"; }
warn() { printf "  ${YELLOW}!${RESET} %s\n" "$1"; }
fail() { printf "\n${RED}${BOLD}Installation stopped:${RESET} %s\n" "$1" >&2; exit 1; }
ask() { local prompt="$1" default="$2" answer; read -r -p "$prompt" answer <"$TTY" || answer=""; printf '%s' "${answer:-$default}"; }
require_command() { command -v "$1" >/dev/null 2>&1 || fail "$2"; }

safe_install_target() {
  local target="$1"
  [[ -n "$target" && "$target" != "/" && "$target" != "$HOME" ]] || return 1
  if [[ -d "$target" ]] && find "$target" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null | grep -q .; then
    [[ -f "$target/app/version.json" || -f "$target/.nodecast-install" ]] || return 1
  fi
}

archive_is_safe() {
  tar -tzf "$1" | awk '/^\// { bad=1 } /(^|\/)\.\.($|\/)/ { bad=1 } END { exit bad }'
}

wait_for_health() {
  local attempt
  for attempt in {1..30}; do
    curl -fsS "http://127.0.0.1:${APP_PORT}/api/server/health" >/dev/null 2>&1 && return 0
    sleep 1
  done
  return 1
}

title
step "Checking this system"
OS="$(uname -s)"
[[ "$OS" == "Linux" || "$OS" == "Darwin" ]] || fail "This installer supports Linux and macOS. Use install.ps1 on Windows."
require_command curl "curl is required."
require_command tar "tar is required."
if ! command -v sha256sum >/dev/null 2>&1 && ! command -v shasum >/dev/null 2>&1; then fail "sha256sum or shasum is required."; fi
ok "$OS detected"

step "Choosing an installation mode"
MODE="${NODECAST_MODE:-}"
if [[ -z "$MODE" ]]; then
  printf "\n  ${BLUE}${BOLD}1  Docker — Recommended${RESET}\n"
  printf "     ${DIM}Most reliable, isolated, and fully supported.${RESET}\n\n"
  printf "  ${CYAN}${BOLD}2  Native Python — Best effort${RESET}\n"
  printf "     ${DIM}No Docker required; compatibility depends on this system.${RESET}\n\n"
  choice="$(ask "Select installation mode [1]: " "1")"
  [[ "$choice" == "2" ]] && MODE="host" || MODE="docker"
fi
[[ "$MODE" == "docker" || "$MODE" == "host" ]] || fail "NODECAST_MODE must be 'docker' or 'host'."
if [[ "$MODE" == "docker" ]]; then
  require_command docker "Docker is required for Docker mode. Install Docker Engine/Desktop and try again."
  docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is required."
  docker info >/dev/null 2>&1 || fail "Docker is installed, but its daemon is unavailable."
  ok "Docker and Compose are ready"
else
  require_command python3 "Python 3.11 or newer is required for Native mode."
  python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' || fail "Python 3.11 or newer is required."
  python3 -m venv --help >/dev/null 2>&1 || fail "Python's venv module is required."
  warn "Native mode is best effort and depends on local Python and OS services."
  ok "$(python3 --version) is ready"
fi

AUTO_UPDATE="${NODECAST_AUTO_UPDATE:-}"
if [[ -z "$AUTO_UPDATE" ]]; then
  answer="$(ask "Enable automatic update checks? [Y/n]: " "Y")"
  [[ "$answer" =~ ^[Nn]$ ]] && AUTO_UPDATE="false" || AUTO_UPDATE="true"
fi
[[ "$AUTO_UPDATE" == "true" || "$AUTO_UPDATE" == "false" ]] || fail "NODECAST_AUTO_UPDATE must be 'true' or 'false'."
DEFAULT_DIR="${HOME}/Nodecast"
INSTALL_DIR="${NODECAST_INSTALL_DIR:-}"
[[ -n "$INSTALL_DIR" ]] || INSTALL_DIR="$(ask "Install directory [$DEFAULT_DIR]: " "$DEFAULT_DIR")"
INSTALL_DIR="${INSTALL_DIR/#\~/$HOME}"
safe_install_target "$INSTALL_DIR" || fail "The directory is unsafe or contains files that do not belong to Nodecast: $INSTALL_DIR"
PREVIOUS_MODE=""
if [[ -f "$INSTALL_DIR/.nodecast-install" ]]; then PREVIOUS_MODE="$(sed -n 's/^mode=//p' "$INSTALL_DIR/.nodecast-install" | head -1)"; fi
ok "Mode: $MODE · Directory: $INSTALL_DIR"

step "Choosing accounts and network access"
CURRENT_ACCOUNT_MODE=""; CURRENT_BIND=""; current_origin=""
if [[ -f "$INSTALL_DIR/.env" ]]; then
  CURRENT_ACCOUNT_MODE="$(sed -n 's/^NODECAST_ACCOUNT_MODE=//p' "$INSTALL_DIR/.env" | tail -1)"
  CURRENT_BIND="$(sed -n 's/^NODECAST_BIND_HOST=//p' "$INSTALL_DIR/.env" | tail -1)"
  current_origin="$(sed -n 's/^NODECAST_PUBLIC_ORIGIN=//p' "$INSTALL_DIR/.env" | tail -1)"
fi
ACCOUNT_MODE="${NODECAST_ACCOUNT_MODE:-}"
if [[ -z "$ACCOUNT_MODE" ]]; then
  printf "\n  ${BLUE}${BOLD}1  Personal${RESET}  ${DIM}one Library member plus the owner control account${RESET}\n"
  printf "  ${CYAN}${BOLD}2  Shared${RESET}    ${DIM}multiple independent member Libraries${RESET}\n\n"
  account_default="1"
  [[ "$CURRENT_ACCOUNT_MODE" == "shared" || ( -z "$CURRENT_ACCOUNT_MODE" && -f "$INSTALL_DIR/app/version.json" ) ]] && account_default="2"
  account_choice="$(ask "Account setup [$account_default]: " "$account_default")"
  [[ "$account_choice" == "2" ]] && ACCOUNT_MODE="shared" || ACCOUNT_MODE="personal"
fi
[[ "$ACCOUNT_MODE" == "personal" || "$ACCOUNT_MODE" == "shared" ]] || fail "NODECAST_ACCOUNT_MODE must be 'personal' or 'shared'."

NETWORK_ACCESS="${NODECAST_NETWORK_ACCESS:-}"
if [[ -z "$NETWORK_ACCESS" ]]; then
  printf "\n  ${BLUE}${BOLD}1  This device only${RESET}  ${DIM}127.0.0.1; safest default${RESET}\n"
  printf "  ${CYAN}${BOLD}2  Trusted LAN${RESET}      ${DIM}available to devices on your local network${RESET}\n\n"
  network_default="1"; [[ "$CURRENT_BIND" == "0.0.0.0" ]] && network_default="2"
  network_choice="$(ask "Network access [$network_default]: " "$network_default")"
  [[ "$network_choice" == "2" ]] && NETWORK_ACCESS="lan" || NETWORK_ACCESS="local"
fi
[[ "$NETWORK_ACCESS" == "local" || "$NETWORK_ACCESS" == "lan" ]] || fail "NODECAST_NETWORK_ACCESS must be 'local' or 'lan'."
LAN_HOST="${NODECAST_LAN_HOST:-}"
if [[ "$NETWORK_ACCESS" == "lan" ]]; then
  if [[ -z "$LAN_HOST" ]]; then
    current_host="${current_origin#*://}"; current_host="${current_host%%:*}"
    [[ "$current_host" == "localhost" ]] && current_host=""
    LAN_HOST="$(ask "LAN IP address or hostname${current_host:+ [$current_host]}: " "$current_host")"
  fi
  [[ "$LAN_HOST" =~ ^[A-Za-z0-9.-]+$ ]] || fail "Enter a valid LAN IPv4 address or hostname without http:// or a port."
  warn "LAN mode trusts your local network. Do not expose this port directly to the internet."
fi
ok "Accounts: $ACCOUNT_MODE · Network: $NETWORK_ACCESS"

step "Downloading the latest verified release"
LATEST_TAG="$(curl -fsSL -H 'Accept: application/vnd.github+json' -H 'User-Agent: Nodecast-Installer' "https://api.github.com/repos/$REPO/releases/latest" | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)"
[[ "$LATEST_TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]] || fail "Could not determine a valid latest release tag."
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
ARCHIVE="nodecast-${LATEST_TAG}.tar.gz"
ASSET_ROOT="https://github.com/$REPO/releases/download/$LATEST_TAG"
curl -fL --retry 3 --connect-timeout 15 "$ASSET_ROOT/$ARCHIVE" -o "$TMP_DIR/$ARCHIVE"
curl -fL --retry 3 --connect-timeout 15 "$ASSET_ROOT/SHA256SUMS" -o "$TMP_DIR/SHA256SUMS"
EXPECTED="$(awk -v file="$ARCHIVE" '$2 == file || $2 == "*" file { print $1 }' "$TMP_DIR/SHA256SUMS" | head -1 | tr '[:upper:]' '[:lower:]')"
[[ "$EXPECTED" =~ ^[0-9a-f]{64}$ ]] || fail "The release checksum is missing or invalid."
if command -v sha256sum >/dev/null 2>&1; then ACTUAL="$(sha256sum "$TMP_DIR/$ARCHIVE" | awk '{print $1}')"; else ACTUAL="$(shasum -a 256 "$TMP_DIR/$ARCHIVE" | awk '{print $1}')"; fi
[[ "$ACTUAL" == "$EXPECTED" ]] || fail "Release checksum verification failed."
archive_is_safe "$TMP_DIR/$ARCHIVE" || fail "The release archive contains an unsafe path."
ok "Nodecast $LATEST_TAG checksum verified"

step "Preparing application files"
mkdir -p "$TMP_DIR/extract"
tar -xzf "$TMP_DIR/$ARCHIVE" -C "$TMP_DIR/extract"
SOURCE_DIR="$(find "$TMP_DIR/extract" -mindepth 1 -maxdepth 1 -type d -print -quit)"
[[ -n "$SOURCE_DIR" && -f "$SOURCE_DIR/app/version.json" && -f "$SOURCE_DIR/scripts/run-nodecast.py" ]] || fail "Downloaded release is incomplete."
mkdir -p "$INSTALL_DIR"
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete --exclude='.env' --exclude='contents/' --exclude='.venv/' --exclude='.git/' --exclude='.nodecast-install' "$SOURCE_DIR/" "$INSTALL_DIR/"
else
  (cd "$SOURCE_DIR" && tar --exclude='.env' --exclude='contents' --exclude='.venv' --exclude='.git' -cf - .) | (cd "$INSTALL_DIR" && tar -xf -)
fi
mkdir -p "$INSTALL_DIR/contents"
chmod 700 "$INSTALL_DIR/contents" 2>/dev/null || true
printf 'mode=%s\n' "$MODE" > "$INSTALL_DIR/.nodecast-install"
chmod 600 "$INSTALL_DIR/.nodecast-install" 2>/dev/null || true
if [[ ! -f "$INSTALL_DIR/.env" ]]; then cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"; fi
chmod 600 "$INSTALL_DIR/.env" 2>/dev/null || true
if [[ "$MODE" == "docker" ]]; then
  for pair in "NODECAST_UID=$(id -u)" "NODECAST_GID=$(id -g)"; do
    key="${pair%%=*}"; value="${pair#*=}"
    if grep -q "^${key}=" "$INSTALL_DIR/.env"; then sed -i.bak "s/^${key}=.*/${key}=${value}/" "$INSTALL_DIR/.env" && rm -f "$INSTALL_DIR/.env.bak"; else printf '%s=%s\n' "$key" "$value" >> "$INSTALL_DIR/.env"; fi
  done
fi
if grep -q '^AUTO_UPDATE_DEFAULT=' "$INSTALL_DIR/.env"; then sed -i.bak "s/^AUTO_UPDATE_DEFAULT=.*/AUTO_UPDATE_DEFAULT=$AUTO_UPDATE/" "$INSTALL_DIR/.env" && rm -f "$INSTALL_DIR/.env.bak"; else printf '\nAUTO_UPDATE_DEFAULT=%s\n' "$AUTO_UPDATE" >> "$INSTALL_DIR/.env"; fi
APP_PORT="$(sed -n 's/^APP_PORT=//p' "$INSTALL_DIR/.env" | tail -1)"; APP_PORT="${APP_PORT:-5000}"
[[ "$APP_PORT" =~ ^[0-9]+$ ]] && (( APP_PORT >= 1 && APP_PORT <= 65535 )) || fail "APP_PORT in .env must be between 1 and 65535."
for pair in "NODECAST_ACCOUNT_MODE=$ACCOUNT_MODE" "NODECAST_BIND_HOST=$([[ "$NETWORK_ACCESS" == "lan" ]] && printf '0.0.0.0' || printf '127.0.0.1')" "NODECAST_PUBLIC_ORIGIN=http://$([[ "$NETWORK_ACCESS" == "lan" ]] && printf '%s' "$LAN_HOST" || printf 'localhost'):$APP_PORT"; do
  key="${pair%%=*}"; value="${pair#*=}"
  if grep -q "^${key}=" "$INSTALL_DIR/.env"; then sed -i.bak "s|^${key}=.*|${key}=${value}|" "$INSTALL_DIR/.env" && rm -f "$INSTALL_DIR/.env.bak"; else printf '%s=%s\n' "$key" "$value" >> "$INSTALL_DIR/.env"; fi
done
ok "Configuration and persistent data directory are ready"

step "Installing Nodecast"
if [[ "$MODE" == "docker" ]]; then
  if [[ "$PREVIOUS_MODE" == "host" ]]; then
    if [[ "$OS" == "Linux" ]] && command -v systemctl >/dev/null 2>&1; then systemctl --user disable --now nodecast.service >/dev/null 2>&1 || true; fi
    if [[ "$OS" == "Darwin" ]]; then launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/dev.nodecast.app.plist" >/dev/null 2>&1 || true; fi
  fi
  (cd "$INSTALL_DIR" && docker compose build)
  (cd "$INSTALL_DIR" && docker compose run --rm --user root --cap-add CHOWN --entrypoint chown app -R "$(id -u):$(id -g)" /app/contents)
  (cd "$INSTALL_DIR" && docker compose up -d)
  ok "Docker service started"
else
  if [[ "$PREVIOUS_MODE" == "docker" ]] && [[ -f "$INSTALL_DIR/docker-compose.yml" ]] && command -v docker >/dev/null 2>&1; then (cd "$INSTALL_DIR" && docker compose down) || true; fi
  python3 -m venv "$INSTALL_DIR/.venv"
  "$INSTALL_DIR/.venv/bin/python" -m pip install --disable-pip-version-check -r "$INSTALL_DIR/requirements.txt"
  if [[ "$OS" == "Linux" ]] && command -v systemctl >/dev/null 2>&1; then
    mkdir -p "$HOME/.config/systemd/user"
    SERVICE="$HOME/.config/systemd/user/nodecast.service"
    printf '[Unit]\nDescription=Nodecast\nAfter=network-online.target\n\n[Service]\nType=simple\nWorkingDirectory=%s\nExecStart=%s %s\nRestart=on-failure\nRestartSec=3\nNoNewPrivileges=true\nPrivateTmp=true\nProtectSystem=strict\nReadWritePaths=%s\n\n[Install]\nWantedBy=default.target\n' "$(printf '%q' "$INSTALL_DIR")" "$(printf '%q' "$INSTALL_DIR/.venv/bin/python")" "$(printf '%q' "$INSTALL_DIR/scripts/run-nodecast.py")" "$(printf '%q' "$INSTALL_DIR/contents")" > "$SERVICE"
    systemctl --user daemon-reload
    systemctl --user enable nodecast.service
    systemctl --user restart nodecast.service
  elif [[ "$OS" == "Darwin" ]]; then
    PLIST="$HOME/Library/LaunchAgents/dev.nodecast.app.plist"; mkdir -p "$(dirname "$PLIST")"
    python3 - "$PLIST" "$INSTALL_DIR" <<'PY'
import html, pathlib, sys
plist, root = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
esc = lambda value: html.escape(str(value), quote=True)
content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict><key>Label</key><string>dev.nodecast.app</string>
<key>ProgramArguments</key><array><string>{esc(root / ".venv/bin/python")}</string><string>{esc(root / "scripts/run-nodecast.py")}</string></array>
<key>WorkingDirectory</key><string>{esc(root)}</string><key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
<key>StandardOutPath</key><string>{esc(root / "contents/nodecast.log")}</string>
<key>StandardErrorPath</key><string>{esc(root / "contents/nodecast-error.log")}</string></dict></plist>'''
plist.write_text(content, encoding="utf-8")
PY
    launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
    launchctl bootstrap "gui/$(id -u)" "$PLIST"
  else
    fail "Native mode needs systemd on Linux or launchd on macOS. Docker mode remains available."
  fi
  ok "Native Python service started"
fi

step "Verifying the running application"
if ! wait_for_health; then
  if [[ "$MODE" == "docker" ]]; then note "Run: cd \"$INSTALL_DIR\" && docker compose logs app"; elif [[ "$OS" == "Linux" ]]; then note "Run: journalctl --user -u nodecast.service -n 100"; else note "See: $INSTALL_DIR/contents/nodecast-error.log"; fi
  fail "Nodecast did not become healthy on port $APP_PORT."
fi
ok "Health check passed on http://127.0.0.1:$APP_PORT"

step "Configuring update checks"
NODECAST_INSTALL_DIR="$INSTALL_DIR" NODECAST_MODE="$MODE" NODECAST_APP_PORT="$APP_PORT" bash "$INSTALL_DIR/scripts/install-updater.sh"
if [[ "$AUTO_UPDATE" == "true" ]]; then ok "Automatic update checks are enabled"; else note "The updater is installed but remains inactive until enabled by the owner."; fi

printf "\n${GREEN}${BOLD}Nodecast %s is ready.${RESET}\n" "$LATEST_TAG"
printf "${DIM}────────────────────────────────────────────${RESET}\n"
printf "  Mode       %s%s%s\n" "$BOLD" "$MODE" "$RESET"
printf "  Accounts   %s\n" "$ACCOUNT_MODE"
printf "  Access     %s\n" "$NETWORK_ACCESS"
printf "  Address    ${CYAN}http://localhost:%s${RESET}\n" "$APP_PORT"
printf "  Directory  %s\n\n" "$INSTALL_DIR"
