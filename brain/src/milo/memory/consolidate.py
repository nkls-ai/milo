"""The nightly "sleep": the day's episode stubs become summaries, new facts, updated and retired ones, and a
journal page. One worker call per day, under [memory] consolidate_calls_per_day.

Run it by hand for a day, look first, or take a run back:

    uv run python -m milo.memory.consolidate --day 2026-10-30 --dry-run
    uv run python -m milo.memory.consolidate --day 2026-10-30
    uv run python -m milo.memory.consolidate --undo sleep-2026-10-30-01JBF...

Everything goes through the episode log and the fact store, which only ever append, and each run writes what it
changed to state/sleep/<run>.json, so --undo can put every line back.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from pathlib import Path

from milo.core.logtext import private
from milo.core.memory import TOPICS, ConsolidationReport, Episode, Fact, FactChange, new_id
from milo.core.ports import Clock, EpisodeLog, FactStore, Harness, UsageLedger
from milo.core.types import HarnessError

from . import jsonl

log = logging.getLogger("milo.sleep")

MAX_EPISODES = 150
"""The day's most recent episodes that go in one call. More than that is a very busy day."""
MAX_LINE = 600
MAX_FACTS = 400
MAX_FORGOTTEN = 100
JOURNAL_HEADING = "## Summed up at night"

PROMPT = """\
You are Milo's memory. It is night, and you tidy up what happened on {day}. Do not use any tools, do not read \
or change any files. Answer with one JSON object and nothing else (if your answer must have a `say` field, put \
the JSON object in it as text and set emotion to "neutral").

What Milo knows now, one fact per line with its id and topic:
{facts}

The user asked Milo to forget these. Never add them back, in any wording, even if the day mentions them:
{forgotten}

What happened that day, oldest first, one episode per line with its id:
{episodes}

Answer with this JSON:
{{"episodes": [{{"id": "E1", "summary": "one or two plain sentences about what happened", "people": ["Anna"]}}],
 "add": [{{"text": "a durable fact, one line", "topic": "{topics}", "from": ["E1"]}}],
 "update": [{{"id": "F3", "text": "the fact as it is now true", "from": ["E2"]}}],
 "retire": [{{"id": "F4", "reason": "why it stopped being true", "from": ["E2"]}}],
 "journal": "three to eight short plain lines about the day, for the user to read"}}

Rules:
- Summaries: plain words, in the language the user spoke, no ids, no file names. Leave an episode out if \
there is nothing to say about it.
- Facts are things worth knowing for months: who the user is, their people, work, preferences, routines. Not \
what happened once (that is an episode), not small talk, never passwords or other secrets.
- Every add, update and retire names the episodes it comes from in "from".
- Don't add what Milo already knows. When a known fact changed, update it instead of adding a second one. \
Retire a fact only when the user said it stopped being true.
- A pattern you notice over the facts and today ("calls his mother on Sundays") is a routine fact.
- Write facts about the user in the third person: "The user's sister is Anna."
- Empty lists are fine. Most days add nothing.
"""


