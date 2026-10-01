"""RaipurNetra AI - Layer 1 (SEE): ANPR + violation detection + e-challan engine.

Pipeline (as deployed):
  CCTV frame -> YOLOv8 vehicle detect -> plate region crop -> OCR (CG-04-XX-XXXX)
  -> RTO lookup -> violation classifier -> auto e-challan -> SMS to owner.

This module implements the full pipeline logic on simulated camera feeds so the
demo runs without GPU hardware. `process_plate_text()` exposes the exact post-OCR
path, so plugging a real camera/OCR only replaces the front-end.
"""

import random
import re
import threading
import datetime

from . import config


class ANPREngine:
    PLATE_RE = re.compile(r"^CG-0[1-9]-[A-Z]{2}-\d{4}$")

    def __init__(self):
        self.lock = threading.RLock()
        self.rng = random.Random(99)
        self.detections = []       # recent passes (last 300)
        self.challans = []         # all e-challans (demo session)
        self.heatmap = {jid: {v: 0 for v in config.FINE_AMOUNTS} for jid in config.JUNCTIONS}
        self.heatmap_total = {jid: 0 for jid in config.JUNCTIONS}
        self.counters = {"detections": 0, "violations": 0, "challans": 0,
                         "sms_sent": 0, "paid": 0}
        self.revenue = {"generated": 0, "collected": 0}
        self._challan_seq = 24001
        self.sim_day = datetime.datetime.now(config.IST).date().isoformat()

    # ------------------------------------------------------------------ feed
    def on_vehicles(self, junction_id, vehicles_per_min):
        """Called by the simulator with detected vehicle throughput per camera."""
        expected = vehicles_per_min / 12.0  # demo-scale sampling
        with self.lock:
            n = int(expected) + (1 if self.rng.random() < expected % 1 else 0)
            for _ in range(min(n, 4)):
                self._register_pass(junction_id)

    def _register_pass(self, junction_id, plate=None, force_violation=None):
        rng = self.rng
        plate = plate or rng.choice(list(config.RTO_DB.keys()))
        vehicle = config.RTO_DB[plate]
        vtype = vehicle["vehicle_type"]
        cong = 0.5
        # violation classifier probabilities (as % of passes)
        p = {"red_light": 0.020 + 0.02 * cong,
             "no_helmet": 0.022 if vtype == "bike" else 0.0,
             "wrong_way": 0.004,
             "overspeed": 0.012 if cong < 0.45 else 0.004}
        if force_violation:
            violation = force_violation
        else:
            violation = None
            r = rng.random()
            acc = 0.0
            for v, pv in p.items():
                acc += pv
                if r < acc:
                    violation = v
                    break
        det = {
            "t": datetime.datetime.now(config.IST).isoformat(timespec="seconds"),
            "junction": junction_id,
            "junction_name": config.JUNCTIONS[junction_id]["name"],
            "camera": f"CAM-{junction_id[:3].upper()}",
            "plate": plate,
            "vehicle_type": vtype,
            "violation": violation,
            "speed_kmph": round(rng.uniform(25, 65) if violation != "overspeed" else rng.uniform(72, 96), 1),
            "confidence": round(rng.uniform(0.90, 0.99) if violation else rng.uniform(0.82, 0.97), 2),
        }
        self.counters["detections"] += 1
        if violation:
            self.counters["violations"] += 1
            self.heatmap[junction_id][violation] += 1
            self.heatmap_total[junction_id] += 1
            if rng.random() < 0.85:  # not every violation is auto-challaned (human review loop)
                self._issue_challan(det)
        self.detections.append(det)
        if len(self.detections) > 300:
            self.detections.pop(0)
        return det

    # ------------------------------------------------------------------ challan
    def _issue_challan(self, det):
        vehicle = config.RTO_DB[det["plate"]]
        fine = config.FINE_AMOUNTS[det["violation"]]
        challan = {
            "id": f"EC-{self._challan_seq}",
            "plate": det["plate"],
            "owner": vehicle["owner"],
            "vehicle_type": det["vehicle_type"],
            "model": vehicle["model"],
            "violation": det["violation"],
            "violation_label": config.VIOLATION_LABELS[det["violation"]],
            "fine": fine,
            "junction": det["junction"],
            "junction_name": det["junction_name"],
            "camera": det["camera"],
            "speed_kmph": det["speed_kmph"],
            "confidence": det["confidence"],
            "t": det["t"],
            "evidence": f"frame_{det['camera']}_{det['t'].replace(':', '').replace('-', '')}.jpg",
            "status": "sent",
        }
        self._challan_seq += 1
        self.counters["challans"] += 1
        self.counters["sms_sent"] += 1
        self.revenue["generated"] += fine
        if self.rng.random() < 0.42:
            challan["status"] = "paid"
            self.counters["paid"] += 1
            self.revenue["collected"] += fine
        self.challans.append(challan)
        return challan

    # ------------------------------------------------------------------ real-plate path
    def register_pass_external(self, junction_id, plate, vclass, violation, speed):
        """Public entry used by the video detection engine so real CV events
        (e.g. stop-line crossings) feed the same ANPR/e-challan pipeline."""
        with self.lock:
            return self._register_pass(junction_id, plate=plate, force_violation=violation)

    def process_plate_text(self, text, junction_id="jaistambh"):
        """Post-OCR pipeline: validate CG format -> RTO lookup -> context.
        This is the exact function a real PaddleOCR/EasyOCR result feeds into."""
        plate = (text or "").strip().upper().replace(" ", "")
        valid = bool(self.PLATE_RE.match(plate))
        result = {"input": text, "plate": plate if valid else None,
                  "valid_format": valid, "format_expected": "CG-04-XX-XXXX"}
        if valid:
            vehicle = config.RTO_DB.get(plate) or {
                "plate": plate, "owner": "Unknown (not in RTO sync)",
                "vehicle_type": "car", "model": "-", "rto": plate[:5],
                "challans_pending": 0}
            result["owner_record"] = vehicle
            with self.lock:
                pending = [c for c in self.challans if c["plate"] == plate]
            result["challan_history"] = pending[-5:]
        return result

    # ------------------------------------------------------------------ demo helpers
    def simulate_burst(self, n=12, junction_id=None):
        """Demo button: generate a burst of violations at a hotspot."""
        jid = junction_id or self.rng.choice(list(config.JUNCTIONS.keys()))
        out = []
        with self.lock:
            for _ in range(n):
                v = self.rng.choice(list(config.FINE_AMOUNTS.keys()))
                out.append(self._register_pass(jid, force_violation=v))
        return out

    # ------------------------------------------------------------------ snapshot
    def snapshot(self, limit=80):
        with self.lock:
            challans = sorted(self.challans, key=lambda c: c["t"], reverse=True)
            # Rs.15 lakh/month projection assumes 100 violations/day (proposal model)
            avg_fine = self.revenue["generated"] / max(1, self.counters["challans"])
            revenue_monthly_projected = int(avg_fine * 100 * 30)
            return {
                "detections": list(reversed(self.detections[-limit:])),
                "challans": challans[:limit],
                "counters": dict(self.counters),
                "revenue": dict(self.revenue),
                "revenue_monthly_projected": revenue_monthly_projected,
                "heatmap": {jid: dict(v) for jid, v in self.heatmap.items()},
                "heatmap_total": dict(self.heatmap_total),
                "hotspot": max(self.heatmap_total, key=self.heatmap_total.get) if any(self.heatmap_total.values()) else None,
            }


anpr = ANPREngine()
