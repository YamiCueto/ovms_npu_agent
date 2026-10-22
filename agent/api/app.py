"""Local single-worker HTTP adapter. Agent business logic stays in core."""
import asyncio
import csv
import io
import json
import os
import sys
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.request import urlopen

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from agent.core.config import DEVICE, InferenceMode
from agent.core.model_client import OVMSClient
from agent.core.orchestrator import Orchestrator
from agent.core.telemetry import Telemetry
from agent.core.telemetry import RunTrace
from agent.core.tool_registry import ToolRegistry
from agent.core.benchmark import CASES, validate, summarize
from agent.main import _make_initial_history
from agent.mcp.manager import MCPManager


class RunInput(BaseModel):
    session_id: str
    text: str = Field(min_length=1, max_length=8000)
    mode: InferenceMode = InferenceMode.NORMAL


class BenchmarkInput(BaseModel):
    repetitions: int = Field(default=3, ge=1, le=100)


class State:
    def __init__(self, client=None, telemetry=None):
        self.client = client or OVMSClient()
        self.telemetry = telemetry or Telemetry()
        self.registry = ToolRegistry()
        self.mcp = MCPManager(self.registry)
        self.gate = threading.Lock()
        self.sessions = {}
        self.runs = {}
        self.jobs = {}
        self.tasks = set()
        # Commands are administrator-provided local configuration, never HTTP input.
        self.servers = {'demo': [sys.executable, str(Path(__file__).resolve().parents[1] / 'mcp/demo_server.py')]}
        config = os.getenv('AGENT_MCP_CONFIG')
        if config:
            self.servers.update(json.loads(Path(config).read_text(encoding='utf-8')))

    def reserve(self):
        if not self.gate.acquire(blocking=False):
            raise HTTPException(409, 'Modelo ocupado; espera a que termine la ejecucion actual')

    def allocate(self, mode, text):
        if len(self.runs) >= 500:
            oldest = next(iter(self.runs))
            del self.runs[oldest]
        rid = str(uuid.uuid4())
        run = {'run_id': rid, 'mode': mode.value, 'query': text, 'events': [], 'done': False, 'trace': None}
        self.runs[rid] = run
        return run

    def execute(self, run, history):
        orch = Orchestrator(self.client, self.registry, self.telemetry, InferenceMode(run['mode']))
        def emit(event):
            event['seq'] = len(run['events']) + 1
            run['events'].append(event)
        try:
            messages, _ = orch.run_turn(history, run['query'], emit, run['run_id'])
            if orch.last_trace.success:
                history[:] = messages
        except Exception as exc:
            if not hasattr(orch, 'last_trace'):
                orch.last_trace = RunTrace(run_id=run['run_id'], model=self.client.model,
                                           device=DEVICE, mode=run['mode'], error=str(exc))
                self.telemetry.record(orch.last_trace)
                emit({'type': 'run_started', 'run_id': run['run_id'], 'elapsed_s': 0})
                emit({'type': 'run_failed', 'run_id': run['run_id'], 'elapsed_s': 0,
                      'trace': orch.last_trace.to_dict()})
        finally:
            run['trace'] = orch.last_trace.to_dict()
            run['done'] = True
        return orch.last_trace


