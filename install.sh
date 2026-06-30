#!/usr/bin/env bash
set -e

REPO="https://github.com/sarox-dev/Recollect.git"
DIR="$HOME/.recollect"

echo "→ Checking dependencies..."

command -v docker >/dev/null || { echo "Install Docker first"; exit 1; }
command -v git >/dev/null || { echo "Install Git first"; exit 1; }

echo ""

if [ -d "$DIR/.git" ]; then
  echo "Recollect already installed."
  echo "1) Update"
  echo "2) Reinstall (reset)"

  read -p "Choose: " choice

  if [ "$choice" = "1" ]; then
    git -C "$DIR" pull
  else
    rm -rf "$DIR"
    git clone "$REPO" "$DIR"
  fi
else
  git clone "$REPO" "$DIR"
fi

cd "$DIR"

cp -n .env.example .env || true

docker compose up -d

echo ""
echo "✓ Installed"

# CLI install
sudo ln -sf "$DIR/cli.sh" /usr/local/bin/recollect 2>/dev/null || true

echo "→ CLI available: recollect"
echo "→ start: recollect start"