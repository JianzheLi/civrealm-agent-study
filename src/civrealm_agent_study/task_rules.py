"""Extract the agent-facing portion of a reviewed Markdown TaskSpec."""

from __future__ import annotations

from pathlib import Path

from .config import ConfigError


START_HEADING = "## 给 Agent 的目标与规则"
END_HEADING = "## 玩家可见信息与动作"


def load_agent_task_rules(path: Path) -> str:
    if not path.is_file():
        raise ConfigError(f"TaskSpec does not exist: {path}")
    text = path.read_text(encoding="utf-8")
    start = text.find(START_HEADING)
    end = text.find(END_HEADING)
    if start == -1 or end == -1 or end <= start:
        raise ConfigError(f"TaskSpec agent-facing sections are malformed: {path}")
    rules = text[start + len(START_HEADING) : end].strip()
    if not rules:
        raise ConfigError(f"TaskSpec agent-facing rules are empty: {path}")
    return rules
