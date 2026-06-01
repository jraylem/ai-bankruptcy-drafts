# BKDrafts Backend

FastAPI backend for AI-powered bankruptcy motion drafting, petition review, and Gmail court mail ingestion.

> For a full system architecture overview, diagrams, and module breakdown, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Prerequisites

- Docker Desktop installed and running

## 1) Environment variables

Create a `.env` file in the `bkdrafts-be/` root. All variables below are required unless marked optional.

```bash
# ── AI Providers ──────────────────────────────────────────────────────────────
OPENAI_API_KEY=your_openai_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key

# ── Server ────────────────────────────────────────────────────────────────────
HOST=0.0.0.0
PORT=8000

# ── CORS ──────────────────────────────────────────────────────────────────────
ALLOWED_ORIGINS=["http://your_ip_address", "http://your_ip_address:80"]

# ── File Upload ───────────────────────────────────────────────────────────────
MAX_FILE_SIZE_MB=50

# ── Vectorstore (pgvector) ────────────────────────────────────────────────────
VECTORSTORE_USER=postgres
VECTORSTORE_PASSWORD=postgres
VECTORSTORE_DB=vectorstore_db
VECTORSTORE_HOST=vectorstore
VECTORSTORE_PORT=5432
VECTORSTORE_URL=postgresql+psycopg://postgres:postgres@vectorstore:5432/vectorstore_db

# ── Session / PDF Database ────────────────────────────────────────────────────
CHAT_DATABASE_USER=postgres
CHAT_DATABASE_PASSWORD=postgres
CHAT_DATABASE_DB=chat_db
CHAT_DATABASE_HOST=chat_db
CHAT_DATABASE_PORT=5433
CHAT_DATABASE_URL=postgresql+asyncpg://postgres:postgres@chat_db:5432/chat_db

# ── User Authentication Database ──────────────────────────────────────────────
USER_DATABASE_USER=postgres
USER_DATABASE_PASSWORD=postgres
USER_DATABASE_DB=user_db
USER_DATABASE_HOST=user_db
USER_DATABASE_PORT=5434
USER_DATABASE_URL=postgresql+asyncpg://postgres:postgres@user_db:5432/user_db

# ── JWT ───────────────────────────────────────────────────────────────────────
JWT_SECRET_KEY=your_jwt_secret_key
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30

# ── Redis (Taskiq broker) ────────────────────────────────────────────────────
REDIS_URL=redis://redis:6379/0
REDIS_PORT=6379          # optional, default 6379

# ── SFTP / Archived Petitions ─────────────────────────────────────────────────
SFTP_DESTINATION=/path/to/archived_petitions  # mounted read-only into containers

# ── Court Mail Polling Worker (optional — all have defaults) ──────────────────
COURT_MAIL_POLL_WORKER_ENABLED=true
COURT_MAIL_POLL_INTERVAL_SECONDS=3600
COURT_MAIL_POLL_MAX_RESULTS_PER_TRIGGER=50
COURT_MAIL_POLL_RUN_ON_STARTUP=true

# ── Task Queue Concurrency (optional — all have defaults) ─────────────────────
MAX_CONCURRENT_PLEADING_TASKS=20
MAX_CONCURRENT_REVIEW_TASKS=20
```

## 2) Google OAuth2 credentials (Gmail + Drive)

The Gmail court mail and Google Drive integrations use OAuth2 credentials rather than an API key.

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create or select a project
3. Enable the **Gmail API** and **Google Drive API**
4. Create **OAuth 2.0 credentials** (Desktop App type)
5. Download the credentials file and place it at:

```
src/gmail/credentials.json
```

On first run, a browser window will open for you to authorize access. The resulting token is saved automatically to `src/gmail/token.json` (Gmail) and `src/gmail/drive_token.json` (Drive) and reused on subsequent runs.

> **Optional:** Override the default file locations via env vars:
> ```bash
> GMAIL_V2_CREDENTIALS_PATH=/custom/path/credentials.json
> GMAIL_V2_TOKEN_PATH=/custom/path/token.json
> ```

## 3) Run with Docker Compose

First time (or after any code/dependency change):

```bash
docker compose up --build -d
```

Subsequent starts (no rebuild needed):

```bash
docker compose up -d
```

View logs:

```bash
docker compose logs -f backend
```

Stop all services:

```bash
docker compose down --remove-orphans
```

API default URL: `http://localhost:8000`

### Services started by default

| Service | Description |
|---|---|
| `backend` | FastAPI application (port 8000) |
| `vectorstore` | pgvector (PostgreSQL) for document embeddings |
| `chat_db` | PostgreSQL for sessions and PDF metadata |
| `user_db` | PostgreSQL for user authentication |
| `redis` | Redis broker for task queue (port 6379) |
| `taskiq_worker` | Async task workers (3 replicas) |
| `taskiq_scheduler` | Periodic task scheduler (stale cleanup, etc.) |
