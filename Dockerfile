# Stage 1: Build virtual env dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

# Install standard compilation libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install dependencies in virtual env
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Minimal runtime image
FROM python:3.12-slim AS runner

# Security hardening: Run as non-root user
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -m -s /bin/bash appuser

WORKDIR /app

# Copy virtual env and code from builder
COPY --from=builder /opt/venv /opt/venv
COPY --chown=appuser:appgroup . .

# Setup environment paths
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# SQLite persistence directory configuration
RUN mkdir -p /app/data && chown -R appuser:appgroup /app/data
VOLUME ["/app/data"]

USER appuser

EXPOSE 8000

# Execute server using Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
