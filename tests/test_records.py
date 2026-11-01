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

    def test_history32_keeps_recent_actions_and_resets_between_episodes(self):
        config = load_config('configs/development_history32_output16k.json')
        config['max_env_steps'] = 35
        contents = [json.dumps({'action_id':0, 'reason':f'action-{i}'}) for i in range(35)]
        with tempfile.TemporaryDirectory() as name:
            with patch.dict('os.environ',{'DEEPSEEK_API_KEY':'test-only'}), \
                 patch('civstudy.agent.OpenAI', return_value=fake_client(contents)), \
                 patch('civstudy.runner.make_env',return_value=(FakeEnv(),{},info())), \
                 patch('civstudy.runner.language_state',return_value={'current_state_marker':'visible'}):
                result = run_episode(config,'development_transport',580,0,Path(name))
            steps = read_jsonl(Path(result['trace_path'])/'steps.jsonl')
            calls = read_jsonl(Path(result['trace_path'])/'api_calls.jsonl')
            self.assertEqual(result['env_steps'],35)
            self.assertEqual([len(s['context']['history']) for s in steps],
                             [min(i,32) for i in range(35)])
            # All 35 actions use the same fake game turn: the window counts actions.
            last = json.loads(calls[-1]['request_messages'][1]['content'])
            self.assertEqual([h['reason'] for h in last['history']],
                             [f'action-{i}' for i in range(2,34)])
            self.assertEqual(last['state'],{'current_state_marker':'visible'})
            self.assertEqual(last['legal_actions'],[{'id':0,'action_key':'END_TURN'}])
            self.assertTrue(all(set(h)=={'native_action','reason','before_metrics',
                'after_metrics','state_changes','turn','native_messages'} for h in last['history']))
            self.assertTrue(all(c['parameters']['max_tokens']==16384 for c in calls))
            config['max_env_steps'] = 1
            with patch.dict('os.environ',{'DEEPSEEK_API_KEY':'test-only'}), \
                 patch('civstudy.agent.OpenAI', return_value=fake_client(contents[:1])), \
                 patch('civstudy.runner.make_env',return_value=(FakeEnv(),{},info())), \
                 patch('civstudy.runner.language_state',return_value={}):
                next_result = run_episode(config,'development_transport',581,0,Path(name))
            next_calls = read_jsonl(Path(next_result['trace_path'])/'api_calls.jsonl')
            self.assertEqual(json.loads(next_calls[0]['request_messages'][1]['content'])['history'],[])

    def test_step_limit_preserves_native_unknown(self):
        result, steps, calls = self.run_case(['{"action_id":0,"reason":"end"}']*2)
        self.assertEqual(result['stop_reason'],'step_limit')
        self.assertEqual(result['native_player_status'],-1)
        self.assertFalse(result['success'])


if __name__ == '__main__':
    unittest.main()
