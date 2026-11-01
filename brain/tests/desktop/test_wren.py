"""Wren/: the character's pose maths (director, motion, life, rig) behave like the Mac's, and the figure loads."""
from __future__ import annotations

import json
import time

import pytest

pytest.importorskip("PySide6.QtQuick")

from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QJSEngine  # noqa: E402

from . import qml_harness as harness  # noqa: E402

STATES = ["idle", "listening", "dictating", "transcribing", "thinking", "speaking"]
EMOTIONS = ["neutral", "happy", "excited", "thinking", "concerned", "sad", "sleepy", "confused"]


@pytest.fixture(scope="module")
def js():
    e = QJSEngine()
    for name in ("director", "motion", "life", "rig", "clips", "pose"):
        module = e.importModule(str(harness.QML / "Wren" / f"{name}.mjs"))
        assert not module.isError(), module.toString()
        e.globalObject().setProperty(name.capitalize(), module)

    def run(code):
        value = e.evaluate(f"JSON.stringify((function() {{ {code} }})())")
        assert not value.isError(), value.toString()
        return json.loads(value.toString())
    return run


def test_every_clip_starts_and_ends_at_rest(js):
    bad = js("""
        const out = []
        for (const name in Clips) {
            const c = typeof Clips[name] === "function" ? null : Clips[name]
            if (!c || !c.tracks) continue
            for (const ch in c.tracks) {
                const keys = c.tracks[ch]
                if (Math.abs(keys[keys.length - 1][1]) > 1e-9 || (name !== "holdOff" && Math.abs(keys[0][1]) > 1e-9))
                    out.push(name + "." + ch)
            }
        }
        return out""")
    assert bad == []


def test_poses_follow_the_mac(js):
    poses = js("""
        const i = values => Director.input(values)
        return {
            speakingLoud: Director.pose(i({ state: "speaking", level: 1 })),
            speakingQuiet: Director.pose(i({ state: "speaking", level: 0 })),
            asleep: Director.pose(i({ asleep: true })),
            happy: Director.pose(i({ emotion: "happy" })),
            noting: Director.pose(i({ noting: true })),
            flying: Director.pose(i({ flight: { kind: "flying", dx: 0.6, dy: 0.8 } })),
        }""")
    assert poses["speakingLoud"]["beak"] == pytest.approx(1)
    assert poses["speakingQuiet"]["beak"] == 0
    assert poses["asleep"]["lidL"] == 1 and poses["asleep"]["scarfUp"] == 1 and poses["asleep"]["crest"] == -1
    assert poses["happy"]["lowerL"] == 1 and poses["happy"]["blush"] == 0.8
    assert poses["noting"]["pad"] == 1
    assert poses["flying"]["fly"] == 1 and poses["flying"]["feet"] == 0 and poses["flying"]["turn"] == 0.3


def test_motion_springs_to_the_target_and_settles(js):
    result = js("""
        const m = new Motion.Motion()
        const d = new Director.Director(7)
        d.direct(Director.input(), m, 0, false)
        d.direct(Director.input({ emotion: "happy" }), m, 0.1, false)
        const playing = m.playing.slice()
        let peak = 0
        for (let k = 0; k < 240; ++k) { m.advance(1 / 60); peak = Math.max(peak, m.pose.lift) }
        return { playing, peak, settled: m.settled, lower: m.pose.lowerL }""")
    assert "hop" in result["playing"] and "wiggle" in result["playing"]
    assert result["peak"] > 10  # the hop leaves the ground
    assert result["settled"] and result["lower"] == pytest.approx(1)


def test_a_blink_shuts_and_opens_the_eyes(js):
    lids = js("""
        const m = new Motion.Motion()
        m.blink()
        const out = []
        for (let k = 0; k < 20; ++k) { m.advance(0.02); out.push(m.pose.lidL) }
        return out""")
    assert max(lids) > 0.95 and lids[-1] == pytest.approx(0.2, abs=0.01)


def test_life_blinks_glances_and_follows_the_pointer(js):
    result = js("""
        const life = new Life.Life(3, 0)
        const input = { state: "idle", asleep: false, late: false, cursor: null, towardCentre: -1 }
        let blinks = 0, glances = 0, habits = 0
        for (let t = 0; t < 120; t += 0.05) {
            const p = life.update(input, t)
            if (p.blink) blinks++
            if (p.gaze.dx !== 0 || p.gaze.dy !== 0) glances++
            if (p.habit) habits++
        }
        const look = life.update(Object.assign({}, input, { cursor: { x: 200, y: 0 } }), 121)
        const look2 = life.update(Object.assign({}, input, { cursor: { x: 210, y: 0 } }), 121.1)
        return { blinks, glances, habits, gaze: look2.gaze }""")
    assert result["blinks"] > 10 and result["glances"] > 0 and result["habits"] >= 0
    assert result["gaze"]["dx"] == pytest.approx(1) and result["gaze"]["dy"] == pytest.approx(0)


def test_the_rig_draws_every_state_and_feeling(js):
    broken = js("""
        const out = []
        for (const state of %s) for (const emotion of %s) for (const small of [false, true]) {
            const f = Rig.frame(Director.pose(Director.input({ state, emotion, level: 0.5, noting: emotion === "sad" })), small)
            const text = JSON.stringify(f)
            if (text.indexOf("NaN") >= 0 || text.indexOf("null") >= 0 && !f.pad.shown) out.push(state + "/" + emotion)
            if (!f.body.path || !f.eyeL.ball || !f.beak.upper) out.push(state + "/" + emotion + " empty")
        }
        return out""" % (json.dumps(STATES), json.dumps(EMOTIONS)))
    assert broken == []


def test_lids_are_cut_to_the_eye(js):
    """The lids are clipped without a mask: their outline stays inside the slightly bigger eye ellipse."""
    worst = js("""
        let worst = 0
        for (const lid of [0, 0.3, 0.7, 1]) for (const lower of [0, 0.5, 1]) {
            const e = Rig.eye(lid, lower, 1, 1, [0, 0], [0, 0])
            for (const path of [e.upper, e.lowerLid, e.lidShadow]) {
                const nums = (path.match(/-?[0-9.]+/g) || []).map(Number)
                for (let i = 0; i + 1 < nums.length; i += 2)
                    worst = Math.max(worst, Math.pow(nums[i] / 10.4, 2) + Math.pow(nums[i + 1] / 11.6, 2))
            }
        }
        return worst""")
    assert worst <= 1.001


def test_wren_loads_animates_and_stills_without_warnings():
    app = QGuiApplication.instance()
    e = harness.engine()
    before = len(harness.messages())
    obj = harness.create(e, """
import QtQuick
import Milo
Item {
    property string mood: "idle"
    Wren { id: live; width: 120; height: 120; brainState: parent.mood; level: 0.5 }
    Wren { width: 40; height: 40; still: true; emotion: "sleepy"; asleep: true }
    WrenRig { width: 60; height: 60; pose: live.pose }
    property real beak: live.pose.beak
}""")
    for state in ("listening", "speaking", "thinking", "idle"):
        obj.setProperty("mood", state)
        end = time.monotonic() + 0.3
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.005)
        if state == "speaking":
            assert obj.property("beak") > 0.3
    assert harness.messages()[before:] == []
