# Security

## Scope

ExamCorrector is designed as a local, single-user application. The bundled web interface binds to `127.0.0.1` and is not intended to be exposed directly to a public network.

## Local data

ExamCorrector may create local SQLite databases and uploaded files under `data/`. These are runtime artifacts and are intentionally excluded from version control.