import json
import unittest

from civrealm_agent_study.agent import (
    BaselineAgent,
    DecisionError,
    DeepSeekClient,
    build_messages,
    parse_decision,
)


MODEL = {
    "api_base_url": "https://api.deepseek.com",
    "api_key_env": "DEEPSEEK_API_KEY",
    "request_model": "deepseek-flash",
    "thinking": "enabled",
    "reasoning_effort": "high",
    "top_p": 1.0,
    "max_tokens": 8192,
}
API = {"request_timeout_seconds": 180, "max_network_retries": 1}
LEGAL = [{"action_id": 0, "actor_type": "unit", "actor_id": 7, "action_name": "fortify"}]


class AgentTests(unittest.TestCase):
    def test_parse_valid_decision(self):
        decision = parse_decision('{"action_id": 0, "reason": "Defend."}', LEGAL)
        self.assertEqual(decision["action_id"], 0)

    def test_parse_rejects_stale_action_id(self):
        with self.assertRaisesRegex(DecisionError, "not currently legal"):
            parse_decision('{"action_id": 9, "reason": "Move."}', LEGAL)

    def test_prompt_context_omits_empty_and_duplicate_actions(self):
        messages = build_messages(
            "system",
            "rules",
            {
                "game_turn": 1,
                "env_step": 0,
                "task_metrics": {},
                "actors": {
                    "unit": {
                        7: {
                            "name": "Leader 7",
                            "available_actions": ["fortify"],
                            "observations": {
                                "minimap": {"empty_tile": [], "current_tile": ["hills"]}
                            },
                        }
                    },
                    "city": {},
                },
                "legal_actions": LEGAL,
                "recent_history": [],
                "resource_context": {"remaining_env_steps": 2000},
            },
        )
        content = json.loads(messages[1]["content"])
        self.assertEqual(content["legal_actions"], [[0, "unit:7", "fortify"]])
        self.assertNotIn("available_actions", content["actors"]["unit:7"])
        observation_id = content["actors"]["unit:7"]["observation_refs"]["minimap"]
        self.assertNotIn(
            "empty_tile",
            content["observation_catalog"][observation_id],
        )

    def test_one_correction_can_recover(self):
        responses = iter(
            [
                {"model": "deepseek-flash", "choices": [{"message": {"content": ""}, "finish_reason": "stop"}], "usage": None},
                {"model": "deepseek-flash", "choices": [{"message": {"content": '{"action_id": 0, "reason": "Defend."}'}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
            ]
        )

        def fake_transport(url, headers, payload, timeout):
            return next(responses)

        client = DeepSeekClient(MODEL, API, transport=fake_transport, api_key="test-key")
        agent = BaselineAgent(client, "system", "correct", max_corrections=1)
        result = agent.decide(
            "defend",
            {
                "game_turn": 1,
                "env_step": 0,
                "task_metrics": {},
                "actors": {},
                "legal_actions": LEGAL,
                "recent_history": [],
                "resource_context": {"remaining_env_steps": 2000},
            },
            "decision-0",
        )
        self.assertEqual(result["decision"]["action_id"], 0)
        self.assertEqual(result["correction_count"], 1)
        self.assertEqual([record["purpose"] for record in result["api_records"]], ["decision", "correction"])


if __name__ == "__main__":
    unittest.main()
