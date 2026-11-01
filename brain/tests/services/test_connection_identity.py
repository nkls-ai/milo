"""Native labels and permission scopes come from adapters, never protocol callers."""
import asyncio
from types import SimpleNamespace

from milo.connect.server import Toolbox
from milo.core.app_connections import AppCalendar
from milo.core.ports import ConnectionIdentity, Connections, NamedConnection, connection_identity
from milo.core.types import ActionLevel, AppRef, Decision
from milo.services.connections import in_brain
from milo.services.reply_stream import ActRequest
from milo.services.tool_requests import ToolRequests
from tests.services.test_quick_actions import stack


def test_unknown_backend_gets_neutral_label_without_a_reusable_app_permission():
    assert connection_identity(object(), "Files") == ConnectionIdentity("Files")
    assert connection_identity(SimpleNamespace(identity="untrusted"), "Files").app is None


def test_app_bridge_preserves_the_adapters_identity():
    identity = ConnectionIdentity("Work calendar", AppRef("Calendar app", "calendar.exe"))
    original = AppCalendar(lambda op, args: [], identity)
    bridged = in_brain(Connections(calendar=original), lambda op, args: [], music=False)
    assert isinstance(bridged.calendar, NamedConnection)
    assert bridged.calendar.identity == identity


def test_outlook_action_card_and_scope_name_the_real_backend(tmp_path):
    s = stack(tmp_path, ['<event title="Dentist" start="2026-11-05T15:00"/>'])
    identity = ConnectionIdentity("Outlook", AppRef("Microsoft Outlook", "outlook.exe"))
    s.quick._connections.calendar.identity = identity
    plan = s.quick._add_event(ActRequest("event", {"title": "Dentist", "start": "2026-11-05T15:00"}), "en")
    assert plan.scope == identity.app
    assert asyncio.run(plan.run()).app == "Outlook"


def test_remote_calendar_card_has_a_label_without_borrowing_a_local_app_scope(tmp_path):
    s = stack(tmp_path, ['<event title="Dentist" start="2026-11-05T15:00"/>'])
    s.quick._connections.calendar.identity = ConnectionIdentity("Personal")
    plan = s.quick._add_event(ActRequest("event", {"title": "Dentist", "start": "2026-11-05T15:00"}), "en")
    assert plan.scope is None
    assert asyncio.run(plan.run()).app == "Personal"


def test_toolbox_uses_the_backend_app_instead_of_a_fixed_notes_app():
    apps = []
    outlook = AppRef("Microsoft Outlook", "outlook.exe")
    notes = SimpleNamespace(identity=ConnectionIdentity("Outlook", outlook),
                            create=lambda title, body, folder="": {"title": title})
    brain = SimpleNamespace(approve=lambda kind, summary, app="":
                            (apps.append(app) or Decision(True, ActionLevel.READ, "auto")))
    tools = Toolbox(Connections(notes=notes), brain)
    assert tools.call("notes_create", {"title": "Trip", "body": "Train"}) == {"title": "Trip"}
    assert apps == ["Microsoft Outlook"]


def test_tool_requests_only_accept_apps_whitelisted_by_composition():
    seen = []
    scoped = []
    outlook = AppRef("Microsoft Outlook", "outlook.exe")

    async def allows(app):
        seen.append(app)
        return True, ""

    async def approve(kind, summary, *, scope=None):
        scoped.append(scope)
        return Decision(True, ActionLevel.READ, "auto")

    requests = ToolRequests(SimpleNamespace(approve=approve), None, access=SimpleNamespace(allows=allows),
                            connection_apps=[outlook])

    async def run():
        assert (await requests.handle({"op": "access", "app": "Microsoft Outlook"}))["result"]["allowed"]
        assert not (await requests.handle({"op": "access", "app": "Unconfigured app"}))["ok"]
        assert (await requests.handle({"op": "approve", "kind": "change", "summary": "Edit note",
                                       "app": "Microsoft Outlook"}))["ok"]
        assert (await requests.handle({"op": "approve", "kind": "change", "summary": "Edit note",
                                       "app": "Unconfigured app"}))["ok"]
    asyncio.run(run())
    assert seen == [outlook]
    assert scoped[0].apps == (outlook,) and scoped[1] is None
