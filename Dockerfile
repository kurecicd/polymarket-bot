FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persistent dirs (Railway volume mounted at /data)
RUN mkdir -p /data/runtime /data/data

# Symlink runtime state to the persistent volume
RUN ln -s /data/runtime runtime || true
RUN ln -s /data/data data || true

EXPOSE 8000

CMD uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}