def create_app(state=None):
    state = state or State()

    @asynccontextmanager
    async def lifespan(app):
        yield
        if state.tasks:
            await asyncio.gather(*state.tasks, return_exceptions=True)
        state.mcp.disconnect_all()

    app = FastAPI(title='NPU Agent Lab', version='3.0.0', lifespan=lifespan)
    app.state.lab = state
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost'])

    @app.middleware('http')
    async def local_origin(request, call_next):
        origin = request.headers.get('origin')
        if origin and origin not in ('http://127.0.0.1:8080', 'http://localhost:8080',
                                      'http://127.0.0.1:4200', 'http://localhost:4200'):
            return JSONResponse({'detail': 'Origen no autorizado'}, status_code=403)
        if request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse({'detail': 'Solicitud cross-site rechazada'}, status_code=403)
        if request.method in ('POST', 'PUT', 'PATCH') and not request.headers.get('content-type', '').startswith('application/json'):
            return JSONResponse({'detail': 'Se requiere application/json'}, status_code=415)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        return response

    def schedule(coro):
        task = asyncio.create_task(coro)
        state.tasks.add(task)
        task.add_done_callback(state.tasks.discard)

    @app.get('/api/status')
    def status():
        connected, available, error = False, False, None
        try:
            with urlopen(state.client.base_url + '/models', timeout=3) as response:
                data = json.load(response)
            connected = True
            available = any(m.get('id') == state.client.model for m in data.get('data', []))
        except Exception as exc:
            error = str(exc)[:300]
        return dict(connected=connected, model_available=available, model=state.client.model,
                    configured_device=DEVICE, busy=state.gate.locked(), error=error)

    @app.post('/api/sessions', status_code=201)
    def session():
        if len(state.sessions) >= 100:
            raise HTTPException(429, 'Limite de sesiones; elimina una sesion')
        sid = str(uuid.uuid4())
        state.sessions[sid] = _make_initial_history()
        return {'session_id': sid}

    @app.get('/api/sessions/{sid}')
    def history(sid: str):
        if sid not in state.sessions:
            raise HTTPException(404, 'Sesion desconocida')
        return {'messages': state.sessions[sid]}

    @app.delete('/api/sessions/{sid}')
    def reset(sid: str):
        state.reserve()
        try:
            state.sessions.pop(sid, None)
            return {'deleted': True}
        finally:
            state.gate.release()

    @app.post('/api/runs', status_code=202)
    async def start(body: RunInput):
        if body.session_id not in state.sessions:
            raise HTTPException(404, 'Sesion desconocida')
        if not body.text.strip():
            raise HTTPException(422, 'Consulta vacia')
        state.reserve()
        run = state.allocate(body.mode, body.text)
        async def worker():
            try:
                await asyncio.to_thread(state.execute, run, state.sessions[body.session_id])
            finally:
                state.gate.release()
        schedule(worker())
        return {'run_id': run['run_id']}

    @app.get('/api/runs')
    def runs():
        return [r['trace'] for r in list(state.runs.values()) if r['trace']]

    @app.get('/api/runs/{rid}')
    def run_detail(rid: str):
        if rid not in state.runs:
            raise HTTPException(404, 'Ejecucion no disponible')
        return state.runs[rid]

    @app.get('/api/runs/{rid}/events')
    async def events(rid: str, request: Request):
        if rid not in state.runs:
            raise HTTPException(404, 'Ejecucion no disponible')
        try:
            cursor = max(0, int(request.headers.get('last-event-id', '0')))
        except ValueError:
            raise HTTPException(400, 'Last-Event-ID invalido')
        run = state.runs[rid]
        async def stream():
            nonlocal cursor
            ticks = 0
            while True:
                for event in run['events'][cursor:]:
                    yield f"id: {event['seq']}\nevent: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                    cursor = event['seq']
                if run['done']:
                    break
                if await request.is_disconnected():
                    break
                ticks += 1
                if ticks % 50 == 0:
                    yield ': heartbeat\n\n'
                await asyncio.sleep(.1)
        return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    @app.get('/api/mcp')
    def mcp_list():
        return {'servers': [{'id': sid, 'connected': sid in state.mcp._clients,
                             'tools': state.mcp._tools.get(sid, [])} for sid in state.servers],
                'tools': state.registry.schemas()}

    @app.post('/api/mcp/{sid}/connect')
    def connect(sid: str):
        if sid not in state.servers:
            raise HTTPException(404, 'Servidor no autorizado en configuracion local')
        state.reserve()
        try:
            return {'tools': state.mcp.connect(sid, state.servers[sid])}
        except Exception as exc:
            raise HTTPException(400, str(exc))
        finally:
            state.gate.release()

    @app.delete('/api/mcp/{sid}')
    def disconnect(sid: str):
        state.reserve()
        try:
            state.mcp.disconnect(sid)
            return {'disconnected': True}
        finally:
            state.gate.release()

    @app.post('/api/benchmarks', status_code=202)
    async def benchmark(body: BenchmarkInput):
        state.reserve()
        jid = str(uuid.uuid4())
        job = {'id': jid, 'done': False, 'rows': [], 'summary': [], 'total': body.repetitions * len(CASES) * 2}
        state.jobs[jid] = job
        def work():
            try:
                for repeat in range(body.repetitions):
                    for case in CASES:
                        modes = ('normal', 'rapido') if repeat % 2 == 0 else ('rapido', 'normal')
                        for mode in modes:
                            run = state.allocate(InferenceMode(mode), case['query'])
                            job['active_run_id'] = run['run_id']
                            trace = state.execute(run, _make_initial_history())
                            job['rows'].append(dict(case=case['id'], repeat=repeat + 1, correct=validate(case, trace), **trace.to_dict()))
                job['summary'] = summarize(job['rows'])
            except Exception as exc:
                job['error'] = str(exc)
            finally:
                job['done'] = True
                state.gate.release()
        schedule(asyncio.to_thread(work))
        return {'id': jid}

    @app.get('/api/benchmarks/{jid}')
    def benchmark_result(jid: str):
        if jid not in state.jobs:
            raise HTTPException(404, 'Benchmark desconocido')
        return state.jobs[jid]

    @app.get('/api/benchmarks/{jid}/export')
    def export(jid: str, format: str = 'json'):
        job = benchmark_result(jid)
        if format == 'json':
            return Response(json.dumps(job, ensure_ascii=False), media_type='application/json', headers={'Content-Disposition': 'attachment; filename=benchmark.json'})
        if format != 'csv':
            raise HTTPException(422, 'Formato: json o csv')
        output = io.StringIO(newline='')
        fields = ['case', 'repeat', 'mode', 'correct', 'success', 'total_latency_s', 'total_hops', 'total_prompt_tokens', 'total_completion_tokens', 'final_answer', 'error']
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for row in job['rows']:
            # Prevent formula execution when opening CSV in spreadsheets.
            writer.writerow({k: "'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@', '\t', '\r')) else v for k, v in row.items()})
        return Response(output.getvalue(), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename=benchmark.csv'})

    dist = Path(__file__).resolve().parents[2] / 'web/dist/lab/browser'
    if dist.exists():
        app.mount('/', StaticFiles(directory=dist, html=True), name='web')
    return app


app = create_app()
