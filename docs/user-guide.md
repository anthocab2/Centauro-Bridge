# Guía de uso local

## Instalación y arranque

Requisitos: Python 3.11, `uv`, acceso de red para instalar las dependencias y una base Atlas destinada al MVP para la prueba real. Desde la raíz del repositorio:

```powershell
uv sync --locked --python 3.11
uv run streamlit run dashboard.py
```

Abra `http://127.0.0.1:8501`. El servidor escucha únicamente en la máquina local. No necesita credenciales para usar **Explorar datos de prueba**: muestra diez barras sintéticas DEMO y lo indica en pantalla. Ese ejemplo recorre reconstrucción, validación, tabla, gráfico y filtros; no contacta con Massive o Atlas, ni crea un trabajo.

El dashboard y la CLI usan por defecto el mismo estado: `%LOCALAPPDATA%/CentauroBridge` en Windows; `$XDG_STATE_HOME/CentauroBridge` o `~/.local/state/CentauroBridge` en POSIX. No cambie esa ruta por trabajo ni la sitúe en una unidad de red. Si la instalación ya usa una ruta personalizada, indíquela siempre:

```powershell
uv run streamlit run dashboard.py -- --state-dir 'C:\Centauro\estado'
uv run centauro-bridge --state-dir 'C:\Centauro\estado' jobs
```

El doble guion separa argumentos de Streamlit y del dashboard. Conserve el directorio de estado al actualizar la aplicación. Espere a que termine cualquier trabajador antes de reemplazar código o dependencias.

## Configurar las conexiones

En **Conexiones**, introduzca nombre de perfil, alias del destino, base MVP y plan declarado, si lo conoce. Introduzca API key de Massive y URI Atlas en los campos protegidos y pulse **Activar perfil en esta sesión**. Para abrir o reanudar un trabajo de la CLI, use los mismos datos públicos de su archivo de perfil, incluido el plan declarado y el clúster de la URI.

Un perfil activado sólo confirma formato válido. El botón **Comprobar ping de Atlas** verifica una respuesta al ping; no prueba permisos de lectura ni escritura. **Comprobar esta operación** realiza una petición Massive de un día y límite 1, sin paginar ni guardar datos. Una respuesta vacía válida confirma esa operación, no datos disponibles para cualquier fecha. El plan exacto sigue siendo desconocido.

Las credenciales permanecen en memoria de la sesión y se entregan al trabajador mediante el mecanismo ya existente del core. No se guardan en SQLite ni archivos de perfil. Al recargar por completo el navegador, cerrar la sesión o reiniciar Streamlit, puede ser necesario introducirlas otra vez. Los trabajos guardados permanecen disponibles y el trabajador continúa de forma independiente. No active otro perfil mientras haya un trabajo activo; la interfaz lo impide.

## Iniciar, consultar y reanudar

En **Extracciones**, complete activo, fecha inicial, fecha final y ajuste; pulse **Iniciar extracción**. Para la primera prueba real elija uno o dos días admitidos por su cuenta y una base MVP. El recibo aceptado sólo indica que el core guardó el trabajo y aceptó su ejecución.

**Actualizar estado** consulta el registro; no inicia otra extracción. El detalle muestra `job_id`, `extraction_id`, solicitud, destino, marcas UTC, ejecución, almacenamiento, verificación y tipo: nueva, reutilizada, recuperada o reanudada. No se muestran porcentajes estimados ni se cuentan documentos raw como barras.

Después de un envío, el formulario queda consumido hasta pulsar **Preparar otra solicitud**. Doble clic y reruns no repiten el envío. Otra pestaña comparte el bloqueo del core cuando usa el mismo directorio de estado. No hay cola: si la instalación está ocupada, consulte el trabajo activo.

