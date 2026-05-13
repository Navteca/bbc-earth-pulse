#!/bin/sh
# Start the ingestion/enrichment worker in the background.
# Both worker and server write to stdout — all logs visible via kubectl logs.
python -m earth_pulse.worker &
WORKER_PID=$!

# Start the MCP server in the foreground.
# When the server exits, kill the worker too so the container exits cleanly.
python -m earth_pulse.server_entry
SERVER_EXIT=$?

kill $WORKER_PID 2>/dev/null
exit $SERVER_EXIT
