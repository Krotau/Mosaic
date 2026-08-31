# Architecture Review: Phased Data Orchestrator

**Status:** Companion review  
**Date:** 2026-08-31  
**Source reviewed:** `Build a phased Data Orchestrator in Python.md`

## Purpose

This document reviews and strengthens the source plan without replacing it. The source plan remains the delivery sequence and requirements baseline. The recommendations below preserve its phases while changing how the code is divided, where interfaces live, and which decisions should be made earlier.

The central recommendation is to organize Mosaic around a small set of deep modules. Each module should expose a domain-shaped interface while hiding persistence, transactions, framework details, and execution-library details in its implementation. This gives callers leverage and keeps changes local.

## Executive assessment

The source plan has a strong domain model and a sensible incremental delivery strategy. In particular, it correctly separates the control plane from the data plane, distinguishes Registration from Scope, makes ScopeContribution a first-class concept, preserves raw input and provenance, separates arrival order from logical order, and delegates established problems to PyArrow, DuckDB, SQLGlot, and PyIceberg.

The main architectural risk is not the domain model; it is the suggested code shape. The proposed top-level folders are mostly technical layers (`repositories`, `transactions`, `storage`, `query`, and `jobs`) with many entity-sized files. If followed literally, that layout encourages shallow modules: a workflow would cross several interfaces and callers would need to coordinate repositories, transactions, storage, validation, and state transitions themselves.

Mosaic should instead expose a few domain-capability interfaces:

1. Control Plane
2. Ingestion
3. Scope Resolution
4. Query Execution
5. Publication
6. Subscriptions, when Phase 9 begins

These are module candidates, not a requirement for six classes. A module may be a package with one public facade and a substantial private implementation. Internal seams are appropriate where behaviour actually varies or where fault injection is required. They should not leak into the external interface.

## What the source plan gets right

The following decisions should remain intact.

### Domain distinctions

- Provider identity is immutable and separate from mutable display metadata.
- A Registration is an independently managed source stream, not a Scope.
- Registration schemas and Scope schemas evolve independently.
- ScopeContribution correctly models the many-to-many relationship between Registrations and Scopes.
- APPEND, ENRICH, and DERIVE describe different contribution semantics and must not collapse into one generic mapping operation.
- Mapping revisions are independent from schema revisions.
- ENRICH requires deterministic identity mapping rather than guessed entity resolution.

### Data correctness

- Raw data is immutable and remains distinct from validated, mapped, or published data.
- Network chunks are transport details, not logical ingest events.
- Partial uploads are never query-visible.
- `event_time`, `produced_at`, `received_at`, `sequence`, and `committed_at` remain separate concepts.
- A sequence watermark is monotonic and may lag physically received data.
- Idempotency, commit-once behaviour, and snapshot consistency are explicit invariants.
- Invalid batches are quarantined atomically instead of silently losing rows.

### Use of existing libraries

- PyArrow is the canonical in-process tabular representation.
- DuckDB owns relational execution.
- SQLGlot owns parsing and syntactic inspection.
- PyIceberg owns durable analytical table semantics.
- FastAPI and Pydantic belong at the HTTP seam, not inside bulk row processing.
- The control-plane database is not used as bulk-data storage.

### Delivery discipline

- Each phase ends with verification and documentation.
- Later infrastructure is explicitly excluded from early phases.
- Query planning is implemented before exposing consumer SQL.
- Publication and subscriptions are delayed until their domain requirements can be exercised.

## Recommended deep modules

The examples below illustrate interface shape. Exact Python names can be chosen during implementation. An interface includes more than method names: invariants, ordering requirements, errors, configuration, and performance expectations are part of it.

### 1. Control Plane module

**Responsibility:** Own authoritative metadata and invariants for Providers, Registrations, schema versions, Scopes, contributions, mappings, and their active revisions.

**External interface:** Accept typed commands and answer typed reads. A compact shape could be:

```python
class ControlPlane:
    def execute(self, command: ControlCommand) -> ControlResult: ...
    def read(self, query: ControlQuery) -> ControlView: ...
    def resolve_snapshot(self, request: SnapshotRequest) -> ControlSnapshot: ...
```

Using command and query types does not eliminate domain concepts; it prevents persistence operations and transaction lifecycles from becoming the caller's interface. If explicit methods prove clearer than command variants, prefer them. The goal is not a three-method class at any cost; the goal is that callers express domain intent rather than coordinating tables.

**Implementation hides:**

- transaction start, retry, commit, and rollback;
- Turso/libSQL and PostgreSQL differences;
- uniqueness and foreign-key handling;
- optimistic or pessimistic concurrency choices;
- schema and mapping revision persistence;
- conversion of database failures into stable domain errors.

**Internal seams:** A control-state persistence seam is justified because Turso/libSQL and PostgreSQL are two real adapters. Tests should run the same Control Plane interface contract against both. Avoid a public repository per entity; that would expose a broad, shallow interface and move invariant coordination into callers.

### 2. Ingestion module

**Responsibility:** Own the lifecycle from upload session creation through immutable raw storage, validation, quarantine, commit, sequence visibility, and watermark advancement.

**External provider-facing interface:**

```python
class Ingestion:
    def begin(self, request: BeginIngest) -> IngestSessionView: ...
    def append(self, session_id: SessionId, chunk: UploadChunk) -> ChunkReceipt: ...
    def finalize(self, session_id: SessionId) -> FinalizeResult: ...
```

Validation and commit may later run asynchronously, but that worker mechanism should be an internal seam. The external interface should expose stable state and outcomes rather than a sequence of implementation steps that callers must invoke in the right order.

**Implementation hides:**

- staging paths and object naming;
- checksums and chunk assembly;
- Arrow decoding and structural validation;
- state-machine transitions;
- idempotency conflict handling;
- quarantine records;
- sequence-gap bookkeeping;
- atomic metadata visibility;
- transaction retries and storage cleanup.

