"""DeepSeek chat client and strict action decision parsing."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable

from .trace import utc_now


class DecisionError(ValueError):
    """Raised when model content cannot select a current legal action."""

    def __init__(
        self,
        message: str,
        api_records: list[dict[str, Any]] | None = None,
        raw_outputs: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.api_records = api_records or []
        self.raw_outputs = raw_outputs or []


class DeepSeekCallError(RuntimeError):
    def __init__(self, message: str, attempts: list[dict[str, Any]]) -> None:
        super().__init__(message)
        self.attempts = attempts


Transport = Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]


def _without_empty(value: Any):
    if isinstance(value, dict):
        compact = {}
        for key, child in value.items():
            child = _without_empty(child)
            if child not in (None, "", [], {}):
                compact[key] = child
        return compact
    if isinstance(value, list):
        return [child for item in value if (child := _without_empty(item)) not in (None, "", [], {})]
    return value


def compact_player_context(
    actors: dict[str, Any], legal_actions: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any], list[list[Any]]]:
    compact_actors: dict[str, Any] = {}
    observation_catalog: dict[str, Any] = {}
    observation_ids: dict[str, str] = {}
    for actor_type, actor_map in actors.items():
        for actor_id, actor in actor_map.items():
            actor_key = f"{actor_type}:{actor_id}"
            actor_copy = {
                key: value
                for key, value in actor.items()
                if key not in {"available_actions", "observations"}
            }
            observation_refs = {}
            for observation_name, observation in actor.get("observations", {}).items():
                observation = _without_empty(observation)
                if observation in (None, "", [], {}):
                    continue
                canonical = json.dumps(
                    observation, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                )
                observation_id = observation_ids.get(canonical)
                if observation_id is None:
                    observation_id = f"obs-{len(observation_catalog)}"
                    observation_ids[canonical] = observation_id
                    observation_catalog[observation_id] = observation
                observation_refs[observation_name] = observation_id
            if observation_refs:
                actor_copy["observation_refs"] = observation_refs
            actor_copy = _without_empty(actor_copy)
            if actor_copy:
                compact_actors[actor_key] = actor_copy
    compact_actions = [
        [
            action["action_id"],
            f"{action['actor_type']}:{action['actor_id']}",
            action["action_name"],
        ]
        for action in legal_actions
    ]
    return compact_actors, observation_catalog, compact_actions


def parse_decision(content: str, legal_actions: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(content, str) or not content.strip():
        raise DecisionError("model content is empty")
    try:
        decision = json.loads(content)
    except json.JSONDecodeError as error:
        raise DecisionError(f"model content is not valid JSON: {error.msg}") from error
    if not isinstance(decision, dict):
        raise DecisionError("model content must be a JSON object")
    action_id = decision.get("action_id")
    reason = decision.get("reason")
    if isinstance(action_id, bool) or not isinstance(action_id, int):
        raise DecisionError("action_id must be an integer")
    valid_ids = {action["action_id"] for action in legal_actions}
    if action_id not in valid_ids:
        raise DecisionError(f"action_id {action_id} is not currently legal")
    if not isinstance(reason, str) or not reason.strip():
        raise DecisionError("reason must be a non-empty string")
    parsed = {"action_id": action_id, "reason": reason.strip()}
    for optional in ("expected_effect", "chat"):
        if optional in decision:
            parsed[optional] = decision[optional]
    return parsed


def build_messages(
    system_prompt: str,
    task_rules: str,
    context: dict[str, Any],
) -> list[dict[str, str]]:
    actors, observation_catalog, legal_actions = compact_player_context(
        context["actors"], context["legal_actions"]
    )
    user_content = {
        "task_rules": task_rules,
        "game_turn": context["game_turn"],
        "env_step": context["env_step"],
        "task_metrics": context["task_metrics"],
        "actors": actors,
        "observation_catalog": observation_catalog,
        "legal_actions": legal_actions,
        "recent_history": context.get("recent_history", []),
        "resource_context": context["resource_context"],
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_content, ensure_ascii=False)},
    ]


def _urllib_transport(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        retryable = error.code == 429 or error.code >= 500
        raise DeepSeekCallError(
            f"DeepSeek HTTP {error.code}: {body[:500]}",
            [{"retryable": retryable, "status_code": error.code}],
        ) from error


class DeepSeekClient:
    def __init__(
        self,
        model_config: dict[str, Any],
        api_config: dict[str, Any],
        transport: Transport | None = None,
        api_key: str | None = None,
    ) -> None:
        key_name = model_config["api_key_env"]
        self.api_key = api_key or os.environ.get(key_name)
        if not self.api_key:
            raise DeepSeekCallError(f"environment variable {key_name} is not set", [])
        self.model_config = model_config
        self.api_config = api_config
        self.transport = transport or _urllib_transport

    def _payload(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "model": self.model_config["request_model"],
            "messages": messages,
            "thinking": {"type": self.model_config["thinking"]},
            "reasoning_effort": self.model_config["reasoning_effort"],
            "top_p": self.model_config["top_p"],
            "max_tokens": self.model_config["max_tokens"],
            "response_format": {"type": "json_object"},
        }

    def complete(
        self,
        messages: list[dict[str, str]],
        decision_id: str,
        purpose: str,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        url = self.model_config["api_base_url"].rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = self._payload(messages)
        attempts: list[dict[str, Any]] = []
        max_attempts = self.api_config["max_network_retries"] + 1

        for attempt_number in range(1, max_attempts + 1):
            call_id = str(uuid.uuid4())
            started = time.perf_counter()
            record = {
                "call_id": call_id,
                "decision_id": decision_id,
                "purpose": purpose,
                "attempt_number": attempt_number,
                "requested_at": utc_now(),
                "request_model": payload["model"],
                "request_payload": payload,
            }
            try:
                response = self.transport(
                    url,
                    headers,
                    payload,
                    self.api_config["request_timeout_seconds"],
                )
                message = response["choices"][0]["message"]
                record.update(
                    {
                        "status": "success",
                        "latency_seconds": time.perf_counter() - started,
                        "response_model": response.get("model"),
                        "finish_reason": response["choices"][0].get("finish_reason"),
                        "content": message.get("content"),
                        "usage": response.get("usage"),
                        "usage_unknown": response.get("usage") is None,
                    }
                )
                attempts.append(record)
                return response, attempts
            except Exception as error:
                retryable = True
                if isinstance(error, DeepSeekCallError) and error.attempts:
                    retryable = bool(error.attempts[0].get("retryable", False))
                record.update(
                    {
                        "status": "error",
                        "latency_seconds": time.perf_counter() - started,
                        "error_type": type(error).__name__,
                        "error": str(error),
                        "retryable": retryable,
                    }
                )
                attempts.append(record)
                if not retryable or attempt_number == max_attempts:
                    raise DeepSeekCallError("DeepSeek request failed", attempts) from error
                time.sleep(min(attempt_number, 2))
        raise AssertionError("unreachable")


class BaselineAgent:
    def __init__(
        self,
        client: DeepSeekClient,
        system_prompt: str,
        correction_prompt: str,
        max_corrections: int,
    ) -> None:
        self.client = client
        self.system_prompt = system_prompt
        self.correction_prompt = correction_prompt
        self.max_corrections = max_corrections

    @classmethod
    def from_bundle(cls, bundle: dict[str, Any], repo_root: Path, transport=None):
        agent_config = bundle["shared"]["agent"]
        system_prompt = (repo_root / agent_config["prompt_path"]).read_text(encoding="utf-8")
        correction_prompt = (repo_root / agent_config["correction_prompt_path"]).read_text(encoding="utf-8")
        client = DeepSeekClient(
            bundle["shared"]["model"], bundle["shared"]["api"], transport=transport
        )
        return cls(
            client,
            system_prompt,
            correction_prompt,
            agent_config["max_output_corrections_per_decision"],
        )

    def decide(
        self,
        task_rules: str,
        context: dict[str, Any],
        decision_id: str,
    ) -> dict[str, Any]:
        messages = build_messages(self.system_prompt, task_rules, context)
        api_records: list[dict[str, Any]] = []
        raw_outputs: list[str] = []

        for correction_number in range(self.max_corrections + 1):
            purpose = "decision" if correction_number == 0 else "correction"
            try:
                response, attempts = self.client.complete(messages, decision_id, purpose)
            except DeepSeekCallError as error:
                error.attempts = api_records + error.attempts
                raise
            api_records.extend(attempts)
            content = response["choices"][0]["message"].get("content") or ""
            raw_outputs.append(content)
            try:
                parsed = parse_decision(content, context["legal_actions"])
                return {
                    "decision": parsed,
                    "api_records": api_records,
                    "raw_outputs": raw_outputs,
                    "correction_count": correction_number,
                    "messages": messages,
                }
            except DecisionError as error:
                if correction_number == self.max_corrections:
                    raise DecisionError(str(error), api_records, raw_outputs) from error
                valid_ids = [action["action_id"] for action in context["legal_actions"]]
                messages = messages + [
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": self.correction_prompt
                        + "\n错误："
                        + str(error)
                        + "\n当前合法 action_id："
                        + json.dumps(valid_ids),
                    },
                ]
        raise AssertionError("unreachable")
