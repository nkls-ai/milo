#!/bin/zsh
# Dictation end to end: recorded speech played into a real brain on a throwaway workspace in /tmp.
#   scripts/e2e-dictation.sh                    Whisper on `say` voices, preview against off (takes the model lock)
#   scripts/e2e-dictation.sh --fake             tones and the tone transcriber: no models, half a minute
#   scripts/e2e-dictation.sh --only en-2s,de-15s --streams preview,type,off --reps 3
# Prints a table and exits non-zero if words were lost or pasting, live words or the listening state were slow.
# See brain/src/milo/eval/dictation.py for the cases and the limits.
set -euo pipefail
cd "$(dirname "$0")/../brain"
exec uv run python -m milo.eval.dictation "$@"
