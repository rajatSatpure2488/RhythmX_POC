FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies into the SYSTEM Python (not a project venv).
# Reason: docker-compose bind-mounts ./backend over /app, which would
# shadow any /app/.venv created by `uv sync`. Installing --system puts
# binaries in /usr/local/bin and libs in /usr/local/lib — both survive
# the bind mount, and bare `uvicorn` resolves on PATH.
COPY requirements.txt ./
RUN uv pip install --system --no-cache -r requirements.txt

# Copy everything (app folder + root main.py + other files)
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]