"""Real modifier -> brain/WAV microphone -> Whisper -> IPC -> owned app dictation.

Requires a graphical X11/Windows session, the desktop dependencies and a cached
Whisper model. No real microphone is opened. Close other Milo instances before
running: this injects Right Control into a disposable field owned by this test.
Run through uv with --no-sync; pass --audio with a known 16-bit PCM WAV.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def normalized(text):
    return [str({'nine':9}.get(word, word)) for word in re.findall(r'\w+', text.casefold())]


def run(args, directory: Path) -> dict:
    import numpy as np
    from scipy.signal import resample_poly
    from PySide6.QtWidgets import QApplication
    from milo import system
    from milo.adapters.audio.wav_file import read_wav, write_wav
    from milo.desktop.client import BrainConnection
    from milo.desktop.hotkeys import GlobalHotkeys
    from milo.desktop.controller import DesktopController, ViewModels
    from milo.desktop.native import NativeBridge, writable

    app = QApplication.instance() or QApplication([])
    home, owned = directory / 'Milo', directory / 'field'
    home.mkdir()
    owned.mkdir()
    audio, rate = read_wav(args.audio)
    factor = math.gcd(rate, 16000)
    audio = resample_poly(audio, 16000 // factor, rate // factor).astype(np.float32)
    # The hold confirmation has time to reach the brain before speech begins.
    audio = np.concatenate([np.zeros(8000, np.float32), audio, np.zeros(4800, np.float32)])
    mic = directory / 'virtual-mic.wav'
    write_wav(mic, audio, 16000)
    duration = len(audio) / 16000
    config = '''
[chat]
use = "none"
backchannels = false
quick_actions = false
[harness]
use = "none"
[stt]
use = "faster_whisper"
[stt.faster_whisper]
model = MODEL
preview_model = ""
language = "en"
[tts]
use = "none"
fallback = ""
[audio]
use = "wav"
[audio.wav]
mic = MIC
[dictation]
use = "plain"
stream = "off"
learn = false
[connections]
use = "none"
[home]
use = "none"
[decide]
use = "none"
[memory]
enabled = false
[heartbeat]
enabled = false
[weather]
enabled = false
[hands]
enabled = false
[messages]
enabled = false
[ui]
dictate_key = "right_control"
talk_key = "right_option"
'''.replace('MODEL', json.dumps(args.model)).replace('MIC', json.dumps(str(mic.resolve())))
    (home / 'config.toml').write_text(config, encoding='utf-8')
    fixture_script = Path(__file__).with_name('native-desktop-e2e.py')
    child = None
    stdout = (directory / 'brain.stdout.log').open('w', encoding='utf-8')
    brain = subprocess.Popen([sys.executable, '-m', 'milo.server'], stdout=stdout, stderr=subprocess.STDOUT,
        env={**os.environ, 'MILO_HOME':str(home.resolve()), 'PYTHONUTF8':'1', 'PYTHONUNBUFFERED':'1'},
        **system.isolated_process())
    bridge = NativeBridge(home)
    clipboard = bridge.clipboard.snapshot()
    connection = BrainConnection(home / 'run/brain.sock')
    hotkeys = GlobalHotkeys()
    controller = DesktopController(home, ViewModels(), connection, bridge, hotkeys)
    events, commands, statuses, pasted = [], [], [], []
    connection.event.connect(lambda event: events.append((time.monotonic(), event)))
    hotkeys.command.connect(lambda event: commands.append(event))
    hotkeys.status.connect(statuses.append)
    paste = bridge.paste_dictation

    def observed_paste(text, **options):
        result = paste(text, **options)
        pasted.append((time.monotonic(), text, result))
        return result

    bridge.paste_dictation = observed_paste

    def contents():
        return json.loads((owned / 'fixture.json').read_text(encoding='utf-8'))['text']

    def pump(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(.005)

    def wait_for(predicate, message, timeout=15):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            app.processEvents()
            if (child is not None and child.poll() is not None) or brain.poll() is not None:
                raise AssertionError(f'{message}: child process exited; inspect captured brain logs')
            try:
                value = predicate()
                if value:
                    return value
            except (ValueError, OSError):
                pass
            time.sleep(.01)
        focus = bridge.backend.focus()
        diagnostic = {'pid':focus.pid,'role':focus.role,'editable':focus.editable,'secure':focus.secure,
                      'keyboard_target':bridge._keyboard_target(focus)} if focus else None
        raise AssertionError(f'{message}; focus={diagnostic}; commands={commands}; statuses={statuses}; '
            f'last_events={[event for _,event in events[-3:]]}')

    xdisplay = None
    if sys.platform == 'win32':
        import ctypes
        def key(pressed):
            ctypes.windll.user32.keybd_event(0xA3, 0x1D, 1 | (0 if pressed else 2), 0)
    else:
        from Xlib import X, XK, display
        from Xlib.ext import xtest
        xdisplay = display.Display()
        code = xdisplay.keysym_to_keycode(XK.string_to_keysym('Control_R'))
        if not code:
            raise AssertionError('This X11 session has no physical Right Control key')
        def key(pressed):
            xtest.fake_input(xdisplay, X.KeyPress if pressed else X.KeyRelease, code)
            xdisplay.sync()

    held = False
    try:
        connection.start()
        wait_for(lambda: any(e.get('type') == 'ui_config' for _, e in events), 'Brain did not send hotkey configuration', 30)
        log = home / 'logs/brain.log'
        wait_for(lambda: log.exists() and 'stt engine ready' in log.read_text(encoding='utf-8'),
                 'Whisper did not finish warming', args.timeout)
        # Start the short-lived graphical fixture after potentially cold model
        # loading so its safety timeout can't expire during a download.
        child = subprocess.Popen([sys.executable, str(fixture_script), '--fixture', str(owned)],
            env={**os.environ, 'QT_LINUX_ACCESSIBILITY_ALWAYS_ON':'1'})
        wait_for(lambda: (owned / 'fixture.json').exists(), 'Owned text field did not open')
        fixture_pid = json.loads((owned / 'fixture.json').read_text(encoding='utf-8'))['pid']
        bridge.backend.activate('Milo disposable native integration test')
        target = wait_for(lambda: t if (t := bridge.backend.focus()) and t.pid == fixture_pid and writable(t)
                          and bridge._keyboard_target(t) else None, 'Owned field did not gain editable keyboard focus')
        bridge.backend.set_value(target, '')
        wait_for(lambda: contents() == '', 'Could not clear owned field')
        hotkeys.start()
        wait_for(lambda: hotkeys._keyboard is not None and hotkeys._keyboard.running and hotkeys._keyboard._ready,
                 'Global keyboard hook was not installed')
        if sys.platform == 'win32':
            from pynput._util.win32 import SystemHook
            wait_for(lambda: bool(getattr(SystemHook._HOOKS.get(hotkeys._keyboard.ident), '_hook', None)),
                     'Windows low-level keyboard hook was not installed')
        started = time.monotonic()
        key(True)
        held = True
        wait_for(lambda: any(c.get('type') == 'listen_confirm' for c in commands), 'Right Control did not confirm recording')
        wait_for(lambda: any(e.get('type') == 'state' and e.get('state') == 'dictating' for _, e in events),
                 'Brain did not enter dictation capture')
        pump(duration + .2)
        released = time.monotonic()
        key(False)
        held = False
        wait_for(lambda: pasted, 'No dictation arrived through desktop IPC', args.timeout)
        at, text, result = pasted[0]
        assert result.get('pasted'), result
        assert normalized(text) == normalized(args.expected), (text, args.expected)
        wait_for(lambda: contents() == text, 'Recognized text did not paste into owned field')
        undo = bridge.app_request('text.unwrite', {'field':result['field'], 'text':text})
        assert undo.get('removed'), undo
        wait_for(lambda: contents() == '', 'Undo did not restore the owned field')
        assert [c['type'] for c in commands[:3]] == ['listen_start','listen_confirm','listen_stop'], commands
        return {'platform':sys.platform, 'model':args.model, 'virtual_audio_seconds':round(duration,3),
            'checks':['real OS Right Control hold/release','production brain WAV capture and Whisper',
                'desktop JSONL IPC and native paste into owned app','native exact-field undo'],
            'heard':text, 'key_release_to_paste_seconds':round(at-released,3),
            'total_seconds':round(at-started,3), 'commands':commands[:3]}
    finally:
        if held:
            key(False)
        controller.close()
        bridge.clipboard.clipboard.setMimeData(clipboard)
        if xdisplay is not None:
            xdisplay.close()
        for proc in (child, brain):
            if proc is not None and proc.poll() is None:
                # Windows venv Python can be a redirector with a real child.
                # End the whole owned process tree, not just that redirector.
                from milo.adapters.harness._process import descendants, still_running
                tree = descendants(proc.pid)
                system.signal_processes(proc.pid, [pid for pid, _ in tree], force=False)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    system.signal_processes(proc.pid, still_running(tree), force=True)
                    proc.wait(timeout=5)
        stdout.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio', type=Path, default=Path('build/local-speech-e2e-windows-small/english.wav'))
    parser.add_argument('--expected', default='The meeting starts tomorrow at nine in the morning.')
    parser.add_argument('--model', default='small')
    parser.add_argument('--timeout', type=float, default=120)
    parser.add_argument('--output', type=Path, default=Path('build/dictation-desktop-e2e'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='milo-dictation-e2e-') as temporary:
        directory = Path(temporary)
        try:
            report = run(args, directory)
        finally:
            for source in (directory/'brain.stdout.log', directory/'Milo/logs/brain.log'):
                if source.exists():
                    shutil.copy2(source, args.output/source.name)
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
