# BKDrafts — Inbox Drafting Spec

The **Inbox Review** screen. Left rail lists pending petitions; center chat/PDF surface drives the per-case drafting conversation; top strip hosts **document draft cards**, one per document being generated for the selected case; right rail holds review/decision actions.

This spec is anchored to the BE contract. Every state, payload, and action below maps to a real endpoint or invariant in [`/core`](d:/VanHorn/bkdrafts-be/src/core/). Behaviors not backed by BE are called out explicitly as **Out of scope — requires BE**.

Sources: Apr 20 2026 meeting transcript + target-state screenshot (Jacques Fenelon 25-24573). BE reference: commit `5b8c4b6` on `feat/agt-revamp`.

---

## 0. Screen anatomy (from screenshot)

```
┌────────────────┬──────────────────────────────────────────┬──────────────────┐
│ LEFT (240px)   │ TOP STRIP: Draft Cards (one per doc)     │                  │
│                │ ┌──────────────┐ ┌──────────────┐        │                  │
│ ← Back         │ │ Letter of    │ │ Notice of    │        │                  │
│ [search]       │ │ Explanation  │ │ Withdrawal   │        │ RIGHT (~320px)   │
│ INBOX ▾        │ │ ✓ Generated  │ │ ⟳ Submitting │        │                  │
│  • Jacques F.  │ │ [Open][Email │ │   input...   │        │ Inbox Review     │
│    25-24573    │ │  ][Save]     │ │              │        │                  │
│    PENDING     │ └──────────────┘ └──────────────┘        │ • header w/      │
│  • Zohaib Q.   │ ───────────────────────────────────      │   status         │
│    26-01777    │ CENTER PANE:                             │ • empty state:   │
│    PENDING     │   ┌─ Jacques Fenelon · 25-24573 ────┐    │   "Select a      │
│                │   │  [Chat] [PDF] [Split]           │    │    pending       │
│                │   │                                  │   │    petition"    │
│                │   │  <chat log / pdf / both>        │    │                  │
│                │   │                                  │   │                  │
│                │   │  [⏸ Paused]                     │    │                  │
│                │   └─────────────────────────────────┘   │                  │
│                │   [Review Petition] [Draft            ]   │                  │
│                │   [Pleading ▾] [Draft Order ▾]            │                  │
│ ─── footer ─── │   [type your message…]                   │                  │
│ JT Jhune T.    │                                           │                  │
└────────────────┴──────────────────────────────────────────┴──────────────────┘
```

Fixed pieces:
- **Left rail** — back button, pending-petition search, collapsible **Inbox** list, user footer.
- **Top strip** — horizontal row of **draft cards**, one per document currently being generated or recently completed for the selected case. Cards have 3 lifecycle states (see §2).
- **Center pane** — per-case workspace with `Chat | PDF | Split` view toggle, a `Paused` overlay for awaiting-input states, and an action row: `Review Petition`, `Draft Pleading ▾`, `Draft Order ▾`. Bottom: attorney chat input.
- **Right rail** — **Inbox Review** panel. Empty state when no petition selected; status header + actions when one is.

---

## 1. Data sources & BE mapping

| UI concept | BE endpoint / shape | Notes |
|---|---|---|
| Pending-petition list (left rail) | `GET /core/cases` → `list[CaseResponse]` | Filter FE-side on "pending" status. **BE has no case-status column today** — see Gap #1. |
| Case workspace header | `GET /core/cases/{case_id}` → `CaseResponse` | Shows debtor name + sanitized case number (e.g. `25_24573` displayed as `25-24573`). |
| Draft card per document | `POST /core/draft` → `DraftResponse \| AwaitingInputResponse` | One card = one in-flight or recently-completed `/draft` invocation. Multiple cards = multiple templates running in parallel for the same case. |
| `[Open]` button | `DraftResponse.generated_doc_url` (R2 presigned, 1h TTL) | Opens in docx-editor tab or new window. |
| `[Save]` button | No-op BE: URL is already persistent at `cases/{case_id}/draft/{uuid}.docx`. FE-side "save to case file" or pin action. | R2 key is stable; URL is not. |
| `[Email]` button | **Out of scope — requires BE**. No send-email endpoint in `/core`. | Gap #2. |
| Reco-chip / dropdown / group-dropdown picker (Paused overlay) | `AwaitingInputResponse.pending_inputs: dict[str, PendingUserInput]` | Discriminator on `kind`: `pending_group_dropdown` / `pending_reco_chips` / `pending_dropdown` / `pending_user_input_with_docs`. |
| Resume after user picks | `POST /core/draft/resume` (body: `template_id, case_id, resolved_values, user_picks`) | **BE is stateless** — FE must echo back `resolved_values` from the prior `AwaitingInputResponse` verbatim. `run_id` is correlation-only. |
| `Review Petition` | `GET /core/cases/{case_id}` → petition URL | Opens petition PDF. |
| `Draft Pleading ▾` / `Draft Order ▾` | `GET /core/template` → filter by document class; on pick: `POST /core/draft` | Template list has no class taxonomy today — see Gap #3. |

