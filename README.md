# Centauro Bridge

Application Core para ejecutar extracciones diarias de Massive hacia MongoDB Atlas como trabajos independientes. HBT-CEN-001 incluye CLI, configuración fija por trabajo, estado persistente, exclusión entre trabajadores, recuperación y verificación. Requiere Python 3.11.

El motor ya guarda los datos en Atlas. El adaptador conserva esa persistencia única y sus identidades, hashes, ledger de páginas y checkpoints. Esta versión sigue acoplada a Atlas.

## Ejecutar

Desde una copia de este repositorio, con `uv` disponible:

```powershell
uv sync --locked --python 3.11
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
| `result.bar_count` | `null`: aún no hay lector analítico canónico |

Un retorno `[]` del extractor puede ser una reutilización satisfactoria; se verifica antes de marcar éxito. `declared_plan` es sólo una declaración del perfil. `capability` distingue una petición efectivamente completada de una capacidad desconocida; reutilizar datos no comprueba acceso actual a Massive. El plan exacto permanece desconocido y no se deduce de 401, 403 o 429.

Los códigos de salida de la CLI son 0 para una operación aceptada/consulta correcta, 1 para error operativo, 2 para entrada inválida y 3 para ocupado. Una consulta exitosa puede describir un trabajo fallido: revise `state`.

## Comprobar

```powershell
uv run pytest -q
uv run ruff check .
git diff --check
```

La suite sin red conserva las 94 regresiones unitarias del motor e incorpora pruebas del core con procesos reales y E/S simulada. Las seis pruebas de integración con Atlas se identifican como pendientes cuando no se habilitan explícitamente. Consulte [validación y prueba real pequeña](docs/validation.md).

## Alcance

Procedencia: [centauro-atlas-bridge](https://github.com/anthocab2/centauro-atlas-bridge), commit `ca9e9270d4553ebaea80096e019974eae697fe3e`. Se inicia una historia Git independiente. No se incluyen historial privado, `.env` reales, investigación, documentación privada ni SEC/WKC. [Historia y selección](docs/project-story.md), [arquitectura](docs/architecture.md) y [registro de desarrollo](docs/development-log.md).

HBT-CEN-002 podrá conectar un dashboard a este core. Streamlit, lector analítico, IA, brokers, multiusuario, cancelación y cola de trabajos todavía no están implementados. La integración real Massive + Atlas sigue pendiente en esta entrega por falta de credenciales configuradas.