class NightlyConsolidator:
    """Consolidator on the worker harness. `facts` takes `by=` (JsonlFactStore does) to tag each line."""

    def __init__(self, harness: Harness, episodes: EpisodeLog, facts: FactStore, journal_dir: Path, runs_dir: Path,
                 clock: Clock, ledger: UsageLedger | None = None, *, dry_run: bool = False):
        self._harness = harness
        self._episodes = episodes
        self._facts = facts
        self._journal_dir = journal_dir
        self._runs_dir = runs_dir
        self._clock = clock
        self._ledger = ledger
        self.dry_run = dry_run
        self.proposal: dict | None = None
        """The model's answer, after a run (for --dry-run)."""

    def prompt(self, day: date) -> tuple[str, dict[str, Episode], dict[str, Fact]]:
        """The prompt, and the short aliases (E1, F1) it uses for episode and fact ids."""
        start = datetime.combine(day, time())
        # Episodes that quote mail, files, web pages, the screen or a helper's results stay out: text written by
        # someone else must not come back as a fact or a summary in Milo's own words (ADR 0010).
        happened = [e for e in self._episodes.between(start, start + timedelta(days=1)) if e.trusted][-MAX_EPISODES:]
        known = sorted(self._facts.current(), key=lambda f: f.since)[-MAX_FACTS:]
        episodes = {f"E{i}": e for i, e in enumerate(happened, 1)}
        facts = {f"F{i}": f for i, f in enumerate(known, 1)}
        fact_lines = "\n".join(f"- {a} [{f.topic}] {_line(f.text)}" for a, f in facts.items()) or "- (nothing yet)"
        episode_lines = "\n".join(
            f"- {a} {e.at:%H:%M} {e.kind}: {_line(e.summary)}"
            + (f" (apps: {', '.join(e.apps)})" if e.apps else "") for a, e in episodes.items())
        forgotten = "\n".join(f"- {_line(f.text)}" for f in self._facts.forgotten()[:MAX_FORGOTTEN]) or "- (nothing)"
        text = PROMPT.format(day=f"{day:%A %-d %B %Y}", facts=fact_lines, forgotten=forgotten,
                             episodes=episode_lines, topics="|".join(TOPICS))
        return text, episodes, facts

    async def consolidate(self, day: date) -> ConsolidationReport:
        run = f"sleep-{day.isoformat()}-{new_id(self._clock.now())}"
        text, episodes, facts = self.prompt(day)
        if not episodes:
            return ConsolidationReport(day, run, skipped="nothing happened")
        try:
            reply = await self._harness.reply(text, None)
        except HarnessError as e:
            log.error("the nightly consolidation call failed: %s", e)
            return ConsolidationReport(day, run, calls=1, skipped="the worker failed")
        if self._ledger is not None:
            self._ledger.record("memory", self._harness.name, reply.usage)
        proposal = parse(reply.say)
        self.proposal = proposal
        if proposal is None:
            log.error("the nightly consolidation answer wasn't JSON: %s", private(reply.say))
            return ConsolidationReport(day, run, calls=1, skipped="the answer wasn't readable")
        if self.dry_run:
            return ConsolidationReport(day, run, calls=1, skipped="dry run")
        return self._apply(day, run, proposal, episodes, facts)

    def _apply(self, day: date, run: str, proposal: dict, episodes: dict[str, Episode],
               facts: dict[str, Fact]) -> ConsolidationReport:
        undo: dict = {"run": run, "day": day.isoformat(), "episodes": [], "facts": []}
        notes: list[str] = []
        now = self._clock.now()
        summaries = 0
        for item in _list(proposal, "episodes"):
            old = episodes.get(str(item.get("id")))
            summary = _clean(item.get("summary"))
            if old is None or not old.trusted or not summary or summary == old.summary:
                continue
            people = tuple(dict.fromkeys([*old.people, *(_clean(p) for p in _strings(item.get("people")))]))
            self._episodes.append(replace(old, summary=summary, people=tuple(p for p in people if p)))
            undo["episodes"].append(old.to_dict())
            summaries += 1

        def trusted_source(item: dict) -> Episode | None:
            """The first episode the change comes from that the user said or did. None: from outside or made up."""
            sources = [episodes.get(str(a)) for a in _strings(item.get("from"))]
            return next((e for e in sources if e is not None and e.trusted), None)

        changes: list[FactChange] = []
        known = {f.text.lower() for f in self._facts.current()}
        forgotten = {f.text.lower() for f in self._facts.forgotten()}
        for item in _list(proposal, "add"):
            text, source = _clean(item.get("text")), trusted_source(item)
            if not text or text.lower() in known:
                continue
            if text.lower() in forgotten:
                notes.append(f"left out a fact the user had forgotten: {private(text)}")
                continue
            if source is None:
                notes.append(f"left out a fact without a trusted source: {private(text)}")
                continue
            topic = str(item.get("topic") or "learned")
            # Basics go into every system prompt; only the user puts a fact there (What Milo knows, profile.md).
            topic = topic if topic in TOPICS and topic != "basics" else "learned"
            fact = Fact(new_id(now), text, topic, now, source.id)
            self._facts.add(fact, by=run)
            known.add(text.lower())
            changes.append(FactChange("add", fact.id, text))
        for item in _list(proposal, "update"):
            old, text, source = facts.get(str(item.get("id"))), _clean(item.get("text")), trusted_source(item)
            if old is None or not text or text == old.text:
                continue
            if source is None:
                notes.append(f"left out an update without a trusted source: {private(text)}")
                continue
            fact = Fact(new_id(now), text, old.topic, now, source.id, replaces=old.id, pinned=old.pinned)
            self._facts.add(fact, by=run)
            changes.append(FactChange("update", fact.id, text, f"replaces {old.id}"))
        for item in _list(proposal, "retire"):
            old, source = facts.get(str(item.get("id"))), trusted_source(item)
            if old is None:
                continue
            if source is None:
                notes.append(f"kept a fact the answer wanted retired without a trusted source: {old.id}")
                continue
            reason = _clean(item.get("reason")) or "no longer true"
            self._facts.retire(old.id, reason, by=run)
            changes.append(FactChange("retire", old.id, old.text, reason))
        undo["facts"] = [{"op": c.op, "id": c.fact_id} for c in changes]
        journal = self._journal(day, str(proposal.get("journal") or "").strip())
        jsonl.write_private(self._runs_dir / f"{run}.json", json.dumps(undo, ensure_ascii=False, indent=1))
        for note in notes:
            log.warning("%s", note)
        log.info("slept on %s: %d summaries, %d fact changes", day, summaries, len(changes))
        return ConsolidationReport(day, run, summaries, tuple(changes), journal, calls=1, notes=tuple(notes))

    def _journal(self, day: date, text: str) -> str:
        if not text:
            return ""
        path = self._journal_dir / f"{day.isoformat()}.md"
        body = "\n".join(line.rstrip() for line in text.replace("\r", "").split("\n")).strip()
        try:
            existing = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            existing = f"# {day:%A %-d %B %Y}\n"
        existing = existing.split(JOURNAL_HEADING)[0].rstrip()  # a second run replaces the first one's section
        jsonl.write_private(path, f"{existing}\n\n{JOURNAL_HEADING}\n\n{body}\n")
        return str(path)


