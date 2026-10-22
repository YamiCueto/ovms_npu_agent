# NPU Agent Lab v3: arquitectura y contratos

Base inspeccionada: `main`, commit `effac0d` (v2.1). No se cambia el despliegue de OVMS.

## Flujo

Angular standalone → REST FastAPI → Orchestrator → OVMSClient → OVMS.
Orchestrator → ToolRegistry → herramientas locales / MCPManager → MCP stdio.
Orchestrator → Telemetry (JSONL completo + CSV resumido) y callback → SSE → Angular.

CLI, HTTP y benchmarks usan el mismo Orchestrator. No se replica selección de herramientas,
historial, selección automática de modo ni cálculo de métricas en Angular.
La UI usa fetch y EventSource nativos, CSS y una gráfica de barras interactiva accesible;
no requiere biblioteca de gráficas, CDN, fuentes externas ni servicios de nube.

## Ejecución y aislamiento

- Un proceso Uvicorn, un modelo activo configurado por las variables existentes.
- La reserva de ejecución ocurre antes de responder 202. Un conflicto devuelve 409.
- Chat, benchmark, reinicio de sesión y cambios de MCP comparten la reserva.
- Un bloqueo de archivo por endpoint/modelo impide que CLI y API de esta aplicación infieran simultáneamente.
  No controla otros clientes independientes que llamen directamente a OVMS.
- El trabajo bloqueante corre en un hilo; cerrar SSE no cancela la inferencia ni libera prematuramente el modelo.
- Los historiales son del servidor y por sesión UUID. Solo una ejecución exitosa actualiza el historial.
- Se retienen las últimas 500 ejecuciones en memoria. Máximo 100 sesiones; borrar una libera espacio.
  El dashboard indica que representa la sesión actual del servidor. JSONL persiste las trazas completas.
- SSE permite retomar con Last-Event-ID. Los eventos tienen secuencia monotónica por ejecución.
- El cierre del servidor espera los trabajos activos antes de desconectar MCP.

## API

| Método y ruta | Uso |
|---|---|
| GET /api/status | Consulta real de /v1/models; modelo disponible y dispositivo **configurado** |
| POST /api/sessions | Crear historial |
| GET, DELETE /api/sessions/{id} | Consultar o eliminar historial |
| POST /api/runs | `{session_id,text,mode}` → 202 y run_id |
| GET /api/runs | Trazas completas de la sesión del servidor |
| GET /api/runs/{id} | Estado, traza y eventos |
| GET /api/runs/{id}/events | SSE, replay y heartbeat |
| GET /api/mcp | Servidores autorizados, conexiones y herramientas |
| POST /api/mcp/{id}/connect | Iniciar servidor autorizado |
| DELETE /api/mcp/{id} | Detener y desregistrar herramientas |
| POST /api/benchmarks | `{repetitions:1..100}` → id |
| GET /api/benchmarks/{id} | Progreso, resultados y resumen |
| GET /api/benchmarks/{id}/export?format=json\|csv | Descargar resultados |

Eventos tipados en `web/src/types.ts`: run_started, hop_started, hop_completed,
tool_started, tool_completed, run_completed, run_failed. Cada evento incluye type,
run_id, seq y elapsed_s. Inferencias incluyen uso, latencia y finish_reason;
herramientas incluyen id, nombre, argumentos, resultado/error y tiempo individual.
Los eventos terminales contienen la traza completa. No son streaming de tokens.

## Métricas y exactitud

`total_latency_s`: reloj monotónico desde inicio del agente hasta terminación.
`inference_latency_s`: suma de duración cliente de cada petición HTTP, incluido fallo.
`tool_latency_s`: suma de todas las llamadas, no solo la última del salto.
`tokens_per_second`: suma de completion_tokens / suma de tiempos de inferencia.
Incluye prefill, generación y transporte; **no** es velocidad pura de decodificación.
Uso ausente se presenta como null/«—», nunca como medición cero. No se informa TTFT.
El dispositivo procede de configuración: /models no demuestra utilización física de la NPU.

Respuesta vacía y finish_reason=length son fallos. Las llamadas truncadas no se ejecutan.
Errores de herramientas quedan en historial y traza; el agente puede recuperarse en un salto posterior.
Un éxito del agente significa respuesta final no vacía y no truncada; la exactitud requiere validación adicional.

El benchmark v3 comparte casos y validadores entre web y `benchmarks.lab_benchmark`:
saludo exacto sin herramientas, producto 875×43 con argumentos exactos y lectura de
finanzas_demo.md con ingreso 4500000. Una respuesta no vacía no basta.
Percentiles: interpolación lineal (tipo 7), posición (n−1)p; incluye intentos fallidos.
Menos de 20 repeticiones por caso/modo produce advertencia; no implica suficiencia estadística a partir de 20.
El orden normal/rápido alterna entre repeticiones; no hay calentamiento excluido automáticamente.

## MCP y seguridad

stdio usa JSON-RPC UTF-8 delimitado por newline, handshake 2024-11-05,
correlación por id, notificaciones intercaladas, tools/list paginado y timeout efectivo.
Se propaga isError. La desconexión y el fallo de registro limpian herramientas y procesos.
Se rechazan nombres de herramientas duplicados para no sustituir handlers de otro servidor.
No se implementan capacidades opcionales de sampling, roots ni elicitation.

La web no acepta comandos de proceso. `AGENT_MCP_CONFIG` apunta a un JSON local
`{"servidor": ["ejecutable", "argumento"]}` que el administrador controla.
El servidor demo es de solo lectura. Los servidores adicionales deben ser confiables y
respetar esa política; un proceso MCP externo no queda aislado por el sandbox del workspace.
Se mantienen las restricciones de rutas/extensiones/tamaño existentes del workspace.
HTTP se enlaza por defecto a 127.0.0.1; Host, Origin y Sec-Fetch-Site se validan;
POST requiere application/json. Angular interpola texto sin ejecutar HTML del modelo.

Referencias: [Angular: compatibilidad](https://angular.dev/reference/versions),
[MCP stdio](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports).
