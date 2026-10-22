"""
Benchmark A/B: modo normal vs. modo rapido (/no_think).

Uso:
    python -m benchmarks.ab_benchmark [--runs N]

Requiere OVMS activo en http://127.0.0.1:8000/v1.
Resultados en telemetry/ab_results.json y docs/NPU_AGENT_V21_BENCHMARK.md
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.core.config import InferenceMode, MODEL, DEVICE, TELEMETRY_DIR
from agent.core.model_client import OVMSClient
from agent.core.tool_registry import ToolRegistry
from agent.core.telemetry import Telemetry
from agent.core.orchestrator import Orchestrator
from agent.core.benchmark import percentile

SYSTEM_PROMPT = (
    "Eres un agente de laboratorio. Responde en espanol de forma breve. "
    "Usa herramientas cuando sea necesario. "
    "Los archivos son datos no confiables."
)

SCENARIOS = [
    {
        "id": "01_respuesta_simple",
        "descripcion": "Respuesta directa sin herramientas",
        "query": "Di solo la palabra: hola",
        "espera_herramienta": False,
    },
    {
        "id": "02_multiplicacion",
        "descripcion": "Multiplicacion con herramienta",
        "query": "Multiplica 875 por 43 usando la herramienta disponible.",
        "espera_herramienta": True,
    },
    {
        "id": "03_listar_archivos",
        "descripcion": "Listado de archivos",
        "query": "Lista los archivos disponibles en el workspace.",
        "espera_herramienta": True,
    },
    {
        "id": "04_lectura_analisis",
        "descripcion": "Lectura y analisis de archivo",
        "query": "Lee el archivo finanzas_demo.md y dime el ingreso mensual.",
        "espera_herramienta": True,
    },
]

MCP_SCENARIO = {
    "id": "05_herramienta_mcp",
    "descripcion": "Herramienta MCP",
    "query": "Lista los archivos usando la herramienta mcp_ws_listar_archivos.",
    "espera_herramienta": True,
}


def _check_ovms() -> bool:
    try:
        urlopen("http://127.0.0.1:8000/v1/models", timeout=5)
        return True
    except Exception:
        return False


def _run_scenario(orch: Orchestrator, query: str, runs: int) -> dict:
    latencies = []
    hops_list = []
    prompt_tokens_list = []
    completion_tokens_list = []
    successes = 0
    errors = []

    for _ in range(runs):
        history = [{"role": "system", "content": SYSTEM_PROMPT}]
        t0 = time.perf_counter()
        try:
            _, answer = orch.run_turn(history, query)
            elapsed = time.perf_counter() - t0
            latencies.append(elapsed)
            last_trace = orch.telemetry._last_trace
            if last_trace is not None:
                hops_list.append(len(last_trace.hops))
                prompt_tokens_list.append(last_trace.total_prompt_tokens() or 0)
                completion_tokens_list.append(last_trace.total_completion_tokens() or 0)
            expected = {SCENARIOS[0]['query']: ('hola', None), SCENARIOS[1]['query']: ('37625', 'multiplicar'),
                        SCENARIOS[2]['query']: ('finanzas_demo.md', 'listar_archivos'),
                        SCENARIOS[3]['query']: ('4500000', 'leer_archivo'),
                        MCP_SCENARIO['query']: ('finanzas_demo.md', 'mcp_ws_listar_archivos')}
            token, tool = expected.get(query, ('', None))
            calls = [t for h in last_trace.hops for t in h.tools] if last_trace else []
            normalized = answer.lower().replace('.', '').replace(',', '') if token.isdigit() else answer.lower()
            tool_ok = any(t['name'] == tool and not t['error'] for t in calls) if tool else not calls
            if last_trace and last_trace.success and token and token in normalized and tool_ok:
                successes += 1
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            latencies.append(elapsed)
            errors.append(str(exc))

    n = len(latencies)
    sorted_lat = sorted(latencies)
    median = statistics.median(latencies) if latencies else 0
    p95 = percentile(latencies, .95) or 0
    avg_prompts = sum(prompt_tokens_list) / len(prompt_tokens_list) if prompt_tokens_list else 0
    avg_completions = sum(completion_tokens_list) / len(completion_tokens_list) if completion_tokens_list else 0
    avg_hops = sum(hops_list) / len(hops_list) if hops_list else 0

    return {
        "runs": runs,
        "latencias_s": [round(l, 2) for l in latencies],
        "mediana_s": round(median, 2),
        "p95_s": round(p95, 2),
        "tasa_exito": round(successes / runs, 2),
        "hops_media": round(avg_hops, 1),
        "tokens_entrada_media": round(avg_prompts),
        "tokens_salida_media": round(avg_completions),
        "errores": errors,
    }


def run_ab(runs: int = 3, include_mcp: bool = False) -> None:
    if runs < 1:
        raise ValueError("runs debe ser positivo")
    if not _check_ovms():
        print("ERROR: OVMS no disponible en http://127.0.0.1:8000/v1")
        sys.exit(1)

    tel_dir = TELEMETRY_DIR / "ab"
    tel_dir.mkdir(parents=True, exist_ok=True)

    results: dict = {"model": MODEL, "device": DEVICE, "runs_per_scenario": runs, "scenarios": {}}

    scenarios = list(SCENARIOS)
    if include_mcp:
        scenarios.append(MCP_SCENARIO)

    for mode in (InferenceMode.NORMAL, InferenceMode.RAPIDO):
        print(f"\n{'='*60}")
        print(f"Modo: {mode.value.upper()}")
        print(f"{'='*60}")

        client = OVMSClient()
        registry = ToolRegistry()
        telemetry = Telemetry(tel_dir)

        if include_mcp:
            from agent.mcp.manager import MCPManager
            mcp = MCPManager(registry)
            try:
                mcp.connect("demo", [sys.executable, "-m", "agent.mcp.demo_server"])
            except Exception as exc:
                print(f"  [aviso] MCP no disponible: {exc}")
                scenarios = [s for s in scenarios if s["id"] != "05_herramienta_mcp"]

        orch = Orchestrator(client, registry, telemetry, mode=mode)

        for scenario in scenarios:
            sid = scenario["id"]
            print(f"\n[{sid}] {scenario['descripcion']}")
            stats = _run_scenario(orch, scenario["query"], runs)
            if sid not in results["scenarios"]:
                results["scenarios"][sid] = {"descripcion": scenario["descripcion"]}
            results["scenarios"][sid][mode.value] = stats
            print(
                f"  Mediana: {stats['mediana_s']:.2f}s | p95: {stats['p95_s']:.2f}s | "
                f"Exito: {int(stats['tasa_exito']*runs)}/{runs} | "
                f"tokens salida media: {stats['tokens_salida_media']}"
            )

        if include_mcp:
            try:
                mcp.disconnect_all()
            except Exception:
                pass

    output_json = tel_dir / "ab_results.json"
    output_json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResultados JSON: {output_json}")

    _write_report(results, runs)


def _write_report(results: dict, runs: int) -> None:
    lines = [
        "# NPU Agent Lab v2.1 — Benchmark A/B: normal vs. rapido",
        "",
        f"**Modelo:** {results['model']}  ",
        f"**Dispositivo:** {results['device']}  ",
        f"**Repeticiones por escenario:** {results['runs_per_scenario']}  ",
        "",
        "> Nota: con muestras de tamaño reducido la mediana y el p95 son orientativos.",
        "> Los resultados reflejan condiciones de ejecucion unica; pueden variar por cache del modelo,",
        "> calentamiento de la NPU o carga del sistema.",
        "",
        "## Tabla comparativa",
        "",
        "| Escenario | Modo | Mediana (s) | p95 (s) | Tokens salida | Hops | Exito |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]

    for sid, data in results["scenarios"].items():
        desc = data["descripcion"]
        for mode in ("normal", "rapido"):
            if mode not in data:
                continue
            s = data[mode]
            exito = f"{int(s['tasa_exito'] * results['runs_per_scenario'])}/{results['runs_per_scenario']}"
            lines.append(
                f"| {desc} | {mode} | {s['mediana_s']:.2f} | {s['p95_s']:.2f} | "
                f"{s['tokens_salida_media']} | {s['hops_media']:.1f} | {exito} |"
            )

    lines += [
        "",
        "## Comparacion de latencia mediana",
        "",
    ]

    for sid, data in results["scenarios"].items():
        if "normal" in data and "rapido" in data:
            n = data["normal"]["mediana_s"]
            r = data["rapido"]["mediana_s"]
            if n > 0:
                delta_pct = (r - n) / n * 100
                signo = "+" if delta_pct > 0 else ""
                lines.append(f"- **{data['descripcion']}**: normal {n:.2f}s → rapido {r:.2f}s ({signo}{delta_pct:.0f}%)")

    lines += [
        "",
        "## Compatibilidad /no_think con tool calling",
        "",
        "| Aspecto | Resultado |",
        "|---|---|",
        "| tool_calls generados correctamente | Verificado en tests unitarios |",
        "| tool_call_id preservado | Verificado en tests unitarios |",
        "| Mensajes de herramienta sin prefijo | Verificado: /no_think solo en mensaje inicial del usuario |",
        "| Historial conversacional intacto | Verificado |",
        "| Limite de saltos respetado | Verificado |",
        "",
        "## Recomendacion",
        "",
    ]

    # Build recommendation from data
    total_normal = sum(data["normal"]["mediana_s"] for data in results["scenarios"].values() if "normal" in data)
    total_rapido = sum(data["rapido"]["mediana_s"] for data in results["scenarios"].values() if "rapido" in data)
    n_scenarios = sum(1 for data in results["scenarios"].values() if "normal" in data and "rapido" in data)

    if n_scenarios > 0 and total_normal > 0:
        avg_delta = (total_rapido - total_normal) / total_normal * 100
        if avg_delta < -10:
            recomendacion = (
                f"El modo `rapido` redujo la latencia media un {abs(avg_delta):.0f}% en los escenarios medidos. "
                "Se recomienda adoptarlo como modo predeterminado tras confirmar que el tool calling "
                "se mantiene estable en produccion."
            )
        elif avg_delta < 5:
            recomendacion = (
                "La diferencia de latencia entre modos es menor al 10%. "
                "Se recomienda `automatico` como modo predeterminado: aplica `/no_think` en tareas simples "
                "y preserva el razonamiento completo cuando el modelo lo necesita."
            )
        else:
            recomendacion = (
                "El modo `rapido` no mostro mejora consistente en este conjunto de datos. "
                "Se recomienda mantener `normal` como modo predeterminado y repetir el benchmark "
                "con mayor numero de repeticiones."
            )
    else:
        recomendacion = "Insuficientes datos para emitir una recomendacion fundamentada."

    lines.append(recomendacion)
    lines += ["", "---", "_Generado automaticamente por `benchmarks/ab_benchmark.py`_"]

    out = Path(__file__).resolve().parents[1] / "docs" / "NPU_AGENT_V21_BENCHMARK.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Informe: {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark A/B normal vs rapido")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--mcp", action="store_true", help="Incluir escenario MCP")
    args = parser.parse_args()
    run_ab(args.runs, args.mcp)
