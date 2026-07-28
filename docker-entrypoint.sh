#!/bin/sh
set -e

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

# Remap the baked-in appuser to whatever PUID/PGID this host's mounted
# volumes actually need, so one published image works on any host.
groupmod -o -g "$PGID" appuser
usermod -o -u "$PUID" appuser

mkdir -p .config .logs .daemons src/index

# .daemons is a tmpfs mount (see docker-compose.yml) — it's purely
# in-container coordination state (PID lock files), so it's mounted fresh
# and empty on every container start, owned by root. Hand it to the
# unprivileged user so it can actually create lock files there. This also
# means the old stale-lock-cleanup-on-crash concern no longer applies: a
# fresh tmpfs has nothing stale to clean up.
chown "$PUID:$PGID" .daemons

exec setpriv --reuid "$PUID" --regid "$PGID" --clear-groups "$@"