**Internal seams:** Blob storage is an internal seam. A production local-files adapter plus a fault-injecting test adapter are useful because interrupted upload and partial-write behaviour are essential tests. Add an object-storage adapter only when cloud storage is implemented. Arrow conversion is normally an internal implementation detail unless two genuinely different input formats require adapters.

### 3. Scope Resolution module

**Responsibility:** Convert a requested logical Scope projection and a pinned metadata snapshot into an immutable physical plan.

**External interface:**

```python
class ScopeResolver:
    def plan(self, request: ScopePlanRequest) -> ScopeQueryPlan: ...
```

`ScopePlanRequest` should contain the logical Scope, requested fields, authorization context, and consistency requirements. `ScopeQueryPlan` should contain only resolved, immutable facts: contribution revisions, source fields, mappings, join/union semantics, object or table references, visible positions, and provenance requirements.

This is a real module rather than a helper because both Query Execution and Publication can eventually call it. Its single operation carries substantial domain behaviour, which gives the interface high leverage.

**Implementation hides:**

- contribution selection;
- APPEND compatibility rules;
- ENRICH identity and cardinality rules;
- field-level source selection;
- mapping revision selection;
- activation intervals;
- watermark and snapshot pinning;
- virtual versus materialized source selection.

### 4. Query Execution module

**Responsibility:** Safely execute consumer SQL over logical Scopes and return Arrow results.

**External interface:**

```python
class QueryEngine:
    def execute(self, request: QueryRequest) -> QueryResult: ...
```

`QueryResult` may expose a `RecordBatchReader` plus query metadata. The caller should not separately invoke SQLGlot, Scope Resolution, relation construction, DuckDB, or result conversion.

**Implementation hides:**

- SQLGlot parsing and policy checks;
- extraction of logical Scope and field requirements;
- calls to Scope Resolution;
- DuckDB relation registration and name rewriting;
- parameter binding;
- time, memory, and output limits;
- cancellation;
- Arrow streaming;
- cleanup of an isolated DuckDB execution context.

DuckDB is an implementation dependency, not automatically a seam. Until a second execution engine is genuinely required, a public `QueryExecutor` port would be hypothetical indirection. Keep DuckDB-specific code private and focused so it can be extracted later if a real second adapter appears.

### 5. Publication module

**Responsibility:** Publish selected resolved data into durable Iceberg-backed representations while retaining lineage and stable field identity.

**External interface:**

```python
class Publisher:
    def publish(self, request: PublicationRequest) -> PublicationResult: ...
```

**Implementation hides:**

- PyIceberg catalog and storage configuration;
- Arrow-to-Iceberg schema translation;
- stable field-ID assignment;
- snapshot commit and retry behaviour;
- additive evolution and rename handling;
- source-to-snapshot lineage;
- orphan-file recovery.

PyIceberg should remain private to this module and the relation-reading implementation used by Query Execution. Do not create an abstract analytical-table interface in Phase 0. Its useful shape will only be known after virtual and materialized execution both exist.

### 6. Subscription module

Introduce this module in Phase 9 rather than creating an empty placeholder in Phase 0.

**Responsibility:** Own subscription definitions, independent contribution cursors, leasing or worker coordination, and transactional cursor advancement.

Its interface should describe consumption intent and acknowledgement. It must not expose database transactions or imply one global Scope sequence. Whether it reads via Query Execution, Scope Resolution, or a dedicated change reader should be decided from Phase 9 use cases rather than guessed now.

## Seam and adapter strategy

### Real seams to establish early

1. **Control-state persistence:** Turso/libSQL and PostgreSQL are explicitly required adapters. The seam belongs inside the Control Plane and Ingestion implementations, not in HTTP handlers.
2. **Blob storage:** Local storage and a fault-injecting test adapter justify an internal seam in Phase 3. A cloud adapter can be added later without changing the Ingestion interface.
3. **Clock and identifier generation:** Deterministic test adapters are useful for lifecycle timestamps, activation intervals, and immutable identifiers. Keep these internal.

### Seams that should remain internal

- SQLGlot parsing and DuckDB execution inside Query Execution.
- PyArrow decoding and validation inside Ingestion.
- PyIceberg operations inside Publication.
- retry classification inside persistence adapters.
- HTTP request/response conversion at the FastAPI seam.

### Hypothetical seams to avoid

- one repository interface for every domain entity;
- a generic query-engine port with only a DuckDB adapter;
- a generic table-format port with only a PyIceberg adapter;
- a matcher interface before multiple profiling strategies need independent replacement;
- event-bus interfaces before asynchronous delivery is required;
- empty packages for future jobs, events, and processing.

The deletion test is useful here. Deleting a generic `ProviderRepository` should not merely move five CRUD statements into a handler. Deleting the Control Plane module should cause transaction handling, revision selection, uniqueness rules, error translation, and concurrency logic to reappear across many callers. That indicates that the deeper module is earning its place.

## Recommended package structure

Create packages when their phase begins. Do not scaffold every future directory in Phase 0.

```text
src/mosaic/
├── app.py                         # composition root and FastAPI creation
├── config.py
├── control_plane/
│   ├── __init__.py                # deliberately small public interface
│   ├── interface.py               # commands, reads, results, errors
│   ├── model.py                   # cohesive domain types and invariants
│   ├── implementation.py
│   ├── migrations/
│   └── _adapters/
│       ├── libsql.py
│       └── postgres.py
├── ingestion/
│   ├── __init__.py
│   ├── interface.py
│   ├── model.py
│   ├── implementation.py
│   └── _adapters/
│       ├── local_blob.py
│       └── faulting_blob.py       # test-only
├── scopes/
│   ├── __init__.py
│   ├── interface.py
│   ├── plan.py
│   └── resolver.py
├── query/
│   ├── __init__.py
│   ├── interface.py
│   ├── implementation.py
│   ├── policy.py
│   └── _duckdb.py
├── publication/                   # add in Phase 8
├── subscriptions/                 # add in Phase 9
└── http/
    ├── providers.py
    ├── registrations.py
    ├── ingest.py
    └── query.py
```

