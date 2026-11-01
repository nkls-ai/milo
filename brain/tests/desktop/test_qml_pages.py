"""Every QML control and page loads without a QML warning, light and dark, and sends the wire commands its samples
expect, shaped as protocol/messages.json defines them. Samples: tests/desktop/page_samples/*.json."""
import pytest

pytest.importorskip("PySide6.QtQuick")

from milo.desktop import qml_preview as q  # noqa: E402

SAMPLES = q.samples()
STATES = [(name, state) for name, sample in SAMPLES.items() for state in sample["states"]]
INTERACTIONS = [(name, i) for name, sample in SAMPLES.items() for i in range(len(sample.get("interactions", [])))]
CONTROLS = sorted(p.stem for p in q.CONTROLS.glob("*.qml") if p.stem != "Tones")  # Tones is a singleton


@pytest.fixture(params=["light", "dark"])
def appearance(request):
    q.application()
    q.set_appearance(request.param)
    yield request.param
    q.set_appearance(None)


@pytest.fixture
def light():
    q.application()
    q.set_appearance("light")
    yield
    q.set_appearance(None)


@pytest.mark.parametrize("name,state", STATES)
def test_page_loads_without_warnings(name, state, appearance):
    with q.Warnings() as warnings:
        loaded = q.load_sample(SAMPLES[name], state)
        q.settle(200)
        loaded.close()
    assert warnings.messages == []


@pytest.mark.parametrize("control", CONTROLS)
def test_control_loads_alone_without_warnings(control, tmp_path):
    q.application()
    holder = tmp_path / "Holder.qml"
    holder.write_text(f"import QtQuick\nimport Milo.Controls\nItem {{ width: 300; height: 200; {control} {{}} }}\n",
                      encoding="utf-8")
    with q.Warnings() as warnings:
        q.load(holder, size=(300, 200)).close()
    assert warnings.messages == []


@pytest.mark.parametrize("name,index", INTERACTIONS)
def test_interaction_sends_wire_commands(name, index, light):
    interaction = SAMPLES[name]["interactions"][index]
    with q.Warnings() as warnings:
        loaded = q.load_sample(SAMPLES[name], interaction["state"])
        q.run_steps(loaded, interaction["steps"])
        loaded.close()
    assert warnings.messages == []
    assert loaded.commands == interaction.get("expect", [])
    for command in loaded.commands:
        assert q.wire_problems(command) == []
    if "actions" in interaction:
        assert [list(a) for a in loaded.actions] == interaction["actions"]


def test_confirm_answer_matches_the_python_rule():
    """wire.mjs's confirmAnswer and model.confirmation_answer build the same message."""
    from milo.desktop.model import confirmation_answer
    q.application()
    loaded = q.load(q.SAMPLES.parent / "qml" / "WireProbe.qml", size=(10, 10))
    questions = [{"id": "a", "question": "?", "always": False, "money": False},
                 {"id": "b", "question": "?", "always": True, "money": False},
                 {"id": "c", "question": "?", "always": False, "money": False,
                  "choices": [{"id": "yes", "label": "Take notes"}, {"id": "never", "label": "Never for Zoom"}]}]
    for question in questions:
        offered = [c["id"] for c in question.get("choices") or []] or ["yes", "no"] + (["always"] if question["always"] else [])
        for choice in offered:
            assert q._plain(loaded.root.answer(question, choice)) == confirmation_answer(question, choice)
        assert q._plain(loaded.root.answer(question, "maybe")) is None
    loaded.close()
