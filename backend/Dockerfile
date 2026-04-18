# Build context: repo root (source_dir: / in app.yaml)
# dockerfile_path: backend/Dockerfile

FROM python:3.11-slim

WORKDIR /app

# Install system deps needed for asyncpg (postgres C extension)
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer-cached until requirements change)
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source (alembic/, app/, legacy routers/ + services/ all land in /app/)
COPY backend/ .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
