#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose up -d
echo
echo "Doccano should be at: http://localhost:8000"
echo "Login:"
echo "  username: admin"
echo "  password: password"
