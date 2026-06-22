# Database

`migrations/` contiene DDL versionado aplicable manualmente sobre PostgreSQL. El proyecto no incluye todavía un runner de migraciones; aplica los archivos SQL en orden ascendente.

```powershell
psql "$env:DATABASE_URL" -f database/migrations/001_initial_schema.sql
```
