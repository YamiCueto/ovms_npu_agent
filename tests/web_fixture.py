"""Deterministic HTTP fixture for browser E2E; never used by agent.api launcher."""
import tempfile
import time
from pathlib import Path
from agent.api.app import State, create_app
from agent.core.telemetry import Telemetry
from tests.test_orchestrator import _make_chat_response as response, _tool_call as call


class FixtureClient:
    model = 'TEST FIXTURE - not NPU'
    base_url = 'http://127.0.0.1:1/v1'

    def chat(self, messages, **kwargs):
        time.sleep(.35)
        query = next(m['content'] for m in reversed(messages) if m['role']=='user')
        if 'lenta' in query:
            time.sleep(1)
        if 'timeout' in query:
            raise TimeoutError('OVMS timeout (test fixture)')
        if 'vacia' in query:
            return response('')
        if 'truncada' in query:
            return response('Parcial', finish_reason='length')
        if 'Multiplica' in query or 'multiplica' in query:
            if messages[-1]['role'] != 'tool':
                return response(None, [call('multiplicar',{'a':875,'b':43})], 'tool_calls')
            return response('37625')
        if 'Lee finanzas' in query:
            if messages[-1]['role'] != 'tool':
                return response(None,[call('leer_archivo',{'nombre':'finanzas_demo.md'})],'tool_calls')
            return response('4500000 COP')
        return response('hola')


temporary = tempfile.TemporaryDirectory(prefix='npu-e2e-')
app = create_app(State(FixtureClient(), Telemetry(Path(temporary.name))))
