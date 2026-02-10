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
tailscale cert pro.tail375484.ts.net
```

This creates `pro.tail375484.ts.net.crt` and `pro.tail375484.ts.net.key` in the current directory.

### 2. Start the server

```bash
.venv/bin/uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8443 \
  --ssl-keyfile pro.tail375484.ts.net.key \
  --ssl-certfile pro.tail375484.ts.net.crt
```

### 3. Open on your iPhone

Make sure Tailscale is connected on your phone, then open:

```
https://pro.tail375484.ts.net:8443
```

No cert warnings, camera works, accessible from anywhere on your tailnet.

### Add to Home Screen (optional)

In Safari: Share button > "Add to Home Screen" for an app-like experience.

### Quick reference

| What | Value |
|---|---|
| Tailscale IP | `100.88.194.45` |
| MagicDNS name | `pro.tail375484.ts.net` |
| URL | `https://pro.tail375484.ts.net:8443` |
| Fallback (HTTP, no camera) | `http://100.88.194.45:8000` |
