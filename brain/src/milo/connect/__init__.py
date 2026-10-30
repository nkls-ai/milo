"""Milo's app connections as an MCP stdio server: the worker CLI (Codex or Claude Code) starts it per task.

`python -m milo.connect` with MILO_HOME set. It reads [connections] from config.toml, asks the brain over
run/tools.sock before any action that needs the user's yes, and never sends mail.
"""
