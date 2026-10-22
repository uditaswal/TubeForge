FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
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

USER tubeforge
EXPOSE 8080
CMD ["uvicorn", "tubeforge.main:app", "--host", "0.0.0.0", "--port", "8080"]
