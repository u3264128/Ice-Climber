#!/bin/sh
set -eu
if command -v python >/dev/null 2>&1; then
    python=python
else
    python=python3
fi
exec "$python" -X utf8 "$(dirname "$0")/../../build.py" verify "$@"
