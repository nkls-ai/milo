"""Opt-in production dictation with real OS hooks, an owned app and virtual audio.

MILO_REAL_DICTATION=1 uv run --no-sync pytest tests/desktop/test_dictation_pipeline_e2e.py
Needs desktop dependencies, cached Whisper small and the generated English WAV.
On Linux use an isolated X11 desktop (xvfb-run + dbus-run-session).
"""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.skipif(os.environ.get('MILO_REAL_DICTATION') != '1', reason='opt-in actual desktop hooks and local inference')
def test_real_hotkey_brain_whisper_ipc_native_paste_and_undo(tmp_path):
    root = Path(__file__).resolve().parents[3]
    script = root / 'scripts/dictation-desktop-e2e.py'
    audio = root / 'build/local-speech-e2e-windows-small/english.wav'
    assert audio.exists(), 'Generate the English speech fixture with scripts/local-speech-e2e.py first'
    result = subprocess.run([sys.executable, str(script), '--audio', str(audio), '--output', str(tmp_path)],
                            capture_output=True, text=True, encoding='utf-8', timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((tmp_path / 'report.json').read_text(encoding='utf-8'))
    assert report['model'] == 'small' and len(report['checks']) == 4
    assert [command['type'] for command in report['commands']] == ['listen_start', 'listen_confirm', 'listen_stop']
