from datetime import date, datetime

from milo.core.ports import UsageHistory
from milo.core.types import Usage
from milo.core.usage import Call, Dictated, summarize
from milo.memory.history import JsonlDictationHistory
from milo.memory.ledger import JsonlUsageLedger
from milo.memory.usage_log import JsonlUsageHistory
from tests.fakes import FakeClock


def test_reads_back_what_the_ledger_and_the_history_wrote(tmp_path):
    clock = FakeClock()
    ledger = JsonlUsageLedger(tmp_path / "usage.jsonl", clock)
    dictations = JsonlDictationHistory(tmp_path / "dictation-history.jsonl", clock)
    ledger.record("chat", "claude_live", Usage(100, 80, 5))
    dictations.append("Grüße an alle, bis morgen", "Mail")
    clock.advance(days=2)
    ledger.record("task", "codex", Usage(20000, 0, 300))
    dictations.append("ok", None)
    with (tmp_path / "usage.jsonl").open("a") as f:
        f.write("not json\n{\"ts\": \"2026-10-31T10:00:00\", \"input_tokens\": \"many\"}\n")

    history = JsonlUsageHistory(tmp_path / "usage.jsonl", tmp_path / "dictation-history.jsonl")
    assert isinstance(history, UsageHistory)
    assert history.calls(date(2026, 10, 29)) == [
        Call(datetime(2026, 10, 29, 9), "chat", "claude_live", Usage(100, 80, 5)),
        Call(datetime(2026, 10, 31, 9), "task", "codex", Usage(20000, 0, 300))]
    assert history.calls(date(2026, 10, 30)) == [Call(datetime(2026, 10, 31, 9), "task", "codex", Usage(20000, 0, 300))]
    assert history.dictations(date(2026, 10, 1)) == [Dictated(datetime(2026, 10, 29, 9), "Mail", 5),
                                                      Dictated(datetime(2026, 10, 31, 9), "", 1)]
    assert history.first_day() == date(2026, 10, 29)


def test_missing_files_are_no_usage_yet(tmp_path):
    history = JsonlUsageHistory(tmp_path / "usage.jsonl", tmp_path / "dictation-history.jsonl")
    assert history.calls(date(2026, 1, 1)) == [] and history.dictations(date(2026, 1, 1)) == []
    assert history.first_day() is None


def test_summary_has_every_day_of_the_span_and_ranks_sources_and_apps():
    day = lambda d, h=9: datetime(2026, 10, d, h)  # noqa: E731
    calls = [Call(day(20), "chat", "x", Usage(999, 0, 1)),  # before the span
             Call(day(29), "chat", "x", Usage(100, 50, 10)), Call(day(30), "task", "x", Usage(5000, 0, 100)),
             Call(day(30, 23), "chat", "x", Usage(200, 100, 20))]
    dictations = [Dictated(day(30), "Mail", 3), Dictated(day(30), "Slack", 40), Dictated(day(28), "Mail", 2)]
    s = summarize(calls, dictations, date(2026, 10, 30), 3, date(2026, 10, 20))
    assert [d["day"] for d in s.daily] == ["2026-10-28", "2026-10-29", "2026-10-30"]
    assert s.daily[0] == {"day": "2026-10-28", "calls": 0, "input_tokens": 0, "cached_input_tokens": 0,
                          "output_tokens": 0, "dictations": 1, "words": 2}
    assert s.daily[2]["calls"] == 2 and s.daily[2]["input_tokens"] == 5200 and s.daily[2]["words"] == 43
    assert s.sources == [{"source": "task", "calls": 1, "tokens": 5100}, {"source": "chat", "calls": 2, "tokens": 330}]
    assert s.apps == [{"app": "Slack", "dictations": 1, "words": 40}, {"app": "Mail", "dictations": 2, "words": 5}]
    assert s.since == date(2026, 10, 20)
