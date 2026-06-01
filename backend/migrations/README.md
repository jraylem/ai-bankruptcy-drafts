# Database Migrations

This directory contains database migration scripts for schema changes.

## Running Migrations

### ⚠️ Important: Run Inside Docker Container

Migration scripts **must be run inside the Docker container** because:
- Database hostnames (`chat_db`, `user_db`, `vectorstore`) only resolve inside the Docker network
- The `.env` configuration expects Docker service names as hosts
- This ensures proper network connectivity to PostgreSQL containers

### Using Docker (Required):

```bash
# 1. Make sure all services are running
docker compose up -d

# 2. Run the migration inside the backend container
# Use 'uv run python' since the project uses uv package manager
docker compose exec backend uv run python migrations/add_case_number_to_threads.py

# Or using module syntax:
docker compose exec backend uv run python -m migrations.add_case_number_to_threads
```

### Alternative: If running from host machine

If you need to run from the host machine, you would need to:
1. Modify the database URL temporarily to use `localhost` instead of `chat_db`
2. Use the mapped port (e.g., `5433` for chat_db)
3. **Not recommended** - Use Docker method instead

## Migration Scripts

### `add_case_number_to_threads.py`

Adds the `case_number` column to the `chat_threads` table.

- **Date**: 2025-01-XX
- **Purpose**: Add case_number field to thread metadata
- **Status**: Ready to run
- **Safety**: Checks if column exists before adding (idempotent)

### `add_is_viewed_to_courtdrive_ingestions.py`

Adds the `is_viewed` column to the `courtdrive_ingestions` table.

- **Date**: 2026-03-12
- **Purpose**: Persist whether a pending petition candidate has been opened by the user
- **Status**: Ready to run
- **Safety**: Checks if column exists before adding (idempotent)

## Notes

- All migrations should be idempotent (safe to run multiple times)
- Always backup your database before running migrations in production
- Test migrations in a development environment first

