# Origen y selección del motor

Centauro Bridge adapta un extractor existente para convertir una llamada de extracción en un trabajo consultable, independiente del proceso que lo solicita. El primer incremento termina en Application Core; una interfaz gráfica corresponde a HBT-CEN-002.

El origen es el repositorio privado `anthocab2/centauro-atlas-bridge`, en el commit `ca9e9270d4553ebaea80096e019974eae697fe3e`. El 22 de octubre de 2026 se comprobó que `main` seguía en ese commit. No había cambios posteriores que reconciliar. El destino público `anthocab2/Centauro-Bridge` estaba vacío.

Se obtuvieron archivos seleccionados mediante el conector autenticado de GitHub. La historia del origen no es ancestro de ningún commit del destino. `engine-provenance.json` registra los 47 archivos seleccionados y sus hashes de objeto Git de origen. En HBT-CEN-001, 44 se conservaron byte por byte y tres tuvieron adaptaciones explícitas (`config.py`, `pyproject.toml`, `uv.lock`). HBT-CEN-002 separa funciones puras desde cuatro módulos del motor, conservando algoritmos e importaciones públicas, y actualiza dependencias; el manifiesto distingue ambas entregas.

Se incorporan el flujo Massive diario, utilidades de Atlas e ingestion, almacenamiento raw, particionado BSON, ledger canónico, checkpoints, ejecución, recuperación y verificación. También se conservan las pruebas correspondientes: 94 casos unitarios y seis de integración con Atlas. El script de paginación Massive se conserva porque sus pruebas ejercitan recuperación y reconciliación. Las utilidades y CLI anteriores se mantienen como código interno de regresión; el único comando de producto instalado es `centauro-bridge`.

Se excluyen `documents/`, pruebas WKC, `pc/`, scripts de carga ajenos al recorrido seleccionado, documentación privada, datos de investigación y credenciales. SEC/WKC no forma parte del producto inicial. No se trasladan los README ni los documentos de planificación del origen.

Se mantiene `centauro_atlas_bridge` como nombre de importación y Python 3.11 para limitar los cambios de compatibilidad. El nombre del paquete/producto es Centauro Bridge. La adaptación añade coordinación y estados, sin convertir todavía el motor en un extractor independiente de Atlas ni duplicar su persistencia.
