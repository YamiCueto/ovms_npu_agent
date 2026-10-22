"""Deterministic benchmark cases shared by HTTP and command line."""
import math
import re

CASES = [
    {"id": "saludo", "query": "Di solo la palabra: hola", "expected": "hola", "tool": None},
    {"id": "producto", "query": "Multiplica 875 por 43 usando multiplicar.", "expected": "37625", "tool": "multiplicar", "args": {"a": 875, "b": 43}},
    {"id": "lectura", "query": "Lee finanzas_demo.md con leer_archivo y dime el ingreso mensual.", "expected": "4500000", "tool": "leer_archivo", "args": {"nombre": "finanzas_demo.md"}},
]

def percentile(values, p):
    """Linear interpolation at (n - 1) * p (Hyndman-Fan type 7)."""
    if not values:
        return None
    values = sorted(values)
    index = (len(values) - 1) * p
    lo, hi = math.floor(index), math.ceil(index)
    return values[lo] + (values[hi] - values[lo]) * (index - lo)

def validate(case, trace):
    import json
    tools = [t for h in trace.hops for t in h.tools]
    answer = trace.final_answer.lower().strip().rstrip('.!')
    if case['tool'] is None:
        return trace.success and answer == case['expected'] and not tools
    normalized = re.sub(r'(?<=\d)[.,\s](?=\d)', '', answer)
    correct_answer = case['expected'] in re.findall(r'\d+', normalized)
    correct_tool = False
    for tool in tools:
        try:
            correct_tool |= (tool['name'] == case['tool'] and not tool['error']
                             and json.loads(tool['arguments']) == case['args'])
        except (ValueError, TypeError):
            pass
    return trace.success and correct_answer and correct_tool

def summarize(rows):
    result = []
    for case in CASES:
        for mode in ('normal', 'rapido'):
            group = [r for r in rows if r['case'] == case['id'] and r['mode'] == mode]
            latencies = [r['total_latency_s'] for r in group]
            result.append(dict(case=case['id'], mode=mode, n=len(group),
                               p50=percentile(latencies, .5), p95=percentile(latencies, .95),
                               correct=sum(r['correct'] for r in group),
                               warning='Muestra insuficiente: menos de 20 repeticiones por caso y modo' if len(group) < 20 else None))
    return result
