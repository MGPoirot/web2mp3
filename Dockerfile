FROM python:3.10-slim-bookworm

ARG UID=1000
ARG GID=1000

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        curl \
        unzip \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh

RUN (getent group "${GID}" || groupadd -g "${GID}" appuser) \
    && useradd -m -u "${UID}" -g "${GID}" appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
    && mkdir -p .config .logs .daemons src/index Music \
    && chown -R "${UID}:${GID}" /app

USER appuser

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["sleep", "infinity"]
