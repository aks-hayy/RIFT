#!/usr/bin/env sh
set -eu

python_cmd=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        python_cmd="$candidate"
        break
    fi
done
if [ -z "$python_cmd" ]; then
    echo "Python 3.10 or newer is required." >&2
    exit 1
fi

version="$($python_cmd -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
major="${version%%.*}"
minor="${version#*.}"
if [ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 10 ]; }; then
    echo "RIFT requires Python 3.10 or newer; detected $version." >&2
    exit 1
fi

root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root_dir"
if [ ! -x .venv/bin/python ]; then
    "$python_cmd" -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install --no-cache-dir "$root_dir"
echo "RIFT is ready. Start it with: .venv/bin/rift start"
