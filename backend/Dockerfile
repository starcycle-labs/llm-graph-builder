# Base image with all dependencies
FROM python:3.10-slim AS base

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libmagic1 \
        libgl1-mesa-glx \
        libreoffice \
        cmake \
        poppler-utils \
        tesseract-ocr && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set LD_LIBRARY_PATH
ENV LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu

# Set working directory
WORKDIR /code

# Copy only requirements first to leverage Docker cache
COPY requirements.txt /code/

# Install Python dependencies with no cache and in a single layer
RUN pip install --no-cache-dir -r requirements.txt

# Create necessary directories
RUN mkdir -p /code/merged_files /code/chunks

# Final application image
FROM base AS app

# Copy application code
COPY . /code

# Set environment variables
ENV PORT=8080

EXPOSE 8080

# Set command
CMD ["sh", "-c", "gunicorn score:app --workers 8 --threads 8 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT} --timeout 300"]
