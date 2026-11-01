"""Provider integration through actual shared Agent and fake HTTP only."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import httpx2 as httpx
from openai import OpenAI
from civstudy import agent
from civstudy.common import ROOT, load_config, read_jsonl
from civstudy.openrouter import api_key, reported_cost, request_parameters, OpenRouterResponseError
from civstudy.runner import collect


class OpenRouterTests(unittest.TestCase):
    def config(self):
        return load_config(ROOT/'configs/development_openrouter.json')

    def test_request_correction_usage_and_credential_isolation(self):
        requests=[]
        def handle(request):
            body=json.loads(request.content); requests.append(body)
            self.assertEqual(str(request.url),'https://openrouter.ai/api/v1/chat/completions')
            self.assertEqual(request.headers['authorization'],'Bearer offline-openrouter')
            self.assertEqual(body['model'],'deepseek/deepseek-v4.1-flash-1017')
            self.assertEqual(body['reasoning'],{'effort':'high'})
            self.assertTrue(body['provider']['require_parameters'])
            self.assertNotIn('thinking',body)
            self.assertNotIn('reasoning_effort',body)
            self.assertEqual(body['max_tokens'],16384)
            self.assertEqual(body['response_format'],{'type':'json_object'})
            correction=len(requests)>1
            return httpx.Response(200,json={'id':f'gen-test-{len(requests)}','created':0,
                'object':'chat.completion','model':body['model'],'provider':'TestProvider',
                'choices':[{'index':0,'message':{'role':'assistant','content':json.dumps({'action_id':0,'reason':'test'}) if correction else ''},'finish_reason':'stop' if correction else 'length'}],
                'usage':{'prompt_tokens':100,'completion_tokens':10,'total_tokens':110,'cost':0.002,
                         'prompt_tokens_details':{'cached_tokens':25},'completion_tokens_details':{'reasoning_tokens':8}}})
        def client(**kwargs):
            self.assertEqual(kwargs['max_retries'],0)
            self.assertEqual(kwargs['timeout'],600)
            return OpenAI(**kwargs,http_client=httpx.Client(transport=httpx.MockTransport(handle)))
        with tempfile.TemporaryDirectory() as directory, patch.object(agent,'OpenAI',client), \
             patch.dict(os.environ,{'OPENROUTER_API_KEY':'offline-openrouter','DEEPSEEK_API_KEY':'offline-direct'}):
            ledger=Path(directory)/'api_calls.jsonl'
            instance=agent.Agent(self.config(),ledger,{'run_id':'offline-test'})
            try:
                decision=instance.decide({'test':True},1,'test-decision',{})
            finally:
                instance.client.close()
            self.assertEqual(decision['action_id'],0)
            calls=read_jsonl(ledger)
            self.assertEqual([c['purpose'] for c in calls],['decision','correction'])
            self.assertEqual(sum(c['cost_usd'] for c in calls),.004)
            self.assertTrue(all(c['price_period']=='openrouter_reported' for c in calls))
            self.assertEqual(calls[0]['usage']['prompt_cache_hit_tokens'],25)
            self.assertEqual(calls[0]['usage']['prompt_cache_miss_tokens'],75)
            self.assertNotIn('prompt_cache_hit_tokens',calls[0]['usage_raw'])
            self.assertEqual(calls[0]['provider'],'TestProvider')
            self.assertEqual(calls[0]['response_id'],'gen-test-1')
            self.assertEqual(len(requests[1]['messages']),4)
            self.assertNotIn('offline-openrouter',ledger.read_text())
            self.assertNotIn('offline-direct',ledger.read_text())

    def test_http_200_provider_error_retains_billing(self):
        def client(**kwargs):
            return OpenAI(**kwargs,http_client=httpx.Client(transport=httpx.MockTransport(
                lambda request:httpx.Response(200,json={'error':{'code':502,'message':'never log raw error'},
                    'usage':{'prompt_tokens':1,'completion_tokens':0,'total_tokens':1,'cost':0.001}}))))
        with tempfile.TemporaryDirectory() as directory, patch.object(agent,'OpenAI',client), \
             patch.dict(os.environ,{'OPENROUTER_API_KEY':'offline-openrouter'}):
            ledger=Path(directory)/'api_calls.jsonl'
            instance=agent.Agent(self.config(),ledger,{})
            try:
                with self.assertRaises(OpenRouterResponseError): instance.decide({},1,'error',{})
            finally:
                instance.client.close()
            call=read_jsonl(ledger)[0]
            self.assertEqual(call['http_status'],200)
            self.assertEqual(call['provider_error_code'],502)
            self.assertEqual(call['cost_usd'],.001)
            self.assertFalse(call['usage_unknown'])
            self.assertNotIn('never log raw error',ledger.read_text())

    def test_429_is_logged_once_with_retry_after_and_unknown_cost(self):
        attempts=[]
        def handle(request):
            attempts.append(1)
            return httpx.Response(429,headers={'retry-after':'30'},json={'error':{'code':429,'message':'do not log this body'}})
        def client(**kwargs):
            return OpenAI(**kwargs,http_client=httpx.Client(transport=httpx.MockTransport(handle)))
        with tempfile.TemporaryDirectory() as directory, patch.object(agent,'OpenAI',client), \
             patch.dict(os.environ,{'OPENROUTER_API_KEY':'offline-openrouter'}):
            ledger=Path(directory)/'api_calls.jsonl'; instance=agent.Agent(self.config(),ledger,{})
            try:
                with self.assertRaises(Exception): instance.decide({},1,'rate-limit',{})
            finally:
                instance.client.close()
            self.assertEqual(len(attempts),1)
            call=read_jsonl(ledger)[0]
            self.assertEqual(call['http_status'],429)
            self.assertEqual(call['retry_after_s'],30)
            self.assertIsNone(call['cost_usd'])
            self.assertNotIn('do not log this body',ledger.read_text())

    def test_missing_openrouter_key_fails_before_starting_scene(self):
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'offline-direct'},clear=True), \
             patch('civstudy.runner.run_episode') as run:
            with self.assertRaisesRegex(SystemExit,'OPENROUTER_API_KEY is absent'):
                collect('development_build_city',ROOT/'configs/development_openrouter.json',limit=5)
            run.assert_not_called()

    def test_direct_api_and_missing_cost_semantics(self):
        direct=load_config()
        self.assertEqual(request_parameters(direct),{'reasoning_effort':'high','extra_body':{'thinking':{'type':'enabled'}}})
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'offline-direct','OPENROUTER_API_KEY':'offline-openrouter'}):
            self.assertEqual(api_key(direct),'offline-direct')
        self.assertEqual(reported_cost({}),(None,'unknown'))
        self.assertEqual(reported_cost({'cost':0}),(0,'openrouter_reported'))
        config=self.config(); config['base_url']='https://example.invalid'
        with self.assertRaises(ValueError): api_key(config)


if __name__=='__main__': unittest.main()
