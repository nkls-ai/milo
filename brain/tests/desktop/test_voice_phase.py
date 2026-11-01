"""The capsule's rules, from protocol/voice_phases.json, which the Mac's VoicePhaseTableTests run too."""
import json
from pathlib import Path

import pytest

from milo.desktop.presentation.voice_phase import (Ear, VoicePhase, label, level_height, phase_of, tail,
                                                   thinking_label)

TABLE = json.loads((Path(__file__).parents[3] / "protocol" / "voice_phases.json").read_text(encoding="utf-8"))


def _phase(spec):
    if spec is None:
        return None
    return VoicePhase(spec["kind"], spec.get("mode", ""), spec.get("handsFree", False))


@pytest.mark.parametrize("case", TABLE["cases"], ids=[c["name"] for c in TABLE["cases"]])
def test_every_case_matches_the_mac(case):
    i = {**TABLE["defaults"], **{k: v for k, v in case.items() if k not in ("name", "phase")}}
    ear = Ear(i["ear"]["kind"], i["ear"]["mode"]) if i["ear"] else None
    got = phase_of(state=i["state"], ear=ear, hands_free=i["handsFree"], pasted=i["pasted"],
                   connected=i["connected"], last_mode=i["lastMode"], answering=i["answering"])
    assert got == _phase(case["phase"])


def test_labels_are_short_and_in_his_voice():
    assert label(VoicePhase("armed", "talk"), words=False) == ""
    assert label(VoicePhase("caught", "talk"), words=False) == "Got it"
    assert label(VoicePhase("thinking"), words=True) == ""
    assert label(VoicePhase("thinking"), words=False) == "Thinking"
    for phase in (VoicePhase("listening", "talk"), VoicePhase("listening", "dictate", True),
                  VoicePhase("caught", "dictate"), VoicePhase("transcribing", "dictate"), VoicePhase("pasted"),
                  VoicePhase("thinking"), VoicePhase("offline")):
        assert len(label(phase, words=False).split()) <= 3
        assert phase.spoken


def test_long_thinking_says_so():
    assert thinking_label(1, words=True) == ""
    assert thinking_label(1, words=False) == "Thinking"
    assert thinking_label(8, words=True) == "Still on it"
    assert thinking_label(30, words=True) == "Taking a while"


def test_the_meter_ignores_room_noise_and_fills_for_a_voice():
    assert level_height(0) == 0
    assert level_height(0.03) == 0
    assert level_height(0.3) > 0.4
    assert level_height(1) == 1


def test_colours_and_recording():
    assert VoicePhase("pasted").color_mode == "dictate"
    assert VoicePhase("thinking").color_mode == "talk"
    assert VoicePhase("offline").color_mode == ""
    assert VoicePhase("armed", "talk").recording and not VoicePhase("pasted").recording


def test_tail_keeps_the_newest_words():
    text = " ".join(f"word{i}" for i in range(60))
    cut = tail(text, 40)
    assert cut.startswith("…") and cut.endswith("word59") and len(cut) <= 41
