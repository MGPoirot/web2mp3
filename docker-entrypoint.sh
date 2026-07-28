#!/bin/sh
set -e

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

# Remap the baked-in appuser to whatever PUID/PGID this host's mounted
# volumes actually need, so one published image works on any host.
groupmod -o -g "$PGID" appuser
usermod -o -u "$PUID" appuser

mkdir -p .config .logs .daemons src/index

# A hard container stop/OOM leaves stale daemon lock files behind (they're
# only cleaned up via atexit). A freshly-started container has no real
# daemons running yet, so it's always safe to clear them here.
rm -f .daemons/*.tmp 2>/dev/null || true

exec setpriv --reuid "$PUID" --regid "$PGID" --clear-groups "$@"
