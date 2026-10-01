"""RaipurNetra AI - Layer 4 (TELL): WhatsApp Cloud API gateway.

Shows exactly how TrafficGPT plugs into WhatsApp in production:

  * Meta WhatsApp Cloud API webhook (GET verify + POST receive) — point the
    Meta App dashboard at /api/whatsapp/webhook and messages flow in.
  * Outbound replies via Graph API when WHATSAPP_TOKEN is configured;
    otherwise replies are stored in an outbox so the bundled simulator page
    (frontend/whatsapp_sim.html) demonstrates the identical message flow.
  * Every inbound/outbound message is logged for the dashboard.

No other component changes: the webhook calls the same TrafficGPT brain.
"""

import threading
import datetime
import json

import requests

from . import config
from . import settings


class WhatsAppGateway:
    def __init__(self, bot):
        self.bot = bot
        self.lock = threading.RLock()
        self.log = []             # message log (both directions)
        self.outbox = []          # replies awaiting real delivery (no token)
        self.configured = bool(settings.WHATSAPP_TOKEN and settings.WHATSAPP_PHONE_ID)

    # ------------------------------------------------------------------ log
    def _log(self, direction, sender, text, via):
        with self.lock:
            self.log.append({
                "t": datetime.datetime.now(config.IST).isoformat(timespec="seconds"),
                "direction": direction, "sender": sender, "text": text, "via": via,
            })
            self.log = self.log[-200:]

    def snapshot(self):
        with self.lock:
            return {"configured": self.configured, "log": self.log,
                    "phone_number_id": settings.WHATSAPP_PHONE_ID or "(not set)",
                    "webhook_path": "/api/whatsapp/webhook"}

    # ------------------------------------------------------------------ webhook
    def verify(self, mode, token, challenge):
        if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
            return int(challenge)
        return None

    def receive(self, payload):
        """Parse a Meta Cloud API webhook payload and answer each message."""
        try:
            entries = payload.get("entry", [])
            replies = []
            for entry in entries:
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    for msg in value.get("messages", []) or []:
                        if msg.get("type") != "text":
                            continue
                        sender = msg.get("from", "unknown")
                        text = msg.get("text", {}).get("body", "")
                        self._log("in", sender, text, "webhook")
                        reply = self.bot.handle(text, user=f"wa-{sender}")["reply"]
                        replies.append((sender, text, reply))
                        self._deliver(sender, reply)
            return replies
        except Exception as exc:
            self._log("error", "webhook", repr(exc), "parser")
            return []

    # ------------------------------------------------------------------ send
    def _deliver(self, to, text):
        if self.configured:
            ok = self._send_graph(to, text)
            self._log("out", to, text, "graph-api" if ok else "graph-failed")
            return ok
        self._log("out", to, text, "outbox (no token - simulator mode)")
        with self.lock:
            self.outbox.append({"to": to, "text": text,
                                "t": datetime.datetime.now(config.IST).isoformat(timespec="seconds")})
            self.outbox = self.outbox[-100:]
        return False

    def _send_graph(self, to, text):
        url = f"{settings.WHATSAPP_GRAPH_URL}/{settings.WHATSAPP_PHONE_ID}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text[:4096]},
        }
        try:
            r = requests.post(url, json=payload, timeout=10,
                              headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
                                       "Content-Type": "application/json"})
            return r.status_code < 300
        except Exception:
            return False

    # ------------------------------------------------------------------ simulate
    def simulate(self, sender, text):
        """Same pipeline as the real webhook, driven by the simulator page."""
        self._log("in", sender, text, "simulator")
        reply = self.bot.handle(text, user=f"wa-{sender}")["reply"]
        self._deliver(sender, reply)
        return reply


def attach(bot):
    return WhatsAppGateway(bot)
