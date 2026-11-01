"""Focused failure-conservation tests; no server or paid calls."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from civstudy.agent import Agent
from civstudy.common import load_config, read_jsonl
from civstudy.runner import run_episode
from civstudy.env import action_menu


class FakeEnv:
    def __init__(self, success=False):
        self.unwrapped = SimpleNamespace(civ_controller=SimpleNamespace(player_ctrl=SimpleNamespace(my_player_id=0),unit_ctrl=SimpleNamespace(units={}),messages=[]))
        self.success = success
    def step(self, action):
        return {}, 0, self.success, False, info(1 if self.success else -1, 1 if self.success else 0)
    def close(self):
        pass


def info(success=-1, status=0):
    return {'turn':1,'minitask':{'status':status,'success':success,'mini_score':0,'mini_goal':1},'available_actions':{}}


def fake_client(contents):
    replies = [SimpleNamespace(model='model-test', usage=None,
                               choices=[SimpleNamespace(message=SimpleNamespace(content=c),finish_reason='stop')]) for c in contents]
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=None)))
    iterator = iter(replies)
    client.chat.completions.create = lambda **kwargs: next(iterator)
    return client


class RecordingTests(unittest.TestCase):
    def test_chat_uses_separate_communication_channel(self):
        native, menu = action_menu({'available_actions':{'player':{'message':{'chat':True}},'unit':{1:{'build_city':True}}}})
        self.assertEqual(native,[('unit',1,'build_city'),None])
        self.assertEqual(len(menu),2)

    def run_case(self, contents, success=False, max_steps=2):
        config = load_config(); config['max_env_steps'] = max_steps
        with tempfile.TemporaryDirectory() as name:
            with patch.dict('os.environ',{'DEEPSEEK_API_KEY':'test-only'}), \
                 patch('civstudy.agent.OpenAI', return_value=fake_client(contents)), \
                 patch('civstudy.runner.make_env',return_value=(FakeEnv(success),{},info())), \
                 patch('civstudy.runner.language_state',return_value={}):
                result = run_episode(config,'development_transport',580,0,Path(name))
            folder = Path(result['trace_path'])
            return result, read_jsonl(folder/'steps.jsonl'), read_jsonl(folder/'api_calls.jsonl')

    def test_protocol_failure_retains_both_requests_without_action(self):
        result, steps, calls = self.run_case(['[]','{"action_id":99,"reason":"x"}'])
        self.assertEqual(result['stop_reason'],'output_failure')
        self.assertEqual(result['env_steps'],0)
        self.assertEqual(result['api_calls_total'],2)
        self.assertEqual([c['purpose'] for c in calls],['decision','correction'])
        self.assertEqual(result['unknown_cost_calls'],2)
        self.assertTrue(steps[0]['messages'])
        self.assertEqual(steps[0]['execution_response'],'not_submitted')

    def test_native_success_does_not_require_score_threshold(self):
        result, steps, calls = self.run_case(['{"action_id":0,"reason":"end"}'],success=True)
        self.assertTrue(result['success'])
        self.assertEqual(result['mini_score'],0)
        self.assertEqual(result['stop_reason'],'native_success')
        self.assertEqual(result['env_steps'],1)

    def test_step_limit_preserves_native_unknown(self):
        result, steps, calls = self.run_case(['{"action_id":0,"reason":"end"}']*2)
        self.assertEqual(result['stop_reason'],'step_limit')
        self.assertEqual(result['native_player_status'],-1)
        self.assertFalse(result['success'])


if __name__ == '__main__':
    unittest.main()