This layout is illustrative rather than prescriptive. Files should split when they improve locality, not to achieve one file per noun. Private adapter folders make it clear that callers do not depend on persistence or engine interfaces. The composition root is the only place that should know which concrete adapters are selected from configuration.

## Transaction ownership and cross-module workflows

### Keep transactions behind module interfaces

Callers should never do this:

```python
with transaction_manager.transaction() as tx:
    registrations.save(tx, registration)
    schemas.activate(tx, schema)
    watermarks.advance(tx, position)
```

That interface requires the caller to know ordering, invariants, retry semantics, and storage layout. Instead, one domain operation should own the full transaction and retry it as a whole.

Persistence adapters may have different locking behaviour. The module interface should promise common outcomes and invariants, not identical SQL or lock acquisition.

### Do not attempt a database/blob distributed transaction

Ingestion spans control-state persistence and blob storage. Avoid a two-phase commit. A safer workflow is:

1. Write chunks to an uncommitted staging location.
2. Finalize and checksum an immutable raw object.
3. Validate from that immutable object.
4. Commit a metadata record that points to it in one control-plane transaction.
5. Make visibility depend only on committed metadata.
6. Reconcile unreferenced staged or finalized objects with an idempotent cleanup job.

This makes partial and failed work recoverable while preserving atomic consumer visibility.

### Return immutable snapshots across modules

Scope Resolution should receive or acquire one immutable `ControlSnapshot`. Query Execution pins the resulting `ScopeQueryPlan` for the whole query. No downstream code should re-read active mappings or watermarks midway through execution.

The snapshot should carry explicit revision and commit identifiers. Time alone is insufficient because clocks may collide or be reordered.

## Domain decisions missing from the source plan

The following questions should be resolved before or during the indicated phase. They are not reasons to delay Phase 0.

### ENRICH merge semantics — decide before Phase 5

Deterministic key mapping is necessary but not sufficient. Define:

- whether each contribution must be one-to-one or may be one-to-many;
- what happens when a contribution contains duplicate Scope keys;
- whether multiple contributions may map to the same canonical field;
- precedence or conflict behaviour when values disagree;
- whether null means “no value” or an explicit value that can overwrite another;
- whether an unmatched enriching record is omitted, retained separately, or produces a sparse Scope record.

Without these rules, two correct implementations can return different query results.

### Sequence origin and gap policy — decide before Phase 4

For a SEQUENCE Registration, define the initial expected position. “First seen becomes the start” and “registration declares its start” have different failure modes. Also define whether a missing position can be administratively skipped, how that decision is audited, and whether a duplicate sequence with a different payload is a conflict.

Model physically committed and ordered-visible states separately. A batch at sequence 101 may be durably committed while remaining invisible until 100 closes the gap.

### Idempotency conflict semantics — decide before Phase 3

Retrying the same message identifier with the same content should return the original logical result. Reusing it with a different checksum, schema version, sequence, or registration should raise a stable conflict rather than silently returning success.

### Initial input formats — decide before Phase 3

Select a deliberately small first contract, preferably Arrow IPC streaming if provider constraints allow it. Supporting CSV, JSON, Parquet, and Arrow simultaneously multiplies parsing, type-coercion, error-reporting, and streaming semantics. Raw storage can retain any bytes, but validation needs a declared format and format version.

### Canonical schema fingerprint — decide before Phase 2

Version the fingerprint algorithm itself. Define which Arrow schema properties participate, how metadata is ordered, and how library-version changes are handled. A fingerprint is a stable protocol fact once persisted, not merely `hash(str(schema))`.

### SQL semantics and authorization — decide before Phase 7

Requested-field extraction must account for `*`, aliases, expressions, functions, CTEs, subqueries, and joins between Scopes. Resolve names against Scope schemas rather than relying on syntactic column collection alone.

Authorization should be applied to the resolved logical plan before relations are registered with DuckDB. DuckDB should run in an isolated, locked-down context with no arbitrary filesystem, extension, attach, or network access. Use bound parameters; never authorize through SQL string concatenation.

### Provenance granularity — decide incrementally

Record-level provenance for APPEND and field/value-level provenance for ENRICH have very different storage costs. Define the minimum queryable lineage required in Phase 5, then design a compact representation. Do not promise universal field-level provenance without a cost and retention model.

## Testing strategy

The interface is the primary test surface. Tests should exercise behaviour through the same interface used by production callers.

### Contract suites

- Run the Control Plane contract against both database adapters.
- Run Ingestion lifecycle and failure contracts against local and fault-injecting blob adapters.
- Run Scope Resolution as pure or mostly in-process tests using immutable snapshots.
- Run Query Execution end-to-end with SQL text, logical Scope fixtures, and Arrow results.
- Run Publication against a real local Iceberg setup once that module exists.

### Test observable outcomes

Assert returned results, durable public state, visibility, and stable errors. Avoid asserting private SQL calls, helper invocation order, private object layout, or internal repository methods.

### Concurrency tests

Use deterministic coordination primitives such as barriers and explicit transaction hooks rather than timing sleeps. Test the same invariant under both database adapters, while allowing the adapters to use different isolation and retry strategies.

High-value model-based or property tests include:

- watermark monotonicity over arbitrary receipt/commit orders;
- at-most-once logical commit under retries;
- legal ingest state transitions;
- stable Scope plans for a pinned snapshot;
- additive Scope evolution preserving old records;
- cursor monotonicity and upper bounds.

When a deep module replaces a cluster of shallow helpers, remove redundant helper-level tests. Layering both sets of tests would increase maintenance without increasing confidence.

## Phase-by-phase amendments

### Phase 0 — Project foundation

