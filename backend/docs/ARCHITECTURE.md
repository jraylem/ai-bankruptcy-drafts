# BKDrafts Backend — Architecture

BKDrafts is an AI-powered backend for bankruptcy attorneys. It automates motion drafting by ingesting court emails via Gmail, extracting structured fields using LLM agents, filling legal document templates (PDF/DOCX), and running petition reviews — all orchestrated through an async task queue.

---

## Table of Contents

1. [System Architecture](#1-system-architecture)
2. [Module Interconnections](#2-module-interconnections)
3. [Pleading Generation Flow](#3-pleading-generation-flow)
4. [Task State Machine](#4-task-state-machine)
5. [Recommendation Chips](#5-recommendation-chips)
6. [Motion Type Reference](#6-motion-type-reference--extraction--document-mapping)
7. [Database Layout](#7-database-layout)
8. [Vectorstore Collections](#8-vectorstore-collections)
9. [AI Models & Usage](#9-ai-models--usage)
10. [Background Services](#10-background-services)
11. [Frontend Connection Patterns](#11-frontend-connection-patterns)
12. [Dashboard Analytics](#12-dashboard-analytics)
13. [Petition Review Flow](#13-petition-review-flow)
14. [Task Event Stream](#14-task-event-stream)
15. [Key Environment Variables](#15-key-environment-variables)

---

## 1. System Architecture

```mermaid
graph TD
    FE["Frontend\nReact / TypeScript"]

    subgraph API["FastAPI  ·  src/main.py"]
        ROUTES["Routers  /api/*\nauth · chatbot · motions · gmail\npleadings · reviews · events\nstream · dashboard"]
        MW["ActivityLogMiddleware\nAudit trail on every HTTP action"]
        POLLER["CourtMailPollWorker\nhourly background poll"]
    end

    subgraph QUEUE["Task Queue"]
        TQ["Taskiq Workers\n3 replicas · async-native"]
        RQ["Redis\nbroker + result backend\n+ Streams (user_events:*)"]
    end

    subgraph AIBLOCK["AI Layer"]
        AGENTS["LangGraph Agents\nsrc/gmail/agents/\nsrc/chatbot/agents/"]
        OAI["OpenAI\ngpt-4.1-mini · gpt-4o-mini · gpt-5.4-mini\ntext-embedding-3-small"]
        ANT["Anthropic\nClaude Sonnet 4.6 · Opus 4.6\n+ Vision (PDF checkbox & field reading)"]
    end

    subgraph GAPIS["Google APIs"]
        GMAIL_API["Gmail API\nOAuth2"]
        DRIVE_API["Google Drive API\nOAuth2"]
    end

    subgraph FILL["Document Generation\nsrc/motion_filling/"]
        PDF["PDF Templates\n20+ motion types"]
        DOCX["DOCX Templates\n20+ motion types"]
    end

    subgraph STORAGE["Storage"]
        PGVEC["pgvector\nbankruptcy_knowledge_*\ngmail_*  ·  gmail_dismissed_*"]
        CHATDB["chat_db  PostgreSQL 17\nsessions · PDFs · threads\nmotion_draft_logs · activity_logs\nreview_results · monitored_motions"]
        USERDB["user_db  PostgreSQL 17\nusers"]
        RSTATE["Redis\npleading_task:*  review_task:*\nuser_events:* (Streams)\nTTL 2h"]
        SFTP["SFTP Mount\narchived petitions\nread-only"]
    end

    FE -- "REST · JWT" --> ROUTES
    FE -- "SSE stream" --> ROUTES
    FE -- "long-poll task status" --> ROUTES

    ROUTES --> TQ
    TQ --> RQ

    ROUTES --> AGENTS
    TQ --> AGENTS
    AGENTS --> OAI
    AGENTS --> ANT

    AGENTS <--> PGVEC
    ROUTES --> PGVEC
    ROUTES --> CHATDB
    ROUTES --> USERDB

    TQ --> RSTATE
    TQ --> FILL
    FILL --> CHATDB

    POLLER --> GMAIL_API
    POLLER --> RQ
    GMAIL_API --> PGVEC
    DRIVE_API --> SFTP

    SFTP --> FILL
```

---

## 2. Module Interconnections

```mermaid
graph LR
    subgraph ROUTES_LAYER["Routes Layer"]
        R_PLEAD["routes/pleadings.py"]
        R_REVIEW["routes/reviews.py"]
        R_EVENTS["routes/events.py"]
        R_STREAM["routes/stream.py"]
        R_DASH["routes/dashboard/"]
        R_GMAIL["gmail/routes.py"]
        R_CD["courtdrive/routes.py"]
        R_CB["chatbot/routes.py"]
        R_AUTH["auth/routes.py"]
    end

    subgraph TASK_LAYER["Tasks Layer  src/tasks/"]
        ORCH["orchestrator.py\nstart_pleading_generation()\nget_extractor()\nget_document_generator()"]
        REV_ORCH["review_orchestrator.py\nstart_review_task()"]
        EXTRACT["extractors.py\n20 Extractor classes"]
        PT["pleading_tasks_taskiq.py\nextract_pleading_payload()\ngenerate_pleading_documents()"]
        RT["review_tasks_taskiq.py\nrun_petition_review()"]
        PHELP["pleading_helpers.py\n_enrich_prefilled()\n_generate_documents_sync()"]
        TSTATE["task_state.py\nPleadingTaskState · Redis read/write"]
        RVSTATE["review_task_state.py\nReviewTaskState · Redis read/write"]
        EVSTREAM["event_stream.py\nemit_task_event() · Redis XADD"]
        SCHEMAS["schemas.py\nPydantic models\nUSER_INPUT_FIELDS"]
    end

    subgraph GMAIL_LAYER["Gmail Layer  src/gmail/"]
        G_SVC["service/\nextend.py · modify.py\nvalue.py · ... (20 files)"]
        G_AGENTS["agents/\nGmailMotion*Agent (20 files)"]
        G_TOOLS["tools/\n@tool factories (20 files)"]
        G_PROMPTS["prompts/\nfield prompts (20 files)"]
        G_INGEST["service/ingest.py\ningest_gmail_emails_for_session()"]
        G_AUTH["auth.py\nOAuth2 tokens"]
        G_POLL["poll_worker.py\nCourtMailPollWorker"]
        G_WFLOW["workflow_services.py\ncase matching · acceptance"]
    end

    subgraph FILL_LAYER["Motion Filling  src/motion_filling/"]
        F_EXTEND["fill_motion_extend.py\ngenerate_extend_suggestions()"]
        F_MODIFY["fill_motion_modify.py\ngenerate_delinquent_reason_suggestions()"]
        F_WAIVE["fill_motion_waive.py\ngenerate_employment_explanation_suggestions()"]
        F_REINSTATE["fill_motion_reinstate.py\ngenerate_why_dismissed_suggestions()"]
        F_DELAY_O["fill_motion_order_delay.py\ngenerate_extension_explanation_suggestions()"]
        F_REST["fill_motion_*.py\n(15 other motion types)"]
        F_COMMON["generator_common.py\nshared helpers"]
    end

    subgraph AI_LAYER["AI Layer"]
        LGGRAPH["LangGraph\ncreate_react_agent()"]
        OAI["OpenAI\ngpt-4.1-mini · gpt-4o-mini · gpt-5.4-mini"]
        ANT["Anthropic Claude\nSonnet 4.6 · Opus 4.6"]
        EMBED["text-embedding-3-small"]
    end

    subgraph STORAGE["Storage"]
        PGVEC[("pgvector")]
        CHATDB[("chat_db")]
        REDIS[("Redis")]
    end

    R_PLEAD --> ORCH
    R_PLEAD --> PT
    R_REVIEW --> REV_ORCH
    R_EVENTS --> EVSTREAM
    R_STREAM --> G_SVC
    R_DASH --> CHATDB

    ORCH --> EXTRACT
    ORCH --> PHELP
    PT --> ORCH
    PT --> TSTATE
    PT --> G_INGEST

    REV_ORCH --> RT
    RT --> RVSTATE

    TSTATE --> EVSTREAM
    RVSTATE --> EVSTREAM
    EVSTREAM --> REDIS

    EXTRACT --> G_SVC
    G_SVC --> G_AGENTS
    G_AGENTS --> G_TOOLS
    G_AGENTS --> G_PROMPTS
    G_AGENTS --> LGGRAPH
    LGGRAPH --> OAI
    LGGRAPH --> ANT
    G_TOOLS --> PGVEC

    PHELP --> F_EXTEND
    PHELP --> F_MODIFY
    PHELP --> F_WAIVE
    PHELP --> F_REINSTATE
    PHELP --> F_DELAY_O

    F_EXTEND & F_MODIFY & F_WAIVE & F_REINSTATE & F_DELAY_O & F_REST --> F_COMMON
    F_COMMON --> CHATDB

    G_INGEST --> EMBED
    EMBED --> PGVEC

    TSTATE --> REDIS
    RVSTATE --> REDIS
    G_POLL --> G_INGEST
    G_AUTH --> PGVEC
```

---

## 3. Pleading Generation Flow

```mermaid
sequenceDiagram
    actor User
    participant FE as Frontend
    participant API as FastAPI
    participant Q as Taskiq / Redis
    participant Gmail as Gmail API
    participant Ingest as gmail/service/ingest.py
    participant Extract as tasks/extractors.py
    participant Agent as gmail/agents/*.py
    participant LLM as OpenAI / Claude
    participant VStore as pgvector
    participant Enrich as tasks/pleading_helpers.py
    participant Fill as motion_filling/*.py

    User->>FE: Select motion type + trigger generate
    FE->>API: POST /api/pleadings/generate\n{ session_id, motion_type, source, include_cos }
    API->>Q: dispatch extract_pleading_payload(task_id, ...)
    API-->>FE: { task_id }

    FE->>API: GET /api/pleadings/tasks/{task_id} (poll every ~2s)

    note over Q: Status → CHECKING_EXISTING
    Q->>Q: Scan generated_pdf/ + generated_docx/\nfor existing files matching session_id

    alt Existing documents found
        Q-->>API: { status: EXISTING_FOUND, documents: {...} }
        API-->>FE: User prompted to reuse or regenerate
    else No existing documents
        note over Q: Status → EXTRACTING
        Q->>Gmail: Gmail API OAuth2 fetch\n(case_number filtered)
        Gmail-->>Ingest: Raw email threads
        Ingest->>VStore: Embed + store as gmail_<session_id>

        Q->>Extract: get_extractor(session_id, motion_type, source)
        Extract->>Agent: GmailMotion*Agent.extract_payload()
        Agent->>VStore: search_vectorstore(gmail_<session_id>)
        Agent->>VStore: search_vectorstore(bankruptcy_knowledge_<session_id>)
        VStore-->>Agent: Relevant chunks
        Agent->>LLM: Per-field system prompts (ReAct loop)
        LLM-->>Agent: Extracted field values
        Agent-->>Extract: Structured payload (Pydantic model)

        opt include_cos = true
            Extract->>Agent: GmailCertServiceAgent.extract_payload()
            Agent-->>Extract: CertificateOfServicePayload
        end

        opt motion_type == claim AND include_order_sustaining
            Extract->>Agent: GmailOrderSustainingAgent.extract_payload()
            Agent-->>Extract: OrderSustainingPayload
        end

        Extract-->>Q: { motion_payload, service_payload, order_payload }

        note over Enrich: Generate AI Recommendation Chips
        Q->>Enrich: _enrich_prefilled(motion_type, payload)
        Enrich->>Fill: generate_*_suggestions(payload)
        Fill->>LLM: Generate 2-4 contextual suggestions per field
        LLM-->>Fill: ["Suggestion A", "Suggestion B", ...]
        Fill-->>Enrich: { field: [chips] }
        Enrich-->>Q: { prefilled: {...}, suggestions: { field: [chips] } }

        note over Q: Status → AWAITING_INPUT
        Q->>Q: Store to Redis:\npleading_task:<task_id>\n{ prefilled, suggestions, input_fields }
    end

    API-->>FE: { status: AWAITING_INPUT, prefilled, suggestions, input_fields }

    User->>FE: Review pre-filled fields\nClick chips or type custom values
    FE->>API: POST /api/pleadings/tasks/{task_id}/submit-input\n{ user_input: { field: value } }

    note over Q: Status → GENERATING
    API->>Q: dispatch generate_pleading_documents(task_id, user_input)
    Q->>Q: Merge user_input into motion_payload
    Q->>Fill: generate_pdf_from_payload(merged_payload)
    Q->>Fill: generate_docx_from_payload(merged_payload)

    opt include_cos = true
        Q->>Fill: fill_motion_service.generate_pdf/docx(service_payload)
    end

    Fill-->>Q: Files written to:\ngenerated_pdf/<type>_<session_id>_*.pdf\ngenerated_docx/<type>_<session_id>_*.docx

    note over Q: Status → COMPLETED
    Q->>Q: Store file paths in Redis task state
    API-->>FE: { status: COMPLETED, documents: { pdf_path, docx_path } }
    User->>FE: Download PDF / DOCX
```

---

## 4. Task State Machine

```mermaid
stateDiagram-v2
    [*] --> PENDING : task dispatched to queue

    PENDING --> CHECKING_EXISTING : worker picks up task
    CHECKING_EXISTING --> EXISTING_FOUND : existing files found for session
    CHECKING_EXISTING --> EXTRACTING : no existing files

    EXISTING_FOUND --> COMPLETED : user confirms reuse (use-existing)
    EXISTING_FOUND --> EXTRACTING : user requests regenerate
    EXISTING_FOUND --> CANCELLED : user cancels

    EXTRACTING --> AWAITING_INPUT : payload extracted\nchips generated\nuser input required
    EXTRACTING --> GENERATING : no user input fields for this motion type
    EXTRACTING --> AWAITING_INPUT : intermediate input needed\n(e.g. no dismissed case emails found)
    EXTRACTING --> FAILED : extraction error

    AWAITING_INPUT --> GENERATING : user submits input\nvia submit-input endpoint

    GENERATING --> COMPLETED : PDF + DOCX written to disk
    GENERATING --> FAILED : generation error

    PENDING --> CANCELLED : user cancels
    AWAITING_INPUT --> CANCELLED : user cancels
    GENERATING --> CANCELLED : user cancels
```

**Redis key pattern:** `pleading_task:<task_id>` · `review_task:<task_id>` · TTL: 2 hours

**Task payload stored in Redis:**
```json
{
  "task_id": "uuid",
  "status": "AWAITING_INPUT",
  "motion_type": "extend",
  "session_id": "session-uuid",
  "motion_payload": { "...extracted fields..." },
  "service_payload": { "...cos fields..." },
  "input_fields": ["dismissal_reason", "change_in_circum"],
  "prefilled": { "debtor_name": "John Doe", "dismissal_reason": "", "..." },
  "suggestions": {
    "dismissal_reason": ["Previous case dismissed due to insufficient income", "..."],
    "change_in_circum": ["Debtor returned to full-time employment", "..."]
  }
}
```

---

## 5. Recommendation Chips

Chips are AI-generated suggestion strings shown to the attorney for free-text fields. The attorney can click a chip to auto-fill a field or type their own value.

```mermaid
flowchart TD
    A["tasks/pleading_tasks_taskiq.py\nextract_pleading_payload()"] --> B["Extraction complete\nmotion_payload ready"]
    B --> C{"Does motion_type\nhave USER_INPUT_FIELDS?"}
    C -- No --> G["Status → GENERATING\nskip chip generation"]
    C -- Yes --> D["tasks/pleading_helpers.py\n_enrich_prefilled(motion_type, payload)"]

    D --> E1["extend → fill_motion_extend\ngenerate_extend_suggestions()"]
    D --> E2["modify → fill_motion_modify\ngenerate_delinquent_reason_suggestions()"]
    D --> E3["waive → fill_motion_waive\ngenerate_employment_explanation_suggestions()"]
    D --> E4["reinstate → fill_motion_reinstate\ngenerate_why_dismissed_suggestions()"]
    D --> E5["order-delay → fill_motion_order_delay\ngenerate_extension_explanation_suggestions()"]
    D --> E6["objection-sustain →\nparse SlotNumb · Creditor · TrusteeCalendar\nDocketNumber from order_sustaining_payload"]

    E1 & E2 & E3 & E4 & E5 --> F["Claude LLM\nGenerates 2-4 contextual strings\nfrom motion payload + email context"]
    E6 --> F2["Split multi-line extracted fields\ninto option list (no LLM call)"]

    F & F2 --> H["suggestions dict\n{ field_name: [chip1, chip2, ...] }"]
    H --> I["task_state.set_input_required()\nStored in Redis with prefilled + input_fields"]
    I --> J["Status → AWAITING_INPUT\nFrontend receives suggestions"]
```

**Chips per motion type:**

| Motion Type | Field | Chip Source |
|---|---|---|
| `extend` | `dismissal_reason` | Claude — generates from dismissed case email context |
| `extend` | `change_in_circum` | Claude — generates from petition + employment context |
| `modify` | `delinquent_reason` | Claude — generates from payment history context |
| `waive` | `employment_explanation` | Claude — generates from employment/income context |
| `reinstate` | `WhyDismissedDetailed` | Claude — generates from dismissal email context |
| `order-delay` | `WhyExtensionNeeded` | Claude — generates from delay motion context |
| `objection-sustain` | `SlotNumb`, `Creditor`, `TrusteeCalendar`, `DocketNumber` | Parsed directly from extracted claim email fields (no LLM) |

---

## 6. Motion Type Reference — Extraction & Document Mapping

Every motion type has a dedicated agent for extraction and a dedicated filler for document generation.

| Motion Type | Gmail Agent | Extraction Source | Motion Filling File | Output Documents | User Input Fields |
|---|---|---|---|---|---|
| `extend` | `agents/extend.py` | Gmail dismissed case emails + petition PDF | `fill_motion_extend.py` | Motion to Extend the Stay (PDF + DOCX) | `dismissal_reason`, `change_in_circum` |
| `modify` | `agents/modify.py` | Gmail payment/creditor emails + petition PDF | `fill_motion_modify.py` | Motion to Modify (PDF + DOCX) | `delinquent_reason`, `creditors`, `claim_slot` |
| `value` | `agents/value.py` | Gmail valuation emails + petition PDF | `fill_motion_value.py` | Motion to Value (PDF + DOCX) | `Select1`, `Select2`, `Percent1`, `Price1`, `...` |
| `withdraw` | `agents/withdraw.py` | Gmail attorney/debtor emails + petition PDF | `fill_motion_withdraw.py` | Motion to Withdraw (PDF + DOCX) | _(none — fully auto)_ |
| `waive` | `agents/waive.py` | Gmail employment/fee emails + petition PDF | `fill_motion_waive.py` | Motion to Waive Filing Fee (PDF + DOCX) | `employment_explanation` |
| `claim` | `agents/objection_claim.py` | Gmail creditor/claim emails + petition PDF | `fill_motion_claim.py` | Objection to Claim (PDF + DOCX) | `Basis` |
| `delay` | `agents/delay.py` | Gmail property/creditor emails + petition PDF | `fill_motion_delay.py` | Motion to Delay (PDF + DOCX) | `ReasonForDelay`, `Explain`, `IfReaffirmation` |
| `reinstate` | `agents/reinstate.py` | Gmail dismissal history emails + petition PDF | `fill_motion_reinstate.py` | Motion to Reinstate (PDF + DOCX) | `WhyDismissedDetailed` |
| `suggestion` | `agents/suggestion.py` | Gmail legal action emails + petition PDF | `fill_motion_suggestion.py` | Suggestion of Bankruptcy (PDF + DOCX) | `CaseNumber`, `Creditor`, `County`, `CircuitNumber` |
| `loe` | `agents/cert_service.py` | Gmail trustee emails + petition PDF | `fill_motion_loe.py` | Letter of Explanation (PDF + DOCX) | `explanation` |
| `ex-parte-extension` | `agents/ex_parte_extension.py` | Gmail deadline emails + petition PDF | `fill_ex_parte_motion_extension.py` | Ex Parte Extension (PDF + DOCX) | _(none — fully auto)_ |
| `order-extend` | `agents/order_extend.py` | Gmail extend motion + hearing emails | `fill_order_granting_extend.py` | Order on Extend — regular or expedite variant (PDF + DOCX) | `CalendarDate`, `DocketMotion`, `OptionalConditions` |
| `order-value` | `agents/order_value.py` | Gmail value motion + hearing emails | `fill_order_value.py` | Order on Value (PDF + DOCX) | `Creditor`, `DocketNumber`, `TrusteeCalendar`, `CarModel`, `Value`, `...` |
| `order-delay` | `agents/order_delay.py` | Gmail delay motion + hearing emails | `fill_motion_order_delay.py` | Order on Delay (PDF + DOCX) | `WhyExtensionNeeded` |
| `order-withdraw` | `agents/order_withdraw.py` | Gmail withdraw hearing emails | `fill_order_withdraw.py` | Order on Withdraw (PDF + DOCX) | `TrusteeCalendar`, `DocketNumber` |
| `order-waive` | `agents/order_waive.py` | Gmail waive hearing emails | `fill_order_waive.py` | Order on Waive (PDF + DOCX) | `TrusteeCalendar`, `DocketNumber` |
| `order-reinstate` | `agents/order_reinstate.py` | Gmail reinstate hearing emails | `fill_order_reinstate.py` | Order on Reinstate (PDF + DOCX) | `X1`, `X2`, `X3` |
| `notice-withdraw` | `agents/notice_withdraw.py` | Gmail notice emails + petition PDF | `fill_notice_withdraw.py` | Notice of Withdrawal (PDF + DOCX) | `ECFNumber`, `DocumentTitle` |
| `objection-sustain` | `agents/order_sustaining_objection.py` | Derived from `claim` extraction | `fill_order_sustaining_objection.py` | Order Sustaining Objection (PDF + DOCX) | `SlotNumb`, `Creditor`, `TrusteeCalendar`, `DocketNumber` |
| `order-extension` | `agents/order_extension.py` | Gmail extension emails + petition PDF | `fill_order_extension.py` | Order on Motion for Extension (PDF + DOCX) | _(none — fully auto)_ |

**Every motion type also optionally generates:**
- `fill_motion_service.py` → Certificate of Service (PDF + DOCX) when `include_cos=true`

---

## 7. Database Layout

```mermaid
erDiagram
    SESSIONS {
        uuid id PK
        string case_number
        bool active
        timestamp created_at
    }
    PDF_DOCUMENTS {
        uuid id PK
        uuid session_id FK
        string filename
        string source
        string collection_name
    }
    CHAT_THREADS {
        uuid id PK
        uuid session_id FK
        string openai_thread_id
        string district
        string case_number
    }
    CHAT_MESSAGES {
        uuid id PK
        uuid thread_id FK
        string role
        text content
        timestamp created_at
    }
    COURTDRIVE_INGESTIONS {
        uuid id PK
        uuid session_id FK
        string ingestion_type
        string status
        timestamp created_at
    }
    MOTION_DRAFT_LOGS {
        uuid id PK
        uuid session_id FK
        string motion_type
        string status
        jsonb document_paths
        timestamp created_at
        timestamp completed_at
    }
    USER_ACTIVITY_LOGS {
        uuid id PK
        uuid session_id FK
        string action
        string metadata
        timestamp created_at
    }
    REVIEW_RESULTS {
        uuid id PK
        uuid session_id FK
        jsonb result
        timestamp created_at
    }
    MONITORED_MOTIONS {
        uuid id PK
        uuid session_id FK
        string motion_type
        string status
    }
    USERS {
        uuid id PK
        string email
        string hashed_password
        timestamp created_at
    }

    SESSIONS ||--o{ PDF_DOCUMENTS : "has"
    SESSIONS ||--o{ CHAT_THREADS : "has"
    CHAT_THREADS ||--o{ CHAT_MESSAGES : "has"
    SESSIONS ||--o{ MOTION_DRAFT_LOGS : "has"
    SESSIONS ||--o{ USER_ACTIVITY_LOGS : "has"
    SESSIONS ||--o{ REVIEW_RESULTS : "has"
    SESSIONS ||--o{ MONITORED_MOTIONS : "has"
    SESSIONS ||--o{ COURTDRIVE_INGESTIONS : "has"
```

**Three separate PostgreSQL instances:**

| Instance | Env prefix | Purpose |
|---|---|---|
| `chat_db` | `CHAT_DATABASE_*` | Sessions, PDFs, threads, messages, motion logs, activity logs, reviews, monitored motions |
| `user_db` | `USER_DATABASE_*` | User credentials only |
| `vectorstore` | `VECTORSTORE_*` | pgvector — all embedded document chunks |

---

## 8. Vectorstore Collections

| Collection Name | Content | Created By | Consumed By |
|---|---|---|---|
| `bankruptcy_knowledge_<session_id>` | Petition PDF pages (chunked + embedded) | `chatbot/vectorestore.py` on PDF upload | All extraction agents — petition context |
| `gmail_<session_id>` | Court email threads (embedded) | `gmail/service/ingest.py` on Gmail ingest | All Gmail extraction agents |
| `gmail_dismissed_<session_id>` | Dismissed case emails only | `gmail/service/ingest.py` | Motion `extend` agent only |
| `generated_motion` | Text extracted from generated DOCX | `tasks/pleading_helpers.py` after doc generation | Future agent references to previously drafted motions |

---

## 9. AI Models & Usage

| Model | Provider | Temperature | Used For |
|---|---|---|---|
| `gpt-4.1-mini` | OpenAI | 0.3 | LangGraph ReAct agents — Gmail field extraction (all 20 motion types), chatbot reasoning |
| `gpt-4o-mini` | OpenAI | 0.7 | Creative text enhancement inside motion templates (`motion_filling/*.py`) |
| `gpt-5.4-mini` (reasoning=`low`) | OpenAI | 0 | Complex trustee reasoning — `extend` motion agent only |
| `text-embedding-3-small` | OpenAI | — | Embedding petition PDFs + court emails into pgvector |
| `claude-sonnet-4-6` | Anthropic | 0 | Chatbot agents (`agents/chat.py`), parallel petition review (`agents/review.py`), Gmail field extraction, recommendation chips, dashboard AI insights (`analytics_insights.py`), Claude Vision PDF queries (`petition_vision_extractor.py`) |
| `claude-opus-4-6` | Anthropic | 0 | Deep reasoning on complex extraction tasks |

---

## 10. Background Services

| Service | File | Trigger | What It Does |
|---|---|---|---|
| `CourtMailPollWorker` | `src/gmail/poll_worker.py` | Hourly (`COURT_MAIL_POLL_INTERVAL_SECONDS=3600`) + optional on startup | Fetches up to 50 new court emails via Gmail API, embeds + stores per active session |
| `cleanup_stale_tasks` | `src/tasks/cleanup_tasks_taskiq.py` | Every 5 min (Taskiq scheduler) | Removes tasks stuck in non-terminal states beyond threshold time |
| `reconcile_auto_archived_petitions` | `src/tasks/cleanup_tasks_taskiq.py` | Every 30 min (Taskiq scheduler) | Marks pending sessions whose petition files were archived as inactive |
| `ActivityLogMiddleware` | `src/main.py` | Every HTTP request | Intercepts all API responses (status < 400), logs action name + metadata + duration to `user_activity_logs` table |

---

## 11. Frontend Connection Patterns

| Pattern | Endpoint Pattern | Used For |
|---|---|---|
| **REST + JWT** | `/api/auth/*`, `/api/chatbot/*`, `/api/motions/*` | Login, session management, PDF upload, file download, dashboard |
| **Long-poll** | `GET /api/pleadings/tasks/{task_id}` | Client polls every ~2s waiting for `AWAITING_INPUT` or `COMPLETED` |
| **Long-poll** | `GET /api/reviews/tasks/{task_id}` | Same pattern for petition review tasks |
| **SSE** | `GET /api/events?user_id={uid}` | Real-time task state push for both pleading + review tasks via Redis Streams; supports `Last-Event-ID` reconnect |
| **SSE** | `GET /api/motion-objection-sustain-stream/{session_id}` | Real-time generation progress for objection sustain motion |
| **SSE** | `GET /api/pdf/{session_id}/analyze-stream` | Real-time PDF analysis progress on petition upload |
| **SSE** | `GET /api/dashboard/analytics/insights` | Streaming Claude-generated dashboard insights |

No WebSockets — all real-time communication is SSE or client-side polling.

---

## 12. Dashboard Analytics

The dashboard (`src/routes/dashboard/`) is assembled from 9 sub-modules and exposes analytics, KPIs, AI-powered insights, an audit log, and data exports.

### Endpoint Reference

| Endpoint | Module | Description |
|---|---|---|
| `GET /api/dashboard/cases` | `kpis.py` | Global case KPI: total, active, by chapter |
| `GET /api/dashboard/users` | `kpis.py` | User KPI: total registered, active |
| `GET /api/dashboard/motions` | `kpis.py` | Motion KPI: total by type, orders vs motions |
| `GET /api/dashboard/charts/motions-daily` | `kpis.py` | 30-day motion volume trend |
| `GET /api/dashboard/charts/cases-daily` | `kpis.py` | 30-day case volume trend |
| `GET /api/dashboard/charts/motions-by-type` | `kpis.py` | Motion composition data (pie chart) |
| `GET /api/dashboard/system/status` | `kpis.py` | Court-mail poll worker health, last run time + result |
| `GET /api/dashboard/analytics/insights` | `analytics_insights.py` | Claude-powered AI insights (SSE, streaming) |
| `GET /api/dashboard/analytics/users` | `analytics_users.py` | Per-user activity breakdown |
| `GET /api/dashboard/analytics/users/{user_id}` | `analytics_users_detail.py` | Single-user detail with activity trend |
| `GET /api/dashboard/analytics/cases` | `analytics_cases.py` | Case list with status, chapter, motion history |
| `GET /api/dashboard/analytics/motions` | `analytics_motions.py` | Motion history by type, session, status |
| `GET /api/dashboard/activity-log` | `activity_log.py` | Full audit log with advanced filtering |
| `GET /api/dashboard/activity-log/actions` | `activity_log.py` | Distinct action keys + counts (for filter dropdowns) |
| `GET /api/dashboard/export/users` | `exports.py` | CSV / JSON export of all users |
| `GET /api/dashboard/export/users/{user_id}` | `exports.py` | CSV / JSON export of single user |

### AI Insights Flow

```mermaid
flowchart TD
    A["GET /api/dashboard/analytics/insights\n?date_range=30d"] --> B{"Cache hit?\n5-min TTL keyed by\nstart_iso + end_iso"}
    B -- Hit --> Z["Stream cached response"]
    B -- Miss --> C["Compute period-over-period metrics\ncurrent period vs prior equal-length period"]
    C --> D["Build Claude tool context\nquery_activity_log() · list_all_analytics_data()"]
    D --> E["Claude Sonnet 4.6\nInvoke with tools"]
    E -- "calls tool" --> F["query_activity_log()\nfiltered audit log entries"]
    E -- "calls tool" --> G["list_all_analytics_data()\nconsolidated motion/case metrics"]
    F & G --> E
    E --> H["Generate markdown insights\n+ suggested actions"]
    H --> I["Stream response to frontend\n+ store in 5-min cache"]
```

### Activity Log Middleware

`ActivityLogMiddleware` (`src/main.py`) runs on every HTTP response with status < 400:

- Matches request method + path prefix to a named **action** (`generate_document`, `download_motion`, `upload_pdf`, `accept_case`, `draft_motion`, etc.)
- Extracts `user_id` from the JWT Bearer token if present
- Captures metadata: `status_code`, `duration_ms`, `motion_type`, `format`, `session_id`
- Writes a row to `user_activity_logs` in `chat_db`
- Powers the audit log, per-user analytics, and AI insights

---

## 13. Petition Review Flow

The review system runs a **parallel, multi-group analysis** of an uploaded bankruptcy petition and synthesizes the findings into a single master review.

### Review Task State Machine

```mermaid
stateDiagram-v2
    [*] --> PENDING : task dispatched to queue

    PENDING --> PROCESSING : worker picks up task

    PROCESSING --> COMPLETED : all groups + master review complete\nresult saved to DB + chat thread
    PROCESSING --> FAILED : extraction or agent error
    PROCESSING --> CANCELLED : user cancels

    PENDING --> CANCELLED : user cancels
```

**Redis key:** `review_task:{task_id}` · TTL: 2 hours

### Sequence Diagram

```mermaid
sequenceDiagram
    actor User
    participant FE as Frontend
    participant API as FastAPI
    participant RevOrch as review_orchestrator.py
    participant Q as Taskiq / Redis
    participant Parallel as parallel_reviewer.py
    participant Agents as chatbot/agents/review.py
    participant LLM as Claude Sonnet 4.6
    participant DB as chat_db

    User->>FE: Open session with uploaded petition PDF
    FE->>API: POST /api/reviews/start\n{ session_id, pdf_path }
    API->>RevOrch: start_review_task(user_id, session_id, pdf_path)
    RevOrch->>Q: enqueue run_petition_review(task_id)
    API-->>FE: { task_id, status: PENDING }

    FE->>API: GET /api/events (SSE — receives status updates)

    note over Q: Status → PROCESSING
    Q->>Parallel: run_parallel_bankruptcy_review_async(pdf_path, session_id)

    note over Parallel: Phase 1 — Extract Client Info
    Parallel->>Agents: CaseNumberAgent + DebtorNameAgent
    Agents->>LLM: Extract case number + debtor name from PDF
    LLM-->>Agents: case_number, debtor_name

    note over Parallel: Phase 2 — Parallel Group Reviews
    par Schedule A/B (property)
        Parallel->>Agents: BankruptcyReviewAgent("AB")
        Agents->>LLM: Review with AB_PROMPT
        LLM-->>Agents: AB review text
    and Schedule C/D (debts + exemptions)
        Parallel->>Agents: BankruptcyReviewAgent("CD")
        Agents->>LLM: Review with CD_PROMPT
        LLM-->>Agents: CD review text
    and Schedule I/J/Summary (income + expenses)
        Parallel->>Agents: BankruptcyReviewAgent("IJ")
        Agents->>LLM: Review with IJ_PROMPT
        LLM-->>Agents: IJ review text
    and SOFA (Statement of Financial Affairs)
        Parallel->>Agents: BankruptcyReviewAgent("SOFA")
        Agents->>LLM: Review with SOFA_PROMPT
        LLM-->>Agents: SOFA review text
    end

    note over Parallel: Cascade dependencies
    Parallel->>Agents: BankruptcyReviewAgent("EF") with SOFA context
    Agents->>LLM: Review E/F creditors
    LLM-->>Agents: EF review text
    Parallel->>Agents: BankruptcyReviewAgent("GH") with E/F context
    Agents->>LLM: Review G/H contracts + codebtors
    LLM-->>Agents: GH review text

    note over Parallel: Phase 3 — Master Synthesis
    Parallel->>Agents: MasterReviewAgent.run_master_review(all_group_reviews)
    Agents->>LLM: Synthesize all groups into executive summary
    LLM-->>Agents: master_review markdown

    Parallel-->>Q: { debtor_name, case_number, group_reviews, master_review }

    Q->>DB: Save to ReviewResults + ChatThread
    note over Q: Status → COMPLETED

    API-->>FE: SSE event: { status: COMPLETED }
    FE->>API: GET /api/reviews/tasks/{task_id}
    API-->>FE: { master_review, group_reviews, debtor_name, case_number }
    User->>FE: View review results
```

### Schedule Group Breakdown

| Group | Schedules Covered | Depends On |
|---|---|---|
| `AB` | Schedule A/B — Real & Personal Property | None |
| `CD` | Schedule C (Exemptions) + D (Secured Creditors) | None |
| `IJ` | Schedule I (Income), J (Expenses), Summary of Schedules | None |
| `SOFA` | Statement of Financial Affairs | None |
| `EF` | Schedule E/F — Unsecured Priority + Non-Priority Creditors | SOFA |
| `GH` | Schedule G (Executory Contracts), H (Codebtors) | E/F |

Groups A/B, C/D, I/J, and SOFA run fully in parallel. E/F and G/H run sequentially after their dependencies complete, injecting prior group results as context.

---

## 14. Task Event Stream

Both pleading and review task systems emit real-time state changes to the frontend over a single SSE connection backed by **Redis Streams**.

### Architecture

```mermaid
flowchart LR
    A["PleadingTaskState\ntask_state.py"] -- "emit_task_event()" --> C["Redis Stream\nuser_events:{user_id}\nXADD · MAXLEN 500"]
    B["ReviewTaskState\nreview_task_state.py"] -- "emit_task_event()" --> C
    C -- "XREAD BLOCK 15s" --> D["routes/events.py\nGET /api/events"]
    D -- "SSE text/event-stream" --> E["Frontend\nnative EventSource"]
    E -- "Last-Event-ID header\non reconnect" --> D
```

### SSE Endpoint Behavior

**`GET /api/events?user_id={uid}`**

1. On connect: snapshot current state of all active pleading + review tasks for the user and emit immediately
2. Tail `user_events:{user_id}` stream via `XREAD BLOCK 15000` (15-second timeout)
3. On timeout (no new events): emit a `:keepalive` SSE comment to prevent connection drop
4. On reconnect: client sends `Last-Event-ID` header; server resumes from that stream entry ID — no missed events

### Event Types

| Event | Emitted When |
|---|---|
| `status_changed` | Task transitions to any new `TaskStatus` value |
| `progress` | Worker updates `progress_message` (e.g., "Ingesting Gmail emails…") |
| `input_required` | Extraction complete, user must fill free-text fields before generation |
| `existing_found` | Existing documents detected for the session |
| `completed` | Documents generated and written to disk / review saved to DB |
| `failed` | Unrecoverable error — includes `error_detail` |
| `cancelled` | User or system cancelled the task |

### Redis Stream Configuration

| Setting | Value |
|---|---|
| Key pattern | `user_events:{user_id}` |
| Max entries per stream | 500 (MAXLEN, trimmed on XADD) |
| Stream TTL | 7 200 s (2 hours) |
| XREAD block timeout | 15 000 ms |

---

## 15. Key Environment Variables

See [README.md](../README.md) for the full `.env` reference. Non-obvious ones explained:

| Variable | Why it matters |
|---|---|
| `SFTP_DESTINATION` | Local path mounted read-only into containers as `/app/uploads/archived_petitions` |
| `GMAIL_V2_CREDENTIALS_PATH` | Override default `src/gmail/credentials.json` OAuth2 file location |
| `COURT_MAIL_POLL_RUN_ON_STARTUP` | `true` = poll Gmail immediately on backend start, not just on schedule |
| `MAX_CONCURRENT_PLEADING_TASKS` | Per-user cap on simultaneous in-flight pleading generation tasks |
| `MAX_CONCURRENT_REVIEW_TASKS` | Per-user cap on simultaneous in-flight petition review tasks |