Ante `worker_start_unknown`, el panel consulta el core y exige **Consultar estado tras inicio incierto** antes de habilitar otro intento. Revise los trabajos encontrados; la ausencia de recibo no prueba que no exista un trabajador. Si el trabajo está fallido o interrumpido, active su perfil original, prepare otra solicitud y pulse **Reanudar con un nuevo trabajo**. Se crea otro `job_id` enlazado al anterior, conservando `extraction_id` y solicitud.

## Verificar y explorar los datos

En **Datos**, seleccione el trabajo terminado, active su perfil original y pulse **Verificar y abrir datos**. El lector comprueba identidad y destino antes de consultar Atlas y vuelve a verificar las páginas y chunks canónicos. Si falta un fragmento, hay alteración, conflicto o evidencia inválida, no abre el conjunto como válido. También puede rechazar un trabajo marcado históricamente como verificado: importa la evidencia actual.

Una lectura satisfactoria muestra periodo solicitado y observado, UTC, proveedor, ajuste, conteo reconstruido y estado de integridad al abrir. **Referencia y capturas canónicas** contiene extracción, hashes, documentos y fechas disponibles. El conteo pertenece a esta lectura; el resultado histórico del core mantiene `bar_count=null`.

**Mostrar desde/hasta (UTC)** filtra el mismo conjunto utilizado por tabla, velas y volumen. Puede ampliar, desplazar y restablecer el gráfico con sus controles. No se rellenan fines de semana ni huecos. Un timestamp repetido con todos los valores OHLCV iguales cuenta una vez, registra el duplicado y conserva sus páginas de origen; valores incompatibles bloquean la lectura. Una extracción vacía válida muestra su referencia y un mensaje sin fabricar datos.

El panel conserva un snapshot en la sesión, con su instante de lectura. Cambiar filtros no consulta de nuevo Atlas. Para comprobar otra vez la evidencia pulse **Verificar y abrir datos**; un fallo retira la vista anterior. La etiqueta de integridad se refiere al instante de lectura, no a una vigilancia continua de la base.

## Diagnósticos habituales

| Situación | Acción |
| --- | --- |
| Perfil o destino no coinciden | Active el nombre, alias, base, plan declarado y clúster originales. Puede renovar credenciales. |
| 401 / credenciales rechazadas | Revise la credencial correspondiente, sin copiarla a mensajes o capturas. |
| 403 / acceso restringido | Compruebe permisos y fechas admitidas para esa operación; no deduzca un plan exacto del código. |
| 429 / límite temporal | Espere antes de otro intento. El motor conserva sus reintentos existentes. |
| Atlas no responde o la lectura falla | Revise red, disponibilidad y permisos de lectura. Un ping satisfactorio no demuestra escritura. |
| Instalación ocupada | Consulte el trabajo activo; no abra un directorio alternativo para eludir el bloqueo. |
| Fragmento ausente o integridad inválida | Investigue el ledger y la ingesta en la base MVP; el dashboard no corrige ni mezcla evidencia automáticamente. |
| Evidencia cambió durante la lectura | Espere a que cese la actividad y vuelva a verificar. |
| Trabajador interrumpido | Consulte el estado y reanude con el perfil original. No borre a mano SQLite ni el archivo de bloqueo. |

## Cierre de la prueba real y límites

Una prueba real completa requiere: extracción pequeña verificada, apertura de sus barras desde el panel y repetición exacta que produzca otro trabajo con el mismo `extraction_id` y modo reutilizado. Registre IDs, estados, fechas, conteo del lector y referencias sin secretos. El [procedimiento de validación](validation.md) conserva esa prueba como pendiente hasta ejecutarla con credenciales.

El MVP es local y carga una extracción en memoria. No incluye IA, brokers, usuarios múltiples, análisis avanzados, cancelación ni colas. Para HBT-CEN-003 quedan validar servicios reales, medir el volumen soportado y acordar el siguiente alcance; este documento no declara esas funciones implementadas.

Referencias de las APIs utilizadas: [Session State](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state), [AppTest](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest) y [velas Plotly](https://plotly.com/python/candlestick-charts/).
