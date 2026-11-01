from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from civrealm_agent_study.config import load_config_bundle
from civrealm_agent_study.runner import run_episode


REPO_ROOT = Path(__file__).resolve().parents[1]


def info(turn=1, success=-1):
    return {
        "turn": turn,
        "my_player_id": 0,
        "minitask": {"status": 0 if success == -1 else 1, "success": success},
        "llm_info": {
            "unit": {
                7: {
                    "available_actions": ["fortify"],
                    "observations": {"minimap": {}},
                }
            }
        },
    }


class FakeSession:
    port = 6300

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def reset(self, task_type, difficulty, instance_id):
        return {}, info()

    def step(self, action):
        return {}, 1.0, True, False, info(turn=2, success=1)


class FakeUnresolvedSession(FakeSession):
    def step(self, action):
        return {}, 0.0, False, False, info(turn=2, success=-1)


class FakeAgent:
    def decide(self, task_rules, context, decision_id):
        return {
            "decision": {"action_id": 0, "reason": "Hold position."},
            "api_records": [
                {
                    "call_id": "call-1",
                    "purpose": "decision",
                    "status": "success",
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                    },
                }
            ],
            "raw_outputs": ['{"action_id": 0, "reason": "Hold position."}'],
            "correction_count": 0,
            "messages": [],
        }


class RunnerTests(unittest.TestCase):
    def test_zero_max_env_steps_is_rejected(self):
        with TemporaryDirectory() as temporary_directory:
            bundle = load_config_bundle(REPO_ROOT)
            bundle = deepcopy(bundle)
            bundle["local"]["runtime"]["run_root"] = temporary_directory
            with self.assertRaisesRegex(ValueError, "max_env_steps must be positive"):
                run_episode(
                    bundle,
                    REPO_ROOT,
                    "battle_defend_city",
                    669,
                    max_env_steps=0,
                    agent=FakeAgent(),
                    session_factory=FakeSession,
                )

    def test_native_success_is_recorded(self):
        with TemporaryDirectory() as temporary_directory:
            bundle = load_config_bundle(REPO_ROOT)
            bundle = deepcopy(bundle)
            bundle["local"]["runtime"]["run_root"] = temporary_directory
            result = run_episode(
                bundle,
                REPO_ROOT,
                "battle_defend_city",
                669,
                agent=FakeAgent(),
                session_factory=FakeSession,
                batch_id="batch-test",
            )
            self.assertEqual(result["stop_reason"], "native_success")
            self.assertEqual(result["batch_id"], "batch-test")
            self.assertEqual(result["env_steps"], 1)
            self.assertEqual(result["api_calls_total"], 1)
            self.assertEqual(result["usage"]["total_tokens"], 15)
            self.assertAlmostEqual(
                result["estimated_cost_usd"]["off_peak"], 0.0000045
            )
            self.assertTrue(Path(result["result_dir"], "episode_result.json").is_file())

    def test_development_game_turn_limit_is_not_native_failure(self):
        with TemporaryDirectory() as temporary_directory:
            bundle = load_config_bundle(REPO_ROOT)
            bundle = deepcopy(bundle)
            bundle["local"]["runtime"]["run_root"] = temporary_directory
            result = run_episode(
                bundle,
                REPO_ROOT,
                "battle_defend_city",
                669,
                max_game_turns=1,
                agent=FakeAgent(),
                session_factory=FakeUnresolvedSession,
            )
            self.assertEqual(result["stop_reason"], "interrupted")
            self.assertEqual(result["stop_detail"], "development_game_turn_limit")
            self.assertFalse(result["success"])


if __name__ == "__main__":
    unittest.main()
