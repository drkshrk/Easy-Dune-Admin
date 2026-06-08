FROM python:3.11-slim

ARG TARGETARCH
ARG DOCKER_CLI_VERSION=27.5.1
ARG EDA_BUILD_REVISION=unknown
ARG EDA_BUILD_DIRTY=unknown

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EDA_DATA_DIR=/data \
    EDA_LOG_DIR=/data/logs \
    DUNE_ROOT=/redblink \
    ENABLE_HOST_COMMAND_RUNNER=1 \
    ENABLE_STACK_INSTALLER=0 \
    ENABLE_HOST_SHELL=0 \
    EDA_BUILD_REVISION="${EDA_BUILD_REVISION}" \
    EDA_BUILD_DIRTY="${EDA_BUILD_DIRTY}"

WORKDIR /app

# Easy Dune Admin shells out to RedBlink's `runtime/scripts/dune`, which in
# turn expects common Linux tooling and Docker access. The Docker socket is
# mounted at runtime by docker-compose.yml; the official static Docker CLI
# supplies the client because Debian slim images do not always include docker.io.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        iproute2 \
        netcat-openbsd \
        procps \
        screen \
        tar \
        tini \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    case "${TARGETARCH:-amd64}" in \
        amd64) docker_arch="x86_64" ;; \
        arm64) docker_arch="aarch64" ;; \
        *) echo "Unsupported Docker CLI architecture: ${TARGETARCH:-unknown}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://download.docker.com/linux/static/stable/${docker_arch}/docker-${DOCKER_CLI_VERSION}.tgz" -o /tmp/docker.tgz; \
    tar -xzf /tmp/docker.tgz -C /tmp; \
    mv /tmp/docker/docker /usr/local/bin/docker; \
    chmod +x /usr/local/bin/docker; \
    rm -rf /tmp/docker /tmp/docker.tgz; \
    docker --version

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY docker/entrypoint.sh /usr/local/bin/easy-dune-admin-entrypoint.sh
RUN chmod +x /usr/local/bin/easy-dune-admin-entrypoint.sh

VOLUME ["/data"]
EXPOSE 8089

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8089/login', timeout=3).read()"

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/easy-dune-admin-entrypoint.sh"]
CMD ["python", "app.py"]
