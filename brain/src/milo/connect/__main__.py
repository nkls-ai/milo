"""Composition root of the app-connections server. The worker CLI starts it; stdout belongs to MCP."""

from __future__ import annotations

import dataclasses
import logging
import logging.handlers
import os
import sys
from pathlib import Path


def main() -> None:
    from milo import adapters
    from milo.config import Config
    from milo.core.clock import SystemClock
    from milo.core.logtext import log_content
    from milo.core.registry import CONNECTIONS, AdapterContext
    from milo.memory.workspace import Workspace

    from milo.transport.tool_client import BrainClient
    from .memory_tools import RemoteMemory
    from .milo_tools import RemoteMilo
    from .server import BrainPhone, Toolbox, mcp_server

    home = Path(os.environ.get("MILO_HOME", "~/Milo")).expanduser()
    workspace = Workspace(home)
    config = Config.load(workspace.config_path)
    workspace.log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.handlers.RotatingFileHandler(
                            workspace.log_dir / "connect.log", maxBytes=512 * 1024, backupCount=1, encoding="utf-8")])
    log_content(config.logging.content)

    adapters.load_builtin()
    name, options = config.pluggable("connections")
    connections = CONNECTIONS.create(name, options, AdapterContext(home, workspace.state_dir, SystemClock()))
    switches = config.connections
    off = {f.name: None for f in dataclasses.fields(connections)
           if not switches.enabled or not getattr(switches, f.name, True)}
    connections = dataclasses.replace(connections, **off)
    brain = BrainClient(workspace.tools_socket_path)
    if config.messages.enabled:
        connections = dataclasses.replace(connections, phone=BrainPhone(brain))
    toolbox = Toolbox(connections, brain, RemoteMemory(brain) if config.memory.enabled else None, RemoteMilo(brain))
    logging.getLogger("milo.connect").info("serving %d tools (%s)", len(toolbox.tools), name)
    mcp_server(toolbox).serve(sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()
