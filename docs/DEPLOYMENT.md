# Deployment Guide — RaipurNetra AI

The app is a single FastAPI service (API + dashboard + simulation engine). This guide
covers local demo, Docker, VPS and cloud-PaaS deployments, plus how to scale it later.

---

## 1. Local demo (Windows / Linux)

```bash
cd raipur_netra
pip install -r requirements.txt
run.bat                 # Windows (uses Python313 automatically)
# or:
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Dashboard: http://localhost:8000 · Swagger API docs: http://localhost:8000/docs

## 2. Docker

```bash
docker compose up --build -d
# dashboard on http://<host>:8000
```

Volumes persist generated reports and uploads. To ship the YOLO weights inside the
image, remove the `NOTE` comment in the Dockerfile (weights are git-ignored).

## 3. VPS (Ubuntu + nginx + systemd)

```bash
sudo apt update && sudo apt install -y python3-venv nginx
cd /opt && git clone <your-repo> raipur_netra && cd raipur_netra
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && nano .env        # set tokens, ports
```

`/etc/systemd/system/raipurnetra.service`:

```ini
[Unit]
Description=RaipurNetra AI
After=network.target

[Service]
WorkingDirectory=/opt/raipur_netra
EnvironmentFile=/opt/raipur_netra/.env
ExecStart=/opt/raipur_netra/.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now raipurnetra
```

nginx reverse proxy (`/etc/nginx/sites-available/raipurnetra`):

```nginx
server {
    listen 80;
    server_name traffic.raipur.gov.in;          # your domain
    client_max_body_size 200M;                  # video uploads

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/raipurnetra /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
# then: sudo certbot --nginx -d traffic.raipur.gov.in   (HTTPS)
```

## 4. Cloud PaaS (Render / Railway / Fly.io)

* **Build command:** `pip install -r requirements.txt`
* **Start command:** `python -m uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
* Set env vars (`WHATSAPP_TOKEN`, …) in the dashboard. Free tiers run the demo fine;
  for YOLO video processing pick a container with ≥2 GB RAM.
* Add a persistent disk mounted at `/app/reports` if you want reports to survive deploys.

---

## Why WORKERS=1 (important)

The live city engine (CCTV simulation, signal state, bus GPS) is **in-process** — it is the
single source of truth the dashboard polls. Running multiple uvicorn workers would start
multiple divergent copies of the city. This is by design for the demo/edge scale:

* **Vertical scale:** one worker comfortably serves hundreds of dashboard clients (state
  payloads are small; polling is 2 s).
* **Horizontal scale (future):** extract the engine state to Redis and make workers
  stateless — see EXTENDING.md → "Scale-out path". Edge devices (Jetson Nano) already
  operate autonomously, so the cloud tier is only aggregation, which scales linearly.

## WhatsApp go-live checklist

1. developers.facebook.com → create App (type: Business) → add **WhatsApp** product.
2. Copy the *permanent token* → `WHATSAPP_TOKEN`, and the *Phone number ID* → `WHATSAPP_PHONE_NUMBER_ID`.
3. Set `WHATSAPP_VERIFY_TOKEN` to the same value in your `.env` and in the Meta webhook config.
4. Webhook callback URL: `https://<your-domain>/api/whatsapp/webhook` → verify → subscribe to **messages**.
5. Message the sandbox/test number — TrafficGPT replies live. Done: no other code changes.

## Health & monitoring

* `GET /api/health` — liveness + model freshness (wire to UptimeRobot/K8s probe)
* `GET /api/health` fields include predictor `trained_at` for alerting on stale models
* Structured logs go to stdout (journald/docker logs)
