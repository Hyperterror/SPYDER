# Knowledge Graph & Snapshot Publishing

## 1. Architecture
- **Derived Projection**: Neo4j (`5-community`) and JSON/CSV snapshots serve as the derived analytical graph over authoritative PostgreSQL `ParsedRecord`s and MinIO originals.
- **Node Types**: 11 observable types (`PERSON`, `VICTIM`, `CASE`, `PHONE`, `DEVICE`, `VEHICLE`, `BANK_ACCOUNT`, `SOCIAL_ACCOUNT`, `LOCATION`, `EVIDENCE`, `ORGANIZATION`) plus provisional `IdentityHypothesis` overlays (`PROVISIONAL_IDENTITY`).
- **Typed Edges**: `APPEARS_IN`, `OBSERVES_ENTITY`, `USED_PHONE`, `USED_DEVICE`, `CALLED`, `MESSAGED`, `TRANSFERRED_TO`, `OWNED_ACCOUNT`, `CONNECTED_TO_TOWER`, `SIGHTED_AT`, `TRAVELED_TO`.

## 2. Atomic Versioned Publication (`backend/app/services/graph_publisher.py`)
1. Reads optional read-only synthetic baseline plus all ACTIVE `ParsedRecord` rows and active/accepted `IdentityHypothesis` edges from PostgreSQL (never mutating synthetic input CSVs).
2. Validates graph integrity (`validate_graph_candidate`: non-empty IDs, valid node endpoints for edges, zero ground-truth tokens).
3. Writes staged outputs to `output/graphsage/snapshots/<version_tag>/` and swaps pointers atomically (`os.replace`), recording a `GraphSnapshot` row in PostgreSQL.
4. On validation failure, aborts cleanly, keeps the prior `ACTIVE` snapshot untouched, and records `FAILED` status.
5. Synchronizes active nodes/edges to Neo4j best-effort; if Neo4j is unavailable, `/api/v1/cases/{case_id}/graph/subgraph` falls back seamlessly to PostgreSQL `ParsedRecord` construction across all modalities with depth, relationship type, and time-window filtering.
