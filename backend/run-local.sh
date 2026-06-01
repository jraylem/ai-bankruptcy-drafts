#!/bin/bash

cd "$(dirname "$0")"

# macOS: ensure homebrew binaries are in PATH (for soffice/LibreOffice)
if [[ "$OSTYPE" == "darwin"* ]]; then
  export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
fi

# macOS fork safety workaround
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES

# Start Taskiq worker and scheduler in the background
echo "Starting Taskiq worker..."
TASKIQ_WORKER=true uv run taskiq worker src.taskiq_app:broker --workers 1 &
TASKIQ_WORKER_PID=$!

echo "Starting Taskiq scheduler..."
uv run taskiq scheduler src.taskiq_scheduler:scheduler &
TASKIQ_SCHEDULER_PID=$!

trap "echo 'Stopping Taskiq...'; kill $TASKIQ_WORKER_PID $TASKIQ_SCHEDULER_PID 2>/dev/null" EXIT

# Start FastAPI
echo "Starting FastAPI..."
uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
