# Validación HBT-CEN-001

Fecha: 22 de octubre de 2026. Entorno ejecutado: Windows, Python 3.11.15, dependencias fijadas en `uv.lock`. La ruta POSIX está implementada, pero su ejecución en Linux queda pendiente; no se afirma una validación multiplataforma.

## Validación sin servicios externos

```powershell
uv sync --locked --python 3.11
uv run pytest -q
uv run ruff check .
git diff --check
```

Resultado final de pytest: **140 passed, 6 skipped**. Son 94 regresiones unitarias del origen y 46 casos nuevos del core. Las seis omisiones corresponden exclusivamente a las pruebas de integración Atlas preservadas, que requieren credenciales y la activación explícita `CENTAURO_REAL_ATLAS=1`. Ruff y la revisión de espacios del diff pasan. Los resultados de la ejecución se guardan también en `validation-results.txt`.

| Criterio | Evidencia ejecutada |
| --- | --- |
| Configuración fija | Dataclasses congeladas, entorno del coordinador intacto, credenciales resueltas una vez, dotenv ajeno ignorado e importación tardía del motor |
| Exclusión real | Dos solicitudes simultáneas: una aceptada y otra ocupada; un solo registro activo; bloqueo mantenido durante verificación |
| Independencia y recuperación | Trabajador sigue vivo después de terminar el proceso solicitante; trabajador terminado se marca interrumpido; PID/fecha/token incorrectos no prueban vida |
| Reanudación | Nuevo job_id enlazado al anterior, mismo extraction_id y rechazo de otro destino |
| Persistencia única | Extractor/verificador reales con E/S simulada; segunda ejecución reutiliza sin descargar ni duplicar raw |
| Estados | Ejecución/almacenamiento completados con verificación fallida; interrupción consultable; éxito sólo tras confirmación |
| Resultados | Nueva extracción, vacía válida, reutilización, reanudación paginada y recuperación del checkpoint final; bar_count desconocido |
| Diagnósticos | HTTP controlado 401, 403, 429 y reintentos; errores de transporte, credenciales/permisos Atlas y trabajador; sin textos secretos |
| Regresión | Las 94 pruebas originales permanecen y pasan; hashes de los archivos importados consignados en `engine-provenance.json` |

La simulación MongoDB no sustituye el comportamiento transaccional, permisos, red ni límites reales de Atlas. Las pruebas con procesos verifican el bloqueo y la recuperación en el sistema operativo, no sólo mediante dobles en memoria.

## Prueba real pequeña — pendiente

No estaban configuradas `MASSIVE_API_KEY` ni `MONGODB_URI`, ni una conexión operativa de este core a la base MVP. No se realizó extracción real. No se da por comprobada la capacidad de ningún plan Massive.

1. Prepare una base dedicada al MVP y configure el perfil público; no use una base de investigación o producción. El ejemplo usa `centauro_bridge_mvp`.
2. Introduzca las credenciales como muestra el README. No las pase como argumentos CLI ni las guarde en archivos versionados.
3. Inicie una solicitud pequeña y consulte su resultado:

```powershell
$primero = uv run centauro-bridge start --profile profiles/mvp.example.toml AAPL 2025-01-02 2025-01-03 | ConvertFrom-Json
uv run centauro-bridge status $primero.job_id
```

4. Cuando termine, compruebe `state=verified`, `execution_status=completed`, `storage_status=completed`, `verification_status=verified`. Si la ventana histórica no está permitida por la cuenta, seleccione una ventana breve admitida; conserve el diagnóstico observado, sin deducir un plan exacto.
5. Repita exactamente la misma solicitud después de que termine el primer trabajador. Espere otro job_id, igual extraction_id, `result.mode=reused`, `verified=true` y `bar_count=null`. Si existe un checkpoint completo de un intento fallido puede aparecer `recovered`.
6. Para probar concurrencia contra servicios reales, solicite el segundo trabajo mientras el primero siga activo: debe devolver `busy`. Para probar recuperación, use únicamente la base MVP y compruebe la identidad completa del trabajador antes de terminarlo; después consulte su estado y use `resume`.

Pruebas de integración Atlas heredadas, separadas de la extracción real Massive (la prueba de recuperación heredada usa HTTP simulado):

```powershell
$env:MONGODB_DATABASE = "centauro_bridge_mvp"
$env:CENTAURO_REAL_ATLAS = "1"
uv run pytest tests/integration -q -rs
```

Estos tests crean datos de prueba en la base indicada y limpian sus registros. La conexión Atlas debe estar operativa. El test de recuperación heredado puede omitir por indisponibilidad de conexión: cualquier omisión significa integración pendiente, nunca validación real satisfactoria. La prueba Massive + Atlas sólo queda validada al ejecutar el procedimiento anterior y registrar su evidencia sin secretos.

## Pendientes y HBT-CEN-002

Prueba real pequeña; ejecución de la suite en POSIX; dashboard que consuma este core; lector canónico para contar/consultar barras; gestión de cancelación/colas si se requiere. IA, brokers y multiusuario quedan fuera de esta entrega.
