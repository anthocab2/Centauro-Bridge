# Centauro Bridge

Aplicación local para ejecutar extracciones diarias de Massive hacia MongoDB Atlas y explorar sus barras OHLCV. HBT-CEN-002 añade un dashboard Streamlit y un lector canónico sobre el Application Core de HBT-CEN-001: CLI, configuración fija por trabajo, estado persistente, exclusión entre trabajadores, recuperación y verificación. Requiere Python 3.11.

El motor ya guarda los datos en Atlas. El adaptador conserva esa persistencia única y sus identidades, hashes, ledger de páginas y checkpoints. Esta versión sigue acoplada a Atlas.

## Project Charter — Stage 2

La entrega de planificación de Holberton está en
[docs/stage_2](docs/stage_2/README.md). Incluye el
[Project Charter completo en inglés](docs/stage_2/PROJECT_CHARTER.md), con
objetivos SMART, roles, alcance, riesgos y cronograma, y la
[respuesta de la tarea 0](docs/stage_2/0-project_objectives.md).
El cronograma es una propuesta pendiente de revisión con el equipo y el mentor.

## Technical Documentation — Stage 3

La entrega de Stage 3 está en [docs/stage_3](docs/stage_3/README.md):
[documentación técnica completa en inglés](docs/stage_3/TECHNICAL_DOCUMENTATION.md),
[historias MoSCoW y mockups de la tarea 0](docs/stage_3/0-user_stories_and_mockups.md),
arquitectura, clases, datos, secuencias, contratos de API y planes de SCM/QA.
Los mockups usan valores sintéticos; la validación real de servicios sigue pendiente.

## Ejecutar

Desde una copia de este repositorio, con `uv` disponible:

```powershell
uv sync --locked --python 3.11
uv run streamlit run dashboard.py
```

Abra `http://127.0.0.1:8501`. Configure el perfil en **Conexiones**, envíe una solicitud en **Extracciones** y pulse **Verificar y abrir datos** en **Datos**. Las credenciales se introducen en campos protegidos y permanecen en la sesión local. El botón **Explorar datos de prueba** permite recorrer el panel con una serie sintética, sin conexiones ni trabajos reales.

La [guía de uso](docs/user-guide.md) explica instalación, estado compartido con la CLI, verificación, filtros y errores habituales. La tabla y el gráfico Plotly usan el mismo conjunto filtrado. Antes de abrir una extracción, el lector comprueba en Atlas la evidencia canónica actual; una verificación histórica de SQLite no basta.

La CLI sigue disponible:

```powershell
uv run centauro-bridge --help
```

Revise `profiles/mvp.example.toml`: contiene referencias públicas y nombres de variables, nunca credenciales. Use una base destinada al MVP; el ejemplo selecciona `centauro_bridge_mvp`. La URI debe conectar al clúster donde existe esa base y permitir las operaciones de ingesta.

Ejemplo en PowerShell 7, introduciendo las credenciales sin incluirlas en el historial:

```powershell
$env:MASSIVE_API_KEY = Read-Host "Credencial de Massive" -MaskInput
$env:MONGODB_URI = Read-Host "URI de Atlas para el MVP" -MaskInput
$inicio = uv run centauro-bridge start --profile profiles/mvp.example.toml AAPL 2025-01-02 2025-01-03 | ConvertFrom-Json
$inicio
uv run centauro-bridge status $inicio.job_id
uv run centauro-bridge jobs
```

`start` devuelve `accepted`, `job_id` y `extraction_id` cuando el trabajador tiene el bloqueo y el trabajo está guardado. La ejecución continúa después de salir del comando. Consulte `status` hasta obtener `verified`, `failed` o `interrupted`; `accepted` no significa extracción completada. Una solicitud concurrente devuelve `busy` y, cuando ya está disponible, el identificador del trabajo activo. No hay cola.

La solicitud queda congelada, incluido `adjusted` (verdadero salvo `--unadjusted`). Cambiar el perfil o el entorno del coordinador no cambia un trabajo en curso. El trabajador recibe sus variables explícitas antes de importar la configuración del motor y no carga `.env`.

