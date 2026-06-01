# AGT Revamp — Frontend Alignment Spec

## Overview

The BE `feat/agt-revamp` branch reorganized the agent engine and exposed a
committed-template **Draft** endpoint. The FE currently implements the
Studio authoring flow (parse → generate-template → dry-run → compose-agent-config)
but has **no wiring for the final `POST /draft` call** — i.e. the production
flow that runs a *committed* `agent_config` against a real case and returns a
filled, R2-hosted `.docx`.

This spec describes the FE changes needed to close that gap and align the
Studio flow with the current BE contract.

---

## BE Contract Reference (feat/agt-revamp, as of 2026-04-14)

All routes are mounted under `/api/v2/core`.

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/cases` | Ingest petition PDF → creates Case + pgvector collections |
| `GET`  | `/cases` | List cases |
| `GET`  | `/cases/{case_id}` | Get single case |
| `POST` | `/template/composer/parse` | Parse docx only (no LLM) |
| `POST` | `/template/composer/generate-template?template_name=…` | Parse + LLM extract variables, persist `template.docx` |
| `POST` | `/template/composer/compose-agent-config?template_id=…` | **Commit** agent_config to DraftTemplate row |
| `POST` | `/template/dry-run` | Run draft pipeline *without* persisting, for iteration |
| **`POST`** | **`/draft`** | **NEW** — run draft against committed template + case, returns filled docx URL |
| `GET`  | `/template` | List templates |
| `GET`  | `/template/{template_id}` | Get template detail |
| `GET`/`POST`/`PUT` | `/template/reference-data*` | Constants CRUD |
| `GET`  | `/template/connectors` | Available source connectors |

### `POST /draft` request/response

```ts
// Request
{ template_id: string; case_id: string }

// Response
{
  template_id: string;
  case_id: string;
  resolved_values: ResolvedTemplateValue[];
  generated_doc_url: string;   // R2 presigned URL
  validation: {
    valid: boolean;
    errors: string[];
    warnings: string[];  // includes "Unresolved placeholder: …" and low-confidence notes
  };
}
```

`ResolvedTemplateValue` shape already exists in the BE dry-run response and
should be reused on the FE (same fields as `DryRunResult.resolved_values`).

---

## Conceptual Flow on FE

```
Studio (author)                        Production (execute)
────────────────                       ───────────────────
upload template ─► generate-template
                         │
                         ▼
                   edit spec ◄────────┐
                         │             │ iterate
                         ▼             │
                    dry-run ───────────┘
                         │
                         ▼
              compose-agent-config  (commit)
                         │
                         ▼
                    DraftTemplate.agent_config saved
                                                 │
                                                 ▼
                             [NEW] draft(template_id, case_id) ─► .docx URL
