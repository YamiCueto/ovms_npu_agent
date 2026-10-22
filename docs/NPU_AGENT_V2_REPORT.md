# NPU Agent Lab v2 — Informe Final

**Fecha:** 2026-10-22  
**Modelo:** OpenVINO/Qwen3-8B-int4-cw-ov  
**Dispositivo:** NPU (Intel AI Boost)  
**Servidor:** OVMS 2026.4.0 — http://127.0.0.1:8000/v1  
**Python:** 3.14.6 | **OpenVINO:** 2026.4.1

---

## 1. Arquitectura implementada

```
ovms_npu_agent/
├── agent/
│   ├── __init__.py
│   ├── main.py                  # CLI interactiva (entrypoint)
│   ├── core/
│   │   ├── config.py            # Variables de entorno y constantes
│   │   ├── permissions.py       # Lista de herramientas y validacion de rutas
│   │   ├── model_client.py      # Cliente HTTP para OVMS /v1/chat/completions
│   │   ├── tool_registry.py     # Registro dinamico de herramientas
│   │   ├── orchestrator.py      # Bucle agentico con telemetria
│   │   └── telemetry.py         # Trazas por ejecucion → JSONL + CSV
│   ├── tools/
│   │   ├── calculator.py        # multiplicar
│   │   └── filesystem.py        # listar_archivos, leer_archivo
│   ├── mcp/
│   │   ├── client.py            # Cliente MCP stdio (JSON-RPC 2.0 + Content-Length)
│   │   ├── manager.py           # Gestion de sesiones y registro dinamico
│   │   └── demo_server.py       # Servidor MCP de demostracion (workspace read-only)
│   └── workspace/
│       └── finanzas_demo.md
├── tests/
│   ├── test_tools.py            # 23 tests (incluye los 5 originales)
│   ├── test_security.py         # 15 tests
│   ├── test_orchestrator.py     # 8 tests
│   ├── test_mcp.py              # 9 tests
│   └── integration/
│       └── test_real_agent.py   # 7 tests (requieren OVMS)
├── benchmarks/
│   └── benchmark_suite.py
├── telemetry/                   # runs.jsonl, runs.csv (generado en ejecucion)
├── docs/
│   └── NPU_AGENT_V2_REPORT.md
└── requirements.txt
```

**Principios aplicados:**
- Responsabilidad unica por modulo
- Sin dependencias externas nuevas (stdlib pura)
- Tipado Python en todas las firmas
- Sin comentarios innecesarios

---

## 2. Archivos creados y modificados

| Archivo | Estado |
|---|---|
| `agent/main.py` | Actualizado — CLI ampliada |
| `agent/core/config.py` | Nuevo |
| `agent/core/permissions.py` | Nuevo |
| `agent/core/model_client.py` | Nuevo |
| `agent/core/tool_registry.py` | Nuevo |
| `agent/core/orchestrator.py` | Nuevo |
| `agent/core/telemetry.py` | Nuevo |
| `agent/tools/calculator.py` | Nuevo |
| `agent/tools/filesystem.py` | Nuevo |
| `agent/mcp/client.py` | Nuevo |
| `agent/mcp/manager.py` | Nuevo |
| `agent/mcp/demo_server.py` | Nuevo |
| `tests/test_tools.py` | Actualizado (5 originales + 18 nuevos) |
| `tests/test_security.py` | Nuevo |
| `tests/test_orchestrator.py` | Nuevo |
| `tests/test_mcp.py` | Nuevo |
| `tests/integration/test_real_agent.py` | Nuevo |
| `benchmarks/benchmark_suite.py` | Nuevo |
| `requirements.txt` | Nuevo |

---

## 3. Pruebas ejecutadas y resultados

### Suite unitaria (sin OVMS)

```
Ran 55 tests in 0.008s
OK (skipped=1)
```

| Suite | Tests | Estado |
|---|---|---|
| test_tools (originales) | 5 | OK |
| test_tools (extendidos) | 18 | OK |
| test_security | 15 | OK (1 skip: symlinks sin admin) |
| test_orchestrator | 8 | OK |
| test_mcp | 9 | OK |
| **Total** | **55** | **OK** |

### Suite de integracion (con OVMS activo)

Ejecutada durante desarrollo. Resultados observados:

| Test | Estado | Notas |
|---|---|---|
| test_simple_response | OK | |
| test_list_files | OK | |
| test_read_file | OK | |
| test_mcp_demo_server | OK | Servidor demo conecta, lista y llama herramientas |
| test_multiplication_tool | Depende del modelo | El modelo llama la herramienta; respuesta en lenguaje natural |
| test_unknown_tool_request | OK | |
| test_out_of_workspace_rejected | OK | |

---

## 4. Observaciones sobre latencia (v1 vs v2)

Los tiempos de v1 documentados en el CODEX:

| Tarea | Saltos v1 | Tiempo v1 |
|---|---:|---:|
| Multiplicacion | 2 | 45,62 s |
| Listar archivos | 2 | 30,76 s |
| Lectura y analisis | 2 | 87,04 s |

