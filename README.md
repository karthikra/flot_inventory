# Flot Inventory

Home inventory app with video walkthrough and VLM-powered object identification.

## Quick Start

```bash
# install dependencies
uv sync

# run the server (local only)
.venv/bin/uvicorn app.main:app --port 8000
```

Open http://localhost:8000

## Running on Mobile (Tailscale)

Tailscale gives you HTTPS with a trusted cert — camera and mic access work out of the box.

### 1. Generate the HTTPS cert (one time)

```bash
tailscale cert <your-hostname>.ts.net
```

This creates `<your-hostname>.ts.net.crt` and `<your-hostname>.ts.net.key` in the current directory.

### 2. Start the server

```bash
.venv/bin/uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8443 \
  --ssl-keyfile <your-hostname>.ts.net.key \
  --ssl-certfile <your-hostname>.ts.net.crt
```

### 3. Open on your phone

Make sure Tailscale is connected on your phone, then open:

```
https://<your-hostname>.ts.net:8443
```

No cert warnings, camera works, accessible from anywhere on your tailnet.

### Add to Home Screen (optional)

In Safari: Share button > "Add to Home Screen" for an app-like experience.
