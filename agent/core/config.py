import os
from enum import Enum
from pathlib import Path


class InferenceMode(str, Enum):
    NORMAL = "normal"
    RAPIDO = "rapido"
    AUTOMATICO = "automatico"


DEFAULT_MODE = InferenceMode(os.getenv("AGENT_MODE", InferenceMode.NORMAL.value))

MODEL = os.getenv("OVMS_MODEL", "OpenVINO/Qwen3-8B-int4-cw-ov")
BASE_URL = os.getenv("OVMS_BASE_URL", "http://127.0.0.1:8000/v1").rstrip("/")
DEVICE = os.getenv("OVMS_DEVICE", "NPU")
WORKSPACE = (Path(__file__).resolve().parents[1] / "workspace").resolve()
MAX_HOPS = int(os.getenv("AGENT_MAX_HOPS", "8"))
MAX_FILE_BYTES = int(os.getenv("AGENT_MAX_FILE_BYTES", "8192"))
ALLOWED_EXTENSIONS = {".txt", ".md"}
REQUEST_TIMEOUT = int(os.getenv("AGENT_TIMEOUT", "180"))
MAX_TOOL_CALLS_PER_RUN = int(os.getenv("AGENT_MAX_TOOL_CALLS", "20"))
TELEMETRY_DIR = Path(
    os.getenv("AGENT_TELEMETRY_DIR", str(Path(__file__).resolve().parents[2] / "telemetry"))
)
