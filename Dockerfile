FROM python:3.10-slim-bookworm

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

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY as-app /usr/local/bin/as-app
RUN chmod +x /usr/local/bin/docker-entrypoint.sh /usr/local/bin/as-app \
    && mkdir -p .config .logs .daemons src/index Music \
    && chmod -R a+rX /app

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["sleep", "infinity"]
