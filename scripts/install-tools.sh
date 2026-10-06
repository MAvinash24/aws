#!/usr/bin/env bash
set -Eeuo pipefail
python3 -m pip install --disable-pip-version-check -r requirements-tools.txt
python3 scripts/install-binaries.py --output "${TOOLS_BIN_DIR:-/usr/local/bin}"
