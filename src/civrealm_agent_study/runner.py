"""Run one fully recorded CivRealm episode with the shared baseline Agent."""

from __future__ import annotations

import time
import subprocess
from pathlib import Path
from typing import Any, Callable

from .agent import BaselineAgent, DecisionError, DeepSeekCallError
from .config import sha256_file
from .env import MinitaskSession, next_actor_context, summarize_reset_info
from .task_rules import load_agent_task_rules
from .trace import EpisodeTrace, make_run_id, utc_now


def _native_stop_reason(info: dict[str, Any], terminated: bool, truncated: bool):
    minitask = info.get("minitask", {})
    success = minitask.get("success", minitask.get("is_mini_success"))
    if success == 1:
        return "native_success"
    if success == 0:
        return "native_failure"
    if truncated:
        return "infrastructure_error"
    if terminated:
        return "execution_failure"
    return None


def _usage_totals(api_records: list[dict[str, Any]]) -> dict[str, int]:
    totals = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "reasoning_tokens": 0,
    }
    for record in api_records:
        usage = record.get("usage") or {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            totals[key] += int(usage.get(key) or 0)
        details = usage.get("completion_tokens_details") or {}
        totals["reasoning_tokens"] += int(
            details.get("reasoning_tokens") or usage.get("reasoning_tokens") or 0
        )
    return totals


def _attach_cost_bounds(
    record: dict[str, Any], pricing: dict[str, Any]
) -> dict[str, Any]:
    usage = record.get("usage")
    if not usage:
        record["estimated_cost_usd"] = None
        return record
    rates = pricing["deepseek_flash"]
    unit = pricing["unit_tokens"]
    prompt = int(usage.get("prompt_tokens") or 0)
    cache_hit = int(
        usage.get("prompt_cache_hit_tokens")
        or (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
        or 0
    )
    cache_miss = int(usage.get("prompt_cache_miss_tokens") or max(prompt - cache_hit, 0))
    output = int(usage.get("completion_tokens") or 0)
    record["estimated_cost_usd"] = {
        tier: (
            cache_hit * rates["input_cache_hit"][tier]
            + cache_miss * rates["input_cache_miss"][tier]
            + output * rates["output"][tier]
        )
        / unit
        for tier in ("off_peak", "peak")
    }
    record["pricing_checked_on"] = pricing["checked_on"]
    record["pricing_source"] = pricing["source"]
    return record


def _save_api_record(
    trace: EpisodeTrace,
    api_records: list[dict[str, Any]],
    record: dict[str, Any],
    pricing: dict[str, Any],
) -> None:
    record = _attach_cost_bounds(record, pricing)
    trace.append_api_call(record)
    api_records.append(record)


def _cost_totals(api_records: list[dict[str, Any]]) -> dict[str, float]:
    return {
        tier: sum(
            (record.get("estimated_cost_usd") or {}).get(tier, 0.0)
            for record in api_records
        )
        for tier in ("off_peak", "peak")
    }


def _git_state(repo_root: Path) -> dict[str, Any]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {
        "commit": commit.stdout.strip() if commit.returncode == 0 else None,
        "dirty": bool(status.stdout.strip()) if status.returncode == 0 else None,
    }


def run_episode(
    bundle: dict[str, Any],
    repo_root: Path,
    task_type: str,
    instance_id: int,
    max_env_steps: int | None = None,
    max_game_turns: int | None = None,
    agent: Any | None = None,
    session_factory: Callable[[], Any] = MinitaskSession,
    attempt_number: int = 1,
    batch_id: str | None = None,
) -> dict[str, Any]:
    shared = bundle["shared"]
    task_config = shared["tasks"].get(task_type)
    if task_config is None or "task_spec" not in task_config:
        raise ValueError(f"Task is not configured with a TaskSpec: {task_type}")
    task_manifest = bundle["instances"]["tasks"].get(task_type)
    if task_manifest is None or instance_id not in task_manifest["selected_ids"]:
        raise ValueError(f"Instance {instance_id} is not in the manifest for {task_type}")

    step_limit = (
        shared["environment"]["max_env_steps"]
        if max_env_steps is None
        else max_env_steps
    )
    if step_limit <= 0:
        raise ValueError("max_env_steps must be positive")
    if max_game_turns is not None and max_game_turns <= 0:
        raise ValueError("max_game_turns must be positive when provided")
    if attempt_number <= 0:
        raise ValueError("attempt_number must be positive")
    task_spec_path = repo_root / task_config["task_spec"]
    prompt_path = repo_root / shared["agent"]["prompt_path"]
    correction_prompt_path = repo_root / shared["agent"]["correction_prompt_path"]
    task_rules = load_agent_task_rules(task_spec_path)
    agent = agent or BaselineAgent.from_bundle(bundle, repo_root)

    run_id = make_run_id("baseline")
    episode_id = f"{task_type}_normal_{instance_id}_attempt-{attempt_number}"
    run_root = Path(bundle["local"]["runtime"]["run_root"])
    trace = EpisodeTrace(run_root, run_id, episode_id)
    video_expected = (
        shared["experiment"]["status"] == "frozen"
        and shared["video"]["required_for_pipeline_validation"]
        and instance_id in task_manifest["pipeline_validation_ids"]
    )
    trace.write_manifest(
        {
            "run_id": run_id,
            "batch_id": batch_id,
            "kind": "baseline_episode",
            "created_at": utc_now(),
            "config_status": shared["experiment"]["status"],
            "config_sha256": bundle["sha256"],
            "artifact_sha256": {
                "task_spec": sha256_file(task_spec_path),
                "baseline_prompt": sha256_file(prompt_path),
                "correction_prompt": sha256_file(correction_prompt_path),
            },
            "study_repo": _git_state(repo_root),
            "task_type": task_type,
            "difficulty": shared["experiment"]["difficulty"],
            "instance_id": instance_id,
            "attempt_number": attempt_number,
            "max_env_steps": step_limit,
            "max_game_turns_override": max_game_turns,
            "video_expected": video_expected,
            "environment": bundle["local"]["environment"],
            "model": shared["model"],
            "agent": shared["agent"],
        }
    )

    started = time.perf_counter()
    api_records: list[dict[str, Any]] = []
    history: list[dict[str, Any]] = []
    initial_turn = None
    final_info: dict[str, Any] = {}
    env_steps = 0
    stop_reason = "interrupted"
    stop_detail = None
    terminated = False
    truncated = False
    error: dict[str, str] | None = None
    pending_step: dict[str, Any] | None = None
    planned_actor_keys: set[str] = set()
    planned_turn = None

    try:
        with session_factory() as session:
            _, info = session.reset(
                task_type, shared["experiment"]["difficulty"], instance_id
            )
            initial_turn = info.get("turn")
            final_info = info

            while env_steps < step_limit:
                if info.get("turn") != planned_turn:
                    planned_actor_keys.clear()
                    planned_turn = info.get("turn")
                scheduled_actor, prompt_actors, legal_actions = next_actor_context(
                    info, planned_actor_keys
                )
                decision_id = f"decision-{env_steps:06d}"
                before = summarize_reset_info(info)
                selected_action = None
                decision_result = None

                if legal_actions:
                    context = {
                        "game_turn": info.get("turn"),
                        "env_step": env_steps,
                        "task_metrics": info.get("minitask", {}),
                        "actors": prompt_actors,
                        "legal_actions": legal_actions,
                        "recent_history": history[-shared["agent"]["recent_action_history"] :],
                        "resource_context": {
                            "remaining_env_steps": step_limit - env_steps,
                            "api_calls_used": len(api_records),
                            "elapsed_seconds": time.perf_counter() - started,
                        },
                    }
                    pending_step = {
                        "run_id": run_id,
                        "episode_id": episode_id,
                        "decision_id": decision_id,
                        "env_step": env_steps,
                        "created_at": utc_now(),
                        "before": before,
                        "scheduled_actor": scheduled_actor,
                        "legal_actions": legal_actions,
                    }
                    decision_result = agent.decide(task_rules, context, decision_id)
                    for api_record in decision_result["api_records"]:
                        _save_api_record(
                            trace, api_records, api_record, shared["pricing"]
                        )
                    action_id = decision_result["decision"]["action_id"]
                    selected_action = next(
                        action for action in legal_actions if action["action_id"] == action_id
                    )
                    planned_actor_keys.add(scheduled_actor)

                _, reward, terminated, truncated, next_info = session.step(selected_action)
                after = summarize_reset_info(next_info)
                step_record = {
                    "run_id": run_id,
                    "episode_id": episode_id,
                    "decision_id": decision_id,
                    "env_step": env_steps,
                    "created_at": utc_now(),
                    "before": before,
                    "scheduled_actor": scheduled_actor,
                    "legal_actions": legal_actions,
                    "model_decision": decision_result["decision"] if decision_result else None,
                    "raw_outputs": decision_result["raw_outputs"] if decision_result else [],
                    "selected_action": selected_action,
                    "automatic_end_turn": selected_action is None,
                    "execution": {
                        "reward": reward,
                        "terminated": terminated,
                        "truncated": truncated,
                    },
                    "after": after,
                }
                trace.append_step(step_record)
                pending_step = None
                history.append(
                    {
                        "env_step": env_steps,
                        "game_turn_before": before.get("turn"),
                        "action": selected_action or {"action_name": "end_turn"},
                        "reward": reward,
                        "game_turn_after": after.get("turn"),
                        "task_metrics_after": after.get("minitask"),
                    }
                )
                env_steps += 1
                info = next_info
                final_info = next_info

                native_reason = _native_stop_reason(info, terminated, truncated)
                if native_reason:
                    stop_reason = native_reason
                    break
                if (
                    max_game_turns is not None
                    and isinstance(initial_turn, int)
                    and isinstance(info.get("turn"), int)
                    and info["turn"] - initial_turn >= max_game_turns
                ):
                    stop_reason = "interrupted"
                    stop_detail = "development_game_turn_limit"
                    break
            else:
                stop_reason = "step_limit"
    except DecisionError as exception:
        for api_record in exception.api_records:
            _save_api_record(trace, api_records, api_record, shared["pricing"])
        stop_reason = "output_failure"
        error = {"type": type(exception).__name__, "message": str(exception)}
        if pending_step is not None:
            trace.append_step(
                {
                    **pending_step,
                    "model_decision": None,
                    "raw_outputs": exception.raw_outputs,
                    "selected_action": None,
                    "automatic_end_turn": False,
                    "execution": None,
                    "decision_error": error,
                }
            )
    except DeepSeekCallError as exception:
        for api_record in exception.attempts:
            _save_api_record(trace, api_records, api_record, shared["pricing"])
        stop_reason = "infrastructure_error"
        error = {"type": type(exception).__name__, "message": str(exception)}
        if pending_step is not None:
            trace.append_step(
                {
                    **pending_step,
                    "model_decision": None,
                    "raw_outputs": [],
                    "selected_action": None,
                    "automatic_end_turn": False,
                    "execution": None,
                    "decision_error": error,
                }
            )
    except Exception as exception:
        stop_reason = "infrastructure_error"
        error = {"type": type(exception).__name__, "message": str(exception)}

    final_turn = final_info.get("turn")
    result = {
        "run_id": run_id,
        "batch_id": batch_id,
        "episode_id": episode_id,
        "task_type": task_type,
        "difficulty": shared["experiment"]["difficulty"],
        "instance_id": instance_id,
        "attempt_number": attempt_number,
        "success": stop_reason == "native_success",
        "stop_reason": stop_reason,
        "stop_detail": stop_detail,
        "native_status": final_info.get("minitask"),
        "initial_turn": initial_turn,
        "final_turn": final_turn,
        "game_turns_elapsed": final_turn - initial_turn
        if isinstance(final_turn, int) and isinstance(initial_turn, int)
        else None,
        "env_steps": env_steps,
        "api_calls_total": len(api_records),
        "response_models": sorted(
            {
                record["response_model"]
                for record in api_records
                if record.get("response_model")
            }
        ),
        "usage_unknown_calls": sum(
            1 for record in api_records if record.get("usage_unknown")
        ),
        "usage": _usage_totals(api_records),
        "estimated_cost_usd": _cost_totals(api_records),
        "terminated": terminated,
        "truncated": truncated,
        "elapsed_seconds": time.perf_counter() - started,
        "video_expected": video_expected,
        "error": error,
        "completed_at": utc_now(),
        "result_dir": str(trace.episode_dir),
    }
    trace.write_result(result)
    return result
