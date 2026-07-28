#!/bin/sh
set -e

mkdir -p .config .logs .daemons src/index

# A hard container stop/OOM leaves stale daemon lock files behind (they're
# only cleaned up via atexit). A freshly-started container has no real
# daemons running yet, so it's always safe to clear them here.
rm -f .daemons/*.tmp 2>/dev/null || true

exec "$@"
