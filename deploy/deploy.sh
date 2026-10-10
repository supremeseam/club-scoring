#!/usr/bin/env bash
# Pull, rebuild and restart. Migrations run automatically in the app container's entrypoint.
set -euo pipefail
cd "$(dirname "$0")/.."
git pull --ff-only
docker compose --profile backup build
docker compose --profile backup up -d
docker image prune -f >/dev/null
docker compose ps