```

---

## Dry-Run Result Behavior (existing flow — update)

**Current (broken UX):** after Dry Run completes, the FE shows a toast
banner `"Dry run complete — N of N values resolved"` with a `View generated
draft ↗` external link. Users have to leave the page to see the result.

**Required:** render the dry-run's generated docx **inline in the Document
Preview panel** using the Draft tab, and make it **editable** in-place via
the existing docx-editor component (the fork already used elsewhere in the
app for docx editing). The toast should collapse to a brief
`"Dry run complete"` confirmation only — no external link.

Behavior:

- On dry-run success, auto-switch the preview to the **Draft** tab.
- Load the generated dry-run docx into the docx-editor (not a read-only viewer).
- User can edit the draft in-place. Edits are local to the session and do
  not mutate the stored `template.docx` or any persisted record — dry-run
  remains non-persistent by design.
- The **Template** tab continues to show the unfilled template unchanged.
- The same Draft-tab rendering is reused for the final **Run Draft** flow
  (see §5) — one component, two data sources (dry-run result vs. committed
  draft). The only difference: the committed-draft view can optionally
  persist edits (out of scope for this spec — confirm with PM).

This change replaces the current "View generated draft ↗" pattern entirely.

---

## What Needs to Change

### 1. New constants

**File:** `src/constants/index.ts`

Add to `API_ENDPOINTS.CORE`:

```ts
DRAFT: '/api/v2/core/draft',
```

### 2. New types

**File:** `src/types/studio.ts`

Add:

```ts
export interface DraftValidation {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

export interface DraftResult {
  template_id: string;
  case_id: string;
  resolved_values: ResolvedTemplateValue[];   // reuse existing type
  generated_doc_url: string;
  validation: DraftValidation;
}

export interface DraftRequest {
  template_id: string;
  case_id: string;
}
```

If `ResolvedTemplateValue` / `DryRunResult` currently live as inline/local
types, promote `ResolvedTemplateValue` to a top-level export in `types/studio.ts`
and have `DryRunResult` reuse it — so draft + dry-run share one shape.

### 3. New service method

**File:** `src/services/studio.service.ts`

Append to `StudioService`:

```ts
draft(templateId: string, caseId: string): Promise<ApiResponse<DraftResult>> {
  return apiService.post<DraftResult>(API_ENDPOINTS.CORE.DRAFT, {
    template_id: templateId,
    case_id: caseId,
  });
}
```

### 4. Store / state

**File:** `src/stores/useStudioStore.ts`

Add action + state slice for draft execution, parallel to the existing
`dryRun` handling:

- `draftResult: DraftResult | null`
- `isDrafting: boolean`
- `draftError: string | null`
- `runDraft(templateId, caseId)` → calls `studioService.draft`, sets state,
  toasts on warnings/errors.

Draft state must be **separate** from dry-run state — a committed template can
still be dry-run for spec iteration; both should coexist without one clobbering
the other.

### 5. UI — "Run Draft" entry point

Surface a **Run Draft** action on the template detail / workspace once
`agent_config` is committed (i.e. template has been composed). Gate it on:

- template exists
- `agent_config` is present on the fetched `DraftTemplateDetail` (if not
  already exposed, request BE to include an `is_committed: boolean` flag or
  check `agent_config !== null`)
- a `case_id` is selected (reuse the case picker already used by dry-run)

UX behavior:

- Button label: **Run Draft**
- On click → call `runDraft(templateId, caseId)`
- While pending: disable, show spinner
- On success:
  - Toast: `"Draft generated"`
  - **Render the filled docx inline in the Document Preview → Draft tab
    using the editable docx-editor component** (same component used for the
    dry-run preview above). Point it at `generated_doc_url`. Auto-switch
    the preview to the Draft tab on first successful run so the user sees
    the result immediately.
  - The Draft tab should be **disabled** until a draft (or dry-run) has
    been generated.
  - Also show a result panel with:
    - Validation warnings list (yellow if any warnings, red if `valid === false`)
    - Resolved values table (same rendering as dry-run result)
    - Secondary "Open in new tab" / download link (escape hatch only)
- On failure: toast the BE error detail

### 6. Distinguishing Dry-Run vs Draft visually

They share rendering for `resolved_values` but differ in:

| | Dry-Run | Draft |
|-|---------|-------|
| Persists anything? | No | Yes (R2 doc) |
| Needs committed config? | No | Yes |
| Returns docx URL? | No | Yes |
| Purpose | iterate on spec | produce deliverable |

The result banner should clearly label which mode produced the displayed
output so users don't confuse an iteration preview with a finalized draft.

---

## Out of Scope

- Polling / async task flow — `POST /draft` is currently synchronous on the
  BE. If it's later migrated to the parallel-pleading task pattern (see
  `post-parallelization-migration-implementation-fe.md`), wrap then.
- Case ingestion UI — already implemented.
- Reference-data CRUD UI — already implemented.

---

## Acceptance Criteria

1. User can author a template (parse → generate → edit spec → dry-run →
   compose-agent-config) end-to-end as today.
2. After compose-agent-config succeeds, a **Run Draft** action appears.
3. Selecting a case and clicking Run Draft calls `POST /api/v2/core/draft`,
   and on success renders a downloadable link to `generated_doc_url` plus
   validation warnings.
4. Draft result does not overwrite or blank out the dry-run result panel
   (and vice versa).
5. All new types are exported from `src/types/studio.ts`; no `any` in the
   new service / store code.
