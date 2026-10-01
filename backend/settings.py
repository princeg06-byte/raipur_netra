"""RaipurNetra AI - runtime settings (environment-driven, future-proof).

All operational knobs live here so the system can be reconfigured or moved
to real hardware feeds without code changes. Override anything via env vars
or a `.env` file (see `.env.example`).
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env(key, default):
    return os.environ.get(key, default)


class Settings:
    # --- server
    HOST = _env("RN_HOST", "0.0.0.0")
    PORT = int(_env("RN_PORT", "8000"))
    WORKERS = int(_env("RN_WORKERS", "1"))  # simulator is in-process: keep 1 (see DEPLOYMENT.md)

    # --- paths
    DATA_DIR = Path(_env("RN_DATA_DIR", BASE_DIR / "data"))
    MODELS_DIR = Path(_env("RN_MODELS_DIR", BASE_DIR / "models"))
    REPORTS_DIR = Path(_env("RN_REPORTS_DIR", BASE_DIR / "reports"))
    UPLOADS_DIR = Path(_env("RN_UPLOADS_DIR", DATA_DIR / "uploads"))

    # --- vision (Layer 1)
    # fine-tuned Raipur model first, then stock COCO; MOG2 as final fallback
    YOLO_MODEL_PATHS = [
        Path(_env("RN_YOLO_MODEL", MODELS_DIR / "yolo_raipur_best.pt")),
        Path("yolov8n.pt"),
    ]
    YOLO_CONF = float(_env("RN_YOLO_CONF", "0.30"))
    VISION_FRAME_INTERVAL = float(_env("RN_VISION_FRAME_INTERVAL", "0.5"))  # sec between analysed frames
    VISION_MAX_UPLOAD_MB = int(_env("RN_VISION_MAX_UPLOAD_MB", "200"))

    # --- prediction (Layer 2)
    PREDICT_HORIZONS = [30, 60]           # minutes
    PREDICT_RETRAIN_INTERVAL_MIN = int(_env("RN_RETRAIN_MIN", "15"))
    PREDICT_MODEL_DIR = Path(_env("RN_PREDICT_MODEL_DIR", MODELS_DIR / "congestion"))

    # --- WhatsApp (Layer 4) - Meta WhatsApp Cloud API
    WHATSAPP_TOKEN = _env("WHATSAPP_TOKEN", "")           # permanent/system-user access token
    WHATSAPP_PHONE_ID = _env("WHATSAPP_PHONE_NUMBER_ID", "")
    WHATSAPP_VERIFY_TOKEN = _env("WHATSAPP_VERIFY_TOKEN", "raipurnetra-verify-2026")
    WHATSAPP_GRAPH_URL = _env("WHATSAPP_GRAPH_URL", "https://graph.facebook.com/v20.0")

    # --- map tiles (frontend) — keyless providers; override via env
    TILE_URL = _env("RN_TILE_URL",
                    "https://server.arcgisonline.com/ArcGIS/rest/services/"
                    "Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}")
    TILE_ATTR = _env("RN_TILE_ATTR", "Tiles &copy; Esri — Esri, DeLorme, NAVTEQ")

    # --- misc
    LOG_LEVEL = _env("RN_LOG_LEVEL", "INFO")


settings = Settings()
for p in (settings.DATA_DIR, settings.UPLOADS_DIR, settings.PREDICT_MODEL_DIR,
          settings.REPORTS_DIR):
    p.mkdir(parents=True, exist_ok=True)

# module-level aliases so consumers can `from . import settings; settings.HOST`
for _k in dir(settings):
    if _k.isupper():
        globals()[_k] = getattr(settings, _k)