def undo(run: str, runs_dir: Path, episodes: EpisodeLog, facts: FactStore) -> int:
    """Take back everything run `run` changed. Returns how many lines were written."""
    record = json.loads((runs_dir / f"{run}.json").read_text())
    written = 0
    for old in record.get("episodes", []):
        episodes.append(Episode.from_dict(old))  # the stub again, as the newest version
        written += 1
    for change in reversed(record.get("facts", [])):
        if change["op"] in ("add", "update"):
            facts.retire(change["id"], f"undo {run}", by="undo")
        elif change["op"] == "retire":
            facts.restore(change["id"], f"undo {run}", by="undo")
        written += 1
    return written


def parse(text: str) -> dict | None:
    """The JSON object in the answer, also when it is wrapped in a `say` or a code fence."""
    text = text.strip()
    for candidate in (text, text[text.find("{"):text.rfind("}") + 1] if "{" in text else ""):
        try:
            data = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(data, dict) and isinstance(data.get("say"), str) and "{" in data["say"]:
            return parse(data["say"])
        if isinstance(data, dict):
            return data
    return None


def _list(proposal: dict, key: str) -> list[dict]:
    value = proposal.get(key)
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value] if isinstance(value, list) else []


def _clean(value) -> str:
    return " ".join(str(value or "").split())[:MAX_LINE]


def _line(text: str) -> str:
    text = " ".join(text.replace("<", "‹").replace(">", "›").split())
    return text if len(text) <= MAX_LINE else text[:MAX_LINE] + "…"


# ---- by hand


def main(argv: list[str] | None = None) -> int:
    args = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                   formatter_class=argparse.RawDescriptionHelpFormatter)
    args.add_argument("--day", help="YYYY-MM-DD, default yesterday")
    args.add_argument("--home", default=os.environ.get("MILO_HOME", "~/Milo"))
    args.add_argument("--dry-run", action="store_true", help="ask the worker, print its answer, change nothing")
    args.add_argument("--prompt", action="store_true", help="only print the prompt; no worker call")
    args.add_argument("--undo", metavar="RUN", help="take back the run with this name (see state/sleep/)")
    opts = args.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)

    from milo import adapters
    from milo.config import Config
    from milo.core.clock import SystemClock
    from milo.core.registry import HARNESSES, AdapterContext

    from .episodes import JsonlEpisodeLog
    from .facts import JsonlFactStore
    from .ledger import JsonlUsageLedger
    from .workspace import Workspace

    workspace = Workspace(Path(opts.home).expanduser())
    clock = SystemClock()
    episodes = JsonlEpisodeLog(workspace.episodes_dir, clock)
    facts = JsonlFactStore(workspace.facts_path, clock)
    runs = workspace.state_dir / "sleep"
    if opts.undo:
        print(f"took back {undo(opts.undo, runs, episodes, facts)} line(s) of {opts.undo}")
        return 0
    day = date.fromisoformat(opts.day) if opts.day else clock.now().date() - timedelta(days=1)
    if opts.prompt:
        print(NightlyConsolidator(None, episodes, facts, workspace.journal_dir, runs, clock).prompt(day)[0])
        return 0
    config = Config.load(workspace.config_path)
    adapters.load_builtin()
    name, options = config.pluggable("harness")
    harness = HARNESSES.create(name, options, AdapterContext(workspace.home, workspace.state_dir, clock))
    sleeper = NightlyConsolidator(harness, episodes, facts, workspace.journal_dir, runs, clock,
                                  JsonlUsageLedger(workspace.usage_path, clock), dry_run=opts.dry_run)
    report = asyncio.run(sleeper.consolidate(day))
    if opts.dry_run:
        print(json.dumps(sleeper.proposal, ensure_ascii=False, indent=2))
    print(f"{day}: {report.skipped or 'done'}; {report.episodes} summaries, {len(report.changes)} fact changes"
          + (f"; journal {report.journal}" if report.journal else "") + (f"; run {report.run}" if not report.skipped else ""))
    for change in report.changes:
        print(f"  {change.op} {change.fact_id}: {change.text}")
    for note in report.notes:
        print(f"  note: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