- Establish only the composition root, configuration, HTTP health interface, test tooling, and documentation.
- Record the deep-module direction in the initial ADR.
- Do not create empty packages for all later phases.
- Document supported Python and dependency versions, but verify version-sensitive combinations in small executable spikes rather than asserting compatibility from documentation alone.
- Include actor/request context in external request models even if authorization is permissive initially; retrofitting identity into every interface in Phase 11 would be disruptive.

### Phase 1 — Control-plane persistence

- Build the Control Plane module, not a public repository collection.
- Keep the database seam internal and run one module contract suite against both adapters.
- Make the whole domain command the retry unit.
- Use database constraints as a second line of defence, then translate adapter-specific failures into stable domain outcomes.
- Allow adapter-specific migrations where required; portability of behaviour matters more than forcing every database through identical SQL.

### Phase 2 — Provider, Registration, and Schema HTTP interfaces

- Implement FastAPI routes as thin adapters over the Control Plane interface.
- Keep Pydantic types at the HTTP seam and use domain types internally.
- Treat schema fingerprint format and version as persisted protocol decisions.
- Return stable conflict errors for duplicate-but-different schema submissions.

### Phase 3 — Ingest sessions and raw storage

- Introduce the Ingestion module with its stable lifecycle interface.
- Keep chunk paths, staging rules, and BlobStore details private.
- Define idempotency mismatch behaviour and the first accepted payload format.
- Make cleanup and recovery idempotent from the beginning, even if initially invoked manually.

### Phase 4 — Validation and commit

- Deepen the existing Ingestion implementation rather than exposing validation, commit, and watermark modules to callers.
- Distinguish durable commit from ordered visibility in names and returned state.
- Define sequence origin and administrative gap policy.
- Exercise validation and concurrency through `finalize` or an internal worker interface, not by testing private helpers.

### Phase 5 — Scope and contribution semantics

- Keep authoring and activation of Scope metadata in the Control Plane module.
- Specify ENRICH cardinality, duplicate-key, null, and field-conflict semantics.
- Store mapping revisions and activation as immutable revisions selected atomically.
- Avoid a generic mapping engine; implement the three contribution modes as explicit domain behaviour.

### Phase 6 — Scope resolution

- Add the one-operation Scope Resolution module.
- Make `ScopeQueryPlan` immutable and serializable enough for diagnostics.
- Keep execution-engine concepts out of the logical plan where possible.
- Include pinned revision identifiers, visible positions, and provenance requirements in the plan.

### Phase 7 — SQL query interface

- Add one deep Query Execution interface over SQLGlot, Scope Resolution, and DuckDB.
- Introduce query limits, cancellation, and isolated execution here rather than postponing all of them to Phase 11.
- Test complex name resolution and Scope authorization before relation registration.
- Return Arrow streaming results without leaking the lifetime of a global DuckDB connection.

### Phase 8 — PyIceberg publication

- Introduce Publication only now.
- Preserve the Query Execution interface while adding materialized source selection behind Scope Resolution and relation construction.
- Record field-ID allocation and rename rules in an ADR before persisting the first Iceberg schema.
- Treat failed metadata commits and orphan files as normal recoverable outcomes.

### Phase 9 — Subscriptions and cursors

- Introduce a separate Subscription module based on concrete consumption use cases.
- Keep cursor transactions and worker leases behind its interface.
- Reuse immutable Scope snapshots and contribution positions; do not infer a global Scope sequence.

### Phase 10 — Profiling and mapping proposals

- Keep profiling computation separate from approval and activation, which remain Control Plane commands.
- Use internal deterministic strategies first.
- Introduce a matcher seam only when at least two adapters or independently replaceable strategies are real.
- Store proposal inputs and algorithm versions so proposals are reproducible.

### Phase 11 — Hardening

- Treat this phase as expansion, not the first appearance of security and resource safety.
- Actor context, stable audit facts, query isolation, and basic limits should already exist at the phases where their interfaces are introduced.
- Add production-grade credential management, policy sophistication, observability, maintenance automation, and stress testing here.

## Recommended ADRs

Write ADRs when the corresponding decision becomes active:

1. Module interfaces and composition root — Phase 0
2. Control-state persistence seam and transaction retry contract — Phase 1
3. Canonical Arrow schema representation and fingerprint version — Phase 2
4. Raw object lifecycle, idempotency conflicts, and recovery — Phase 3
5. Sequence origin, gap handling, and visibility — Phase 4
6. APPEND and ENRICH merge semantics — Phase 5
7. Immutable ScopeQueryPlan and snapshot consistency — Phase 6
8. SQL policy, authorization, and DuckDB isolation — Phase 7
9. Iceberg field-ID and publication commit rules — Phase 8
10. Subscription cursor model — Phase 9

An ADR should state the decision and consequences, not duplicate the whole phase specification.

## Prioritized recommendations

### Adopt now

- Organize the code around deep domain modules rather than technical layers.
- Keep transaction and repository mechanics behind module interfaces.
- Use a single composition root to select concrete adapters.
- Treat immutable snapshots and stable domain errors as interface concepts.
- Create packages only when a phase needs them.
- Move basic security context and query resource safety earlier than Phase 11.

### Decide before the relevant phase

- schema fingerprint protocol;
- ingest payload formats;
- idempotency mismatch behaviour;
- sequence origin and gap administration;
- ENRICH cardinality and conflict semantics;
- provenance granularity;
- SQL name resolution and authorization rules;
- Iceberg field-ID allocation.

### Avoid

- public CRUD repositories per entity;
- callers controlling transaction scopes;
- generic ports with only one adapter;
- empty future-facing packages;
- a shared “utilities” module that collects cross-domain logic;
- passing Pydantic models, raw dictionaries, or database rows through the whole system;
- testing private helpers when the same behaviour is observable through a module interface.

## Suggested success criterion for the architecture

For each phase, a caller should be able to use the new capability through one domain-shaped interface without knowing which database, storage layout, parser, or execution engine implements it. Tests should cross that same seam. If a persistence or execution change requires edits across HTTP handlers and domain workflows, the module is too shallow. If the change remains inside one implementation and its adapter contract, the design is delivering leverage and locality.

