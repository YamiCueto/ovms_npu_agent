import csv
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .config import TELEMETRY_DIR


@dataclass
class HopTrace:
    hop: int
    tool_name: str | None
    tool_result_preview: str | None
    prompt_tokens: int
    completion_tokens: int
    inference_latency_s: float
    tool_latency_s: float
    finish_reason: str | None


@dataclass
class RunTrace:
    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    model: str = ""
    device: str = ""
    mode: str = "normal"
    user_query: str = ""
    started_at: float = field(default_factory=time.time)
    hops: list[HopTrace] = field(default_factory=list)
    final_answer: str = ""
    total_latency_s: float = 0.0
    success: bool = False
    error: str = ""

    def total_prompt_tokens(self) -> int:
        return sum(h.prompt_tokens for h in self.hops)

    def total_completion_tokens(self) -> int:
        return sum(h.completion_tokens for h in self.hops)


_CSV_FIELDS = [
    "run_id", "model", "device", "mode", "success", "total_hops",
    "total_prompt_tokens", "total_completion_tokens", "total_latency_s", "error",
]


class Telemetry:
    def __init__(self, directory: Path = TELEMETRY_DIR):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self._jsonl_path = self.directory / "runs.jsonl"
        self._csv_path = self.directory / "runs.csv"
        self._csv_has_header = self._csv_path.exists()
        self._last_trace: RunTrace | None = None

    def record(self, trace: RunTrace) -> None:
        self._last_trace = trace
        row = {
            "run_id": trace.run_id,
            "model": trace.model,
            "device": trace.device,
            "mode": trace.mode,
            "success": trace.success,
            "total_hops": len(trace.hops),
            "total_prompt_tokens": trace.total_prompt_tokens(),
            "total_completion_tokens": trace.total_completion_tokens(),
            "total_latency_s": round(trace.total_latency_s, 3),
            "error": trace.error,
        }
        with open(self._jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

        with open(self._csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
            if not self._csv_has_header:
                writer.writeheader()
                self._csv_has_header = True
            writer.writerow(row)

    def summary(self) -> str:
        if not self._jsonl_path.exists():
            return "Sin datos de telemetria."
        lines = self._jsonl_path.read_text(encoding="utf-8").strip().splitlines()
        if not lines:
            return "Sin ejecuciones registradas."
        records = [json.loads(l) for l in lines]
        count = len(records)
        successes = sum(1 for r in records if r.get("success"))
        latencies = [r.get("total_latency_s", 0) for r in records]
        avg_lat = sum(latencies) / count
        median_lat = sorted(latencies)[count // 2]
        total_tokens = sum(r.get("total_completion_tokens", 0) for r in records)
        return (
            f"Ejecuciones: {count} | Exitosas: {successes} | "
            f"Latencia media: {avg_lat:.2f}s | Mediana: {median_lat:.2f}s | "
            f"Tokens generados (total): {total_tokens}"
        )
