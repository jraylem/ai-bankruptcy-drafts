# Docker Deployment Guide

Steps to run this frontend project using Docker Compose.

## Prerequisites

- Docker Desktop installed and running
- Backend container (`ai_chatbot_backend`) must be running first

---

## First-Time Setup

### 1. Verify the backend is running

```bash
docker ps | grep backend
```

You should see `ai_chatbot_backend` in the list. If not, start the backend first before proceeding.

### 2. Verify `.env` is configured correctly

The `.env` file must have:

```env
VITE_API_URL=http://localhost
VITE_APP_NAME=AI Petition Reviewer
```

> **Important:** Do NOT set `VITE_API_URL=http://localhost:8000`. Using port 8000 directly causes CORS errors in the browser. The app must route API calls through nginx (port 80), which then proxies them internally to the backend container.

### 3. Run the frontend

```bash
docker compose up --build -d
```

This will:
- Build the React app inside a Node.js container
- Bake the `.env` variables into the build
- Serve the built files via nginx on port 80

### 4. Open in browser

```
http://localhost
```

---

## Subsequent Runs (No Code Changes)

If nothing changed, skip the build step:

```bash
docker compose up -d
```

---

## Stopping the Container

```bash
docker compose down
```

---

## Viewing Logs

```bash
docker logs ai-chatbot-frontend-new
```

---

## Rebuilding After Code Changes

Always rebuild when source files or `.env` are modified (Vite bakes env vars at build time):

```bash
docker compose up --build -d
```

---

## Troubleshooting

### "host not found in upstream" error in logs

nginx fails to start if it cannot resolve a container hostname on the network.
Check that the backend container is running and on the `bkdrafts-be_app-network` network:

```bash
docker inspect ai_chatbot_backend --format '{{json .NetworkSettings.Networks}}'
```

The network name `bkdrafts-be_app-network` must appear in the output.

### Cannot reach http://localhost

Check if the container is actually running (not restarting):

```bash
docker ps | grep ai-chatbot-frontend-new
```

If the STATUS column shows `Restarting`, check the logs:

```bash
docker logs ai-chatbot-frontend-new
```

### Network error on the page (API calls failing)

This is most likely a CORS issue caused by a wrong `VITE_API_URL` in `.env`.

Make sure `.env` has:
```env
VITE_API_URL=http://localhost
```

Then rebuild:
```bash
docker compose up --build -d
```

---

## Notes

- The `docker-compose.yml` connects the frontend to `bkdrafts-be_app-network` (the same network the backend uses) so nginx can proxy `/api/` requests to the backend container by hostname.
- The `/signup` proxy block in `nginx.conf` is commented out — it requires a separate `landing` container that is not part of this setup.
- Vite bakes environment variables at **build time**, not runtime. Any change to `.env` requires a full rebuild (`--build`).
