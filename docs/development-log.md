# Registro de desarrollo

## HBT-CEN-001 — 22 de octubre de 2026

- Lectura dirigida de configuración, Massive, Atlas/ingestion y sus pruebas. No se encontraron `AGENTS.md` aplicables en los ancestros del workspace ni en el árbol de origen. Se aplicó MTE v2 según el encargo: lectura acotada, modificaciones localizadas y evidencia de validación.
- Origen comprobado en `ca9e9270d4553ebaea80096e019974eae697fe3e`; destino inicialmente vacío. Se importaron únicamente los archivos consignados en `engine-provenance.json`, con historia nueva y sin documentación/investigación privada.
- Las 94 regresiones unitarias incorporadas pasaron antes de añadir el core. No se borraron ni modificaron para resolver fallos. Las seis pruebas Atlas originales se conservaron con una condición explícita de ejecución externa añadida en `conftest.py`.
- Nueva configuración congelada con referencias públicas y credenciales resueltas antes de crear el proceso. Única adaptación funcional en el motor: evitar dotenv cuando un trabajador recibe configuración explícita.
- Nuevos módulos de aplicación para CLI, validación, diagnósticos, adaptador, coordinación, trabajador y estado SQLite versionado. `portalocker` mantiene exclusión real; `psutil` verifica identidad de proceso más allá del PID.
- Conservación de los algoritmos originales de identidad/hash y persistencia única. Verificación independiente del éxito del transporte. Retorno vacío del extractor aceptado para reutilización/recuperación; ningún conteo de barras a partir de IDs raw.
- Pruebas nuevas de concurrencia entre procesos, supervivencia al cierre del coordinador, interrupción, reanudación, perfil fijo, destino distinto, secretos, 401/403/429, respuestas vacías y corrupción de evidencia.
- La integración sin red ejecuta el extractor y verificador reales con HTTP controlado y MongoDB simulado. `mongomock` 4.3 no acepta el argumento opcional `sort=None` de PyMongo 4.17 en bulk update; la prueba adapta únicamente ese argumento, exige que sea `None` y conserva el resto de la operación. No se modificó el motor por esta limitación del simulador.
- La CLI anterior no se instala como comando público: el punto de entrada del producto es `centauro-bridge`. Las utilidades internas anteriores siguen disponibles para regresión y no son la API de coordinación.
- Credenciales Massive/Atlas no disponibles en el entorno de esta entrega. No se conectó a servicios reales ni se escribió en una base remota. Ver procedimiento pendiente en `validation.md`.
