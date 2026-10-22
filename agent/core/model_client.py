import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import BASE_URL, MODEL, REQUEST_TIMEOUT


class OVMSClient:
    def __init__(
        self,
        base_url: str = BASE_URL,
        model: str = MODEL,
        timeout: int = REQUEST_TIMEOUT,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 768,
        temperature: float = 0,
    ) -> dict:
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            self.base_url + "/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                data = json.load(response)
        except HTTPError as exc:
            detail = exc.read(2000).decode("utf-8", errors="replace")
            raise RuntimeError(f"OVMS HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"No se pudo conectar a OVMS: {exc.reason}") from exc

        if "choices" not in data or not data["choices"]:
            raise RuntimeError("Respuesta sin choices de OVMS")
        return data
