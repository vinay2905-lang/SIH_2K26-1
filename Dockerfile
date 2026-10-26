# Single-container PRAMAAN for hosts that run one Docker service (Render, Railway, Koyeb, Cloud Run, ...):
# the React build, the API and its background jobs in one process, and SQLite inside the container.
# The synthetic demo data is loaded while the image is built, so the service starts quickly and every
# restart begins from the same clean demo. For a real deployment use docker-compose.yml (PostgreSQL and
# a separate worker); see docs/DEPLOY.md.

FROM node:20-alpine AS web
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim

# Tesseract with Hindi for scanned documents
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY --from=web /src/dist /app/frontend/dist
COPY deploy/start-single.sh /app/start.sh

RUN useradd --create-home pramaan && mkdir -p /data && chown pramaan /data
USER pramaan

ENV PRAMAAN_DATA_DIR=/data \
    PRAMAAN_DATABASE_URL=sqlite:////data/pramaan.db \
    PRAMAAN_JOB_MODE=thread \
    PRAMAAN_SHOW_DEMO_LOGINS=true \
    PYTHONUNBUFFERED=1

# Demo data (encrypted with the built-in development key, which is fine for synthetic data only)
RUN python -m app.seed

EXPOSE 8000
CMD ["sh", "/app/start.sh"]
