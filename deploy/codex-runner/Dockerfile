# syntax=docker/dockerfile:1.7
FROM node:24.19.0-bookworm-slim AS runtime
RUN npm install --global --prefix /runtime @openai/codex@0.149.0 \
    && mkdir -p /runtime/node/bin \
    && cp /usr/local/bin/node /runtime/node/bin/

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    HOME=/var/lib/tubeforge-codex CODEX_HOME=/var/lib/tubeforge-codex/.codex \
    TIKTOKEN_CACHE_DIR=/opt/tubeforge-codex-runner/tokenizer-cache
RUN apt-get update \
    && apt-get install -y --no-install-recommends bubblewrap ca-certificates libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 writer-socket \
    && useradd --uid 10001 --gid 1000 --home-dir /var/lib/tubeforge-codex tubeforge-codex \
    && install -d -m 0700 -o 10001 -g 1000 /var/lib/tubeforge-codex /var/lib/tubeforge-codex/.codex \
    && install -d -m 0750 -o 10001 -g 1000 /run/tubeforge-codex
COPY --from=runtime /runtime /opt/tubeforge-codex-runner/codex-runtime
WORKDIR /build
COPY pyproject.toml readme.md ./
COPY src ./src
COPY .agents/skills ./.agents/skills
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install '.[codex-runner]' \
    && python -c "import tiktoken; tiktoken.get_encoding('o200k_base')" \
    && chmod -R a+rX "$TIKTOKEN_CACHE_DIR"
COPY deploy/codex-runner/listen.py /usr/local/lib/tubeforge-codex-listen.py
WORKDIR /
USER 10001:1000
CMD ["python", "/usr/local/lib/tubeforge-codex-listen.py"]
