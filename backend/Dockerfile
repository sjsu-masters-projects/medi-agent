FROM python:3.12-slim

WORKDIR /app

# OCR runs only in the Cloud Run Job, but it uses this same image.  Keep the
# executable and both supported locale packs in the image so a scanned Spanish
# document is never silently downgraded to an unavailable in-process parser.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-spa \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first for Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/

# PYTHONDONTWRITEBYTECODE is set below, so without this every cold start recompiles the
# application's own modules. Compile once at build time.
RUN python -m compileall -q src

# Set Python path so `app` package is importable
ENV PYTHONPATH=/app/src
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Cloud Run expects the server to listen on port 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
