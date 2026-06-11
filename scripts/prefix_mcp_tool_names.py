#!/usr/bin/env python3
"""Одноразово: префикс onec-data_ для имён MCP-инструментов в текстах агента."""

from __future__ import annotations

import re
from pathlib import Path

PREFIX = "onec-data_"
ROOT = Path(__file__).resolve().parent.parent

# Файлы, где агент читает имена инструментов (не server.py — там def onec_*).
TARGETS = [
    ROOT / ".opencode" / "agents" / "1c-analyst.md",
    ROOT / "WELCOME.md",
    ROOT / "AGENTS.md",
    ROOT / "README.md",
    ROOT / ".opencode" / "skills" / "1c-connection" / "SKILL.md",
    ROOT / ".opencode" / "skills" / "1c-work-modes" / "SKILL.md",
    ROOT / ".opencode" / "skills" / "1c-investigation-pipeline" / "SKILL.md",
    ROOT / ".opencode" / "skills" / "1c-cases" / "SKILL.md",
    ROOT / ".opencode" / "skills" / "1c-requirements-sheet" / "SKILL.md",
    ROOT / ".opencode" / "skills" / "1c-config-sources" / "SKILL.md",
    ROOT / ".opencode" / "skills" / "1c-obsidian-archive" / "SKILL.md",
    ROOT / ".opencode" / "skills" / "1c-web-research" / "SKILL.md",
    ROOT / "mcp" / "welcome.py",
    ROOT / "mcp" / "workflow_gates.py",
    ROOT / "mcp" / "agent_reply.py",
    ROOT / "mcp" / "connect_errors.py",
    ROOT / "mcp" / "bridge_client.py",
    ROOT / "mcp" / "session_context.py",
    ROOT / "mcp" / "config_sources.py",
    ROOT / "mcp" / "metadata_cache.py",
    ROOT / "mcp" / "connection_session.py",
    ROOT / "mcp" / "server.py",
]

# Не трогаем «def onec_*» — это имена функций в server.py.
TOOL_PATTERN = re.compile(
    rf"(?<!def )(?<!{re.escape(PREFIX)})(?<![\w-])onec_[a-z0-9_]+"
)


def prefix_tools(text: str) -> str:
    return TOOL_PATTERN.sub(lambda m: PREFIX + m.group(0), text)


def main() -> None:
    for path in TARGETS:
        if not path.is_file():
            print(f"skip (нет файла): {path}")
            continue
        original = path.read_text(encoding="utf-8")
        updated = prefix_tools(original)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            print(f"updated: {path.relative_to(ROOT)}")
        else:
            print(f"unchanged: {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
