FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        curl \
        unzip \
        ca-certificates \
        util-linux \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh

# Baseline non-root user; docker-entrypoint.sh remaps it to the PUID/PGID
# given at container start, so a single published image works on any host
# regardless of what UID/GID owns its mounted volumes.
RUN useradd -m -u 1000 -s /bin/sh appuser

# docker-entrypoint.sh exports this too, but `docker exec` bypasses ENTRYPOINT
# entirely -- so dl/daemon/inspect/cookie would otherwise inherit root's
# HOME=/root, drop to the unprivileged uid via setpriv, and leave yt-dlp
# trying to write its cache into a directory it can no longer touch.
ENV HOME=/home/appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY docker-cmd.sh /usr/local/bin/docker-cmd.sh
COPY dl inspect cookie daemon /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh /usr/local/bin/docker-cmd.sh \
        /usr/local/bin/dl /usr/local/bin/inspect /usr/local/bin/cookie \
        /usr/local/bin/daemon \
    && mkdir -p .config .logs .daemons src/index .gui/transcripts Music \
    && chmod -R a+rX /app

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["docker-cmd.sh"]
