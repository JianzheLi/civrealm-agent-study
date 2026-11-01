"""OpenRouter wire-format and accounting helpers; no policy or hidden retries."""
import math
import os

BASE_URL = 'https://openrouter.ai/api/v1'


def api_key_name(config):
    if config.get('api_provider') == 'openrouter':
        if config['base_url'].rstrip('/') != BASE_URL:
            raise ValueError('OpenRouter config must use https://openrouter.ai/api/v1')
        return 'OPENROUTER_API_KEY'
    return 'DEEPSEEK_API_KEY'


def api_key(config):
    name = api_key_name(config)
    value = os.environ.get(name, '').strip()
    if not value:
        raise ValueError(f'{name} is absent; no request was started.')
    return value


def request_parameters(config):
    if config.get('api_provider') == 'openrouter':
        return {'extra_body': {'reasoning': {'effort': config['reasoning_effort']},
                               'provider': config.get('openrouter_provider', {'require_parameters': True}),
                               'usage': {'include': True}}}
    return {'reasoning_effort': config['reasoning_effort'],
            'extra_body': {'thinking': {'type': 'enabled'}}}


def reported_cost(usage):
    cost = (usage or {}).get('cost')
    if isinstance(cost, (int, float)) and not isinstance(cost, bool) and math.isfinite(cost) and cost >= 0:
        return cost, 'openrouter_reported'
    return None, 'unknown'


class OpenRouterResponseError(Exception):
    def __init__(self, body):
        super().__init__('OpenRouter returned an error or no completion choices')
        self.body, self.status_code = body, 200


def response_metadata(reply):
    """Retain billing even if a 200 response contains a provider error."""
    raw = reply.usage.model_dump() if getattr(reply, 'usage', None) else None
    usage = dict(raw) if raw is not None else None
    if usage is not None:
        cached = (usage.get('prompt_tokens_details') or {}).get('cached_tokens')
        total = usage.get('prompt_tokens')
        if cached is not None and total is not None and 0 <= cached <= total:
            usage.update(prompt_cache_hit_tokens=cached, prompt_cache_miss_tokens=total-cached)
    return {'response_id': getattr(reply, 'id', None),
            'provider': getattr(reply, 'provider', None),
            'actual_model': getattr(reply, 'model', None),
            'usage_raw': raw, 'usage': usage}


def check_response(reply):
    if getattr(reply, 'error', None):
        raise OpenRouterResponseError({'error': reply.error})
    if not getattr(reply, 'choices', None):
        raise OpenRouterResponseError({'error': {'code': 'missing_completion_choices'}})


def error_metadata(error):
    # Never persist error messages, raw bodies or authorization headers.
    body = getattr(error, 'body', None)
    details = body.get('error', body) if isinstance(body, dict) else {}
    details = details if isinstance(details, dict) else {}
    code = details.get('code')
    result = {}
    if isinstance(code, int) or code == 'missing_completion_choices':
        result['provider_error_code'] = code
    response = getattr(error, 'response', None)
    retry_after = response.headers.get('retry-after') if response is not None else None
    if retry_after is not None:
        try:
            seconds = float(retry_after)
            if math.isfinite(seconds) and seconds >= 0:
                result['retry_after_s'] = seconds
        except (TypeError, ValueError):
            pass
    return result
