FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core chromium fonts-liberation fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 tubeforge

COPY pyproject.toml readme.md ./
COPY src ./src
COPY .agents/skills ./.agents/skills
COPY migrations ./migrations
COPY docs ./docs
COPY tests ./tests
COPY alembic.ini ./
RUN python -m pip install --no-cache-dir ".[dev,local-media,kokoro,alignment,reference-renderer]"

# Node + HyperFrames for the "Story" video style (Chromium is installed above).
COPY --from=node:24-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:24-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && npm install -g hyperframes@0.8.192
ENV TUBEFORGE_HYPERFRAMES_BIN=/usr/local/bin/hyperframes

USER tubeforge
EXPOSE 8080
CMD ["uvicorn", "tubeforge.main:app", "--host", "0.0.0.0", "--port", "8080"]
