"""One QApplication for the entire test process, as in the real desktop.

Qt does not support repeatedly destroying/recreating its application while
Python-owned QObject cycles or deferred deletes from earlier tests remain.
Individual widget fixtures may borrow this instance, but never own its lifetime.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(scope="session", autouse=True)
def desktop_application():
    try:
        from PySide6.QtCore import QCoreApplication, QEvent
        from PySide6.QtWidgets import QApplication
    except ModuleNotFoundError:
        # The state/provider tests also run without optional desktop extras;
        # individual widget modules decide whether their own Qt tests can run.
        yield None
        return
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    yield application
    application.closeAllWindows()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    application.processEvents()
