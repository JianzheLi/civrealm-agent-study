"""Load and validate shared, local, and instance configuration files."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when an experiment configuration is incomplete or inconsistent."""


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ConfigError(f"Configuration file does not exist: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigError(f"Configuration root must be a mapping: {path}")
    return data


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require(mapping: dict[str, Any], key: str, location: str) -> Any:
    if key not in mapping:
        raise ConfigError(f"Missing {location}.{key}")
    return mapping[key]


def validate_config_bundle(
    shared: dict[str, Any],
    local: dict[str, Any],
    instances: dict[str, Any],
) -> None:
    experiment = _require(shared, "experiment", "shared")
    tasks = _require(shared, "tasks", "shared")
    environment = _require(shared, "environment", "shared")
    model = _require(shared, "model", "shared")

    if experiment.get("difficulty") != "normal":
        raise ConfigError("First-round difficulty must be normal")
    episode_count = experiment.get("episodes_per_task")
    if not isinstance(episode_count, int) or episode_count <= 0:
        raise ConfigError("experiment.episodes_per_task must be a positive integer")
    if environment.get("max_env_steps") != 2000:
        raise ConfigError("First-round max_env_steps must be 2000")
    if model.get("api_key_env") != "DEEPSEEK_API_KEY":
        raise ConfigError("The API key must be read from DEEPSEEK_API_KEY")
    if local.get("member") != instances.get("owner"):
        raise ConfigError("Local member and instance manifest owner do not match")

    candidate = _require(instances, "candidate_ids", "instances")
    lower = _require(candidate, "min", "instances.candidate_ids")
    upper = _require(candidate, "max", "instances.candidate_ids")
    validation_count = shared["instances"]["first_n_for_pipeline_validation"]

    for task_name, task_manifest in _require(instances, "tasks", "instances").items():
        if task_name not in tasks:
            raise ConfigError(f"Unknown task in instance manifest: {task_name}")
        if tasks[task_name].get("owner") != local["member"]:
            raise ConfigError(f"Task {task_name} is not assigned to {local['member']}")

        selected = _require(task_manifest, "selected_ids", task_name)
        validation = _require(task_manifest, "pipeline_validation_ids", task_name)
        if len(selected) != episode_count:
            raise ConfigError(
                f"{task_name} must contain {episode_count} IDs, got {len(selected)}"
            )
        if len(set(selected)) != len(selected):
            raise ConfigError(f"{task_name} contains duplicate instance IDs")
        if not all(isinstance(value, int) and lower <= value <= upper for value in selected):
            raise ConfigError(f"{task_name} contains an out-of-range instance ID")
        if selected[:validation_count] != validation:
            raise ConfigError(f"{task_name} validation IDs must be the first selected IDs")


def load_config_bundle(
    repo_root: Path,
    shared_path: Path | None = None,
    local_path: Path | None = None,
    instances_path: Path | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    shared_file = (shared_path or repo_root / "configs" / "first_round.yaml").resolve()
    local_file = (local_path or repo_root / "configs" / "local.yaml").resolve()
    shared = load_yaml(shared_file)
    local = load_yaml(local_file)
    member = local.get("member")
    if not isinstance(member, str) or not member.strip():
        raise ConfigError("local.member must be a non-empty string")
    instances_file = (
        instances_path
        or repo_root / "configs" / "instances" / f"{member}_first_round.yaml"
    ).resolve()
    paths = {
        "shared": shared_file,
        "local": local_file,
        "instances": instances_file,
    }
    bundle = {
        "shared": shared,
        "local": local,
        "instances": load_yaml(instances_file),
    }
    validate_config_bundle(bundle["shared"], bundle["local"], bundle["instances"])
    bundle["paths"] = {name: str(path) for name, path in paths.items()}
    bundle["sha256"] = {name: sha256_file(path) for name, path in paths.items()}
    return bundle
