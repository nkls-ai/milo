"""Real local speech inference, without microphone, speakers or cloud credentials.

Windows can generate its own fixture with SAPI. On Linux pass that WAV (or your
own recording) with --audio and --expected. Weights download on the first run.
The default tiny model keeps smoke testing small; --model small tests the
production CPU default. This is a correctness probe, not a latency target.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import wave
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

from milo.adapters.stt.faster_whisper import FasterWhisper

PHRASE = "The meeting starts tomorrow at nine in the morning."


def normalized(text: str) -> list[str]:
    # Both "nine" and "9" preserve the spoken information.
    numbers = {word: str(index) for index, word in enumerate(
        ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"))}
    return [numbers.get(word, word) for word in re.findall(r"\w+", text.casefold())]


def fixture(path: Path) -> None:
    if sys.platform != "win32":
        raise RuntimeError("Pass --audio with a local speech WAV on this platform")
    import win32com.client

    stream = win32com.client.Dispatch("SAPI.SpFileStream")
    stream.Open(str(path.resolve()), 3, False)
    try:
        voice = win32com.client.Dispatch("SAPI.SpVoice")
        voice.AudioOutputStream = stream
        voice.Speak(PHRASE)
    finally:
        stream.Close()


def read_audio(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as source:
        if source.getsampwidth() != 2:
            raise ValueError("Use an uncompressed 16-bit PCM WAV")
        audio = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2").astype(np.float32) / 32768
        audio = audio.reshape(-1, source.getnchannels()).mean(axis=1)
        rate = source.getframerate()
    common = math.gcd(rate, 16000)
    return resample_poly(audio, 16000 // common, rate // common).astype(np.float32)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path)
    parser.add_argument("--expected", default=PHRASE)
    parser.add_argument("--model", default="tiny")
    parser.add_argument("--output", type=Path, default=Path("build/local-speech-e2e"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    audio_path = args.audio or args.output / "english.wav"
    if args.audio is None:
        fixture(audio_path)
    audio = read_audio(audio_path)
    engine = FasterWhisper(args.model, preview_model="", language="en")
    started = time.perf_counter()
    engine.warm()
    loaded = time.perf_counter() - started
    started = time.perf_counter()
    text = engine.transcribe(audio)
    elapsed = time.perf_counter() - started
    words = engine.words(audio)
    expected = normalized(args.expected)
    heard = normalized(text)
    # A smoke fixture should preserve its complete simple sentence.
    ok = expected == heard and bool(words) and all(0 <= w.start <= w.end for w in words)
    report = {"ok": ok, "platform": sys.platform, "model": args.model, "device": "cpu",
              "audio": str(audio_path), "expected": args.expected, "heard": text,
              "audio_seconds": len(audio) / 16000, "load_seconds": loaded,
              "transcribe_seconds": elapsed, "timed_words": len(words)}
    (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
