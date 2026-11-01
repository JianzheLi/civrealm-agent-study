"""Execute one deterministic legal action without calling an LLM."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import ConfigError, load_config_bundle
from .env import MinitaskSession, ordered_legal_actions, summarize_reset_info
from .trace import EpisodeTrace, make_run_id, utc_now


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--task", required=True)
    parser.add_argument("--instance-id", type=int)
    args = parser.parse_args(argv)

    try:
        bundle = load_config_bundle(args.repo_root)
    except ConfigError as error:
        print(f"[FAIL] config: {error}")
        return 1

    task_manifest = bundle["instances"]["tasks"].get(args.task)
    if task_manifest is None:
        print(f"[FAIL] task is not assigned in this manifest: {args.task}")
        return 1
    instance_id = args.instance_id
    if instance_id is None:
        instance_id = task_manifest["pipeline_validation_ids"][0]
    if instance_id not in task_manifest["selected_ids"]:
        print(f"[FAIL] instance {instance_id} is not in the recorded manifest")
        return 1

    run_id = make_run_id("smoke")
    episode_id = f"{args.task}_normal_{instance_id}_attempt-1"
    run_root = Path(bundle["local"]["runtime"]["run_root"])
    trace = EpisodeTrace(run_root, run_id, episode_id)
    trace.write_manifest(
        {
            "run_id": run_id,
            "kind": "pipeline_smoke_no_api",
            "created_at": utc_now(),
            "config_sha256": bundle["sha256"],
            "task_type": args.task,
            "difficulty": "normal",
            "instance_id": instance_id,
            "smoke_policy": "first_actor_first_legal_action",
            "api_enabled": False,
        }
    )

    with MinitaskSession() as session:
        _, before_info = session.reset(args.task, "normal", instance_id)
        legal_actions = ordered_legal_actions(before_info)
        if not legal_actions:
            print("[FAIL] environment returned no legal LLM actions")
            return 1
        selected = legal_actions[0]
        _, reward, terminated, truncated, after_info = session.step(selected)

        trace.append_step(
            {
                "run_id": run_id,
                "episode_id": episode_id,
                "decision_id": "decision-000000",
                "env_step": 0,
                "created_at": utc_now(),
                "policy": "pipeline_smoke_no_api",
                "before": summarize_reset_info(before_info),
                "legal_actions": legal_actions,
                "selected_action": selected,
                "execution": {
                    "reward": reward,
                    "terminated": terminated,
                    "truncated": truncated,
                },
                "after": summarize_reset_info(after_info),
            }
        )
        trace.write_result(
            {
                "run_id": run_id,
                "episode_id": episode_id,
                "task_type": args.task,
                "difficulty": "normal",
                "instance_id": instance_id,
                "env_steps": 1,
                "api_calls_total": 0,
                "stop_reason": "pipeline_smoke_complete",
                "native_status": after_info.get("minitask"),
                "terminated": terminated,
                "truncated": truncated,
                "port": session.port,
                "completed_at": utc_now(),
            }
        )

    print(json.dumps({"run_id": run_id, "episode_id": episode_id, "result_dir": str(trace.episode_dir)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
