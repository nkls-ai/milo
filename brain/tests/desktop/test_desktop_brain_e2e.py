"""The QML shell's view models against a real brain over the real local socket, both ways.

Only the model, audio and native-device adapters are fakes. The protocol, the brain, live turns, the approval
policy, the server, the desktop client, the controller and the view models are real.
"""
import asyncio
import threading
import time

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication

from milo.desktop.client import BrainConnection
from milo.desktop.controller import DesktopController, ViewModels


def wait_for(predicate, seconds=10):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        QCoreApplication.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    assert predicate()


def test_typed_turn_and_money_approval_through_a_real_brain(tmp_path, sock_path):
    from milo.transport.unix_socket import UnixSocketServer
    from tests.fakes import FakeLiveModel, RecordingSink
    from tests.services.stack import Stack

    ready, shared, errors = threading.Event(), {}, []

    class WireSink(RecordingSink):
        server = None

        def emit(self, event):
            super().emit(event)
            if self.server is not None:
                self.server.emit(event)

        def request(self, event):
            self.events.append(event)
            return self.server.request(event) if self.server is not None else None

    async def serve():
        sink = WireSink()
        stack = Stack(sink=sink, model=FakeLiveModel(["[happy] Hello from the real brain."]), confirm_timeout_s=15)
        server = UnixSocketServer(sock_path, stack.brain.handle, stack.brain.greeting, stack.brain.app_gone)
        sink.server = server
        shutdown = asyncio.Event()
        shared.update(stack=stack, loop=asyncio.get_running_loop(), shutdown=shutdown)
        try:
            await server.start()
            ready.set()
            await shutdown.wait()
        finally:
            await server.close()
            await stack.tasks.close()
            stack.close()

    def worker():
        try:
            asyncio.run(serve())
        except BaseException as error:
            errors.append(error)
            ready.set()

    thread = threading.Thread(target=worker, name="real-brain-qml-e2e", daemon=True)
    thread.start()
    assert ready.wait(10), "The real local server did not start"
    if errors:
        raise errors[0]
    views = ViewModels()
    client = BrainConnection(sock_path)
    controller = DesktopController(tmp_path, views, client)
    try:
        client.start()
        wait_for(lambda: views.window.connected and bool(views.store.settings))
        assert views.window.sendText("hello from the desktop", "")
        wait_for(lambda: "Hello from the real brain." in views.presence.bubble)
        stack, loop = shared["stack"], shared["loop"]
        question = asyncio.run_coroutine_threadsafe(
            stack.approvals.confirm("Confirm this simulated payment?", money=True, speak=False), loop)
        wait_for(lambda: views.presence.question.get("id") is not None)
        assert views.presence.question["money"] is True
        # A money question offers no Allow always: asking for it sends nothing.
        views.presence.answer("always")
        time.sleep(0.05)
        QCoreApplication.processEvents()
        assert not question.done()
        views.presence.answer("yes")
        wait_for(lambda: question.done() and not views.store.confirmations)
        assert question.result() is True
    finally:
        controller.close()
        shared["loop"].call_soon_threadsafe(shared["shutdown"].set)
        thread.join(timeout=10)
    assert not thread.is_alive()
    assert not errors
