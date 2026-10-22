# NPU Agent Lab v3.0 — implementación y validación

Fecha: 22 de octubre de 2026. Base: `main`, `effac0d` (v2.1).
Cambios locales, sin commit ni push. No se modificaron despliegue, modelo ni configuración de OVMS.

## Implementación por fases

1. **Arquitectura:** se inspeccionaron agente, herramientas, seguridad, MCP, telemetría,
   CLI, benchmarks y pruebas existentes. El contrato y decisiones están en [V3_ARCHITECTURE.md](V3_ARCHITECTURE.md).
2. **API:** FastAPI en loopback, sesiones, consultas, exclusión, tareas en hilos,
   eventos SSE con secuencia y reanudación, consulta real de disponibilidad OVMS.
3. **UI:** Angular 22 standalone; Dashboard, Chat, Inspector, MCP y Benchmark.
   Diseño oscuro verde/cian, responsive, teclado, reduced-motion, sin activos de nube.
4. **Observabilidad:** eventos de inicio/fin por inferencia y herramienta, errores,
   ids, argumentos, resultados, tokens, finish_reason y trazas completas persistidas.
5. **Benchmark:** normal/rápido, repeticiones, validación semántica determinista,
   percentiles tipo 7, advertencia de muestra pequeña, resultados JSON y CSV.
   CLI v3 comparte casos y validadores. Se corrigieron percentiles y falsos éxitos
   en los scripts históricos sin sobrescribir sus informes previos.
6. **Pruebas:** regresión del núcleo, API, stdio real, navegador escritorio/móvil
   con fixture determinista y navegador contra OVMS real.
7. **Documentación:** instrucciones de instalación/arranque, API, fórmulas,
   límites, configuración MCP, pruebas y evidencia.

## Correcciones del núcleo

- Respuestas vacías ya no son éxito; `length` es fallo explícito y no ejecuta herramientas truncadas.
- Cada herramienta conserva su propia traza y su tiempo; los tiempos se suman por salto.
- `tool_call_id` se conserva en historial y eventos; se detectan ids ausentes/duplicados en un mensaje.
- Se aplica el límite de llamadas a herramientas configurado, además del límite de saltos.
- Los timeouts conservan el tiempo de inferencia fallida; uso desconocido se presenta como no disponible.
- La CLI y API solo incorporan a la conversación turnos exitosos.
- Bloqueo por modelo entre procesos de la aplicación; ninguna ruta de API inicia trabajo conflictivo.
- MCP stdio usa newline JSON, timeout efectivo y correlación por id. Desconectar elimina handlers.
  Registro fallido revierte herramientas; nombres duplicados no sobrescriben herramientas existentes.

## Validación ejecutada

| Validación | Resultado |
|---|---|
| Angular production build | Correcto, Angular 22.2.3 / CLI 22.2.4 / TypeScript 6.0.3 |
| Unitarias + API + stdio | 96 pruebas: 95 correctas, 1 omitida por permisos de symlink en Windows |
| E2E Chrome, fixture | 6 correctos en 40,2 s; escritorio y móvil, incluida recarga durante ejecución |
| E2E Chrome, OVMS real | 1 prueba correcta con tres consultas, una por modo |
| Python compileall | Correcto |
| git diff --check | Sin errores de whitespace |

El fixture no inventa mediciones del hardware: se identifica como `TEST FIXTURE - not NPU`
y solo se usa en `tests.web_fixture`. El lanzador normal usa OVMSClient.
Los E2E cubren chat y modos, eventos y herramientas, métricas, reinicio, vacío/length/timeout,
MCP conectar/desconectar, exactitud y exportación del benchmark. La prueba adicional
de recuperación comprueba eventos antes de finalizar y recarga durante la consulta.

Las pruebas de API verifican conflictos 409 con chat/benchmark/MCP/reinicio,
replay SSE, historial tras fallo, rechazos de origen/Host/contenido y servidores no autorizados.
Las de stdio ejecutan un proceso Python real y comprueban timeout y denegación de traversal.
Se mantiene una advertencia de deprecación de Starlette para su TestClient con httpx;
no afectó resultados y no es una dependencia del cliente de inferencia.

## Inferencia real desde navegador

Modelo reportado disponible: `OpenVINO/Qwen3-8B-int4-cw-ov`.
Dispositivo configurado: NPU; no se midió utilización física de hardware.
Consulta: `Multiplica 875 por 43 usando multiplicar.` Cada modo inició una conversación limpia,
solicitó la herramienta con argumentos 875 y 43, recibió 37625 y terminó correctamente en dos saltos.

| Modo | Tiempo total | Tokens entrada | Tokens salida | Saltos | tok/s efectivo |
|---|---:|---:|---:|---:|---:|
| normal | 58,759 s | 828 | 503 | 2 | 8,560 |
| rapido | 14,580 s | 836 | 60 | 2 | 4,115 |
| automatico | 14,842 s | 836 | 60 | 2 | 4,043 |

Una muestra por modo verifica funcionamiento; **no** permite conclusiones estadísticas de rendimiento.
tok/s = tokens de salida reportados / tiempo acumulado de inferencia, incluido prefill y transporte.
No se informa TTFT ni velocidad pura de decodificación. El modo normal produjo más tokens reportados,
lo cual explica por qué su tok/s efectivo puede ser mayor aunque tarde más en completar la respuesta.

Evidencia: [trazas reales JSON](validation/v3-real-traces.json) y
[captura del dashboard real](validation/v3-real-dashboard.png).

## Límites explícitos

- Backend de un worker; estado interactivo en memoria. El reinicio del servidor elimina sesiones
  y resultados HTTP, pero no las trazas JSONL. Dashboard: últimas 500 consultas de la sesión del servidor.
- El benchmark completo con muestra amplia y servidores MCP de terceros no se ejecutó en hardware real.
  Se validaron transporte stdio y servidor demo; capacidades MCP opcionales no están implementadas.
- Los procesos MCP adicionales deben ser confiables y de solo lectura; autorizar un proceso externo
  no lo aísla a nivel de sistema operativo. La web no permite escribir comandos de proceso.
- No se controla a otros clientes ajenos a esta aplicación que invoquen OVMS directamente.
- Descargas de dependencias requieren red en instalación; la ejecución de la solución es local.

## Arranque

Con las dependencias y build preparados:

```powershell
.\.venv\Scripts\python.exe -m agent.api
```

Abrir `http://127.0.0.1:8080`. Los comandos completos de instalación, CLI y pruebas están en el README.
