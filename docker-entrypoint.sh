#!/bin/sh
set -e

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

# Remap the baked-in appuser to whatever PUID/PGID this host's mounted
# volumes actually need, so one published image works on any host.
groupmod -o -g "$PGID" appuser
usermod -o -u "$PUID" appuser

mkdir -p .config .logs .daemons src/index .gui/transcripts

# .daemons is a tmpfs mount (see docker-compose.yml) — it's purely
# in-container coordination state (PID lock files), so it's mounted fresh
# and empty on every container start, owned by root. Hand it to the
# unprivileged user so it can actually create lock files there. This also
# means the old stale-lock-cleanup-on-crash concern no longer applies: a
# fresh tmpfs has nothing stale to clean up.
chown "$PUID:$PGID" .daemons

# .gui is a bind mount; Docker auto-creates it owned by root the first time
# it doesn't exist on the host, and the mkdir -p above (still running as
# root) doesn't fix that. -R is fine here: unlike /music, this only ever
# holds a small sqlite db and small per-submission transcripts.
chown -R "$PUID:$PGID" .gui

# setpriv changes uid/gid but not $HOME -- left as root's "/root", tools
# like yt-dlp resolve their cache dir off $HOME and would try (and fail) to
# write to /root/.cache once running as the unprivileged user. Point HOME
# at appuser's real home instead, and make sure it's actually owned by
# whatever PUID/PGID it just got remapped to (usermod -u alone doesn't
# chown existing files).
chown -R "$PUID:$PGID" /home/appuser
export HOME=/home/appuser

exec setpriv --reuid "$PUID" --regid "$PGID" --clear-groups "$@"
