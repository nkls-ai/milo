"""Finding a device by what the user called it (ADR 0037): "the kitchen light", „Licht in der Küche“, „alle Lichter“."""

from milo.core.home import Device, find, many

DEVICES = [
    Device("1", "Kitchen ceiling light", "light", "Kitchen"),
    Device("2", "Kitchen counter light", "light", "Kitchen"),
    Device("3", "Stehlampe", "light", "Wohnzimmer"),
    Device("4", "Küchenlicht", "light"),
    Device("5", "Blinds", "cover", "Living room"),
    Device("6", "Front door", "lock"),
    Device("7", "Movie night", "scene"),
    Device("8", "Desk lamp", "light", "Office"),
    Device("9", "Desk lamp strip", "light", "Office"),
]


def names(wanted: str, **kw) -> list[str]:
    return [d.name for d in find(DEVICES, wanted, **kw)[0]]


def test_a_name_in_other_words_or_the_other_language_finds_it():
    assert names("the living room blinds", scene=False) == ["Blinds"]
    assert names("die Haustür", scene=False) == ["Front door"]
    assert names("Stehlampe im Wohnzimmer", scene=False) == ["Stehlampe"]
    assert names("Licht in der Küche", scene=False) == ["Küchenlicht"], "just that, in both languages"
    assert set(names("kitchen lights", scene=False)) == {"Kitchen ceiling light", "Kitchen counter light",
                                                          "Küchenlicht"}


def test_the_one_whose_words_are_just_the_words_said_wins_over_longer_names():
    assert find(DEVICES, "the desk lamp", scene=False) == ([DEVICES[7]], True)


def test_plural_words_mean_all_of_them():
    assert many("the kitchen lights") and many("alle Lichter") and not many("kitchen light")
    assert len(names("alle Lichter", scene=False)) == 6


def test_scenes_only_when_asked_for_unless_only_a_scene_matches():
    assert names("movie night", scene=True) == ["Movie night"]
    assert names("movie night", scene=False) == ["Movie night"], "the model wrote a scene as a device"
    assert names("blinds", scene=True) == []
