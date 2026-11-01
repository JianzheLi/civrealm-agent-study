"""Run one task manifest in order and keep resumable compact summaries."""

from __future__ import annotations

import csv
import json
import multiprocessing
import os
import tempfile
import time
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
    "manifest_index",
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
            ordered = sorted(
                results,
                key=lambda result: (
                    result.get("manifest_index", len(results)),
                    result.get("attempt_number", 1),
                ),
            )
            writer.writerows(_csv_row(result) for result in ordered)
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
    workers: int,
) -> dict[str, Any]:
    completed_ids = {
        result["instance_id"]
        for result in results
        if result.get("stop_reason") != "infrastructure_error"
    }
    return {
        "batch_id": batch_id,
        "state": state,
        "workers": workers,
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
    workers: int,
) -> dict[str, Any]:
    _write_csv_atomic(batch_dir / "episode_results.csv", results)
    status = _status(batch_id, instance_ids, results, state, workers)
    write_json_atomic(batch_dir / "batch_status.json", status)
    return status


def _episode_job(payload: tuple[Any, ...]) -> dict[str, Any]:
    (
        episode_runner,
        bundle,
        repo_root,
        task_type,
        instance_id,
        max_env_steps,
        max_game_turns,
        attempt_number,
        batch_id,
    ) = payload
    return episode_runner(
        bundle,
        repo_root,
        task_type,
        instance_id,
        max_env_steps=max_env_steps,
        max_game_turns=max_game_turns,
        attempt_number=attempt_number,
        batch_id=batch_id,
    )


def _next_attempt(results: list[dict[str, Any]], instance_id: int) -> int:
    return 1 + max(
        (
            result.get("attempt_number", 1)
            for result in results
            if result["instance_id"] == instance_id
        ),
        default=0,
    )


def run_batch(
    bundle: dict[str, Any],
    repo_root: Path,
    task_type: str,
    *,
    limit: int | None = None,
    resume_batch_id: str | None = None,
    max_env_steps: int | None = None,
    max_game_turns: int | None = None,
    workers: int = 1,
    episode_runner: Callable[..., dict[str, Any]] = run_episode,
    batch_ready: Callable[[str, Path], None] | None = None,
) -> dict[str, Any]:
    task = bundle["instances"]["tasks"].get(task_type)
    if task is None:
        raise ValueError(f"Task is not assigned in this manifest: {task_type}")
    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive")
    if workers <= 0:
        raise ValueError("workers must be positive")
    if episode_runner is run_episode:
        key_name = bundle["shared"]["model"]["api_key_env"]
        if not os.environ.get(key_name):
            raise ValueError(f"environment variable {key_name} is not set")

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
        if manifest.get("workers", 1) != workers:
            raise ValueError("workers does not match the batch manifest")
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
            "workers": workers,
        }
        write_json_atomic(batch_dir / "batch_manifest.json", manifest)

    if batch_ready is not None:
        batch_ready(batch_id, batch_dir)

    results_path = batch_dir / "episode_results.jsonl"
    results = _load_jsonl(results_path)
    completed_ids = {
        result["instance_id"]
        for result in results
        if result.get("stop_reason") != "infrastructure_error"
    }
    _write_outputs(batch_dir, batch_id, instance_ids, results, "running", workers)

    remaining_ids = [
        instance_id for instance_id in instance_ids if instance_id not in completed_ids
    ]
    manifest_indexes = {
        instance_id: index for index, instance_id in enumerate(instance_ids)
    }

    def record(result: dict[str, Any]) -> bool:
        result = {
            **result,
            "batch_id": batch_id,
            "manifest_index": manifest_indexes[result["instance_id"]],
        }
        append_jsonl(results_path, result)
        results.append(result)
        if result.get("stop_reason") == "infrastructure_error":
            return False
        completed_ids.add(result["instance_id"])
        _write_outputs(batch_dir, batch_id, instance_ids, results, "running", workers)
        return True

    try:
        if workers == 1:
            for instance_id in remaining_ids:
                result = _episode_job(
                    (
                        episode_runner,
                        bundle,
                        repo_root,
                        task_type,
                        instance_id,
                        max_env_steps,
                        max_game_turns,
                        _next_attempt(results, instance_id),
                        batch_id,
                    )
                )
                if not record(result):
                    return _write_outputs(
                        batch_dir,
                        batch_id,
                        instance_ids,
                        results,
                        "paused_infrastructure_error",
                        workers,
                    )
        else:
            context = multiprocessing.get_context("spawn")
            pool = context.Pool(processes=min(workers, len(remaining_ids) or 1))
            active: dict[Any, int] = {}
            pending = iter(remaining_ids)
            exhausted = False
            paused = False
            try:
                while active or not exhausted:
                    while not paused and not exhausted and len(active) < workers:
                        try:
                            instance_id = next(pending)
                        except StopIteration:
                            exhausted = True
                            break
                        payload = (
                            episode_runner,
                            bundle,
                            repo_root,
                            task_type,
                            instance_id,
                            max_env_steps,
                            max_game_turns,
                            _next_attempt(results, instance_id),
                            batch_id,
                        )
                        active[pool.apply_async(_episode_job, (payload,))] = instance_id

                    ready = [job for job in active if job.ready()]
                    if not ready:
                        time.sleep(0.1)
                        continue
                    for job in ready:
                        active.pop(job)
                        if not record(job.get()):
                            paused = True
                    if paused and not active:
                        break
                pool.close()
                pool.join()
            except BaseException:
                pool.terminate()
                pool.join()
                raise
            if paused:
                return _write_outputs(
                    batch_dir,
                    batch_id,
                    instance_ids,
                    results,
                    "paused_infrastructure_error",
                    workers,
                )
    except KeyboardInterrupt:
        _write_outputs(
            batch_dir, batch_id, instance_ids, results, "interrupted", workers
        )
        raise
    except Exception:
        _write_outputs(
            batch_dir, batch_id, instance_ids, results, "interrupted", workers
        )
        raise

    return _write_outputs(
        batch_dir, batch_id, instance_ids, results, "completed", workers
    )
