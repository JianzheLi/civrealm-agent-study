"""Command-line entry point for a resumable task batch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .agent import DeepSeekCallError
from .batch import run_batch
from .config import ConfigError, load_config_bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--task", required=True)
    parser.add_argument("--limit", type=int, help="New batches only; run the first N manifest IDs")
    parser.add_argument("--resume", metavar="BATCH_ID")
    parser.add_argument("--max-env-steps", type=int)
    parser.add_argument(
        "--max-game-turns",
        type=int,
        help="Development-only override; stop after this many elapsed game turns",
    )
    args = parser.parse_args(argv)

    try:
        bundle = load_config_bundle(args.repo_root)
        status = run_batch(
            bundle,
            args.repo_root.resolve(),
            args.task,
            limit=args.limit,
            resume_batch_id=args.resume,
            max_env_steps=args.max_env_steps,
            max_game_turns=args.max_game_turns,
        )
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Resume later with --resume BATCH_ID")
        return 130
    except (ConfigError, ValueError, DeepSeekCallError) as error:
        print(f"[FAIL] {error}")
        return 2 if isinstance(error, DeepSeekCallError) else 1

    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 2 if status["state"] == "paused_infrastructure_error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
