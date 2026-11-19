#!/usr/bin/env bash
# Set up dryer with Lua 5.4 on Ubuntu (including Ubuntu under WSL2).
#
# Not a supported host: dryer runs on native Windows x64 only (ADR 0002 in
# home-uml-viewer). The
# script is kept because it is the only setup a restored Linux host has, and
# deleting it is a separate decision, not a tidy-up that rides along with #5.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d ../crapper ]; then
  echo "dryer imports ../crapper; clone it next to this repo first." >&2
  exit 1
fi

sudo apt-get update
sudo apt-get install -y python3 python3-venv build-essential \
  lua5.4 liblua5.4-dev luarocks

sudo luarocks --lua-version=5.4 install busted
sudo luarocks --lua-version=5.4 install luacov
sudo luarocks --lua-version=5.4 install luacov-reporter-lcov

python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'

echo "Done. Run: .venv/bin/pytest"
