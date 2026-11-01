"""Verify the OS speaker monitor with a quiet generated tone. Does not open the microphone.

No captured audio is saved: the report contains only duration, levels and the
energy of this test's two known tones.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

import numpy as np


def run(output: Path) -> int:
    import sounddevice as sd
    from milo.desktop.meeting_audio import source_for
    from milo.core.types import STT_SAMPLE_RATE

    rate = STT_SAMPLE_RATE
    duration = 0.7
    t = np.arange(round(rate * duration), dtype=np.float32) / rate
    fade = np.minimum(1, np.minimum(t / 0.02, (duration - t) / 0.02))
    tones = [997, 1553]
    marker = np.concatenate([np.zeros(rate // 5, dtype=np.float32),
                             *(0.025 * fade * np.sin(2 * np.pi * hz * t) for hz in tones),
                             np.zeros(rate // 5, dtype=np.float32)]).astype(np.float32)
    pieces = []
    with source_for("them") as source:
        def play():
            time.sleep(0.15)
            sd.play(marker, rate, blocking=True)
        player = threading.Thread(target=play, name="owned-test-tone", daemon=True)
        player.start()
        until = time.monotonic() + 2.3
        while time.monotonic() < until:
            pieces.append(source.read())
        player.join(timeout=1)
        sd.stop()
    audio = np.concatenate(pieces)
    spectrum = np.abs(np.fft.rfft(audio * np.hanning(len(audio))))
    frequencies = np.fft.rfftfreq(len(audio), 1 / rate)
    measured = {hz: float(np.max(spectrum[np.abs(frequencies - hz) < 4]) / len(audio) * 2) for hz in tones}
    if any(level < 0.001 for level in measured.values()):
        raise AssertionError(f"The speaker monitor did not capture both test tones: {measured}")
    report = {"platform": sys.platform, "source": type(source).__name__, "sample_rate": rate,
              "captured_seconds": round(len(audio) / rate, 3), "rms": round(float(np.sqrt(np.mean(audio**2))), 5),
              "marker_amplitude": {str(key): round(value, 5) for key, value in measured.items()},
              "microphone_opened": False, "captured_audio_saved": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("build/meeting-loopback-e2e.json"))
    raise SystemExit(run(parser.parse_args().output))
