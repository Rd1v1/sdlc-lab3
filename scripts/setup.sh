#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
.venv/bin/python -c 'import sys; assert sys.version_info >= (3,13); assert sys.prefix != sys.base_prefix'
.venv/bin/python -m pip install --disable-pip-version-check --cache-dir .cache/pip -r requirements.txt
