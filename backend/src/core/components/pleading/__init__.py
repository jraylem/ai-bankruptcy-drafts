"""V2 template-draft pleading module.

Async taskiq pipeline that wraps the studio draft engine
(`src.core.components.engines.draft.service`) so multiple template drafts
can run concurrently on the Draft v2 page. Each draft attempt becomes a
pill in the FE strip and resolves AWAITING_INPUT pauses via the SSE-driven
input modal. Mirrors the legacy `/dashboard` pleading UX but template-driven.

Runs against its own broker (`core_broker`, queue_name `taskiq:core`) so a
dedicated worker process picks up these jobs without colliding with the
legacy `src.taskiq_app:broker`.
"""
