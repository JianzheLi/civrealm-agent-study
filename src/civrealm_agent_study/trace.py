"""Minimal durable records for smoke episodes and the future runner."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_run_id(kind: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return f"{stamp}_{kind}"


def _json_default(value: Any):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def write_json_atomic(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, indent=2, default=_json_default)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=_json_default))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


class EpisodeTrace:
    def __init__(self, run_root: Path, run_id: str, episode_id: str) -> None:
        self.run_dir = run_root / run_id
        self.episode_dir = self.run_dir / "episodes" / episode_id
        self.episode_dir.mkdir(parents=True, exist_ok=False)
        self.steps_path = self.episode_dir / "steps.jsonl"
        self.api_calls_path = self.episode_dir / "api_calls.jsonl"
        self.api_calls_path.touch()

    def write_manifest(self, manifest: dict[str, Any]) -> None:
        write_json_atomic(self.run_dir / "manifest.json", manifest)

    def append_step(self, step: dict[str, Any]) -> None:
        append_jsonl(self.steps_path, step)

    def append_api_call(self, call: dict[str, Any]) -> None:
        append_jsonl(self.api_calls_path, call)

    def write_result(self, result: dict[str, Any]) -> None:
        write_json_atomic(self.episode_dir / "episode_result.json", result)
