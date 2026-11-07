"""No network: exercise HTTP/stream failures, redaction, and the shared stop gate."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from agent_lab.accounting import StopRun
from agent_lab.domain import Limits, Model, Pricing, Task, read_json
from agent_lab.telemetry import Recorder
from agent_lab.upstream_diagnostics import UpstreamFailure, describe_failure
from agent_lab.workflow_gateway import Gateway, forward_stream


SECRET = 'fixture-api-secret-123456789'


class Response:
    status = 200
    headers = {'x-request-id': 'fixture-request-id', 'Authorization': SECRET}

    def __init__(self, chunks):
        self.chunks = iter(chunks)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read1(self, size):
        chunk = next(self.chunks, b'')
        if isinstance(chunk, Exception):
            raise chunk
        return chunk


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.model = Model('fixture-openai', 'openai', 'fixture', Pricing('1', '2'), max_output_tokens=128)
        self.provider = SimpleNamespace(model=self.model, _api_key=SECRET)

    def http_error(self, code=429, body=None):
        if body is None:
            body = json.dumps({'error': {'type': 'requests', 'code': 'rate_limit_exceeded',
                'param': 'input', 'message': f'Blocked {SECRET}; Bearer other-token; https://host/?key=secret'},
                'authorization': SECRET, 'input': 'DO_NOT_SAVE_REQUEST'}).encode()
        return urllib.error.HTTPError('https://fixture.invalid/', code, 'failure',
            {'x-request-id': 'fixture-http-id', 'retry-after': '2', 'set-cookie': SECRET}, io.BytesIO(body))

    def fail_forward(self, *, error=None, response=None):
        opener = Mock()
        opener.open.side_effect = error
        if error is None:
            opener.open.return_value = response
        with patch('agent_lab.workflow_gateway.urllib.request.build_opener', return_value=opener):
            with self.assertRaises(UpstreamFailure) as caught:
                forward_stream(self.provider, {'model': 'fixture'}, None)
        self.assertEqual(opener.open.call_count, 1)
        self.assertNotIn(SECRET, json.dumps(caught.exception.diagnostic))
        return caught.exception.diagnostic

    def test_http_status_code_request_id_and_filtered_error_survive(self):
        diagnostic = self.fail_forward(error=self.http_error())
        self.assertEqual(diagnostic['http_status'], 429)
        self.assertEqual(diagnostic['failure_kind'], 'http')
        self.assertEqual(diagnostic['provider_error']['code'], 'rate_limit_exceeded')
        self.assertEqual(diagnostic['request_id'], 'fixture-http-id')
        self.assertEqual(diagnostic['retry_after'], '2')
        text = json.dumps(diagnostic)
        for forbidden in ('DO_NOT_SAVE_REQUEST', 'other-token', 'https://host', 'set-cookie'):
            self.assertNotIn(forbidden, text)

    def test_non_json_and_oversized_bodies_are_not_dumped(self):
        for body in (b'<html>PRIVATE_BODY</html>', b'PRIVATE_BODY' * 2000):
            with self.subTest(size=len(body)):
                diagnostic = self.fail_forward(error=self.http_error(502, body))
                self.assertEqual(diagnostic['http_status'], 502)
                self.assertNotIn('PRIVATE_BODY', json.dumps(diagnostic))
                self.assertNotIn('provider_error', diagnostic)

    def test_read_timeout_keeps_status_request_id_and_partial_byte_count(self):
        diagnostic = self.fail_forward(response=Response([b'PRIVATE_STREAM', TimeoutError()]))
        self.assertEqual(diagnostic['failure_kind'], 'timeout')
        self.assertEqual(diagnostic['stage'], 'read')
        self.assertEqual(diagnostic['received_bytes'], len(b'PRIVATE_STREAM'))
        self.assertEqual(diagnostic['http_status'], 200)
        self.assertEqual(diagnostic['request_id'], 'fixture-request-id')
        self.assertNotIn('PRIVATE_STREAM', json.dumps(diagnostic))

    def test_transport_failure_is_distinct_from_parsing(self):
        diagnostic = self.fail_forward(error=urllib.error.URLError(ConnectionResetError(10054, 'reset')))
        self.assertEqual(diagnostic['failure_kind'], 'transport')
        self.assertEqual(diagnostic['stage'], 'connect')
        self.assertEqual(diagnostic['transport_exception_type'], 'ConnectionResetError')

    def test_bad_sse_and_missing_terminal_preserve_parser_failure(self):
        for body in (b'data: {PRIVATE_INVALID_JSON}\n\n', b'data: {"type":"response.created"}\n\n'):
            diagnostic = self.fail_forward(response=Response([body]))
            self.assertEqual(diagnostic['failure_kind'], 'response_parse')
            self.assertEqual(diagnostic['stage'], 'parse')
            self.assertNotIn('PRIVATE_INVALID_JSON', json.dumps(diagnostic))

    def test_sse_provider_error_is_preserved_without_terminal_usage(self):
        event = {'type': 'error', 'error': {'code': 'invalid_encrypted_content', 'message': 'Invalid history'}}
        diagnostic = self.fail_forward(response=Response([('data: ' + json.dumps(event) + '\n\n').encode()]))
        self.assertEqual(diagnostic['failure_kind'], 'provider_error')
        self.assertEqual(diagnostic['provider_error']['code'], 'invalid_encrypted_content')

    def test_successful_stream_is_returned_unchanged(self):
        raw = {'id': 'fixture-response', 'usage': {'input_tokens': 5, 'output_tokens': 2}, 'output': []}
        body = ('data: ' + json.dumps({'type': 'response.completed', 'response': raw}) + '\n\ndata: [DONE]\n\n').encode()
        opener = Mock(); opener.open.return_value = Response([body])
        with patch('agent_lab.workflow_gateway.urllib.request.build_opener', return_value=opener):
            returned_body, returned_raw = forward_stream(self.provider, {'model': 'fixture'}, None)
        self.assertEqual(returned_body, body)
        self.assertEqual(returned_raw['usage'], raw['usage'])
        self.assertEqual(opener.open.call_count, 1)

    def test_arbitrary_exception_payload_is_not_logged(self):
        diagnostic = describe_failure(RuntimeError('PRIVATE_PROMPT ' + SECRET), 'usage', SECRET)
        self.assertEqual(diagnostic['exception_type'], 'RuntimeError')
        self.assertNotIn('PRIVATE_PROMPT', json.dumps(diagnostic))
        self.assertNotIn(SECRET, json.dumps(diagnostic))

    def gateway(self, directory):
        with patch('agent_lab.providers.require_credential', return_value=SECRET):
            gateway = Gateway(Task.load(ROOT / 'tickets/clamp-boundaries/task.json'), [self.model],
                              Limits(), directory, Recorder(directory), Mock(), Mock())
        gateway.closed = False
        gateway.turn, gateway.active_role, gateway.active_model_id = 'review', 'reviewer', self.model.id
        return gateway

    def test_diagnostic_saved_and_unknown_request_never_retried(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            gateway = self.gateway(directory)
            opener = Mock(); opener.open.side_effect = self.http_error()
            with patch('agent_lab.workflow_gateway.urllib.request.build_opener', return_value=opener):
                for _ in range(2):
                    with self.assertRaisesRegex(StopRun, 'usage_unknown'):
                        gateway.generation(self.model.id, 'responses', {'model': 'fixture'})
            self.assertEqual(opener.open.call_count, 1)
            self.assertEqual(gateway.ledger.summary()['unknown_calls'], 1)
            self.assertFalse(gateway.ledger.summary()['usage_complete'])
            diagnostic = read_json(directory / 'calls/001-error.json')
            self.assertEqual(diagnostic['http_status'], 429)
            self.assertEqual(diagnostic['primary_role'], 'reviewer')
            self.assertEqual(diagnostic['turn'], 'review')
            events = (directory / 'events.jsonl').read_text(encoding='utf-8')
            self.assertIn('upstream_error', events)
            self.assertIn('calls/001-error.json', events)
            self.assertNotIn(SECRET, events)
            self.assertNotIn(SECRET, json.dumps(diagnostic))

    def test_usage_failure_has_its_own_stage_and_provider_response_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary); gateway = self.gateway(directory)
            raw = {'id': 'fixture-response', 'usage': None,
                   'error': {'code': 'billing_limit', 'message': 'Blocked ' + SECRET}}
            with patch('agent_lab.workflow_gateway.forward_stream', return_value=(b'fixture', raw)) as forward:
                with self.assertRaisesRegex(StopRun, 'usage_unknown'):
                    gateway.generation(self.model.id, 'responses', {'model': 'fixture'})
            self.assertEqual(forward.call_count, 1)
            diagnostic = read_json(directory / 'calls/001-error.json')
            self.assertEqual(diagnostic['stage'], 'usage')
            self.assertEqual(diagnostic['failure_kind'], 'provider_error')
            self.assertEqual(diagnostic['response_id'], 'fixture-response')
            self.assertEqual(diagnostic['provider_error']['code'], 'billing_limit')
            self.assertEqual(diagnostic['received_bytes'], len(b'fixture'))
            self.assertNotIn(SECRET, json.dumps(diagnostic))


if __name__ == '__main__':
    unittest.main()
