"""v3 CLI benchmark using the same scenarios and validators as the web API."""
import argparse
import json
from pathlib import Path
from agent.core.benchmark import CASES, summarize, validate
from agent.core.config import InferenceMode
from agent.core.model_client import OVMSClient
from agent.core.orchestrator import Orchestrator
from agent.core.telemetry import Telemetry
from agent.core.tool_registry import ToolRegistry
from agent.main import _make_initial_history


def run(repetitions=3, output=Path('telemetry/benchmark-v3')):
    if not 1 <= repetitions <= 100:
        raise ValueError('Repeticiones: 1 a 100')
    telemetry = Telemetry(output)
    orch = Orchestrator(OVMSClient(), ToolRegistry(), telemetry)
    rows = []
    for repeat in range(repetitions):
        for case in CASES:
            for mode in (['normal','rapido'] if repeat % 2 == 0 else ['rapido','normal']):
                orch.mode = InferenceMode(mode)
                try:
                    orch.run_turn(_make_initial_history(), case['query'])
                except Exception as exc:
                    print(f'Error: {exc}')
                    if not hasattr(orch, 'last_trace'):
                        raise
                trace = orch.last_trace
                rows.append(dict(case=case['id'], repeat=repeat+1, correct=validate(case, trace), **trace.to_dict()))
                print(f"{case['id']} / {mode}: {trace.total_latency_s:.2f}s; correcta={rows[-1]['correct']}")
    result = {'rows': rows, 'summary': summarize(rows)}
    (output/'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Benchmark NPU Agent Lab v3')
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--output', type=Path, default=Path('telemetry/benchmark-v3'))
    args = parser.parse_args()
    run(args.runs, args.output)
