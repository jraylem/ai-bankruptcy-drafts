#!/bin/bash
# Run hand-written migration scripts in `migrations/` via
# `docker compose exec backend uv run`.
#
# A scope flag is REQUIRED — the script intentionally refuses to do
# anything without one so you can't accidentally re-run every migration
# in the repo just by mistyping. Pick exactly one of:
#
#   --all                  Run EVERY migration in migrations/ (the
#                          historical default; safe because each script
#                          is idempotent, but slow on first-run DBs).
#   --latest               Run only migrations ADDED in the last 15
#                          commits. Default post-pull / post-merge mode.
#   --last N               Run only migrations ADDED in the last N commits.
#   --since <ref>          Run only migrations ADDED in <ref>..HEAD.
#                          e.g. --since main, --since origin/feat-X.
#
# Plus the same modifier flags as before:
#   <substring>            Filename substring filter (e.g. "unfiled").
#   --dry-run              List what WOULD run, don't exec.
#   --service <name>       Non-default compose service (default: backend).
#
# --latest, --last, --since all use `git diff --diff-filter=A` so
# MODIFIED migrations don't auto-run (they're already applied; re-running
# an edited one is a deliberate decision — invoke explicitly by filename).
#
# Every migration in this repo is hand-written async Python (NOT Alembic)
# and idempotent — re-running is safe. Order is alphabetical by filename,
# which historically matches dependency order (add_* before backfill_* /
# normalize_* / relax_*).
#
# Migrations MUST run inside the backend container because the database
# hostnames (`chat_db`, `user_db`, `vectorstore`) only resolve inside the
# compose network. See migrations/README.md for the rationale.

set -euo pipefail

cd "$(dirname "$0")"

SERVICE="backend"
DRY_RUN=0
FILTER=""
GIT_RANGE=""
SCOPE=""  # one of: all, latest, last:<N>, since:<ref>
DEFAULT_LATEST_LOOKBACK=15

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --all)
            SCOPE="all"
            shift
            ;;
        --latest)
            SCOPE="latest"
            GIT_RANGE="HEAD~${DEFAULT_LATEST_LOOKBACK}..HEAD"
            shift
            ;;
        --last)
            n="$2"
            if ! [[ "$n" =~ ^[0-9]+$ ]] || [ "$n" -lt 1 ]; then
                echo "ERROR: --last N requires a positive integer, got '$n'" >&2
                exit 2
            fi
            SCOPE="last:$n"
            GIT_RANGE="HEAD~${n}..HEAD"
            shift 2
            ;;
        --last=*)
            n="${1#*=}"
            if ! [[ "$n" =~ ^[0-9]+$ ]] || [ "$n" -lt 1 ]; then
                echo "ERROR: --last=N requires a positive integer, got '$n'" >&2
                exit 2
            fi
            SCOPE="last:$n"
            GIT_RANGE="HEAD~${n}..HEAD"
            shift
            ;;
        --since)
            SCOPE="since:$2"
            GIT_RANGE="$2..HEAD"
            shift 2
            ;;
        --since=*)
            SCOPE="since:${1#*=}"
            GIT_RANGE="${1#*=}..HEAD"
            shift
            ;;
        --service)
            SERVICE="$2"
            shift 2
            ;;
        --service=*)
            SERVICE="${1#*=}"
            shift
            ;;
        --help|-h)
            # Echo the leading comment block as built-in usage.
            sed -n '2,33p' "$0"
            exit 0
            ;;
        --*)
            echo "Unknown flag: $1" >&2
            exit 2
            ;;
        *)
            FILTER="$1"
            shift
            ;;
    esac
done

# No scope = refuse. We don't want a naked invocation to re-run every
# migration; that's a real load event on a populated DB and a long
# detour during normal dev flow.
if [[ -z "$SCOPE" ]]; then
    echo "ERROR: scope flag required. Pick one of:" >&2
    echo "  --all                      run every migration" >&2
    echo "  --latest                   migrations added in last ${DEFAULT_LATEST_LOOKBACK} commits" >&2
    echo "  --last N                   migrations added in last N commits" >&2
    echo "  --since <ref>              migrations added in <ref>..HEAD" >&2
    echo "" >&2
    echo "See ./run_migrations.sh --help for full usage." >&2
    exit 2
fi

# When --latest / --since is in play, ask git for the ADDED-only file list
# in the range. --diff-filter=A excludes modified (M) and deleted (D),
# so a re-edited-but-already-applied migration won't auto-run.
GIT_ADDED=""
if [[ -n "$GIT_RANGE" ]]; then
    if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        echo "ERROR: --latest/--since needs a git repo." >&2
        exit 2
    fi
    if ! GIT_ADDED="$(git diff --name-only --diff-filter=A "${GIT_RANGE}" -- 'migrations/*.py' 2>&1)"; then
        echo "ERROR: git diff failed for range '${GIT_RANGE}':" >&2
        echo "$GIT_ADDED" >&2
        exit 2
    fi
fi

# Collect migration scripts: every .py in migrations/ except __init__.py,
# alphabetically sorted. When --latest/--since is set, intersect with the
# git-added list. Optional FILTER substring is applied last.
MIGRATIONS=()
while IFS= read -r f; do
    base="$(basename "$f")"
    [[ "$base" == "__init__.py" ]] && continue
    if [[ -n "$GIT_RANGE" ]]; then
        # Intersect with the git --diff-filter=A list.
        if ! grep -qxF "$f" <<<"$GIT_ADDED"; then
            continue
        fi
    fi
    if [[ -n "$FILTER" && "$base" != *"$FILTER"* ]]; then
        continue
    fi
    MIGRATIONS+=("$f")
done < <(ls migrations/*.py 2>/dev/null | sort)

if [ ${#MIGRATIONS[@]} -eq 0 ]; then
    echo "No migrations found${FILTER:+ matching \"$FILTER\"}"
    exit 0
fi

echo "==> ${#MIGRATIONS[@]} migration(s) queued (service: ${SERVICE}):"
for m in "${MIGRATIONS[@]}"; do
    echo "    - $m"
done

if [ "$DRY_RUN" -eq 1 ]; then
    echo "(dry-run; not executing)"
    exit 0
fi

# Sanity-check the container is up before iterating — a clear error is
# nicer than a wall of `exec failed: container not running` per migration.
if ! docker compose ps --status running --services 2>/dev/null | grep -qx "${SERVICE}"; then
    echo "ERROR: docker compose service '${SERVICE}' is not running." >&2
    echo "       Start it with: docker compose up -d ${SERVICE}" >&2
    exit 1
fi

FAILED=()
for f in "${MIGRATIONS[@]}"; do
    echo ""
    echo "============================================================"
    echo "==> $f"
    echo "============================================================"
    if ! docker compose exec -T "${SERVICE}" uv run python "$f"; then
        FAILED+=("$f")
        echo "✗ FAILED: $f"
    fi
done

echo ""
if [ ${#FAILED[@]} -eq 0 ]; then
    echo "✅ All ${#MIGRATIONS[@]} migration(s) completed successfully."
    exit 0
fi

echo "❌ ${#FAILED[@]} migration(s) failed:"
for f in "${FAILED[@]}"; do
    echo "    - $f"
done
exit 1
