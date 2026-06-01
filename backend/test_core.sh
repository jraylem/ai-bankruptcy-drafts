#!/bin/bash
# Run the `src/core/` pytest suite via uv so the venv doesn't need to be
# activated in your shell.
#
# Usage:
#   ./test_core.sh                       # run every test under tests/core/
#   ./test_core.sh -m unit               # only unit-marked tests
#   ./test_core.sh -m "not e2e"          # skip e2e layer
#   ./test_core.sh --snapshot-update     # regenerate syrupy snapshots
#   ./test_core.sh tests/core/agents/    # run a specific subtree
#   ./test_core.sh -k derivative -v      # filter by name, verbose
#   ./test_core.sh --coverage            # measure coverage of src/core
#                                          (term + HTML report; gates on
#                                          >=85% via [tool.coverage.report]
#                                          fail_under in pyproject.toml)
#
# Any args other than --coverage are forwarded to pytest verbatim.
#
# Side effect (first run only): installs the pre-push git hook from
# .pre-commit-config.yaml so subsequent `git push`es run this same suite
# locally before contacting the remote. The pre-push hook always passes
# --coverage so pushes are gated on the 85% threshold. Skip with
# `git push --no-verify` only when there's a real reason.

set -euo pipefail

cd "$(dirname "$0")"

_hook=".git/hooks/pre-push"
if [ -f .pre-commit-config.yaml ] && { [ ! -f "$_hook" ] || ! grep -q pre-commit "$_hook" 2>/dev/null; }; then
    echo "Installing pre-push hook (first-run setup) ..."
    uv run pre-commit install --hook-type pre-push >/dev/null
fi

# Detect --coverage flag and expand it into pytest-cov args. Coverage scope
# (src/core) and the 85% fail-under threshold live in pyproject.toml under
# [tool.coverage.*]; we only pass the report formats here so HTML lands in
# htmlcov/ for inspection.
COV_ARGS=()
PYTEST_ARGS=()
for arg in "$@"; do
    if [[ "$arg" == "--coverage" ]]; then
        COV_ARGS=(--cov=src/core --cov-branch --cov-report=term-missing --cov-report=html)
    else
        PYTEST_ARGS+=("$arg")
    fi
done

exec uv run pytest tests/core/ ${COV_ARGS[@]+"${COV_ARGS[@]}"} ${PYTEST_ARGS[@]+"${PYTEST_ARGS[@]}"}
