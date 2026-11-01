"""Validate local configuration and optionally reset real CivRealm tasks."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .config import ConfigError, load_config_bundle


def _run(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def collect_checks(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    local = bundle["local"]
    checks: list[dict[str, Any]] = []

    configured_python = str(local["runtime"]["python_version"])
    actual_python = ".".join(map(str, sys.version_info[:3]))
    checks.append(
        {
            "name": "python_version",
            "status": "pass" if actual_python == configured_python else "fail",
            "expected": configured_python,
            "actual": actual_python,
        }
    )

    civrealm_repo = Path(local["environment"]["civrealm_repo"])
    commit = _run(["git", "rev-parse", "HEAD"], cwd=civrealm_repo)
    actual_commit = commit.stdout.strip() if commit.returncode == 0 else None
    checks.append(
        {
            "name": "civrealm_commit",
            "status": "pass"
            if actual_commit == local["environment"]["civrealm_commit"]
            else "fail",
            "expected": local["environment"]["civrealm_commit"],
            "actual": actual_commit,
        }
    )

    dirty_result = _run(["git", "status", "--porcelain"], cwd=civrealm_repo)
    actual_dirty = bool(dirty_result.stdout.strip())
    checks.append(
        {
            "name": "civrealm_dirty",
            "status": "pass"
            if actual_dirty == local["environment"]["civrealm_dirty"]
            else "fail",
            "expected": local["environment"]["civrealm_dirty"],
            "actual": actual_dirty,
        }
    )

    docker = local["environment"].get("docker", {})
    if local["environment"]["deployment_type"].startswith("docker"):
        executable = docker.get("executable")
        if not executable or not Path(executable).is_file():
            checks.append({"name": "docker_executable", "status": "fail"})
        else:
            inspect = _run(
                [executable, "inspect", docker["container_name"], "--format", "{{.Image}}"]
            )
            actual_image = inspect.stdout.strip() if inspect.returncode == 0 else None
            checks.append(
                {
                    "name": "docker_image_id",
                    "status": "pass" if actual_image == docker["image_id"] else "fail",
                    "expected": docker["image_id"],
                    "actual": actual_image,
                }
            )

    key_name = local["credentials"]["deepseek_api_key_env"]
    checks.append(
        {
            "name": "deepseek_api_key",
            "status": "pass" if os.environ.get(key_name) else "warn",
            "detail": f"environment variable {key_name} is set"
            if os.environ.get(key_name)
            else f"environment variable {key_name} is not set; API phases remain disabled",
        }
    )
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--probe", action="store_true", help="Reset the first validation instance of each assigned task")
    args = parser.parse_args(argv)

    try:
        bundle = load_config_bundle(args.repo_root)
    except ConfigError as error:
        print(f"[FAIL] config: {error}")
        return 1

    checks = collect_checks(bundle)
    for check in checks:
        print(f"[{check['status'].upper()}] {check['name']}: {check.get('detail', check.get('actual'))}")
    if any(check["status"] == "fail" for check in checks):
        return 1

    if args.probe:
        from .env import probe_minitask

        difficulty = bundle["shared"]["experiment"]["difficulty"]
        for task_type, task in bundle["instances"]["tasks"].items():
            instance_id = task["pipeline_validation_ids"][0]
            summary = probe_minitask(task_type, difficulty, instance_id)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
