"""Command-line entry point for one recorded baseline episode."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .agent import DeepSeekCallError
from .config import ConfigError, load_config_bundle
from .runner import run_episode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--task", required=True)
    parser.add_argument("--instance-id", type=int)
    parser.add_argument("--max-env-steps", type=int)
    parser.add_argument(
        "--max-game-turns",
        type=int,
        help="Development-only override; stop after this many elapsed game turns",
    )
    args = parser.parse_args(argv)

    try:
        bundle = load_config_bundle(args.repo_root)
        task = bundle["instances"]["tasks"].get(args.task)
        if task is None:
            raise ConfigError(f"Task is not assigned in this manifest: {args.task}")
        instance_id = args.instance_id
        if instance_id is None:
            instance_id = task["pipeline_validation_ids"][0]
        result = run_episode(
            bundle,
            args.repo_root.resolve(),
            args.task,
            instance_id,
            max_env_steps=args.max_env_steps,
            max_game_turns=args.max_game_turns,
        )
    except (ConfigError, ValueError, DeepSeekCallError) as error:
        print(f"[FAIL] {error}")
        return 2 if isinstance(error, DeepSeekCallError) else 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["stop_reason"] not in {"infrastructure_error"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
