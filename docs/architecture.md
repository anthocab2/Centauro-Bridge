# Application Core

## Recorrido

```text
CLI / Coordinator
  -> Profile + Request inmutables
  -> Popen con entorno explícito y solicitud pública por stdin
     -> Worker adquiere worker.lock del sistema operativo
     -> recupera trabajos huérfanos
     -> importa el motor y calcula su extraction_id original
     -> persiste job_id propio y confirma aceptación
     -> MassiveAtlasAdapter llama extract_daily_aggs
        -> el motor persiste raw, ledger, checkpoints y run en Atlas
     -> adapter llama verify_extraction
     -> persiste resultado seguro y libera worker.lock
```

El coordinador nunca importa el módulo de configuración legado ni cambia su `os.environ`. El perfil resuelve las credenciales una sola vez; sus campos son inmutables y las credenciales no aparecen en `repr` ni en `public()`. El trabajador recibe `MASSIVE_API_KEY`, `MONGODB_URI`, `MONGODB_DATABASE` y el indicador `CENTAURO_EXPLICIT_CONFIG=1` antes de arrancar Python/importar el motor. Ese indicador evita la carga implícita de `.env`. Una reanudación puede resolver credenciales nuevas, porque es un trabajo nuevo.

La comunicación inicial entrega exclusivamente perfil público, solicitud y enlace de reanudación. El trabajador reconstruye el perfil con las credenciales de su entorno y comprueba su consistencia. Un hash del clúster/base, sin usuario, contraseña ni opciones de URI, evita reanudar accidentalmente contra otro clúster con el mismo alias. No es una credencial ni un verificador de contraseñas.

## Exclusión y recuperación

El trabajador adquiere un bloqueo no bloqueante de `portalocker` antes de importar/preparar el motor; lo conserva durante preparación, extracción, almacenamiento y verificación. Nunca transfiere el bloqueo al coordinador. El fichero de bloqueo no se borra, evitando carreras de sustitución del fichero. Dos solicitudes pueden crear procesos auxiliares, pero sólo uno puede preparar o ejecutar el motor; el otro devuelve `busy`.

SQLite guarda un documento JSON público por trabajo con transacciones y un índice parcial que impide dos filas activas. El bloqueo es la garantía primaria de exclusión, incluso si una operación de Atlas continúa mientras el coordinador ya terminó. El trabajador usa un proceso independiente en Windows y una sesión independiente en POSIX.

La identidad del trabajador combina PID, hora de creación del proceso y token aleatorio en su línea de comandos. Consultar sólo un PID no se considera prueba de vida. La recuperación ocurre bajo el mismo bloqueo y marca `interrupted` cuando esa identidad ya no vive. Si faltan permisos para comprobarla, conserva el estado activo y no inicia otra extracción. No se elimina automáticamente una reserva de vida desconocida.

El estado está fuera del código y sobrevive al cierre/reinicio del coordinador y a una actualización del checkout. Tras reiniciar el sistema, la próxima consulta o solicitud reconcilia el trabajador muerto. No hay reintento automático: `resume` crea un nuevo `job_id`, guarda `resumed_from` y usa los mismos parámetros/extraction_id. SQLite usa esquema v1; futuros cambios necesitan migraciones explícitas.

## Contratos y resultados

Sólo se introducen `Profile`, `Request`, `Coordinator`, `State` y el adaptador concreto `MassiveAtlasAdapter`. El motor se invoca con `ticker`, fechas y `adjusted`; conserva exactamente `build_extraction_id` y los algoritmos de ingesta/hash del origen. Un fallo antes del recibo puede dar `worker_start`; si no llega un recibo, `worker_start_unknown` indica que se debe consultar el estado antes de decidir otro intento.

El adaptador inspecciona run/checkpoint para distinguir `new`, `resumed`, `reused` y `recovered`. No guarda otra vez el resultado del extractor. Después de su retorno registra ejecución y almacenamiento completados, pasa a `verifying` y exige `verified is True` del verificador para publicar éxito. Una verificación fallida conserva ejecución/almacenamiento completados y registra estado `failed`, verificación `invalid`. Si se pierde el trabajador durante la verificación, no se atribuye verificación al trabajo interrumpido.

Los IDs de documentos raw no son barras ni necesariamente páginas. El core no usa su longitud como conteo. `bar_count` queda en `null`; la evidencia del verificador sólo permite indicar datos presentes/vacíos/desconocidos y páginas observadas. La recuperación de un checkpoint completo puede devolver `[]` y terminar verificada sin descargar ni escribir raw de nuevo.

## Diagnóstico y límites

Los mensajes se crean localmente a partir de tipos/códigos observados. 401 indica rechazo de autenticación, 403 restricción de acceso y 429 límite de solicitudes tras los reintentos del motor. Los códigos Atlas 18 y 13 distinguen autenticación y permisos. Fallos de transporte se clasifican como conexión. Otros errores permanecen genéricos; no se infiere un plan desde texto libre o HTTP.

El estado comienza con capacidad desconocida. Sólo una extracción nueva/reanudada completada confirma el acceso a esa solicitud; no demuestra acceso a otros endpoints, períodos o planes. Reutilización/recuperación de datos existentes deja desconocida la capacidad actual del proveedor. `declared_plan` y `exact_plan` se mantienen separados.

El trabajador no emite logs/trazas del motor a la CLI: desactiva logging y descarta salida después del recibo. No persiste credenciales, cabeceras ni cuerpos de error. Las credenciales siguen presentes en memoria/entorno del trabajador y dependen de los permisos del sistema operativo.

El alcance es una instalación local por usuario y directorio estable. El bloqueo no es distribuido. Una actualización debe conservar el estado y esperar que termine el trabajador antes de reemplazar dependencias. No hay cola, cancelación, watchdog que mate trabajos lentos, servicio de secretos ni soporte multiusuario. Los reintentos/esperas HTTP existentes se conservan. El sistema no declara interrupción por lentitud mientras el proceso siga vivo.

HBT-CEN-002 debe consumir `start`, `resume` y `status` del core, mostrar sus estados y mantener un único directorio de instalación. Debe evitar importar directamente el extractor desde la interfaz. Dashboard, lector analítico e IA siguen pendientes.
