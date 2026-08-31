# Control plane and data plane

Mosaic separates authoritative orchestration state from bulk analytical data. This
boundary determines where information belongs and prevents a convenient database table
from becoming an accidental data pipeline.

## Control plane

The control plane owns the small, authoritative facts needed to understand and coordinate
the system. In later phases these facts include Provider and Registration identity, schema
and mapping revisions, ScopeContribution configuration, ingest lifecycle state, sequence
visibility, and references to immutable data objects.

Control-plane persistence is not bulk-data storage. A transaction can make metadata
visible, select an active revision, or advance a state machine, but it does not contain
uploaded tables or query results. The future Control Plane Module will hide transaction
lifecycles and database-specific behavior behind a domain-shaped interface.

## Data plane

The data plane carries the tabular bytes: immutable raw uploads, validated batches,
quarantined batches, query inputs, and published analytical snapshots. Later Modules may
use blob storage, Arrow, DuckDB, or Iceberg to implement those capabilities. Those
technologies remain behind Module interfaces so their storage layouts and library types do
not become obligations for every caller.

The distinction can be applied with a simple question:

| Information | Plane | Reason |
|---|---|---|
| Registration identity and active schema revision | Control | Authoritative coordination state |
| Ingest status, checksum, sequence, and object reference | Control | Small lifecycle facts and pointers |
| Uploaded or validated tabular bytes | Data | Bulk immutable content |
| Scope mapping revision | Control | Versioned interpretation of data |
| Materialized analytical snapshot | Data | Queryable bulk content |

Control-plane state tells a Module which immutable data-plane objects are eligible for an
operation. Data-plane storage does not decide which revision is active or which transition
is legal.

## Boundary rules

1. Store identities, revisions, lifecycle state, policy, and immutable object references in
   the control plane.
2. Store bulk rows and analytical artifacts in the data plane.
3. Cross the boundary through a deep Module interface. Callers express domain intent; the
   implementation coordinates its seams and adapters.
4. Do not expose database transactions, object paths, framework models, or execution-engine
   handles as a general application interface.
5. Resolve work against a coherent control-state snapshot before reading the referenced
   data objects.

These rules create depth: a small interface hides substantial coordination. They also
create locality: changes to persistence or storage remain inside the owning implementation
and its adapters.

## Phase 0 boundary

Phase 0 has no operational control plane or data plane. It establishes only the application
composition root, validated settings, structured logging, and an HTTP health interface.
The health result therefore means that the application process is available; it cannot
claim readiness for databases, storage, ingestion, or query execution.

No future package is scaffolded in Phase 0. The distinction in this document constrains
later work without pretending that a database seam, blob adapter, or analytical capability
already exists. See the [Module map](module-map.md) for the approved capability boundaries
and the [architecture review](../../ARCHITECTURE_REVIEW.md) for the longer design rationale.
