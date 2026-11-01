"""Every actual request is journaled, including unusable final outputs."""
import json
import os
import time
from datetime import datetime, timezone
from openai import OpenAI
from .common import ROOT, append_json, now, plain


class OutputFailure(Exception):
    pass


def validate(content, action_count):
    obj = json.loads(content)
    index = obj['action_id']
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < action_count:
        raise ValueError('action_id must be an integer in the current menu')
    if not isinstance(obj.get('reason'), str):
        raise ValueError('reason must be a brief string')
    if obj.get('chat') and not isinstance(obj['chat'], str):
        raise ValueError('chat must be a string')
    if obj.get('chat', '').lstrip().startswith('/'):
        raise ValueError('chat must be plain text, not an administrative slash command')
    return obj


def cost_estimate(usage, config, started):
    if usage is None:
        return None, 'unknown'
    utc = datetime.fromtimestamp(started, timezone.utc)
    # Weekend is off-peak. Weekday public holidays use the conservative peak rate.
    peak = utc.weekday() < 5 and (1 <= utc.hour < 4 or 6 <= utc.hour < 10)
    rates = config['pricing']['peak' if peak else 'off_peak']
    required = ['prompt_tokens', 'completion_tokens', 'prompt_cache_hit_tokens']
    if any(usage.get(k) is None for k in required):
        return None, 'unknown'
    cached = usage['prompt_cache_hit_tokens']
    cost = ((usage['prompt_tokens'] - cached) * rates['input'] + cached * rates['cached_input'] +
            usage['completion_tokens'] * rates['output']) / 1e6
    return cost, 'weekday_peak_conservative_holidays' if peak else 'off_peak'


class Agent:
    def __init__(self, config, ledger, identity):
        self.config, self.ledger, self.identity = config, ledger, identity
        self.client = OpenAI(api_key=os.environ['DEEPSEEK_API_KEY'], base_url=config['base_url'],
                             timeout=config['request_timeout_s'], max_retries=0)
        self.system = (ROOT / 'prompts/baseline_v1.txt').read_text()
        self.calls = []

    def decide(self, context, menu_count, decision_id, record):
        messages = [{'role': 'system', 'content': self.system},
                    {'role': 'user', 'content': json.dumps(context, ensure_ascii=False)}]
        record['messages'] = plain(messages)
        record['api_calls'] = []
        for attempt in range(2):
            started = time.time()
            call = dict(self.identity, decision_id=decision_id, call_id=decision_id + f'-call{attempt}',
                        purpose='decision' if attempt == 0 else 'correction', started_at=now(),
                        request_model=self.config['model'], request_messages=plain(messages),
                        parameters={k: self.config[k] for k in ['max_tokens', 'reasoning_effort', 'top_p']},
                        content=None, usage=None, usage_unknown=True, cost_usd=None,
                        actual_model=None, finish_reason=None)
            try:
                reply = self.client.chat.completions.create(
                    model=self.config['model'], messages=messages, top_p=self.config['top_p'],
                    max_tokens=self.config['max_tokens'], reasoning_effort=self.config['reasoning_effort'],
                    response_format={'type': 'json_object'}, extra_body={'thinking': {'type': 'enabled'}})
                call.update(actual_model=reply.model, content=reply.choices[0].message.content or '',
                            finish_reason=reply.choices[0].finish_reason,
                            usage=reply.usage.model_dump() if reply.usage else None)
                call['usage_unknown'] = call['usage'] is None
                call['cost_usd'], call['price_period'] = cost_estimate(call['usage'], self.config, started)
            except BaseException as error:
                # Error response bodies and headers are intentionally not persisted.
                call.update(error_type=type(error).__name__, http_status=getattr(error, 'status_code', None))
                raise
            finally:
                call.update(latency_s=time.time() - started, ended_at=now())
                append_json(self.ledger, call)
                self.calls.append(call)
                record['api_calls'].append(call['call_id'])
            record['content'] = call['content']
            try:
                obj = validate(call['content'], menu_count)
                record['decision'] = obj
                return obj
            except (ValueError, KeyError, TypeError) as error:
                record.setdefault('output_errors', []).append({'call_id': call['call_id'], 'error': str(error)})
                messages += [{'role': 'assistant', 'content': call['content']},
                             {'role': 'user', 'content': f'Correct the final JSON: {error}. Use action_id 0..{menu_count-1}.'}]
        raise OutputFailure('Both final outputs unusable; no action submitted')
