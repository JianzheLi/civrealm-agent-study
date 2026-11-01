"""Run one task manifest in order and keep resumable compact summaries."""

from __future__ import annotations

import csv
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable

from .runner import run_episode
from .trace import append_jsonl, make_run_id, utc_now, write_json_atomic


CSV_FIELDS = [
    "batch_id",
    "run_id",
    "episode_id",
    "task_type",
    "difficulty",
    "instance_id",
    "attempt_number",
    "success",
    "stop_reason",
    "stop_detail",
    "initial_turn",
    "final_turn",
    "game_turns_elapsed",
    "env_steps",
    "api_calls_total",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "reasoning_tokens",
    "estimated_cost_usd_off_peak",
    "estimated_cost_usd_peak",
    "elapsed_seconds",
    "response_models",
    "result_dir",
    "error_type",
    "error_message",
]


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _csv_row(result: dict[str, Any]) -> dict[str, Any]:
    usage = result.get("usage") or {}
    cost = result.get("estimated_cost_usd") or {}
    error = result.get("error") or {}
    return {
        **{field: result.get(field) for field in CSV_FIELDS},
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "reasoning_tokens": usage.get("reasoning_tokens"),
        "estimated_cost_usd_off_peak": cost.get("off_peak"),
        "estimated_cost_usd_peak": cost.get("peak"),
        "response_models": ";".join(result.get("response_models") or []),
        "error_type": error.get("type"),
        "error_message": error.get("message"),
    }


def _write_csv_atomic(path: Path, results: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(_csv_row(result) for result in results)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def _status(
    batch_id: str,
    instance_ids: list[int],
    results: list[dict[str, Any]],
    state: str,
) -> dict[str, Any]:
    completed_ids = {
        result["instance_id"]
        for result in results
        if result.get("stop_reason") != "infrastructure_error"
    }
    return {
        "batch_id": batch_id,
        "state": state,
        "updated_at": utc_now(),
        "planned": len(instance_ids),
        "attempts": len(results),
        "completed": len(completed_ids),
        "remaining": len(instance_ids) - len(completed_ids),
        "successes": sum(
            1
            for instance_id in completed_ids
            if any(
                result["instance_id"] == instance_id and result.get("success")
                for result in results
            )
        ),
        "infrastructure_error_attempts": sum(
            result.get("stop_reason") == "infrastructure_error" for result in results
        ),
    }


def _write_outputs(
    batch_dir: Path,
    batch_id: str,
    instance_ids: list[int],
    results: list[dict[str, Any]],
    state: str,
) -> dict[str, Any]:
    _write_csv_atomic(batch_dir / "episode_results.csv", results)
    status = _status(batch_id, instance_ids, results, state)
    write_json_atomic(batch_dir / "batch_status.json", status)
    return status


def run_batch(
    bundle: dict[str, Any],
    repo_root: Path,
    task_type: str,
    *,
    limit: int | None = None,
    resume_batch_id: str | None = None,
    max_env_steps: int | None = None,
    max_game_turns: int | None = None,
    episode_runner: Callable[..., dict[str, Any]] = run_episode,
) -> dict[str, Any]:
    task = bundle["instances"]["tasks"].get(task_type)
    if task is None:
        raise ValueError(f"Task is not assigned in this manifest: {task_type}")
    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive")

    run_root = Path(bundle["local"]["runtime"]["run_root"])
    batches_root = run_root / "batches"
    if resume_batch_id:
        batch_id = resume_batch_id
        batch_dir = batches_root / batch_id
        manifest_path = batch_dir / "batch_manifest.json"
        if not manifest_path.is_file():
            raise ValueError(f"Batch does not exist: {batch_id}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["task_type"] != task_type:
            raise ValueError("Resume task does not match the batch manifest")
        if manifest["config_sha256"] != bundle["sha256"]:
            raise ValueError("Configuration changed; start a new batch instead of resuming")
        if manifest["max_env_steps_override"] != max_env_steps:
            raise ValueError("max_env_steps does not match the batch manifest")
        if manifest["max_game_turns_override"] != max_game_turns:
            raise ValueError("max_game_turns does not match the batch manifest")
        instance_ids = manifest["instance_ids"]
    else:
        batch_id = make_run_id(f"batch_{task_type}")
        batch_dir = batches_root / batch_id
        instance_ids = task["selected_ids"][:limit]
        manifest = {
            "batch_id": batch_id,
            "created_at": utc_now(),
            "task_type": task_type,
            "difficulty": bundle["shared"]["experiment"]["difficulty"],
            "instance_ids": instance_ids,
            "config_sha256": bundle["sha256"],
            "max_env_steps_override": max_env_steps,
            "max_game_turns_override": max_game_turns,
        }
        write_json_atomic(batch_dir / "batch_manifest.json", manifest)

    results_path = batch_dir / "episode_results.jsonl"
    results = _load_jsonl(results_path)
    completed_ids = {
        result["instance_id"]
        for result in results
        if result.get("stop_reason") != "infrastructure_error"
    }
    status = _write_outputs(batch_dir, batch_id, instance_ids, results, "running")

    try:
        for instance_id in instance_ids:
            if instance_id in completed_ids:
                continue
            attempt_number = 1 + max(
                (
                    result.get("attempt_number", 1)
                    for result in results
                    if result["instance_id"] == instance_id
                ),
                default=0,
            )
            result = episode_runner(
                bundle,
                repo_root,
                task_type,
                instance_id,
                max_env_steps=max_env_steps,
                max_game_turns=max_game_turns,
                attempt_number=attempt_number,
                batch_id=batch_id,
            )
            result = {**result, "batch_id": batch_id}
            append_jsonl(results_path, result)
            results.append(result)
            if result.get("stop_reason") == "infrastructure_error":
                return _write_outputs(
                    batch_dir, batch_id, instance_ids, results, "paused_infrastructure_error"
                )
            completed_ids.add(instance_id)
            status = _write_outputs(batch_dir, batch_id, instance_ids, results, "running")
    except KeyboardInterrupt:
        _write_outputs(batch_dir, batch_id, instance_ids, results, "interrupted")
        raise

    return _write_outputs(batch_dir, batch_id, instance_ids, results, "completed")
