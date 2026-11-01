#!/bin/sh
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export PYTHONUTF8=1
exec uv run --project "$repo/brain" --extra desktop milo-desktop "$@"
