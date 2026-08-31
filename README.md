# Mosaic

Mosaic is a phased data orchestrator. The repository currently implements only the
Phase 0 application foundation: an installable Python package, validated configuration,
structured logging, and a small HTTP health interface. Persistence, ingestion, query
execution, and the other data capabilities described in the architecture are not part of
Phase 0.

## Prerequisites

- [Git](https://git-scm.com/)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

Mosaic pins its development interpreter in `.python-version`. `uv sync` uses that pin and
can install the interpreter when it is not already available.

## Install from a clean clone

```shell
git clone git@github.com:Krotau/Mosaic.git
cd Mosaic
uv sync --locked
cp .env.example .env
```

`uv sync --locked` creates an isolated `.venv`, installs Mosaic from the `src` layout,
and refuses to update a stale lockfile. The example environment contains only non-secret
settings. Do not commit `.env` or credentials.

## Run the application

```shell
uv run uvicorn mosaic.app:app --reload
```

The server listens on `http://127.0.0.1:8000` by default. Check application availability
from another terminal:

```shell
curl --fail http://127.0.0.1:8000/health
```

Reloading is a local-development convenience. Omit `--reload` when checking the normal
server process:

```shell
uv run uvicorn mosaic.app:app
```

The health operation reports only that the Phase 0 application is available. It does not
report database, blob-storage, or analytical-engine readiness because those integrations
do not exist in this phase.

## Configuration

Configuration is read once when the application is constructed. Environment variables
override values from the local `.env` file.

| Variable | Allowed values | Default | Purpose |
|---|---|---|---|
| `MOSAIC_ENVIRONMENT` | `development`, `test`, `production` | `development` | Selects the runtime environment. |
| `MOSAIC_LOG_LEVEL` | `debug`, `info`, `warning`, `error`, `critical` | `info` | Sets the minimum structured-log level. |

Values are case-insensitive. Invalid values fail during settings construction with a
validation error.

## Verify a change

Run every gate from the repository root:

```shell
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
uv build
uv run python -c "from mosaic.app import app; assert app.title == 'Mosaic'"
git status --short
```

Each command is an independent acceptance gate:

- `ruff format --check` verifies formatting without modifying files.
- `ruff check` runs lint and import-order checks.
- `mypy` performs strict static type checking over project and test code.
- `pytest` runs behavior and packaging tests.
- `uv build` creates both the source distribution and wheel from package metadata.
- The direct import constructs the same `mosaic.app:app` target used by Uvicorn.
- `git status --short` must produce no output; environments, caches, and distributions are
  generated locally but ignored.

Complete the real-process smoke check by starting `uv run uvicorn mosaic.app:app` and
requesting `curl --fail http://127.0.0.1:8000/health` from another terminal, as shown in
[Run the application](#run-the-application). CI automates the same startup, readiness,
response, and shutdown sequence.

To apply the formatter before repeating the checks, run:

```shell
uv run ruff format .
```

## Architecture

- [Control plane and data plane](docs/architecture/control-and-data-plane.md)
- [Module map](docs/architecture/module-map.md)
- [ADR 0001: Phase 0 foundation](docs/adr/0001-phase-0-foundation.md)
- [Architecture review and projected file blueprint](ARCHITECTURE_REVIEW.md)
- [Phase 0 specification index](docs/specs/phase-0.md)

The architecture review is a companion design source. The shorter documents above record
the Phase 0 boundary and the decisions contributors need when changing the runnable
foundation.
