"""What the brain needs from the operating system that differs between POSIX and Windows (ADR 0027).

Core code calls these instead of `fcntl`, `os.getuid`, `os.killpg` or `AF_UNIX`, so porting the brain to a new OS
family means one module here with the same functions, not edits all over the core. `posix.py` serves macOS and
Linux. `windows.py` has the same names and raises NotImplementedError, each saying what Windows would use.

Like `adapters/`, this package is outside test_portability's guard: it is where the platform lives.
"""

from __future__ import annotations

import os

if os.name == "nt":
    from .windows import clear_steering, event_loop, precise_timers, replace_file
    from .windows import open_child_no_follow, unlink_child_no_follow, restore_file
    from .windows import (connect_local, isolated_process, make_private, open_no_follow, open_to_others,
                          owned_by_me, peer_is_me, process_table, signal_processes, start_local_server, try_lock)
else:
    from .posix import clear_steering, event_loop, precise_timers, replace_file
    from .posix import open_child_no_follow, unlink_child_no_follow, restore_file
    from .posix import (connect_local, isolated_process, make_private, open_no_follow, open_to_others, owned_by_me,
                        peer_is_me, process_table, signal_processes, start_local_server, try_lock)

FUNCTIONS = ("event_loop", "precise_timers", "replace_file", "open_child_no_follow", "unlink_child_no_follow", "restore_file", "clear_steering", "connect_local", "isolated_process", "make_private", "open_no_follow", "open_to_others", "owned_by_me",
             "peer_is_me", "process_table", "signal_processes", "start_local_server", "try_lock")
"""Everything an OS family's module provides. tests/test_system.py checks both modules have each one."""

__all__ = list(FUNCTIONS)
