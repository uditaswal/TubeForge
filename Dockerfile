FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 tubeforge

COPY pyproject.toml readme.md ./
COPY src ./src
COPY migrations ./migrations
COPY tests ./tests
COPY alembic.ini ./
RUN python -m pip install --no-cache-dir ".[dev]"

USER tubeforge
EXPOSE 8080
CMD ["uvicorn", "tubeforge.main:app", "--host", "0.0.0.0", "--port", "8080"]