# Appendix A — Projected file blueprint

## How to read this appendix

This is the first foreseeable file map for Phases 0–11. It is not a command to scaffold the complete tree in Phase 0. Each path is tagged with the first phase in which it earns its place:

- `[P0]` through `[P11]` identify the first phase that needs the file.
- `[generated]` identifies a file produced by a chosen tool but committed for reproducibility.
- `[optional]` identifies a path that depends on a deployment or workflow decision not yet made.
- `[split later]` identifies a possible future file or nested Module, not something to create initially.

The word **Module** in this review is scale-agnostic: it can be a function, class, Python module, package, or tier-spanning slice with one interface. In the tree below, **Python module** specifically means a `.py` file. A Python module can start as the complete implementation of a Module and later become a package containing a deeper internal Module without changing what callers know.

The tree is intentionally provisional. It enumerates what can be predicted from the source plan, but implementation discoveries can still merge, rename, add, or remove files. The governing rule is locality: create a file when it owns a coherent body of knowledge, not because every domain noun deserves one.

## Projected repository tree

```text
Mosaic/
├── ARCHITECTURE_REVIEW.md                         # current companion review
├── README.md                                      # [P0] product, architecture, setup, commands
├── pyproject.toml                                 # [P0] package metadata and tool configuration
├── uv.lock                                        # [P0][generated] provisional; use chosen tool's lockfile
├── .python-version                                # [P0][optional] local runtime selection
├── .env.example                                   # [P0] documented non-secret configuration
├── .gitignore                                     # [P0]
├── .github/
│   └── workflows/
│       └── ci.yml                                 # [P0] locked install and acceptance gates
├── compose.yaml                                   # [P1][optional] local PostgreSQL contract tests
├── Dockerfile                                     # [P11][optional] only when deployment target is known
│
├── docs/
│   ├── architecture/
│   │   ├── control-and-data-plane.md              # [P0]
│   │   ├── module-map.md                          # [P0] interfaces, dependencies, ownership
│   │   ├── ingest-lifecycle.md                    # [P3]
│   │   ├── scope-resolution.md                    # [P6]
│   │   ├── query-execution.md                     # [P7]
│   │   └── lineage.md                             # [P8]
│   ├── adr/
│   │   ├── 0001-initial-stack.md                  # [P0]
│   │   ├── 0002-control-state-transactions.md     # [P1]
│   │   ├── 0003-arrow-schema-fingerprints.md      # [P2]
│   │   ├── 0004-raw-object-lifecycle.md           # [P3]
│   │   ├── 0005-sequence-visibility.md            # [P4]
│   │   ├── 0006-scope-contribution-semantics.md   # [P5]
│   │   ├── 0007-scope-query-plan.md               # [P6]
│   │   ├── 0008-sql-policy-and-isolation.md       # [P7]
│   │   ├── 0009-iceberg-field-identity.md         # [P8]
│   │   └── 0010-subscription-cursors.md           # [P9]
│   └── runbooks/
│       ├── quarantine.md                          # [P11]
│       ├── stuck-ingest.md                        # [P11]
│       ├── storage-reconciliation.md              # [P11]
│       └── iceberg-maintenance.md                 # [P11]
│
├── src/
│   └── mosaic/
│       ├── __init__.py                            # [P0] package version; minimal exports
│       ├── app.py                                 # [P0] composition root and FastAPI construction
│       ├── config.py                              # [P0] validated environment configuration
│       ├── log_config.py                          # [P0] structured logging setup
│       ├── identifiers.py                         # [P1] shared typed immutable identifiers
│       ├── clock.py                               # [P1] Clock interface and production adapter
│       │
│       ├── http/
│       │   ├── __init__.py                        # [P0]
│       │   ├── health.py                          # [P0]
│       │   ├── errors.py                          # [P2] domain-error to HTTP-result mapping
│       │   ├── context.py                         # [P2] actor, request, correlation context
│       │   ├── providers.py                       # [P2] provider request/response adapter
│       │   ├── registrations.py                   # [P2] registration request/response adapter
│       │   ├── schemas.py                         # [P2] schema request/response adapter
│       │   ├── ingest.py                          # [P3] upload and ingest-session adapter
│       │   ├── scopes.py                          # [P5] Scope and contribution adapter
│       │   ├── query.py                           # [P7] consumer SQL and Arrow streaming adapter
│       │   ├── subscriptions.py                   # [P9]
│       │   ├── profiling.py                       # [P10]
│       │   └── administration.py                  # [P11] quarantine and lineage operations
│       │
│       ├── control_plane/
│       │   ├── __init__.py                        # [P1] intentional public exports only
│       │   ├── interface.py                       # [P1] commands, reads, results, guarantees
│       │   ├── model.py                           # [P1] cohesive state and invariants
│       │   ├── errors.py                          # [P1] stable caller-visible errors
│       │   ├── implementation.py                  # [P1] command/read orchestration
│       │   ├── _store.py                          # [P1] private persistence seam
│       │   ├── _migrations.py                     # [P1] migration discovery and execution
│       │   ├── schema_codec.py                    # [P2] Arrow schema serialization/fingerprint
│       │   ├── scope_rules.py                     # [P5] contribution/schema activation rules
│       │   ├── snapshots.py                       # [P6] atomic immutable snapshot construction
│       │   ├── _adapters/
│       │   │   ├── __init__.py                    # [P1]
│       │   │   ├── libsql.py                      # [P1] local control-state adapter
│       │   │   └── postgres.py                    # [P1] cloud control-state adapter
│       │   └── migrations/
│       │       ├── libsql/
│       │       │   ├── 0001_catalog.sql           # [P1]
│       │       │   ├── 0002_ingestion.sql         # [P3]
│       │       │   ├── 0003_scope_revisions.sql   # [P5]
│       │       │   ├── 0004_publications.sql      # [P8]
│       │       │   ├── 0005_subscriptions.sql     # [P9]
│       │       │   └── 0006_hardening.sql         # [P11]
│       │       └── postgres/
│       │           ├── 0001_catalog.sql           # [P1]
│       │           ├── 0002_ingestion.sql         # [P3]
│       │           ├── 0003_scope_revisions.sql   # [P5]
│       │           ├── 0004_publications.sql      # [P8]
│       │           ├── 0005_subscriptions.sql     # [P9]
│       │           └── 0006_hardening.sql         # [P11]
│       │
│       ├── ingestion/
│       │   ├── __init__.py                        # [P3] intentional public exports only
│       │   ├── interface.py                       # [P3] begin, append, finalize, state reads
│       │   ├── model.py                           # [P3] sessions, states, chunks, outcomes
│       │   ├── errors.py                          # [P3]
│       │   ├── implementation.py                  # [P3] complete lifecycle facade
│       │   ├── _blob.py                           # [P3] private BlobStore seam
│       │   ├── _local_blob.py                     # [P3] local-files adapter
│       │   ├── _payload.py                        # [P3] assembly, checksum, immutable finalization
│       │   ├── _arrow.py                          # [P4] streaming decode and structural validation
│       │   ├── _ordering.py                       # [P4] sequences, gaps, visible watermark
│       │   └── maintenance.py                     # [P11] staging/orphan reconciliation entry point
│       │
│       ├── scopes/
│       │   ├── __init__.py                        # [P6] intentional public exports only
│       │   ├── interface.py                       # [P6] ScopeResolver interface
│       │   ├── plan.py                            # [P6] immutable ScopeQueryPlan types
│       │   ├── errors.py                          # [P6]
│       │   └── resolver.py                        # [P6] selection, mappings, joins, unions, pinning
│       │
│       ├── query/
│       │   ├── __init__.py                        # [P7] intentional public exports only
│       │   ├── interface.py                       # [P7] QueryEngine and streaming result
│       │   ├── errors.py                          # [P7]
│       │   ├── implementation.py                  # [P7] parse-to-result orchestration
│       │   ├── policy.py                          # [P7] permitted SQL and authorization rules
│       │   ├── _sql.py                            # [P7] SQLGlot parsing and logical-name analysis
│       │   ├── _relations.py                      # [P7] plan-to-DuckDB relation construction
│       │   ├── _duckdb.py                         # [P7] isolated execution and Arrow streaming
│       │   └── _iceberg.py                        # [P8] private Iceberg relation reader
│       │
│       ├── publication/
│       │   ├── __init__.py                        # [P8] intentional public exports only
│       │   ├── interface.py                       # [P8] Publisher interface
│       │   ├── model.py                           # [P8] requests, outcomes, lineage facts
│       │   ├── errors.py                          # [P8]
│       │   ├── implementation.py                  # [P8] resolved plan-to-snapshot orchestration
│       │   ├── _iceberg.py                        # [P8] PyIceberg integration
│       │   ├── _field_ids.py                      # [P8] stable field identity and evolution
│       │   └── maintenance.py                     # [P11] compaction/orphan/metadata operations
│       │
│       ├── subscriptions/
│       │   ├── __init__.py                        # [P9] intentional public exports only
│       │   ├── interface.py                       # [P9] define, poll/read, acknowledge
│       │   ├── model.py                           # [P9] subscription and cursor types
│       │   ├── errors.py                          # [P9]
│       │   └── implementation.py                  # [P9] cursor and concurrency semantics
│       │
│       ├── profiling/
│       │   ├── __init__.py                        # [P10] intentional public exports only
│       │   ├── interface.py                       # [P10] submit/read profile and proposals
│       │   ├── model.py                           # [P10] profiles, evidence, proposals
│       │   ├── errors.py                          # [P10]
│       │   ├── implementation.py                  # [P10] profiling and proposal orchestration
│       │   ├── _statistics.py                     # [P10] Arrow-native deterministic profiling
│       │   ├── _matching.py                       # [P10] deterministic matching strategies
│       │   └── worker.py                          # [P10] background execution entry point
│       │
│       ├── access/
│       │   ├── __init__.py                        # [P11] intentional public exports only
│       │   ├── interface.py                       # [P11] authentication/authorization decisions
│       │   ├── model.py                           # [P11] principals, grants, actions, resources
│       │   ├── errors.py                          # [P11]
│       │   └── implementation.py                  # [P11] credential and privilege rules
│       │
│       ├── audit/
│       │   ├── __init__.py                        # [P11] intentional public exports only
│       │   ├── interface.py                       # [P11] append/read immutable audit facts
│       │   ├── model.py                           # [P11] structured audit records
│       │   └── implementation.py                  # [P11] persistence and redaction rules
│       │
│       ├── telemetry.py                           # [P11] metrics/tracing setup at composition root
│       └── cli.py                                 # [P11] thin administration command adapter
│
├── tests/
│   ├── conftest.py                                # [P0] only genuinely global fixtures
│   ├── test_health.py                             # [P0]
│   ├── test_config.py                             # [P0]
│   ├── test_architecture.py                       # [P1] public/private import discipline
│   ├── fakes/
│   │   ├── __init__.py                            # [P1]
│   │   ├── fixed_clock.py                         # [P1]
│   │   └── faulting_blob.py                       # [P3] test adapter for interrupted writes
│   ├── control_plane/
│   │   ├── conftest.py                            # [P1] adapter matrix and database fixtures
│   │   ├── test_contract.py                       # [P1] shared interface contract
│   │   ├── test_transactions.py                   # [P1] retry and atomicity outcomes
│   │   ├── test_concurrency.py                    # [P1]
│   │   ├── test_migrations.py                     # [P1]
│   │   ├── test_schema_history.py                 # [P2]
│   │   ├── test_schema_codec.py                   # [P2] persisted compatibility vectors
│   │   ├── test_scope_configuration.py            # [P5]
│   │   └── test_scope_activation_races.py         # [P11]
│   ├── http/
│   │   ├── test_catalog_routes.py                 # [P2]
│   │   ├── test_ingest_routes.py                  # [P3]
│   │   ├── test_scope_routes.py                   # [P5]
│   │   ├── test_query_routes.py                   # [P7]
│   │   └── test_administration_routes.py          # [P11]
│   ├── ingestion/
│   │   ├── test_lifecycle.py                      # [P3]
│   │   ├── test_chunk_recovery.py                 # [P3]
│   │   ├── test_idempotency.py                    # [P3]
│   │   ├── test_raw_immutability.py               # [P3]
│   │   ├── test_validation.py                     # [P4]
│   │   ├── test_quarantine.py                     # [P4]
│   │   ├── test_sequence_visibility.py            # [P4]
│   │   ├── test_commit_races.py                   # [P4]
│   │   └── test_reconciliation.py                 # [P11]
│   ├── scopes/
│   │   ├── test_append_plans.py                   # [P6]
│   │   ├── test_enrich_plans.py                   # [P6]
│   │   ├── test_projection_pruning.py             # [P6]
│   │   ├── test_snapshot_pinning.py               # [P6]
│   │   └── test_plan_properties.py                # [P6]
│   ├── query/
│   │   ├── test_query_engine.py                   # [P7] main interface contract
│   │   ├── test_sql_policy.py                     # [P7] unsafe statements via public interface
│   │   ├── test_name_resolution.py                # [P7]
│   │   ├── test_arrow_streaming.py                # [P7]
│   │   ├── test_stable_snapshot.py                # [P7]
│   │   └── test_resource_limits.py                # [P7]/[P11] expanded later
│   ├── publication/
│   │   ├── test_publication.py                    # [P8] main interface contract
│   │   ├── test_field_identity.py                 # [P8]
│   │   ├── test_schema_evolution.py               # [P8]
│   │   ├── test_lineage.py                        # [P8]
│   │   └── test_maintenance.py                    # [P11]
│   ├── subscriptions/
│   │   ├── test_subscription.py                   # [P9] main interface contract
│   │   ├── test_cursor_rules.py                   # [P9]
│   │   ├── test_resume.py                         # [P9]
│   │   └── test_worker_races.py                   # [P9]
│   ├── profiling/
│   │   ├── test_profiling.py                      # [P10] main interface contract
│   │   ├── test_statistics.py                     # [P10]
│   │   ├── test_matching.py                       # [P10]
│   │   └── test_proposal_reproducibility.py       # [P10]
│   ├── access/
│   │   ├── test_access_decisions.py               # [P11]
│   │   └── test_provider_credentials.py           # [P11]
│   └── system/
│       ├── test_contactmoment_flow.py              # [P7] A+B ENRICH through SQL
│       ├── test_machine_telemetry_flow.py          # [P7] many-provider APPEND
│       ├── test_virtual_and_iceberg_parity.py      # [P8]
│       ├── test_active_query_during_commit.py      # [P11]
│       └── test_database_invariant_parity.py       # [P11]
│
└── .github/
    └── workflows/
        └── ci.yml                                 # [P0][optional] if GitHub hosts the repository
```

