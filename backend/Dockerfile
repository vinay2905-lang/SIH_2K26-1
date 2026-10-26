FROM python:3.12-slim

# Tesseract with Hindi for scanned documents (opencv-python-headless needs no extra system libraries).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
RUN useradd --create-home pramaan && mkdir -p /data && chown pramaan /data
USER pramaan

# WEB_CONCURRENCY = number of API processes (read by uvicorn)
ENV PRAMAAN_DATA_DIR=/data \
    PYTHONUNBUFFERED=1 \
    WEB_CONCURRENCY=2
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
