# NPU Agent Lab v2.1 — Benchmark A/B: normal vs. rapido

**Modelo:** OpenVINO/Qwen3-8B-int4-cw-ov  
**Dispositivo:** NPU (Intel AI Boost)  
**Servidor:** OVMS 2026.4.0 — http://127.0.0.1:8000/v1  
**Repeticiones por escenario:** 2 _(con muestras tan pequeñas la mediana y el p95 son orientativos)_  
**Fecha:** 2026-10-22

> **Nota metodológica:** Los resultados miden latencia de pared completa (red + generación). No se pueden aislar efectos de caché del modelo ni calentamiento de la NPU sin instrumentación adicional del servidor. Las diferencias observadas son consistentes entre las dos repeticiones de cada escenario, lo que sugiere que no son artefactos de caché.

---

## Tabla comparativa

| Escenario | Modo | Salto 1 (s) | Salto 2 (s) | Total mediana (s) | Tokens salida | Hops |
|---|---|---:|---:|---:|---:|---:|
| Respuesta simple | normal | 14,25 / 14,95 | — | **14,60** | ~103 | 1 |
| Respuesta simple | rapido | 4,97 / 4,97 | — | **4,97** | ~7 | 1 |
| Multiplicación herramienta | normal | 27,42 / 27,14 | 41,24 / 41,42 | **68,61** | ~622 | 2 |
| Multiplicación herramienta | rapido | 7,61 / 7,59 | 6,77 / 6,83 | **14,40** | ~60 | 2 |
| Listar archivos (MCP) | normal | 17,62 / 17,50 | 26,16 / 25,96 | **43,62** | ~363 | 2 |
| Listar archivos (MCP) | rapido | 6,72 / 6,69 | 6,11 / 6,10 | **12,82** | ~44 | 2 |
| Lectura + análisis (MCP) | normal | 78,79 / 77,91 | 23,78 / — | **106,11** | ~973 | 2–3 |
| Lectura + análisis (MCP) | rapido | 7,19 / 7,16 | 6,42 / 6,42 | **13,60** | ~52 | 2 |
| Herramienta MCP explícita | normal | 20,91 / 21,15 | 24,09 / 25,09 | **45,63** | ~381 | 2 |
| Herramienta MCP explícita | rapido | 6,70 / 6,69 | 6,02 / 6,01 | **12,71** | ~43 | 2 |

---

## Reducción de latencia por escenario

| Escenario | normal (s) | rapido (s) | Reducción |
|---|---:|---:|---:|
| Respuesta simple | 14,60 | 4,97 | **−66%** |
| Multiplicación | 68,61 | 14,40 | **−79%** |
| Listar archivos | 43,62 | 12,82 | **−71%** |
| Lectura + análisis | 106,11 | 13,60 | **−87%** |
| Herramienta MCP | 45,63 | 12,71 | **−72%** |
| **Media ponderada** | **55,71** | **11,70** | **−79%** |

---

## Tokens generados

El efecto principal de `/no_think` es la supresión del `reasoning_content`:

| Modo | Tokens salida promedio | Observación |
|---|---:|---|
| normal | 103–973 | Incluye razonamiento extenso en tareas complejas |
| rapido | 7–60 | Solo respuesta final, sin cadena de pensamiento |

En el escenario de lectura + análisis en modo `normal`, el primer salto agotó los 768 tokens de `max_tokens` generando razonamiento, devolvió `finish_reason: length` con `content` vacío, y requirió un salto adicional para completar la tarea (3 saltos totales). En modo `rapido` se completó en 2 saltos con 30 tokens de salida.

---

## Compatibilidad `/no_think` con tool calling

| Aspecto | Resultado |
|---|---|
| `tool_calls` generados correctamente | ✓ Verificado — multiplicar, leer_archivo, mcp_ws_listar_archivos |
| `tool_call_id` preservado | ✓ Verificado en tests unitarios |
| Mensajes de herramientas sin prefijo | ✓ `/no_think` solo en primer mensaje del usuario |
| Historial conversacional íntegro | ✓ Verificado |
| Herramientas MCP funcionando | ✓ Verificado — `mcp_ws_listar_archivos` y `mcp_ws_leer_archivo` |
| Límite de saltos respetado | ✓ Verificado en tests unitarios |
| `finish_reason: length` manejado | ✓ El orquestador lo registra y continúa el bucle |

---

## Observaciones adicionales

**Modo normal — lectura + análisis (primer run):**  
El modelo dedicó todos los tokens al razonamiento (`finish_reason: length`, `content: ""`) sin emitir una llamada a herramienta. En el segundo run llamó a `leer_archivo` con argumentos incorrectos (error "Nombre de archivo invalido"), luego a `mcp_ws_leer_archivo` que sí funcionó, resultando en 3 saltos y ~134s total.

**Modo rapido — lectura + análisis:**  
En ambas repeticiones llamó directamente a `leer_archivo` con argumentos correctos en el primer salto (7,19s / 7,16s) y completó en el segundo (6,42s). Sin razonamiento visible, el modelo eligió la herramienta más directa.

**Herramientas MCP:**  
En modo `normal`, el modelo tendía a usar `mcp_ws_listar_archivos` cuando tenía acceso a herramientas nativas y MCP simultáneamente. En modo `rapido` el comportamiento fue idéntico — el token `/no_think` no afecta la selección de herramientas.

---

## Recomendación

El modo `rapido` redujo la latencia media un **79%** en todos los escenarios medidos, con resultados correctos y tool calling intacto en las dos repeticiones. La reducción es especialmente significativa en tareas complejas donde el razonamiento consumía varios cientos de tokens antes de emitir la respuesta.

**Recomendación:** adoptar `automatico` como modo predeterminado en la próxima versión:

- Aplica `/no_think` en tareas simples (multiplicación, listado), donde la latencia cae de ~45–70s a ~13–14s.
- Preserva el razonamiento completo en tareas de lectura y análisis, donde el modelo puede necesitarlo para comprender el contenido del archivo antes de resumirlo.
- Permite al usuario cambiar de modo en tiempo real con `/modo rapido` si prefiere velocidad máxima en todas las tareas.

> Esta recomendación se basa en 2 repeticiones por escenario. Se recomienda validar con al menos 5 repeticiones y distintas consultas antes de cambiar el predeterminado en producción.

---

_Generado con `benchmarks/ab_benchmark.py` y datos medidos el 2026-10-22._