## Creation sequence by phase

The projected tree is easier to apply when reduced to what each phase actually adds.

### Phase 0

Create packaging and tool files, the composition root, configuration, logging, the HTTP health adapter, basic tests, two architecture documents, and the initial ADR. Do not create empty domain packages.

### Phase 1

Create the Control Plane package, typed identifiers, clock seam, two persistence adapters, initial migrations, database contract fixtures, and concurrency tests. This is the first deep Module.

### Phase 2

Add the schema codec, the Provider/Registration/schema HTTP adapters, HTTP error mapping and actor context, schema history tests, and the fingerprint ADR. Avoid splitting Provider, Registration, and Schema into separate repository packages.

### Phase 3

Create the Ingestion package, private BlobStore seam, local and fault-injecting adapters, raw-object migrations, ingest HTTP adapter, lifecycle tests, and ingest documentation. Keep validation and watermark behaviour out until Phase 4.

### Phase 4

Add Arrow validation and ordering implementation files, then deepen Ingestion's existing interface. Do not expose separate validation and commit interfaces to HTTP callers.

### Phase 5

Add Scope rules to Control Plane, Scope HTTP routes, Scope migrations, the contribution-semantics ADR, and integration fixtures. The `scopes/` resolver package still does not exist until Phase 6.

### Phase 6

