from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from civrealm_agent_study.config import ConfigError, load_config_bundle, validate_config_bundle
from civrealm_agent_study.env import next_actor_context, ordered_legal_actions
from civrealm_agent_study.trace import EpisodeTrace


REPO_ROOT = Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    def test_repository_config_is_valid(self):
        bundle = load_config_bundle(REPO_ROOT)
        self.assertEqual(bundle["local"]["member"], "songluo")
        self.assertEqual(len(bundle["instances"]["tasks"]), 2)
        self.assertEqual(len(bundle["sha256"]["shared"]), 64)

    def test_duplicate_instance_id_is_rejected(self):
        bundle = load_config_bundle(REPO_ROOT)
        instances = bundle["instances"]
        selected = instances["tasks"]["battle_ancient_era"]["selected_ids"]
        selected[-1] = selected[0]
        with self.assertRaisesRegex(ConfigError, "duplicate"):
            validate_config_bundle(bundle["shared"], bundle["local"], instances)

    def test_legal_actions_keep_environment_order(self):
        info = {
            "llm_info": {
                "unit": {
                    7: {"available_actions": ["move_North", "fortify"]},
                    9: {"available_actions": ["move_East"]},
                }
            }
        }
        actions = ordered_legal_actions(info)
        self.assertEqual([action["action_id"] for action in actions], [0, 1, 2])
        self.assertEqual(actions[1]["action_name"], "fortify")
        self.assertEqual(actions[2]["actor_id"], 9)

    def test_next_actor_context_skips_already_planned_actor(self):
        info = {
            "llm_info": {
                "unit": {
                    7: {"available_actions": ["fortify"]},
                    9: {"available_actions": ["move_East"]},
                }
            }
        }
        actor_key, actors, actions = next_actor_context(info, {"unit:7"})
        self.assertEqual(actor_key, "unit:9")
        self.assertEqual(list(actors["unit"]), [9])
        self.assertEqual(actions[0]["action_id"], 0)

    def test_trace_creates_separate_step_and_api_ledgers(self):
        with TemporaryDirectory() as temporary_directory:
            trace = EpisodeTrace(Path(temporary_directory), "run", "episode")
            trace.write_manifest({"run_id": "run"})
            trace.append_step({"env_step": 0})
            trace.write_result({"stop_reason": "pipeline_smoke_complete"})
            self.assertTrue(trace.steps_path.is_file())
            self.assertEqual(trace.api_calls_path.read_text(encoding="utf-8"), "")
            self.assertTrue((trace.episode_dir / "episode_result.json").is_file())


if __name__ == "__main__":
    unittest.main()
