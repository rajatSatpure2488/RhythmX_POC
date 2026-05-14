# ============================================
# MediSync Backend — Dockerfile
# FastAPI + FHIR Pipeline + FHIR R5 Integration
# ============================================

# ── Stage 1: Builder ─────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /build

# Install dependencies in a virtual env for clean copy
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# requirements.txt is mounted/copied from project root via docker-compose
COPY requirements.txt* ./
RUN if [ -f requirements.txt ]; then \
        pip install --no-cache-dir --upgrade pip && \
        pip install --no-cache-dir -r requirements.txt; \
    fi


# ── Stage 2: Runtime ─────────────────────────
FROM python:3.13-slim AS runtime

LABEL maintainer="MediSync Team"
LABEL description="MediSync FastAPI Backend — Clinical Documentation Pipeline"
LABEL version="1.0.0"

# Security: run as non-root user
RUN groupadd -r medisync && useradd -r -g medisync -d /app -s /sbin/nologin medisync

WORKDIR /app

# Copy virtual env from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY . .

# Python optimizations
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Default port
EXPOSE 8000

# Health check — hit the root endpoint every 30s
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" || exit 1

# Switch to non-root user
USER medisync

# Start server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