Create Scope Resolution, immutable plan types, snapshot construction, and planner tests. This Module is usable without DuckDB.

### Phase 7

Create Query Execution and its HTTP adapter. SQLGlot and DuckDB remain private implementation dependencies. Add resource limits here at least in basic form.

### Phase 8

Create Publication, PyIceberg integration, field-identity rules, lineage documentation, publication migrations, and virtual/materialized parity tests.

### Phase 9

Create Subscriptions, subscription migrations and routes, plus cursor, resume, and worker-race tests.

### Phase 10

Create Profiling and its worker entry point. Mapping proposal approval remains a Control Plane command. Do not create an LLM adapter unless an LLM matcher is actually implemented.

### Phase 11

Create or deepen Access, Audit, telemetry, administration CLI/HTTP adapters, maintenance entry points, runbooks, and the full system stress suite. A deployment file is added only after its target is selected.

## Current-file assessment

At the time of this review, the workspace contains one file:

### `ARCHITECTURE_REVIEW.md`

This remains documentation. It is not part of a runtime Module and does not need a code interface. This appendix makes it long, but length alone is not a reason to split it. Split it into `docs/architecture/review.md` and `docs/architecture/file-blueprint.md` only if the two documents begin changing independently or readers regularly need one without the other.

There are currently no Python files to evaluate for deepening or extraction.

## Files most likely to graduate into nested Modules

The following Python modules should begin as single files. They may later become packages with private internal interfaces when their knowledge separates. This is the specific meaning of “a single file could need to become its own Module within a Module.”

