# Module map

In Mosaic, **Module** means a capability with a small interface and substantial hidden
implementation. A Module can initially be one Python module and later become a package or
tier-spanning slice. Its depth is measured by the leverage its interface gives callers,
not by its file count.

An **interface** includes operations, domain types, invariants, errors, ordering rules, and
performance expectations. An **implementation** hides workflow and technology choices. A
**seam** is a deliberate substitution point where behavior genuinely varies or must be
fault-injected. An **adapter** implements that seam for a particular technology.

## Phase 0 application foundation

Phase 0 is an application foundation, not one of the future domain Modules. Its composition
root is the single place that constructs the FastAPI application from validated settings
and logging configuration. The HTTP health operation is the highest behavioral test seam.
Framework request and response types stay at that edge.

This shape keeps concrete construction local. Later Modules can be injected at the
composition root without making their callers select adapters or control transactions.

## Approved capability Modules

The following boundaries guide later specifications. Their presence here is architectural
direction, not a claim that the capability or package exists in Phase 0.

| Module | First planned phase | External interface expresses | Implementation hides |
|---|---:|---|---|
| Control Plane | 1 | Typed metadata commands, reads, and coherent snapshots | Transactions, retries, persistence schemas, and database adapters |
| Ingestion | 3 | Begin, append, finalize, and inspect an ingest lifecycle | Staging, checksums, validation, quarantine, commit, ordering, and blob layout |
| Scope Resolution | 6 | Plan a logical Scope projection against pinned metadata | Contribution selection, mappings, joins, unions, and source pruning |
| Query Execution | 7 | Execute authorized logical queries and stream results | SQL inspection, relation construction, engine isolation, and resource limits |
| Publication | 8 | Publish a resolved plan as an immutable analytical snapshot | Field identity, table evolution, lineage capture, commit, and recovery |
| Subscriptions | 9 | Define consumption intent, read changes, and acknowledge progress | Independent cursors, leases, concurrency, and transactional advancement |
| Profiling | 10 | Request profiles and inspect evidence-backed proposals | Statistics, matching strategies, background execution, and proposal assembly |

Each caller should cross one highest practical interface. For example, an HTTP adapter asks
Ingestion to finalize a session; it does not separately invoke a checksum service, a blob
repository, a validation helper, and a transaction manager. Keeping that coordination
inside the implementation provides leverage and preserves invariants.

## Dependency direction

```text
HTTP or worker adapter
        |
        v
composition root -> domain Module interface
                           |
                           v
                  private implementation
                    |             |
                    v             v
               internal seam   internal seam
                    |             |
                    v             v
                 adapter       adapter
```

- HTTP and worker code depend on domain interfaces, not private implementations.
- Domain Modules do not import FastAPI request or response models.
- Callers do not own transaction scopes or coordinate multiple persistence repositories.
- Adapters remain private unless there are real interchangeable implementations.
- Cross-Module use goes through the owning interface rather than its tables or object paths.

## Why future packages are absent

Creating empty packages now would give names permanence before behavior reveals the right
boundaries. It would also make shallow technical layers look like approved interfaces.
Mosaic creates a package only when a phase can define and test its capability through the
same seam that callers use.

This is deliberate locality, not missing scaffolding. Phase 0 therefore has no database,
blob-storage, ingestion, Scope, query, publication, subscription, or profiling package.
The architecture documentation names the expected ownership while each later
specification decides the concrete files and real adapters it earns.

## When one file should become a nested Module

A cohesive implementation may start in one file. Split it into a private package only when
the file contains independently changing bodies of knowledge, has real internal seams, or
can no longer keep its orchestration easy to find. For example, a future ingestion
implementation could graduate into a nested implementation package when upload assembly,
validation, commit coordination, and watermark logic each become substantial.

That split must preserve the external interface. It should improve locality inside the
Module, not expose more steps to callers. File size alone is not a sufficient reason to
split, and each domain noun does not need its own file.

The [architecture review](../../ARCHITECTURE_REVIEW.md) is the companion source for the
detailed Module rationale and phase-tagged projected file blueprint.
