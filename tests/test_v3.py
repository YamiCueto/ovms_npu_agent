import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from agent.api.app import State, create_app
from agent.core.benchmark import CASES, percentile, validate
from agent.core.execution_lock import model_lock
from agent.core.orchestrator import Orchestrator
from agent.core.telemetry import Telemetry
from agent.core.tool_registry import ToolRegistry
from agent.mcp.client import MCPClient, MCPError
from agent.mcp.manager import MCPManager
from tests.test_orchestrator import _make_chat_response as response, _tool_call as call


class CoreV3Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tel = Telemetry(Path(self.tmp.name))
        self.client = MagicMock(model='test-v3', base_url='http://test')
        self.orch = Orchestrator(self.client, ToolRegistry(), self.tel)

    def test_empty_and_length_fail_without_executing_truncated_tools(self):
        for result, expected in [(response(''), 'empty_response'), (response('partial', [call('multiplicar', {'a': 2, 'b': 3})], 'length'), 'length')]:
            self.client.chat.return_value = result
            events = []
            self.orch.run_turn([], 'test', events.append)
            self.assertFalse(self.tel._last_trace.success)
            self.assertIn(expected, self.tel._last_trace.error)
            self.assertEqual(events[-1]['type'], 'run_failed')
            self.assertFalse(self.tel._last_trace.hops[0].tools)

    def test_multiple_tools_history_events_and_persistence(self):
        self.client.chat.side_effect = [response(None, [call('multiplicar', {'a': 2, 'b': 3}, 'a'), call('multiplicar', {'a': 4, 'b': 5}, 'b')], 'tool_calls'), response('6 y 20')]
        events = []
        history = [{'role': 'system', 'content': 'test'}]
        messages, _ = self.orch.run_turn(history, 'test', events.append)
        self.assertEqual(len(history), 1)
        self.assertEqual([m['tool_call_id'] for m in messages if m['role'] == 'tool'], ['a', 'b'])
        trace = self.tel._last_trace
        self.assertEqual(len(trace.hops[0].tools), 2)
        self.assertEqual(trace.hops[0].tool_latency_s, sum(t['latency_s'] for t in trace.hops[0].tools))
        self.assertEqual([e['type'] for e in events], ['run_started','hop_started','hop_completed','tool_started','tool_completed','tool_started','tool_completed','hop_started','hop_completed','run_completed'])
        persisted = json.loads((Path(self.tmp.name)/'runs.jsonl').read_text())
        self.assertEqual(len(persisted['hops'][0]['tools']), 2)

    def test_missing_usage_is_not_zero(self):
        result = response('ok'); del result['usage']
        self.client.chat.return_value = result
        self.orch.run_turn([], 'test')
        self.assertIsNone(self.tel._last_trace.to_dict()['tokens_per_second'])
        self.assertIsNone(self.tel._last_trace.total_prompt_tokens())

    def test_cross_process_lock_contract(self):
        with model_lock(self.client):
            with self.assertRaisesRegex(RuntimeError, 'ocupado'):
                with model_lock(self.client):
                    pass

    def test_percentiles_and_accuracy(self):
        self.assertEqual(percentile([1, 2], .95), 1.95)
        self.assertEqual(percentile([4, 1, 3, 2], .5), 2.5)
        self.client.chat.return_value = response('37625')
        self.orch.run_turn([], 'test')
        self.assertFalse(validate(CASES[1], self.tel._last_trace))
        self.client.chat.side_effect = [response(None, [call('multiplicar', {'a':875,'b':43})], 'tool_calls'), response('37.625')]
        self.orch.run_turn([], 'test')
        self.assertTrue(validate(CASES[1], self.tel._last_trace))


