"""Who said what over the whole call, after Stop: the call diarizer's voices onto the transcript's lines."""

from milo.core.meetings import ME, Track, TranscriptLine
from milo.services.meeting_regroup import line_key, regroup, regrouped


def them(start, end, speaker, text="words"):
    return TranscriptLine(start, end, Track.THEM, speaker, text)


def test_two_people_the_live_voices_split_into_many_come_back_as_two_numbered_as_they_spoke():
    lines = [them(0, 3, "S1"), them(3, 5, "S2"), them(5, 9, "S1"), them(9, 10, "S3"), them(10, 14, "S4"),
             TranscriptLine(14, 15, Track.ME, ME, "mine")]
    segments = [(0, 3.1, "B"), (3.1, 5, "A"), (5, 9.2, "B"), (9.2, 14, "A")]
    assert [l.speaker for l in regrouped(lines, regroup(lines, segments))] == ["S1", "S2", "S1", "S2", "S2", ME]


def test_a_speaker_the_user_named_during_the_call_stays_on_the_voice_it_shares_most_with():
    lines = [them(0, 3, "S1"), them(3, 5, "S2"), them(5, 9, "S1"), them(9, 10, "S3"), them(10, 14, "S4")]
    segments = [(0, 3.1, "A"), (3.1, 5, "B"), (5, 9.2, "A"), (9.2, 14, "B")]
    after = regrouped(lines, regroup(lines, segments, named={"S4"}))
    assert [l.speaker for l in after] == ["S1", "S4", "S1", "S4", "S4"], "Sam (S4) keeps his name; A is S1"


def test_new_numbers_never_take_one_a_joined_speaker_or_a_name_holds():
    lines = [them(0, 4, "S1"), them(4, 6, "S2"), them(6, 8, "S1")]
    mapping = regroup(lines, [(0, 4, "A"), (4, 6, "B"), (6, 8, "C")], {"S2": "S1"}, named={"S1"})
    assert mapping == {line_key(lines[0]): "S1", line_key(lines[1]): "S3", line_key(lines[2]): "S4"}, \
        "S2 now stands for S1's name, so it's skipped"


def test_a_line_the_diarizer_heard_nothing_in_goes_to_the_nearest_voice_and_no_voice_changes_nothing():
    lines = [them(0, 2, "S1"), them(30, 32, "S5"), them(40, 42, "S6")]
    after = regrouped(lines, regroup(lines, [(0, 2, "A"), (39, 43, "B")]))
    assert [l.speaker for l in after] == ["S1", "S2", "S2"], "30-32 s is nearer B (39 s) than A (2 s)"
    assert regroup(lines, []) == {}
