"""Studio V2 — parallel namespace for the v2 template studio.

Lives entirely separate from v1's `src/core/agents/` and
`src/core/components/engines/template/`. No file under those v1 paths
is modified during Phases 0-5; v2 imports v1 utility code read-only
(Agent base class, DocxTemplateService, OAuth credential loader,
pgvector lookups, reference_data table). Phase 6 demolishes v1
wholesale once telemetry shows zero v1 traffic.

See plan: agt-version-2-dumb-down.md.
"""
