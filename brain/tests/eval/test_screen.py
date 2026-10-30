"""The on-screen eval's own logic: the table check and which cleanup questions it says yes to."""

import json

from milo.eval.screen import Run, Step, _check_table, _cleanup_answer, _values

WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def test_formulas_count_as_the_amounts_they_come_to():
    rows = ([["Day", "Budget"]] + [[d, 214.29] for d in WEEK[:6]] + [["Sunday", "=1500-SUM(B2:B7)"]]
            + [["Total", "=SUM(B2:B8)"]])
    values = _values({"rows": rows})
    assert round(values[(2, 8)], 2) == 214.26 and values[(2, 9)] == 1500
    run = Run(steps={"1": Step("Making a new table", "sheet_write " + json.dumps({"app": "Numbers", "rows": rows}),
                               "done", 0.0)})
    assert _check_table("Numbers")(run, None) == (True, "1 sheet_write call(s)")


def test_only_plain_arithmetic_is_worked_out():
    assert _values({"rows": [["=__import__('os').system('x')", "=ROUND(1500/7;2)"]]}) == {(2, 1): 214.29}


def _waiting(script: str) -> Run:
    return Run(steps={"1": Step("Running a script", script, "running", 0.0)})


def test_cleanup_says_yes_only_to_closing_quitting_and_deleting_in_its_own_apps():
    close = 'tell application "Numbers"\n  close front document saving no\n  quit\nend tell'
    assert _cleanup_answer(("Numbers",), "Run a script in Numbers? It's in my window.", _waiting(close))
    assert _cleanup_answer(("Numbers",), "May I use Numbers for this? You'll see each step.", Run())
    assert _cleanup_answer(("Numbers",), "I'm about to click “Delete” in Numbers. Go ahead?", Run())
    send = 'tell application "Mail"\n  send front outgoing message\n  delete drafts\nend tell'
    assert not _cleanup_answer(("Mail",), "Run a script in Mail? It's in my window.", _waiting(send))
    other = 'tell application "Numbers" to quit\ntell application "Finder" to delete every file of desktop'
    assert not _cleanup_answer(("Numbers",), "Run a script in Numbers, Finder? It's in my window.", _waiting(other))
    assert not _cleanup_answer(("Numbers",), "Run a script in Numbers? It's in my window.", _waiting(other))
    assert not _cleanup_answer(("Numbers",), "I'm about to click “Send” in Mail. Go ahead?", Run())
    assert not _cleanup_answer(("Numbers",), "Run a script in Numbers? It's in my window.", Run())
    assert not _cleanup_answer((), "May I use Numbers for this? You'll see each step.", Run())
    excel = ("Microsoft Excel",)
    assert _cleanup_answer(excel, "Close the Excel workbook with the weekly budget table without saving it?", Run())
    assert not _cleanup_answer(excel, "Close the Numbers document without saving it?", Run())
    assert not _cleanup_answer(excel, "Close Excel and empty the trash?", Run())
    assert _cleanup_answer(("Mail",), "Delete the reply draft you just made in Mail?", Run())
    assert not _cleanup_answer(("Mail",), "Delete the draft and send the reply?", Run())
    assert not _cleanup_answer(("Mail",), "Delete the newest email?", Run())
    assert not _cleanup_answer(excel, "Delete the reply draft you just made in Mail?", Run())
