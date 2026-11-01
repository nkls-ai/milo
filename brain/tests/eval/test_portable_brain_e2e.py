"""A real brain process, local HTTP chat provider and native IPC; no models, keys or user data.

The only fake boundary is the remote model. Workspace, composition, subprocess,
stream parsing, command routing, history and shutdown are the production code.
"""
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from milo import system


def test_real_brain_process_streams_a_turn_and_persists_history(tmp_path):
    requests = []

    class Provider(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            content = "Hello from the portable brain."
            data = ("data: " + json.dumps({"choices": [{"delta": {"content": content}}]}) +
                    "\n\ndata: [DONE]\n\n").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    provider = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    thread = threading.Thread(target=provider.serve_forever, daemon=True)
    thread.start()
    home = tmp_path / "Milo"
    home.mkdir()
    # JSON string syntax is also TOML basic-string syntax for executable paths.
    (home / "config.toml").write_text(f'''
[chat]
use = "openai_compat"
backchannels = false
[chat.openai_compat]
base_url = "http://127.0.0.1:{provider.server_port}/v1"
model = "local-test-provider"
[harness]
use = "codex"
[harness.codex]
binary = {json.dumps(sys.executable)}
[stt]
use = "none"
[tts]
use = "none"
fallback = ""
[audio]
use = "none"
[connections]
use = "none"
[dictation]
use = "plain"
[heartbeat]
enabled = false
[memory]
enabled = false
[hands]
enabled = false
[weather]
enabled = false
[decide]
use = "none"
''', encoding="utf-8")
    endpoint = home / "run" / "brain.sock"
    env = {**os.environ, "MILO_HOME": str(home), "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1"}
    output = (tmp_path / "brain-output.log").open("wb")
    packaged = os.environ.get("MILO_E2E_EXECUTABLE")
    command = [packaged, "--brain"] if packaged else [sys.executable, "-m", "milo.server"]
    brain = subprocess.Popen(command, env=env, stdout=output, stderr=output,
                             **system.isolated_process())
    sock = None
    try:
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            if brain.poll() is not None:
                raise AssertionError((tmp_path / "brain-output.log").read_text(encoding="utf-8"))
            try:
                sock = system.connect_local(endpoint, 2)
                break
            except OSError:
                time.sleep(0.1)
        assert sock is not None, (home / "logs" / "brain.log").read_text(encoding="utf-8")
        driver = Path(__file__).resolve().parents[3] / "scripts" / "drive-milo.py"
        driven = subprocess.run([sys.executable, str(driver), "hi", "--home", str(home), "--wait", "2"],
                                env=env, capture_output=True, text=True, encoding="utf-8", timeout=15)
        assert driven.returncode == 0, driven.stdout + driven.stderr
        assert "Hello from the portable brain." in driven.stdout, driven.stdout
        sock.sendall(b'{"type":"observe"}\n{"type":"text","text":"Hello Milo","speak":false}\n')
        stream = sock.makefile("rb")
        messages = []
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            message = json.loads(stream.readline())
            messages.append(message)
            if message.get("type") == "entry" and "Hello from the portable brain." in str(message):
                break
        assert requests and requests[-1]["messages"][-1]["role"] == "user"
        assert any("Hello from the portable brain." in str(m) for m in messages)
        sock.sendall(b'{"type":"get_history"}\n')
        while True:
            message = json.loads(stream.readline())
            if message.get("type") == "history":
                assert "Hello Milo" in str(message)
                assert "Hello from the portable brain." in str(message)
                break
        stream.close()
        sock.close()
        sock = None
        # A forced shutdown leaves endpoint records behind. Real user restarts
        # must reclaim them, including pywin32's FILETIME conversion path.
        system.signal_processes(brain.pid, [], force=True)
        brain.wait(timeout=5)
        brain = subprocess.Popen(command, env=env, stdout=output, stderr=output,
                                 **system.isolated_process())
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            if brain.poll() is not None:
                raise AssertionError((tmp_path / "brain-output.log").read_text(encoding="utf-8"))
            try:
                sock = system.connect_local(endpoint, 2)
                break
            except OSError:
                time.sleep(.1)
        assert sock is not None, "Restarted brain did not reclaim its stale endpoint"
        sock.sendall(b'{"type":"observe"}\n{"type":"get_history"}\n')
        with sock.makefile("rb") as restarted:
            while True:
                message = json.loads(restarted.readline())
                if message.get("type") == "history":
                    assert "Hello Milo" in str(message)
                    assert "Hello from the portable brain." in str(message)
                    break
    finally:
        if sock is not None:
            sock.close()
        system.signal_processes(brain.pid, [], force=True)
        brain.wait(timeout=5)
        output.close()
        provider.shutdown()
        provider.server_close()
