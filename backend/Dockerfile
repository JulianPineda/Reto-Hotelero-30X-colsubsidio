FROM python:3.12-slim

WORKDIR /app

# curl: used by the docker-compose healthcheck. build-essential: some
# transitive deps (sentence-transformers -> torch, bcrypt) may need to
# compile on platforms without a prebuilt wheel.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic

RUN pip install --no-cache-dir -e ".[dev]"

RUN mkdir -p /app/exports

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
