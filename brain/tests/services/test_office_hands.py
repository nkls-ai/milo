import asyncio

from milo.services.hands import AppOffice
from tests.fakes import FakeConfirm, FakeHands
from tests.services.test_hands import Setup


class Office:
    def __init__(self, filled=0):
        self.filled = filled
        self.calls = []

    async def describe(self, tool, args):
        self.calls.append(("describe", tool))
        return {"app": args["app"], "document": "Budget.xlsx", "filled": self.filled,
                "new": bool(args.get("new_document"))}

    async def perform(self, tool, args):
        self.calls.append(("perform", tool))
        return {"document": "Budget.xlsx", "text": "Written with the native Office adapter."}


def test_native_office_never_generates_or_runs_applescript():
    office = Office()
    setup = Setup(office=office)
    result = setup.call("sheet_write", {"app": "Microsoft Excel", "rows": [[1]], "new_document": True})
    assert result.text == "Written with the native Office adapter."
    assert office.calls == [("describe", "sheet_write"), ("perform", "sheet_write")]
    assert not any(tool == "run_applescript" for tool, _ in setup.port.calls)


def test_replacing_native_cells_keeps_the_existing_confirmation_gate():
    office = Office(filled=2)
    setup = Setup(confirm=FakeConfirm(False), office=office)
    error = setup.fails("sheet_write", {"app": "Microsoft Excel", "rows": [[1, 2]]})
    assert "user said no" in error.lower()
    assert office.calls == [("describe", "sheet_write")]
    assert setup.confirm.asked == ["Replace 2 filled cells in “Budget.xlsx”?"]


def test_bridge_office_uses_existing_json_messages_and_carries_locale_as_data():
    hands = FakeHands()
    office = AppOffice(hands, "de_DE")

    async def run():
        await office.describe("sheet_write", {"app": "Microsoft Excel", "rows": [[1]]})
        await office.perform("sheet_write", {"app": "Microsoft Excel", "rows": [[1]]})
    asyncio.run(run())
    assert hands.calls == [("describe", {"tool": "sheet_write", "app": "Microsoft Excel", "rows": [[1]]}),
                           ("sheet_write", {"app": "Microsoft Excel", "rows": [[1]], "locale": "de_DE"})]
