FROM node:22-bookworm-slim AS build
WORKDIR /build/frontend
ENV RAYON_NUM_THREADS=1 UV_THREADPOOL_SIZE=2 NODE_OPTIONS=--max-old-space-size=512
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build && npm install --prefix /opt/codex @openai/codex@0.164.0

FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1
WORKDIR /app
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && useradd --uid 10001 --create-home app
RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=build /usr/local/bin/node /usr/local/bin/node
COPY --from=build /opt/codex /opt/codex
COPY backend/ /app/backend/
COPY data/ /app/data/
COPY --from=build /build/frontend/dist/ /app/frontend/dist/
ENV HOME=/home/app CODEX_HOME=/home/app/.codex PATH=/opt/codex/node_modules/.bin:$PATH
USER app
CMD ["python", "-m", "uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8765", "--proxy-headers", "--forwarded-allow-ips", "*"]
