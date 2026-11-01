import csv
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from civrealm_agent_study.batch import run_batch
from civrealm_agent_study.config import load_config_bundle


REPO_ROOT = Path(__file__).resolve().parents[1]


def result_for(task_type, instance_id, attempt_number, stop_reason="native_success"):
    return {
        "run_id": f"run-{instance_id}-{attempt_number}",
        "episode_id": f"{task_type}_normal_{instance_id}_attempt-{attempt_number}",
        "task_type": task_type,
        "difficulty": "normal",
        "instance_id": instance_id,
        "attempt_number": attempt_number,
        "success": stop_reason == "native_success",
        "stop_reason": stop_reason,
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        "estimated_cost_usd": {"off_peak": 0.1, "peak": 0.2},
        "response_models": ["test-model"],
        "result_dir": f"result-{instance_id}-{attempt_number}",
    }


class BatchTests(unittest.TestCase):
    def make_bundle(self, run_root):
        bundle = deepcopy(load_config_bundle(REPO_ROOT))
        bundle["local"]["runtime"]["run_root"] = run_root
        return bundle

    def test_resume_skips_completed_instances(self):
        with TemporaryDirectory() as temporary_directory:
            bundle = self.make_bundle(temporary_directory)
            calls = []

            def fake_runner(bundle, repo_root, task_type, instance_id, **kwargs):
                calls.append((instance_id, kwargs["attempt_number"]))
                return result_for(task_type, instance_id, kwargs["attempt_number"])

            status = run_batch(
                bundle,
                REPO_ROOT,
                "battle_ancient_era",
                limit=2,
                episode_runner=fake_runner,
            )
            self.assertEqual(status["completed"], 2)
            self.assertEqual(len(calls), 2)

            resumed = run_batch(
                bundle,
                REPO_ROOT,
                "battle_ancient_era",
                resume_batch_id=status["batch_id"],
                episode_runner=fake_runner,
            )
            self.assertEqual(resumed["state"], "completed")
            self.assertEqual(len(calls), 2)

            batch_dir = Path(temporary_directory, "batches", status["batch_id"])
            with (batch_dir / "episode_results.csv").open(encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(json.loads((batch_dir / "batch_status.json").read_text())["remaining"], 0)

    def test_infrastructure_error_gets_next_attempt_on_resume(self):
        with TemporaryDirectory() as temporary_directory:
            bundle = self.make_bundle(temporary_directory)

            def failing_runner(bundle, repo_root, task_type, instance_id, **kwargs):
                return result_for(
                    task_type, instance_id, kwargs["attempt_number"], "infrastructure_error"
                )

            paused = run_batch(
                bundle,
                REPO_ROOT,
                "battle_defend_city",
                limit=1,
                episode_runner=failing_runner,
            )
            self.assertEqual(paused["state"], "paused_infrastructure_error")

            attempts = []

            def successful_runner(bundle, repo_root, task_type, instance_id, **kwargs):
                attempts.append(kwargs["attempt_number"])
                return result_for(task_type, instance_id, kwargs["attempt_number"])

            completed = run_batch(
                bundle,
                REPO_ROOT,
                "battle_defend_city",
                resume_batch_id=paused["batch_id"],
                episode_runner=successful_runner,
            )
            self.assertEqual(completed["state"], "completed")
            self.assertEqual(attempts, [2])
            self.assertEqual(completed["attempts"], 2)


if __name__ == "__main__":
    unittest.main()
