# ADR 0001: Phase 0 application foundation

- Status: Accepted
- Date: 2026-08-31

## Context

Mosaic begins with an approved deep-Module architecture but no shared application or
developer workflow. Later phases need a reproducible Python foundation without committing
Phase 0 to persistence, storage, or analytical-engine interfaces before their behavior can
be tested.

## Decision

### Runtime and dependency workflow

Use standard CPython 3.12 with a repository pin and a `src`-layout installable package. Use
uv to create the environment, resolve dependencies, and enforce the committed lockfile.
Direct runtime dependencies are FastAPI, Uvicorn, Pydantic Settings, and structlog.
HTTPX, pytest, Ruff, and mypy are development dependencies.

The project configuration is centralized in `pyproject.toml`; resolved versions live in
`uv.lock`. Generated environments, caches, secrets, and build output remain untracked.

### Application construction

Use one explicit composition root to construct the FastAPI application. It receives a
validated settings object and is the locality where concrete framework setup, logging, and
future adapters are selected. The package root has minimal intentional exports and does
not construct the framework.

### Configuration and logging

Construct configuration once from environment-backed Pydantic settings and inject it into
application construction. Use the `MOSAIC_` prefix. Phase 0 settings cover only runtime
environment and log level; no database, storage, or analytical-engine configuration is
invented.

Configure structlog at the composition boundary and emit structured event and level fields.
Lifecycle events use the same logging setup. Settings representations and the committed
environment example contain no secrets.

### Verification seams

Use the HTTP interface produced by the application factory as the highest Phase 0 behavior
seam. Exercise it in process with HTTPX rather than launching a network server. Test
settings and logging through their public construction and configuration interfaces, not
private helper order.

Formatting checks, linting, strict type checking, and tests remain separate acceptance
gates. Passing one does not stand in for another.

### Deferred integrations

Do not scaffold or depend on Turso/libSQL, PostgreSQL, PyArrow, DuckDB, SQLGlot, PyIceberg,
or blob-storage clients in Phase 0. These are version-sensitive integrations whose useful
seams and compatibility constraints must be verified when their owning phase begins.
Likewise, do not create empty future packages for Control Plane, Ingestion, Scope
Resolution, Query Execution, Publication, Subscriptions, or Profiling.

## Consequences

- A clean clone has one locked install workflow and a consistent set of verification
  commands.
- Tests import the installed `src` package instead of succeeding through repository-root
  path behavior.
- Application construction is repeatable and future adapter selection has one location.
- Environment access and logging policy do not spread through HTTP or future domain code.
- The Phase 0 health interface can establish application availability, but it cannot imply
  readiness for systems that have not been introduced.
- Later specifications retain responsibility for proving real persistence, storage, and
  execution seams. Adding one will require a new decision or an amendment grounded in that
  phase's tests.
- The committed lockfile favors reproducibility; dependency upgrades are intentional work
  that must rerun all verification gates and relevant compatibility checks.

## Alternatives considered

### Scaffold the projected repository tree immediately

Rejected because empty packages would turn guesses into apparent interfaces and encourage
shallow Modules. Documentation records expected ownership until executable behavior earns
the files.

### Expose repositories and transaction management to callers

Rejected because callers would coordinate invariants and persistence details themselves.
Domain-shaped Module interfaces provide more depth and keep changes local.

### Read environment variables throughout the application

Rejected because validation timing, defaults, and test setup would become distributed.
One settings construction seam makes configuration explicit and injectable.

### Add later-phase libraries to the initial lockfile

Rejected because unused dependencies would expand compatibility and maintenance work
without proving an interface. Each owning phase will select and verify the minimum set it
needs.
