"""Thin CivRealm adapter used by smoke checks and the future runner."""

from __future__ import annotations

from typing import Any


def summarize_reset_info(info: dict[str, Any]) -> dict[str, Any]:
    llm_info = info.get("llm_info", {})
    actors = {
        actor_type: {
            "count": len(actor_map),
            "ids": [int(actor_id) for actor_id in actor_map],
            "legal_action_counts": {
                str(actor_id): len(actor.get("available_actions", []))
                for actor_id, actor in actor_map.items()
            },
        }
        for actor_type, actor_map in llm_info.items()
    }
    return {
        "turn": info.get("turn"),
        "my_player_id": info.get("my_player_id"),
        "minitask": info.get("minitask"),
        "actors": actors,
    }


def ordered_legal_actions(info: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the current LLM action mapping without changing its order."""
    actions: list[dict[str, Any]] = []
    for actor_type, actor_map in info.get("llm_info", {}).items():
        for actor_id, actor in actor_map.items():
            for action_name in actor.get("available_actions", []):
                actions.append(
                    {
                        "action_id": len(actions),
                        "actor_type": actor_type,
                        "actor_id": int(actor_id),
                        "action_name": action_name,
                    }
                )
    return actions


def next_actor_context(
    info: dict[str, Any], planned_actor_keys: set[str]
) -> tuple[str | None, dict[str, Any], list[dict[str, Any]]]:
    """Return the first unplanned actor and only that actor's legal actions."""
    for actor_type, actor_map in info.get("llm_info", {}).items():
        for actor_id, actor in actor_map.items():
            actor_key = f"{actor_type}:{actor_id}"
            available_actions = actor.get("available_actions", [])
            if actor_key in planned_actor_keys or not available_actions:
                continue
            actors = {actor_type: {actor_id: actor}}
            legal_actions = [
                {
                    "action_id": action_id,
                    "actor_type": actor_type,
                    "actor_id": int(actor_id),
                    "action_name": action_name,
                }
                for action_id, action_name in enumerate(available_actions)
            ]
            return actor_key, actors, legal_actions
    return None, {}, []


class MinitaskSession:
    """Own one CivRealm environment and expose the shared action contract."""

    def __init__(self) -> None:
        import gymnasium
        import civrealm  # noqa: F401 - importing registers CivRealm environments
        from civrealm.envs.freeciv_wrapper import LLMWrapper

        self.env = LLMWrapper(gymnasium.make("civrealm/FreecivMinitask-v0"))

    def reset(self, task_type: str, difficulty: str, instance_id: int):
        observation, info = self.env.reset(
            minitask_pattern={
                "type": task_type,
                "level": difficulty,
                "id": instance_id,
            }
        )
        return observation, info

    def step(self, action: dict[str, Any] | None):
        native_action = None
        if action is not None:
            native_action = (
                action["actor_type"],
                action["actor_id"],
                action["action_name"],
            )
        return self.env.step(native_action)

    @property
    def port(self) -> int:
        return self.env.unwrapped.get_port()

    def close(self) -> None:
        self.env.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()


def probe_minitask(task_type: str, difficulty: str, instance_id: int) -> dict[str, Any]:
    with MinitaskSession() as session:
        _, info = session.reset(task_type, difficulty, instance_id)
        summary = summarize_reset_info(info)
        summary.update(
            {
                "task_type": task_type,
                "difficulty": difficulty,
                "instance_id": instance_id,
                "port": session.port,
            }
        )
        return summary
