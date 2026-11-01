# syntax=docker/dockerfile:1.7
# Layers run from least to most frequently changed, so editing source never reinstalls the heavy
# dependencies (onnxruntime, ctranslate2, kokoro, piper, playwright...):
#   1 system packages -> 2 Node + HyperFrames -> 3 Python dependencies -> 4 project source.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core chromium fonts-liberation fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 tubeforge

# Node + HyperFrames for the "Story" video style (Chromium is installed above).
COPY --from=node:24-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:24-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN --mount=type=cache,target=/root/.npm \
    ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && npm install -g hyperframes@0.8.192
ENV TUBEFORGE_HYPERFRAMES_BIN=/usr/local/bin/hyperframes

# Third-party dependencies only, read from pyproject.toml, so this layer is rebuilt only when the
# dependency list changes (not on every source edit) and pip's download cache is reused.
COPY pyproject.toml ./
RUN python - <<'PY' > /tmp/requirements.txt
import tomllib
project = tomllib.load(open("pyproject.toml", "rb"))["project"]
extras = project["optional-dependencies"]
wanted = ["dev", "local-media", "kokoro", "alignment", "reference-renderer"]
print("\n".join(project["dependencies"] + [dep for name in wanted for dep in extras[name]]))
PY
RUN --mount=type=cache,target=/root/.cache/pip pip install -r /tmp/requirements.txt

# Project source last. Compose bind-mounts ./src over /app/src, so these copies only matter for a
# bare `docker run`; installing with --no-deps is fast and provides the `tubeforge` CLI.
COPY readme.md ./
COPY src ./src
COPY .agents/skills ./.agents/skills
COPY migrations ./migrations
COPY docs ./docs
COPY tests ./tests
COPY alembic.ini ./
RUN --mount=type=cache,target=/root/.cache/pip pip install --no-deps .

USER tubeforge
EXPOSE 8080
CMD ["uvicorn", "tubeforge.main:app", "--host", "0.0.0.0", "--port", "8080"]
