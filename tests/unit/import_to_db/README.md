# Pruebas de importación

## `test_fra_questions_payload.py`

Comprueba agrupación por código/pregunta, separación de categoría específica, conservación de filtros, generación de documentos distintos, conversión a `ObjectId` y upsert Mongo sin mezclar `answers` en `$setOnInsert`.

## `test_ilga_importer.py`

Comprueba el documento anual ILGA, coma decimal, criterios/pesos y el upsert inmutable por año.

Las conexiones MongoDB se sustituyen por mocks; las pruebas no escriben en bases reales.
