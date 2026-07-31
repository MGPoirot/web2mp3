#!/bin/sh
# Container's default long-running process (this is what docker-entrypoint.sh
# execs, after remapping to PUID/PGID). Runs the optional web GUI unless
# explicitly disabled via GUI_ENABLED=false, in which case the container just
# idles as it always has -- the dl/cookie/inspect commands work via
# `docker exec` either way, regardless of this setting.
if [ "${GUI_ENABLED:-true}" != "false" ]; then
    exec python -m uvicorn src.gui.server:app --host 0.0.0.0 --port "${GUI_PORT:-4546}"
else
    exec sleep infinity
fi
