"""Motion/: the springs are SwiftUI's springs, and they behave in Qt."""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtQuick")

from PySide6.QtCore import QEasingCurve, QPointF  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from . import qml_harness as harness  # noqa: E402

KINDS = {"spring": (0.45, 0.74), "gentle": (0.72, 0.89), "snappy": (0.28, 0.82)}


def analytic(t: float, response: float, damping: float) -> float:
    """SwiftUI's .spring(response:dampingFraction:) from rest, 0 → 1: a unit mass, k = (2π/response)², ζ = damping."""
    w = 2 * math.pi / response
    if damping < 1:
        a, wd = damping * w, w * math.sqrt(1 - damping * damping)
        return 1 - math.exp(-a * t) * (math.cos(wd * t) + a / wd * math.sin(wd * t))
    return 1 - (1 + w * t) * math.exp(-w * t)


def call(engine, module, name, *args):
    engine.globalObject().setProperty("M", module)
    return engine.evaluate(f"JSON.stringify(M.{name}({', '.join(map(json.dumps, args))}))").toString()


def test_the_design_tokens_match_swiftui():
    e, m = harness.module("Motion/spring.mjs")
    for t in (0.05, 0.1, 0.2, 0.4, 0.8):
        for response, damping in [*KINDS.values(), (0.3, 1.0)]:
            assert json.loads(call(e, m, "value", t, response, damping)) == pytest.approx(
                analytic(t, response, damping), abs=1e-9)


@pytest.mark.parametrize("kind", KINDS)
def test_spring_animation_steps_land_on_the_true_curve(kind):
    """Qt's SpringAnimation steps v += spring·(to − x) − damping·v; x += v·0.016. With qtParams the steps follow the
    closed-form spring half a step (8 ms) ahead, within about a percent; mapping k and c straight across is several
    times further off at its best alignment."""
    response, damping = KINDS[kind]
    e, m = harness.module("Motion/spring.mjs")
    params = json.loads(call(e, m, "qtParams", response, damping))
    x = v = 0.0
    worst = naive = 0.0
    xn = vn = 0.0
    k, c = (2 * math.pi / response) ** 2, 4 * math.pi * damping / response
    for step in range(1, 120):
        v += params["spring"] * (1 - x) - params["damping"] * v
        x += v * 0.016
        vn += k * 0.016 * (1 - xn) - c * 0.016 * vn
        xn += vn * 0.016
        truth = analytic((step + 0.5) * 0.016, response, damping)
        worst = max(worst, abs(x - truth))
        naive = max(naive, min(abs(xn - analytic((step + shift) * 0.016, response, damping)) for shift in (0, 0.5, 1)))
    assert worst < 0.012
    assert worst < naive / 2


def test_reduced_motion_is_a_quick_ease_out():
    e, m = harness.module("Motion/spring.mjs")
    params = json.loads(call(e, m, "reducedParams", 0.18))
    x = v = 0.0
    trail = []
    for _ in range(12):  # 0.192 s
        v += params["spring"] * (1 - x) - params["damping"] * v
        x += v * 0.016
        trail.append(x)
    assert all(b > a for a, b in zip(trail, trail[1:]))  # no bounce
    assert trail[0] > 0.2 and 0.98 < trail[-1] <= 1


@pytest.mark.parametrize("kind", KINDS)
def test_colour_curve_follows_the_spring(kind):
    """ColorSpring's Bezier easing, as Qt evaluates it, stays within about a percent of the real spring."""
    response, damping = KINDS[kind]
    e, m = harness.module("Motion/spring.mjs")
    curve = json.loads(call(e, m, "curve", response, damping))
    points = curve["points"]
    assert len(points) // 6 <= 8  # more crashes Qt 6.8, see spring.mjs
    easing = QEasingCurve(QEasingCurve.Type.BezierSpline)
    for i in range(0, len(points), 6):
        easing.addCubicBezierSegment(QPointF(*points[i:i + 2]), QPointF(*points[i + 2:i + 4]), QPointF(*points[i + 4:i + 6]))
    for k in range(201):
        progress = k / 200
        assert easing.valueForProgress(progress) == pytest.approx(
            analytic(progress * curve["duration"], response, damping), abs=0.012)


def test_curve_never_has_more_than_eight_segments():
    e, m = harness.module("Motion/spring.mjs")
    assert len(json.loads(call(e, m, "curve", 0.45, 0.74, 24))["points"]) == 8 * 6


def test_colour_spring_survives_being_loaded_and_closed_again_and_again(tmp_path):
    """Regression: 12+ Bezier segments corrupted Qt's heap (0xc0000374) when ColorSpring items came and went."""
    source = tmp_path / "churn.qml"
    source.write_text("import QtQuick\nimport Milo\n"
                      "Rectangle { width: 10; height: 10; color: 'red'; Behavior on color { ColorSpring {} }\n"
                      "  Component.onCompleted: color = 'blue' }\n", encoding="utf-8")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    result = subprocess.run([sys.executable, str(Path(harness.__file__)), "churn", str(source), "30"],
                            capture_output=True, text=True, timeout=120, env=env,
                            cwd=Path(harness.__file__).parent)
    assert result.returncode == 0, result.stderr[-2000:]
    assert "ok" in result.stdout


def test_components_animate_without_warnings():
    app = QGuiApplication.instance()
    e = harness.engine()
    before = len(harness.messages())
    obj = harness.create(e, """
import QtQuick
import Milo
Item {
    property real at: 0
    property color tone: "black"
    Behavior on at { Spring { kind: "snappy" } }
    Behavior on tone { ColorSpring {} }
    Appear { id: appear; shown: false; Rectangle { width: 10; height: 10 } }
    property real appearScale: appear.scale
    property bool appearVisible: appear.visible
}""")
    assert not obj.property("appearVisible")
    obj.setProperty("at", 1.0)
    obj.setProperty("tone", "white")
    deadline = time.monotonic() + 1.2
    trail = []
    while time.monotonic() < deadline:
        app.processEvents()
        trail.append(obj.property("at"))
        time.sleep(0.005)
    assert trail[-1] == pytest.approx(1, abs=0.002)
    assert max(trail) > 1.0  # a snappy spring overshoots a touch, like SwiftUI's
    assert obj.property("tone").redF() == pytest.approx(1, abs=0.01)
    assert harness.messages()[before:] == []