---

## 2. Draft card — lifecycle states

Each card represents **one `/draft` run** for one `(template_id, case_id)` pair. It has exactly these states:

### 2.1 `Submitting input…` (spinner)
- Fired when FE POSTs `/core/draft` or `/core/draft/resume`.
- Card shows: template name + debtor name + spinner + `Submitting input…`.
- Actions row: hidden.
- No cancel action (BE has no cancel endpoint — Gap #4).

### 2.2 `Awaiting input` (pause — transcript: "awaiting input")
- Fired when `/draft` returns `AwaitingInputResponse` (status = `"awaiting_input"`).
- Card shows: template name + `Awaiting input` + count of pending fields.
- Clicking the card **opens the Paused overlay in the center pane** (see §3) — which renders the `pending_inputs` dict as one widget per field keyed by `property_name`.
- Actions row: hidden until user completes input.
- **Minimum 3 reco chips** per field: BE's `RecoChipsAgent` returns up to 3 ([agents/llm/reco_chips/agent.py](d:/VanHorn/bkdrafts-be/src/core/agents/llm/reco_chips/agent.py)). Transcript said "minimum 3 required" — FE must show **a user-editable text input alongside the chips** so user can always proceed even if BE returns <3.

### 2.3 `Documents generated successfully` (completed — green pill)
- Fired when `/draft` or `/draft/resume` returns `DraftResponse` (status = `"completed"`).
- Card shows: template name + green `Documents generated successfully` + warnings count (if any).
- Actions row: `[Open]` `[Email]` `[Save]`.
  - `[Open]` → open `DraftResponse.generated_doc_url` in docx-editor tab.
  - `[Email]` → **disabled with tooltip** until Gap #2 is addressed.
  - `[Save]` → FE-side pin to case; no BE call.
- Warnings surface as a subtle badge (`1 unresolved`, `2 low confidence`) — from `DraftResponse.warnings` / `unresolved`.

### 2.4 Error state
- Fired on 4xx/5xx from `/core/draft` or `/core/draft/resume`.
- Card shows: template name + red `Failed` + reason.
- Actions: `[Retry]` (re-POST `/core/draft` with same body). No partial state recovery; BE is stateless.
- **BE invariant**: `/core/draft` returns 400 if `agent_config` is null on the template. Show copy: "Template not finalized. Configure template in Studio before drafting." (Refers to [`components/engines/draft/service.py:76`](d:/VanHorn/bkdrafts-be/src/core/components/engines/draft/service.py#L76).)

---

## 3. Paused overlay — rendering `pending_inputs`

When the active card is in state `Awaiting input`, the center pane shows a `[⏸ Paused]` overlay over the chat/PDF area with a stacked list of widgets — **one per entry in `AwaitingInputResponse.pending_inputs`**.

Discriminate on `kind` ([`agents/resolvers/user_input_resolver.py`](d:/VanHorn/bkdrafts-be/src/core/agents/resolvers/user_input_resolver.py)):

| `kind` | Widget | Pick shape returned to BE |
|---|---|---|
| `pending_group_dropdown` | Two-column dropdown: `left_label` / `right_label` with `options: list[DropdownOption]` ({left, right} pairs). User picks a paired row. | `GroupDropdownPick { left, right }` keyed by composite property_name (`"left_var__right_var"`). |
| `pending_reco_chips` | Label + up to 3 chip buttons + **free-text fallback input** + optional `example_sentence` placeholder. | `SingleValuePick { value }` (value = chip text OR user-edited text). |
| `pending_dropdown` | Label + dropdown of `options: list[str]`. | `SingleValuePick { value }` (value = exact option string). |
| `pending_user_input_with_docs` | Label + textarea + multi-file upload (types from `accepted_file_types`). Files upload to `POST /core/cases/{case_id}/supporting-docs` **first**, returning R2 keys. | `SupportingDocsPick { user_text, file_urls: list[str] }` — URLs must be prefixed `cases/{case_id}/supporting_docs/`. |

**Resume flow:**
1. User fills every widget → FE collects `user_picks: dict[str, UserSelection]` keyed by property_name.
2. FE POSTs `/core/draft/resume` with body:
   ```json
   {
     "template_id": "...",
     "case_id": "...",
     "resolved_values": [...echoed verbatim from AwaitingInputResponse.resolved_values...],
     "user_picks": { "property_name_1": {...pick...}, ... }
   }
   ```
3. Card returns to `Submitting input…` spinner, then transitions to `Documents generated successfully` or `Awaiting input` (if BE reveals additional pending inputs — uncommon but possible).

**Hard rule (BE invariant):** FE must preserve the `AwaitingInputResponse` in component state. If the FE drops it (nav, refresh without persistence), there is no server-side resume — user restarts from scratch. See §6 on persistence.

---

## 4. Top strip — multiple concurrent cards

The screenshot shows two cards side-by-side. This means multiple `/core/draft` runs can be in-flight **concurrently** for the same case. FE state model:

```ts
type DraftCardId = `${templateId}_${runIndex}`;  // run_index bumps on each new draft

interface DraftCard {
  id: DraftCardId;
  templateId: string;
  templateName: string;        // from GET /template
  caseId: string;
  debtorName: string;
  state: 'submitting' | 'awaiting_input' | 'completed' | 'error';
  
  // set when awaiting_input:
  pendingInputs?: Record<string, PendingUserInput>;
  resolvedValuesSnapshot?: ResolvedTemplateValue[];  // echo back on resume
  
  // set when completed:
  generatedDocUrl?: string;    // 1h TTL — refresh on expiry
  urlExpiresAt?: number;       // Date.now() + 3600_000
  warnings?: string[];
  unresolved?: string[];
  
  // set when error:
  error?: { status: number; message: string };
}
```

**Presigned URL refresh (BE invariant):** R2 URLs expire in 1h ([common/storage/r2.py](d:/VanHorn/bkdrafts-be/src/core/common/storage/r2.py)). If user clicks `[Open]` on a completed card older than 1h, FE must re-fetch via `GET /core/cases/{case_id}` (which includes fresh presigned URLs for case artifacts) OR re-run `/core/draft`. Prefer the former — it's cheap.

**Cards are ephemeral:** Not persisted in BE. FE-local state only. On nav away + return, cards for in-flight runs are **lost** unless FE writes them to local storage (see §6).

---

## 5. Action row — `Review Petition`, `Draft Pleading`, `Draft Order`

### `Review Petition`
- Opens the petition PDF (`cases/{case_id}/petition.pdf` via presigned URL) in `PDF` or `Split` mode.

### `Draft Pleading ▾` / `Draft Order ▾`
- Dropdown of available templates filtered by document class (Pleading vs. Order vs. other).
- On pick: add a new draft card in `Submitting input…` state and POST `/core/draft` with `{ template_id, case_id }`.
- **BE gap (Gap #3):** `DraftTemplate` has no `doc_type` column; FE must either (a) infer from template name prefix (brittle) or (b) hardcode a classification map until BE adds the field.
- **Transcript-backed minimum templates to support in dropdowns (Apr 20 meeting):**
  - Motion to Waive
  - Notice of Withdrawal
  - Letter of Explanation
  - Motion Certificate of Service *(listed as next focus; may not be ready at first ship)*

---

## 6. Persistence — local storage (transcript 00:08:34, 00:12:03)

Attorney said: *"If I leave… persist value pre-selected. Notice of billing requirements deadline. Need data persistent."*

Backed by the BE invariant that `/core/draft/resume` is stateless — FE **must** hold resume state. Spec:

- Key: `bkdrafts.inbox.{caseId}.draftCards` → serialized `DraftCard[]` array.
- Write on every state transition.
- Hydrate on Inbox screen mount; if any card has state `awaiting_input` with a persisted `resolvedValuesSnapshot`, re-render its Paused overlay so user can pick up where they left off.
- Cards older than 24h with expired presigned URLs should be flagged `state: 'stale'` and offer a `[Re-generate]` action (re-POST `/core/draft`).
- Clear on logout (OR sooner if auth changes).

---

## 7. Grammar-tone auto-heal visibility (transcript 00:24:21, 00:51:20)

Attorney confirmed: *"Grammar tone healed high confidence good."* This is the `UserInputHealAgent` pass inside `finalize_run` — it runs **automatically** on the BE side after the user picks a dropdown/reco-chip/group-dropdown option, polishing the value to fit the surrounding sentence.

FE does **not** trigger heal. But the UI should surface its output:

- On a completed card, clicking `[Open]` shows the docx in the editor with the healed text already substituted — no FE post-processing.
- When user picked a raw option ("is employed as a driver") and the healed output is longer ("Debtor is employed as a driver at United Parcel Service, with responsibilities requiring…"), show a small `ℹ healed` icon next to the resolved field in the Paused overlay's "last submission" preview, with tooltip: *"Grammar & tone adjusted to fit the paragraph."*
- Confidence pills from `ResolvedTemplateValue.confidence` (`high` | `medium` | `low`) drive the `warnings` count on the card — a "low" confidence value appears as a yellow dot in the warnings badge.

---

## 8. Performance & timing budget (transcript 00:16:30)

Attorney noted: *"30 seconds API timing upload file."* This is the observed worst case for supporting-doc upload + analysis round-trip.

UI constraints:
- **30s soft timeout** per `/core/draft` and `/core/draft/resume`; show an `⚠ Still working…` banner on the card at 30s.
- **60s hard timeout** — show retry affordance.
- No timeout on supporting-doc upload itself (`/core/cases/{case_id}/supporting-docs`) since it's a simple multipart POST, but show per-file progress bars.
- LLM-heavy paths (reco-chips generation, heal, auto-derive) can legitimately take 10–20s. Spinner copy should reflect the active stage — not a generic loader. Optional nice-to-have, not blocking.

---

## 9. Right rail — Inbox Review panel

Empty state (no pending petition selected):
- Centered: `📋 Select a pending petition` / *"Choose a petition from the inbox list on the left to review and decide."*

Populated state (petition selected):
- Header: `Inbox Review` + status badge (`PENDING` / `IN REVIEW` / `APPROVED` / `REJECTED`).
- Summary count: *"{n} pending petition{s} ready for review."*
- Actions stack: `[Approve]` `[Reject]` `[Request Changes]` — **Out of scope — requires BE**. No review-decision endpoint exists in `/core` today (Gap #5).

Until Gap #5 lands, render only the header + empty state + summary. No buttons.

---

## 10. Gaps — items the BE does NOT yet support

Numbered for tracking; FE should stub UI and flag with `TODO(BE)` until server-side ships:

1. **Case status column** (`pending` / `in_review` / `approved` / `rejected`). BE `Case` model has no status field. FE filter on left rail is best-effort until BE adds it.
2. **Email the draft.** No send endpoint exists in `/core/draft` or anywhere else. `[Email]` button should be disabled-with-tooltip.
3. **Template classification** (`pleading` / `order` / `notice` / etc.). `DraftTemplate` has no `doc_type` column. Required to populate `Draft Pleading ▾` / `Draft Order ▾` dropdowns reliably.
4. **Cancel an in-flight draft.** No cancel endpoint. Once `/core/draft` is in-flight, FE must wait it out or ignore the eventual response.
5. **Review decisions** (Approve/Reject/Request Changes). No endpoint.
6. **Document chaining / notice-of-hearing gate** (transcript 00:54:18: *"cascading or chaining document chaining sheet protocol has notice of hearing yes or no"*). Not in current BE pipeline — `finalize_run` emits one docx per `/core/draft` invocation. Multi-document cascades are FE-orchestrated (attorney runs `/core/draft` once per template) until BE adds a chaining engine.
7. **Motion Certificate of Service template** (transcript 00:58:34: *"focus for two three hours after lunch on motion certificate of service"*). Template authoring work; no BE change needed — once the docx is uploaded via Studio and `compose-agent-config` is run, it becomes available in the templates dropdown automatically.

---

## 11. Sample-data block for Stitch

Use this when generating the design:

```
Selected petition: Jacques Fenelon · 25-24573 · PENDING
Other inbox item: Zohaib Quddusi · 26-01777 · PENDING
Active attorney: Jhune Trogelio (jhunet@vanhornlawgroup.com)

Draft cards for Jacques Fenelon:
  1. "Letter of Explanation" — state: completed (green) — actions: Open / Email / Save
  2. "Notice of Withdrawal"  — state: submitting (spinner) — copy: "Submitting input..."

Center pane: Chat mode, showing a past conversation with AI recommendations — 
latest assistant message discusses SOFA page review, Schedule E/F claim 
($27,011.62), and homestead exemption analysis. A [⏸ Paused] overlay sits 
over the chat because the Notice of Withdrawal card is awaiting a 
"withdrawal reason" reco-chip pick.

Reco-chip widget (inside Paused overlay) for property "withdrawal_reason":
  Label: "Reason for withdrawal"
  Chips: 
    - "Debtor no longer seeks to proceed with this matter."
    - "Debtor's circumstances have materially changed since filing."
    - "Debtor withdraws this pleading in light of trustee's objection."
  Free-text input below chips, placeholder: "Or type a custom reason…"

Right rail: Inbox Review panel — header + "1 pending petition is ready for review." 
Empty state body.
```

---

## 12. Style notes (consistent with [core-agt-stitch-prompt.md](d:/tmp/core-agt-stitch-prompt.md))

- Light background, purple primary accent, Inter font. Linear-meets-Clio feel.
- Draft cards: rounded rectangles, ~240px wide, 72–84px tall. Left edge colored by state — green for completed, purple for submitting, amber for awaiting_input, red for error.
- Action pills on completed cards (`Open` / `Email` / `Save`): small, outline style, 11–12px.
- Spinner copy should show what stage is running (transcript hints: "Submitting input…", "Healing grammar & tone…", "Generating draft…") — at minimum distinguish the upload/submit phase from the LLM-waiting phase.
- `[⏸ Paused]` overlay: centered pill, muted backdrop (not a full modal); content behind is dimmed but still scannable.

---

## Appendix A — BE contract quick-reference

From [reference_be_core_architecture.md](C:/Users/jhune/.claude/projects/d--VanHorn/memory/reference_be_core_architecture.md):

- **`POST /core/draft`** body: `{ template_id, case_id }` → `DraftResponse | AwaitingInputResponse`.
- **`POST /core/draft/resume`** body: `{ template_id, case_id, resolved_values, user_picks }` → `DraftResponse` only.
- `AwaitingInputResponse.pending_inputs: dict[property_name, PendingUserInput]` — discriminate on `.kind`.
- `AwaitingInputResponse.resolved_values` — must be echoed back verbatim on resume (BE is stateless on run_id).
- `DraftResponse.generated_doc_url` — presigned R2 URL, 1h TTL, refresh via `GET /cases/{case_id}` or new draft.
- 400 on `/core/draft` if `agent_config` is null → compose must run first.
- `SupportingDocsPick.file_urls` must start with `cases/{case_id}/supporting_docs/` or 400.
- `RecoChipsAgent` returns **up to 3** chips (not minimum). Empty list on LLM failure — FE must render the free-text fallback unconditionally.
- Finalized docx lands at `cases/{case_id}/draft/{uuid}.docx`; grammar/tone heal + auto-derive already applied.