### `control_plane/model.py`

Start with cohesive Provider, Registration, schema-version, Scope, and contribution state. Graduate to:

```text
control_plane/model/
├── __init__.py
├── catalog.py
├── schemas.py
├── scopes.py
└── revisions.py
```

Do this only when the clusters have distinct invariants and change independently. Do not create one file per entity merely because there are many nouns.

### `control_plane/implementation.py`

This file owns domain command and read orchestration. Graduate to:

```text
control_plane/_implementation/
├── __init__.py
├── catalog_commands.py
├── scope_commands.py
├── reads.py
└── snapshots.py
```

The external Control Plane interface remains unchanged. Callers must never import these private files.

### `control_plane/_adapters/libsql.py` and `postgres.py`

Each adapter can become its own package when connection handling, statement mapping, retry classification, and row conversion become independently substantial:

```text
control_plane/_adapters/postgres/
├── __init__.py
├── connection.py
├── statements.py
├── rows.py
└── retry.py
```

The private persistence seam should not widen when this happens.

### `ingestion/implementation.py`

This is the strongest split candidate. Start with one lifecycle facade. Once the complete Phase 4 behaviour is present, it may deepen into:

```text
ingestion/_implementation/
├── __init__.py
├── sessions.py
├── assembly.py
├── validation.py
├── commit.py
├── watermarks.py
└── quarantine.py
```

`Ingestion.begin`, `append`, and `finalize` remain the external interface. The nested Module exists to give maintainers locality, not to make callers coordinate six steps.

### `scopes/resolver.py`

Start with one resolver because APPEND and ENRICH share selection, mapping, and snapshot knowledge. Graduate only when the planning algorithms become independently complex:

```text
scopes/_resolver/
├── __init__.py
├── selection.py
├── append.py
├── enrich.py
├── provenance.py
└── pinning.py
```

The only external operation remains `ScopeResolver.plan`.

### `query/implementation.py`

Some complexity is already local to `policy.py`, `_sql.py`, `_relations.py`, and `_duckdb.py`. If orchestration itself grows, move it into a private package:

```text
query/_implementation/
├── __init__.py
├── prepare.py
├── resolve.py
├── execute.py
└── stream.py
```

Do not expose SQLGlot AST or DuckDB connection lifecycles through the Query Engine interface.

### `publication/implementation.py`

Graduate when snapshot writing, schema evolution, lineage recording, and recovery each carry substantial rules:

```text
publication/_implementation/
├── __init__.py
├── schema_evolution.py
├── writer.py
├── lineage.py
└── recovery.py
```

The Publisher interface remains one publication operation plus stable result/error semantics.

### `subscriptions/implementation.py`

Graduate when defining subscriptions, leasing work, reading contributions, and advancing cursors become distinct knowledge clusters:

```text
subscriptions/_implementation/
├── __init__.py
├── definitions.py
├── leases.py
├── delivery.py
└── cursors.py
```

Do not expose database leases as a caller concern.

### `profiling/implementation.py`

Graduate when profile computation, evidence persistence, proposal generation, and background execution change independently:

```text
profiling/_implementation/
├── __init__.py
├── profiles.py
├── proposals.py
├── execution.py
└── persistence.py
```

Deterministic matching strategies can remain private functions until actual adapters need to vary at a seam.

### HTTP adapter files

A route file such as `http/ingest.py` can become `http/ingest/` when transport models, streaming input, response negotiation, and error mapping make it difficult to understand as one file. That nested package is still only an adapter. It must not acquire ingest lifecycle rules that belong in the Ingestion Module.

## Signals that justify a split

Split a Python module into a nested Module when several of these are true:

1. It contains two or more knowledge clusters with different reasons to change.
2. A change repeatedly touches distant sections of the same file but not the rest.
3. Maintainers cannot explain the file's responsibility without using “and” several times.
4. Private types and invariants naturally belong to one subset of the implementation.
5. A real internal seam has at least two adapters or strategies.
6. Tests need deterministic control of an internal dependency such as time, storage failure, or transaction retry.
7. The file can no longer be understood comfortably in one reading or agent context.

Do not split solely because:

- a file crossed an arbitrary line count;
- every class “should” have its own file;
- a future adapter might exist;
- test mocking is easier after exposing private details;
- the folder tree looks more symmetrical.

A split is successful when the external interface becomes no larger and knowledge becomes more local.

## Files deliberately absent

The following paths from a conventional layer-first design should not be created unless later evidence contradicts this review:

```text
src/mosaic/domain/provider.py
src/mosaic/domain/registration.py
src/mosaic/domain/schema.py
src/mosaic/repositories/interfaces.py
src/mosaic/repositories/provider.py
src/mosaic/repositories/registration.py
src/mosaic/transactions/manager.py
src/mosaic/storage/blob.py
src/mosaic/storage/iceberg.py
src/mosaic/jobs/
src/mosaic/events/
src/mosaic/utils.py
```

Their behaviour belongs behind the interfaces of the owning deep Modules. For example, blob storage belongs inside Ingestion, Iceberg publication belongs inside Publication, and transaction retry belongs inside the Module operation being retried. A generic `utils.py` usually hides missing ownership and should be replaced with a well-named private file in the Module that owns the knowledge.

## Public import discipline

Each deep package should use `__init__.py` to expose only its intended interface types. Callers should import from `mosaic.ingestion`, not from `mosaic.ingestion.implementation` or private files. Leading underscores reinforce the rule but do not replace review and tests.

An architecture test can enforce that HTTP adapters and other Modules do not import:

- another Module's `_adapters` or `_implementation` packages;
- concrete database adapters outside the composition root;
- DuckDB outside Query Execution;
- PyIceberg outside Publication and the private query relation reader;
- FastAPI or Pydantic inside deep domain implementations;
- adapter-specific database exceptions outside their adapter.

This import discipline keeps the interface small even as implementations deepen internally.