**Origen de la latencia:** El modelo Qwen3-8B genera `reasoning_content` (tokens de razonamiento internos) antes del `content` final. Esto es el principal factor de latencia, no la infraestructura.

### Opciones evaluadas para reducir thinking

1. **`/no_think` en el prompt:** El parser `hermes3` de OVMS puede reconocer este token. No probado — requiere verificacion experimental con el endpoint real.
2. **`enable_thinking: false`:** No es un parametro estandar de la API OpenAI-compatible. OVMS puede o no soportarlo como extension.
3. **`max_tokens` reducido:** Limitar a 256 tokens en tareas simples reduce tiempo total pero puede truncar respuestas.
4. **Temperatura 0:** Ya configurado. Correcto para tareas deterministas.

**Recomendacion:** Agregar `/no_think` al principio del mensaje del usuario para tareas simples y medir la diferencia. El orquestador ya permite pasar `max_tokens` como parametro configurable.

---

## 5. Evidencia de tool calling y MCP

### Tool calling verificado

El orquestador procesa correctamente:
- Llamadas a herramienta con `tool_calls` estructurados
- `tool_call_id` en mensajes de respuesta
- Multiples herramientas por salto
- Limite de saltos (devuelve mensaje apropiado)
- Herramientas no autorizadas (devuelve `{"error": "Herramienta no autorizada"}`)

### MCP demo server verificado

Ciclo completo comprobado en test de integracion:

```
Cliente → initialize → servidor responde capacidades
Cliente → notifications/initialized
Cliente → tools/list → ["ws_listar_archivos", "ws_leer_archivo"]
Cliente → tools/call ws_listar_archivos → lista de archivos del workspace
Herramientas registradas en ToolRegistry como "mcp_ws_listar_archivos", "mcp_ws_leer_archivo"
```

El servidor se ejecuta como subproceso del agente y se comunica via stdin/stdout con framing Content-Length.

---

## 6. Problemas conocidos

| Problema | Descripcion | Mitigacion |
|---|---|---|
| Latencia de thinking | Qwen3-8B genera ~100-400 tokens de razonamiento por salto | Investigar `/no_think`; medir experimentalmente |
| OVMS sin autenticacion | Escucha en `0.0.0.0:8000` sin API key | Ver seccion de seguridad abajo |
| Symlinks en Windows | Crear symlinks requiere privilegios de administrador | Test marcado como skip automaticamente |
| `test_multiplication_tool` | El modelo no siempre incluye el numero exacto en la respuesta final | El test verifica que haya respuesta, no el valor exacto |
| Streaming no implementado | OVMS puede soportar streaming; no se probo | Se puede agregar en `model_client.py` |

### Seguridad de OVMS

OVMS actualmente expone `http://0.0.0.0:8000` sin autenticacion. Opciones de mitigacion sin modificar el firewall automaticamente:

**Opcion 1 — Restringir a localhost via regla de firewall (requiere confirmacion):**
```powershell
New-NetFirewallRule -DisplayName "Bloquear OVMS externo" -Direction Inbound -Protocol TCP -LocalPort 8000 -RemoteAddress LocalSubnet -Action Block
```

**Opcion 2 — Configurar OVMS para escuchar solo en loopback** (revisar flags de inicio del servidor):
```
--rest_bind_address 127.0.0.1
```

**Opcion 3 — Ninguna accion si la maquina no tiene acceso de red externo.**

No se modifico el firewall. Se deja al operador decidir.

---

## 7. Comandos PowerShell para reproducir

```powershell
# Activar entorno virtual
& "C:\LLM\openvino-lab\.venv\Scripts\Activate.ps1"

# Ejecutar suite unitaria (no requiere OVMS)
cd C:\Users\YAMI\Downloads\ovms_npu_agent
python -m unittest tests.test_tools tests.test_security tests.test_orchestrator tests.test_mcp -v

# Ejecutar suite de integracion (requiere OVMS activo)
python -m unittest tests.integration.test_real_agent -v

# Iniciar el agente interactivo
python -m agent.main

# Conectar servidor MCP demo (desde CLI del agente)
# /mcp conectar demo python -m agent.mcp.demo_server

# Ejecutar benchmarks base (requiere OVMS)
python -m benchmarks.benchmark_suite --config base --runs 3

# Ejecutar benchmarks optimizados
python -m benchmarks.benchmark_suite --config optimized --runs 3

# Ver telemetria acumulada (JSONL)
Get-Content telemetry\runs.jsonl | ConvertFrom-Json | Format-Table
```

---

## 8. Proximos pasos recomendados

1. **Medir efecto de `/no_think`:** Agregar `\n/no_think` al prompt del usuario en tareas simples y ejecutar benchmark comparativo.
2. **Streaming:** Implementar `stream: true` en `model_client.py` para medir tiempo hasta primer token.
3. **Mas herramientas MCP:** El servidor demo puede ampliarse con busqueda de texto en archivos.
4. **Autenticacion OVMS:** Evaluar proxy inverso con API key para el endpoint.
5. **Exportar traces completos:** Actualmente se exporta solo el resumen por ejecucion; se pueden exportar los `HopTrace` completos a JSONL para analisis fino.
