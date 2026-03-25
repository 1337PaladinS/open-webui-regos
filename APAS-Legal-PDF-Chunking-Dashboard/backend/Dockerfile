FROM python:3.11-slim

# System deps for Docling and pdftotext
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    tesseract-ocr \
    libtesseract-dev \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download Docling models at build time so first run doesn't stall
RUN python -c "\
from docling.document_converter import DocumentConverter; \
print('Docling models downloaded successfully') \
" || echo "Docling model pre-download skipped (will download at runtime)"

# Copy app
COPY app/ ./app/

# Create data dir
RUN mkdir -p /data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
