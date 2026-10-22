# Laboratorio: agente local con OVMS y NPU

Requisitos: Windows 11, Python 3.12+ y OVMS sirviendo `OpenVINO/Qwen3-8B-int4-cw-ov` en `http://127.0.0.1:8000/v1`.

## Instalar

Descomprime el ZIP en `C:\LLM\openvino-lab`, de forma que el archivo principal quede en `C:\LLM\openvino-lab\agent\main.py`.

```powershell
Set-Location C:\LLM\openvino-lab
.\.venv\Scripts\Activate.ps1
python .\agent\main.py
```

No necesita instalar librerías adicionales; utiliza únicamente la biblioteca estándar de Python.

## Preguntas de prueba

- `Multiplica 875 por 43 usando una herramienta.`
- `Lista los archivos disponibles.`
- `Lee finanzas_demo.md y dime cuánto queda después de los gastos.`

Comandos: `/salir`, `/reiniciar`, `/herramientas`.

## Pruebas

```powershell
python -m unittest discover -s .\tests -v
```

## Seguridad y límites

- Herramientas autorizadas: `multiplicar`, `listar_archivos`, `leer_archivo`.
- Solo lectura dentro de `agent/workspace`, archivos `.txt` y `.md`, máximo 8 KiB cada uno.
- Sin ejecución de comandos, escritura de archivos ni acceso a finanzas reales.
- Máximo cinco saltos por petición.
- Se imprimen tiempo y tokens por salto.
- No hay integración MCP todavía; este es el agente base para agregarla luego.
- **Importante:** tu OVMS está escuchando en `0.0.0.0:8000` sin autenticación. Restringe el puerto 8000 en el Firewall de Windows a conexiones locales antes de exponer herramientas o información privada. La URL `127.0.0.1` en el cliente no protege al servidor si sigue enlazado a todas las interfaces.
- Los archivos leídos pueden contener instrucciones maliciosas. Este laboratorio restringe operaciones, pero no garantiza inmunidad frente a prompt injection.
- Si `content` aparece vacío, Qwen3 puede haber consumido `max_tokens` en `reasoning_content`. Se puede aumentar el límite o configurar un modo sin razonamiento tras verificar compatibilidad con OVMS.
