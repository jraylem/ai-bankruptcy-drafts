#!/bin/bash
# Pre-start hook for the backend container. Used to block on local Postgres
# containers becoming ready, but those are now managed externally (Neon),
# so there's nothing to wait for. Kept as a no-op exec wrapper so the
# Dockerfile CMD chain stays unchanged.

set -e
exec "$@"
