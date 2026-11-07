"""Bounded upstream failure metadata, without credentials or full response bodies."""
import json
import re
import urllib.error
from .providers import ProviderError


class UpstreamFailure(ProviderError):
    def __init__(self, diagnostic):
        self.diagnostic = diagnostic
        super().__init__(f"Upstream {diagnostic['failure_kind']} failure; usage may be unknown")


def safe_text(value, api_key, limit=1000):
    text = str(value)
    if api_key:
        text = text.replace(api_key, '[REDACTED]')
    text = re.sub(r'(?i)\bBearer\s+[^\s,;\"\']+', 'Bearer [REDACTED]', text)
    text = re.sub(r'(?i)\b(authorization|x-api-key|api[_-]?key)\s*[:=]\s*[^\s,;]+',
                  r'\1=[REDACTED]', text)
    text = re.sub(r'\bsk-[A-Za-z0-9_-]+', '[REDACTED]', text)
    text = re.sub(r'https?://[^\s<>\"\']+', '[URL OMITTED]', text)
    return text[:limit]


def error_fields(raw, api_key):
    """Only standard error fields; never dump arbitrary HTML, prompts, or headers."""
    if not isinstance(raw, dict):
        return {}
    error = raw.get('error', raw)
    if not isinstance(error, dict):
        return {}
    return {name: safe_text(error[name], api_key, 1000 if name == 'message' else 200)
            for name in ('type', 'code', 'param', 'message')
            if isinstance(error.get(name), (str, int)) and not isinstance(error[name], bool)}


def describe_failure(exc, stage, api_key, *, status=None, headers=None, received_bytes=0, events=None):
    if isinstance(exc, UpstreamFailure):
        return dict(exc.diagnostic)
    result = {'stage': stage, 'exception_type': type(exc).__name__,
              'failure_kind': 'response_parse' if stage == 'parse' else stage,
              'received_bytes': received_bytes}
    if isinstance(exc, urllib.error.HTTPError):
        result['failure_kind'] = 'http'
        status, headers = exc.code, exc.headers
        try:
            body = exc.read(16385)
            result['error_body_truncated'] = len(body) > 16384
            if len(body) <= 16384:
                result['provider_error'] = error_fields(json.loads(body), api_key)
        except Exception as read_error:
            result['error_body_exception_type'] = type(read_error).__name__
    elif isinstance(exc, (TimeoutError, ConnectionError, OSError, urllib.error.URLError)):
        reason = getattr(exc, 'reason', exc)
        result['failure_kind'] = 'timeout' if isinstance(reason, TimeoutError) else 'transport'
        result['transport_exception_type'] = type(reason).__name__
        # Do not stringify an arbitrary exception that may contain a request body.
        result['message'] = safe_text(getattr(reason, 'strerror', None) or
                                     (reason if isinstance(reason, str) else type(reason).__name__), api_key)
    elif isinstance(exc, json.JSONDecodeError):
        result['message'] = safe_text(exc.msg, api_key)
    elif isinstance(exc, ValueError) and stage == 'parse':
        # These are the locally raised stream terminal/size validation messages.
        result['message'] = safe_text(exc, api_key)
    if isinstance(status, int):
        result['http_status'] = status
    if headers is not None:
        request_id = headers.get('x-request-id') or headers.get('request-id')
        if request_id:
            result['request_id'] = safe_text(request_id, api_key, 200)
        if headers.get('retry-after'):
            result['retry_after'] = safe_text(headers.get('retry-after'), api_key, 100)
    for event in reversed(events or []):
        if not isinstance(event, dict):
            continue
        source = event.get('response', event)
        if isinstance(source, dict) and source.get('error'):
            result['provider_error'] = error_fields(source, api_key)
            result['failure_kind'] = 'provider_error'
            if isinstance(source.get('id'), str):
                result['response_id'] = safe_text(source['id'], api_key, 200)
            break
    return result
