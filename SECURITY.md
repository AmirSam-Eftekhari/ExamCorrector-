# Security

## Scope

ExamCorrector is designed as a local, single-user application. The bundled web interface binds to `127.0.0.1` and is not intended to be exposed directly to a public network.

## Reporting a security issue

Please do not publish sensitive security details in a public issue. If this project is maintained through a GitHub repository, use the repository's private vulnerability-reporting mechanism when available.

## Local data

ExamCorrector may create local SQLite databases and uploaded files under `data/`. These are runtime artifacts and are intentionally excluded from version control.