class ApiV3Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.model = MagicMock(model='test-api-v3', base_url='http://127.0.0.1:1/v1')
        self.model.chat.return_value = response('hola')
        self.state = State(self.model, Telemetry(Path(self.tmp.name)))
        self.http = TestClient(create_app(self.state), base_url='http://127.0.0.1')
        self.http.__enter__()
        self.addCleanup(self.http.__exit__, None, None, None)
        self.sid = self.http.post('/api/sessions', json={}).json()['session_id']

    def run_request(self, mode='normal', text='hola'):
        return self.http.post('/api/runs', json={'session_id': self.sid, 'text': text, 'mode': mode})

    def wait_run(self, rid):
        for _ in range(200):
            run = self.http.get('/api/runs/'+rid).json()
            if run['done']:
                return run
            time.sleep(.01)
        self.fail('Run did not finish')

    def test_modes_events_replay_and_reset(self):
        for mode in ['normal','rapido','automatico']:
            result = self.run_request(mode)
            self.assertEqual(result.status_code, 202)
            rid = result.json()['run_id']
            run = self.wait_run(rid)
            self.assertTrue(run['trace']['success'])
            stream = self.http.get('/api/runs/'+rid+'/events').text
            self.assertIn('event: hop_completed', stream)
            replay = self.http.get('/api/runs/'+rid+'/events', headers={'Last-Event-ID':'3'}).text
            self.assertNotIn('event: run_started', replay)
            self.assertIn('event: run_completed', replay)
        self.assertEqual(len(self.http.get('/api/sessions/'+self.sid).json()['messages']), 7)
        self.assertEqual(self.http.delete('/api/sessions/'+self.sid).status_code, 200)
        self.assertEqual(self.http.get('/api/sessions/'+self.sid).status_code, 404)

    def test_conflicts_and_events_before_completion(self):
        entered, release = threading.Event(), threading.Event()
        def slow(*args, **kwargs):
            entered.set(); release.wait(5); return response('hola')
        self.model.chat.side_effect = slow
        try:
            rid = self.run_request().json()['run_id']
            self.assertTrue(entered.wait(2))
            run = self.http.get('/api/runs/'+rid).json()
            self.assertFalse(run['done'])
            self.assertEqual(run['events'][-1]['type'], 'hop_started')
            self.assertEqual(self.run_request().status_code, 409)
            self.assertEqual(self.http.post('/api/benchmarks', json={}).status_code, 409)
            self.assertEqual(self.http.delete('/api/sessions/'+self.sid).status_code, 409)
            self.assertEqual(self.http.post('/api/mcp/demo/connect', json={}).status_code, 409)
        finally:
            release.set()
        self.wait_run(rid)

    def test_timeout_failure_retains_history(self):
        self.model.chat.side_effect = TimeoutError('OVMS timeout')
        run = self.wait_run(self.run_request().json()['run_id'])
        self.assertEqual(run['events'][-1]['type'], 'run_failed')
        self.assertIn('timeout', run['trace']['error'])
        self.assertEqual(len(self.state.sessions[self.sid]), 1)

    def test_origin_host_validation_and_unknown_server(self):
        self.assertEqual(self.http.post('/api/sessions', json={}, headers={'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(self.http.get('/api/status', headers={'Host':'evil.example'}).status_code,400)
        self.assertEqual(self.http.post('/api/sessions', content='{}').status_code,415)
        self.assertEqual(self.run_request(text=' ').status_code,422)
        self.assertEqual(self.run_request(mode='turbo').status_code,422)
        self.assertEqual(self.http.post('/api/mcp/arbitrary/connect', json={}).status_code,404)

    def test_benchmark_exports_and_semantic_failures(self):
        jid = self.http.post('/api/benchmarks',json={'repetitions':1}).json()['id']
        for _ in range(200):
            job = self.http.get('/api/benchmarks/'+jid).json()
            if job['done']: break
            time.sleep(.01)
        self.assertTrue(job['done'])
        self.assertEqual(len(job['rows']), 6)
        self.assertEqual(sum(r['correct'] for r in job['rows']), 2)
        self.assertTrue(all(s['warning'] for s in job['summary']))
        self.assertIn('final_answer', self.http.get('/api/benchmarks/'+jid+'/export?format=csv').text)
        self.assertEqual(self.http.get('/api/benchmarks/'+jid+'/export?format=json').json()['id'], jid)


class StdioV3Test(unittest.TestCase):
    def test_real_stdio_connect_call_disconnect(self):
        registry = ToolRegistry(); manager = MCPManager(registry)
        try:
            manager.connect('demo',[sys.executable,'-m','agent.mcp.demo_server'])
            result = registry.execute('mcp_ws_listar_archivos','{}')
            self.assertIn('finanzas_demo.md', str(result))
            denied = registry.execute('mcp_ws_leer_archivo', '{"nombre":"../../secret.md"}')
            self.assertIn('error', denied)
        finally:
            manager.disconnect_all()
        self.assertNotIn('mcp_ws_listar_archivos',registry.names())

    def test_timeout_kills_child(self):
        client = MCPClient([sys.executable,'-c','import time; time.sleep(10)'], timeout=.1)
        with self.assertRaisesRegex(MCPError,'Timeout'):
            client.start()
        self.assertIsNone(client._proc)
