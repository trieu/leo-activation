#!/usr/bin/env bash
set -euo pipefail

# Safely resolve the directory containing this script and docker-compose.yml
# (Assumes this script is saved in the same directory as docker-compose.yml)
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

PROFILE_ID="6D8sWO4mkAQgwPV02vzzqi"

echo "--- Starting scheduled job for profile $PROFILE_ID at $(date) ---"

# Use Docker Compose to run commands sequentially inside the container.
# Notice the addition of the '-T' flag to prevent TTY errors in cron.
/usr/bin/docker compose run -T --rm api bash -c "
    echo '--- Step 1: Syncing profile ---' && \
    python tests/test_synch_profile.py '$PROFILE_ID' && \
    echo '--- Step 2: Running interest score calculation ---' && \
    python -m agentic_tools.recommendation_system.interest_score && \
    echo '--- Step 3: Running recommendation orchestrator (NBA/NLA upsert) ---' && \
    python -m agentic_tools.recommendation_orchestrator
"

echo "--- Job Complete at $(date) ---"