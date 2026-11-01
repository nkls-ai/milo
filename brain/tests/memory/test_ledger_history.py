import json

from milo.core.ports import DictationHistory, UsageLedger
from milo.core.types import Usage
from milo.memory.history import JsonlDictationHistory
from milo.memory.ledger import JsonlUsageLedger, UsageTotals
from tests.fakes import FakeClock


def test_ledger_appends_one_line_per_call(tmp_path):
    clock = FakeClock()
    ledger = JsonlUsageLedger(tmp_path / "state" / "usage.jsonl", clock)
    assert isinstance(ledger, UsageLedger)
    ledger.record("chat", "codex", Usage(19000, 15000, 40))
    clock.advance(minutes=1)
    ledger.record("heartbeat", "codex", Usage(100, 0, 5))
    lines = [json.loads(line) for line in (tmp_path / "state" / "usage.jsonl").read_text(encoding="utf-8").splitlines()]
    assert lines[0] == {"ts": "2026-10-29T09:00:00", "source": "chat", "harness": "codex",
                        "input_tokens": 19000, "cached_input_tokens": 15000, "output_tokens": 40}
    assert lines[1]["source"] == "heartbeat"


def test_today_totals_counts_only_today(tmp_path):
    clock = FakeClock()
    path = tmp_path / "usage.jsonl"
    ledger = JsonlUsageLedger(path, clock)
    assert ledger.today_totals() == UsageTotals(0, Usage())
    ledger.record("chat", "codex", Usage(10, 5, 1))
    clock.advance(days=1)
    ledger.record("chat", "codex", Usage(20, 10, 2))
    ledger.record("chat", "claude", Usage(30, 0, 3))
    with path.open("a") as f:
        f.write("not json\n")
    assert ledger.today_totals() == UsageTotals(2, Usage(50, 10, 5))


def test_dictation_history_keeps_unicode_readable(tmp_path):
    path = tmp_path / "dictation-history.jsonl"
    history = JsonlDictationHistory(path, FakeClock())
    assert isinstance(history, DictationHistory)
    history.append("Grüße aus München", "Mail")
    history.append("second", None)
    raw = path.read_text(encoding="utf-8")
    assert "Grüße" in raw
    first, second = (json.loads(line) for line in raw.splitlines())
    assert first == {"ts": "2026-10-29T09:00:00", "app": "Mail", "text": "Grüße aus München"}
    assert second["app"] is None