Si un trabajador murió, `status`, `jobs` o la siguiente solicitud registran la interrupción. Para reanudar un trabajo fallido o interrumpido:

```powershell
uv run centauro-bridge resume JOB_ID --profile profiles/mvp.example.toml
```

La reanudación crea otro `job_id`, enlaza `resumed_from` y conserva el `extraction_id` original. Exige el mismo perfil público, clúster, base y solicitud; permite renovar credenciales. El motor decide cómo continuar desde Atlas. Un fallo de integridad necesita corregir la evidencia antes de reanudar.

## Estado y resultados

El estado se guarda fuera del checkout: `%LOCALAPPDATA%/CentauroBridge` en Windows y `$XDG_STATE_HOME/CentauroBridge` (o `~/.local/state/CentauroBridge`) en otros sistemas. Mantenga ese directorio al actualizar o mover la aplicación. El esquema SQLite tiene versión; una versión futura desconocida se rechaza sin sobrescribirla.

`--state-dir RUTA`, antes del subcomando, define otra instalación. Todos los procesos de una instalación deben usar la misma ruta local. No use una ruta distinta por trabajo ni un sistema de archivos de red. El bloqueo no coordina máquinas o instalaciones diferentes.

Cada trabajo expone solicitud, perfil sin secretos, fechas UTC, transiciones, identidad del trabajador, ejecución, almacenamiento, verificación y diagnóstico seguro. Nunca devuelve URI, API key, cuerpos de error o trazas del proveedor.

| Campo | Interpretación |
| --- | --- |
| `state` | `preparing`, `executing`, `verifying`, `verified`, `failed`, `interrupted` |
| `execution_status` | Transporte/ejecución; puede ser `completed` aunque falle la verificación |
| `storage_status` | `unknown`, `partial_or_unknown` o `completed`; no afirma ausencia de escrituras tras un fallo |
| `verification_status` | `not_verified`, `running`, `invalid` o `verified` |
| `mode` / `result.mode` | `new`, `resumed`, `reused` o `recovered` según evidencia previa |
| `result.data_status` | `empty`, `present` o `unknown`, basado en la verificación |
| `result.bar_count` | `null` en el histórico del core; el lector calcula y presenta un conteo separado sin reescribirlo |

Un retorno `[]` del extractor puede ser una reutilización satisfactoria; se verifica antes de marcar éxito. `declared_plan` es sólo una declaración del perfil. `capability` distingue una petición efectivamente completada de una capacidad desconocida; reutilizar datos no comprueba acceso actual a Massive. El plan exacto permanece desconocido y no se deduce de 401, 403 o 429.

Los códigos de salida de la CLI son 0 para una operación aceptada/consulta correcta, 1 para error operativo, 2 para entrada inválida y 3 para ocupado. Una consulta exitosa puede describir un trabajo fallido: revise `state`.

## Comprobar

```powershell
uv run pytest -q
uv run ruff check .
git diff --check
```

La suite sin red conserva las 94 regresiones unitarias del motor e incorpora pruebas del core con procesos reales, lector, conexiones y Streamlit AppTest. Resultado HBT-CEN-002 en Windows: **190 passed, 6 skipped**; Ruff aprobado. Las seis pruebas de integración con Atlas siguen pendientes cuando no se habilitan explícitamente. Consulte [validación, capturas y prueba real pequeña](docs/validation.md).

## Alcance

Procedencia: [centauro-atlas-bridge](https://github.com/anthocab2/centauro-atlas-bridge), commit `ca9e9270d4553ebaea80096e019974eae697fe3e`. Se inicia una historia Git independiente. No se incluyen historial privado, `.env` reales, investigación, documentación privada ni SEC/WKC. [Historia y selección](docs/project-story.md), [arquitectura](docs/architecture.md) y [registro de desarrollo](docs/development-log.md).

El dashboard y el lector están implementados y probados con evidencia sintética y E/S simulada. La integración real Massive + Atlas sigue pendiente por falta de credenciales configuradas. IA, brokers, multiusuario, análisis avanzados, cancelación y colas quedan fuera del alcance. Para HBT-CEN-003 quedan la validación real del recorrido y las mejoras que se acuerden después de ella.
