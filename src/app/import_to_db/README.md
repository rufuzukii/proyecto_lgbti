# Importación y persistencia

El paquete transforma fuentes FRA, ILGA y FELGTBI+ en documentos normalizados. La subida normal
registra una revisión pendiente en PostgreSQL y solo una aprobación administrativa persiste el
contenido en MongoDB.

## Flujo efectivo

1. La página de subida valida tamaño, extensión, MIME, firma y esquema.
2. El importador de la fuente construye el payload normalizado.
3. `register_pending_import()` guarda temporalmente el payload en `import_logs`.
4. `/admin/imports` permite revisar, aprobar o descartar.
5. La aprobación persiste, invalida la caché y elimina la fila pendiente.

La API FastAPI de importación sigue el mismo principio: devuelve HTTP 202 y nunca salta la
revisión ni modifica el catálogo FRA antes de aprobar.

## Módulos comunes

- `utils.py`: celdas, cabeceras y números normalizados.
- `import_log.py`: alta, lectura y eliminación de revisiones pendientes.
- `fra/`: CSV FRA, metadatos `Source:`, `survey_year`, catálogo y MongoDB.
- `ilga/`: Rainbow Map CSV/JSON anual.
- `felgtbi/`: validación PDF, lectura, semántica, almacenamiento y persistencia.

El antiguo `ImportErrorHandler` sin consumidores y el helper duplicado `test_connection()` se
eliminaron. El health check central es la única comprobación de conectividad. Las excepciones
técnicas se registran en servidor y las capas de presentación muestran mensajes genéricos.
