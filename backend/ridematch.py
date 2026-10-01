"""RaipurNetra AI - ride matching for daily commuters (Layer 4 - TELL)."""

import threading
import itertools

from . import config
from .routing import hops


class RideMatcher:
    def __init__(self):
        self.lock = threading.RLock()
        self.commuters = []
        self._seq = 1
        self._seed()

    def _seed(self):
        seeds = [
            ("Rahul Verma", "98271-10001", "shankar", "pachpedi", "09:00", "any"),
            ("Sneha Jain", "98271-10002", "shankar", "pachpedi", "09:15", "female"),
            ("Amit Sahu", "98271-10003", "pandri", "vip", "08:45", "any"),
            ("Kavita Dewangan", "98271-10004", "fafadih", "amlidih", "09:30", "female"),
            ("Vikas Chandrakar", "98271-10005", "telibandha", "mowa", "18:00", "any"),
            ("Priya Verma", "98271-10006", "pandri", "vip", "18:15", "female"),
            ("Deepak Kosaria", "98271-10007", "bhatagaon", "jaistambh", "08:30", "any"),
            ("Meena Xess", "98271-10008", "bhatagaon", "jaistambh", "08:40", "any"),
        ]
        for name, contact, o, d, t, gp in seeds:
            self.register(name, contact, o, d, t, gp)

    def register(self, name, contact, origin, destination, time_pref, gender_pref="any"):
        with self.lock:
            rec = {
                "id": f"RM-{self._seq:04d}",
                "name": name, "contact": contact,
                "origin": origin,
                "origin_name": config.JUNCTIONS[origin]["name"] if origin in config.JUNCTIONS else origin,
                "destination": destination,
                "destination_name": config.JUNCTIONS[destination]["name"] if destination in config.JUNCTIONS else destination,
                "time": time_pref, "gender_pref": gender_pref,
            }
            self._seq += 1
            self.commuters.append(rec)
            return rec

    def _score(self, a, b):
        if a["id"] == b["id"]:
            return -1
        hop = hops(a["origin"], b["origin"]) + hops(a["destination"], b["destination"])
        th, tm = a["time"].split(":")
        oh, om = b["time"].split(":")
        tdiff = abs((int(th) * 60 + int(tm)) - (int(oh) * 60 + int(om)))
        score = 100 - hop * 12 - tdiff * 0.8
        if a["gender_pref"] == "female" and b.get("gender") != "female":
            score -= 25  # placeholder until profiles carry gender
        return max(0, round(score))

    def matches_for(self, commuter_id, top=3):
        with self.lock:
            me = next((c for c in self.commuters if c["id"] == commuter_id), None)
            if not me:
                return []
            scored = []
            for other in self.commuters:
                s = self._score(me, other)
                if s > 30:
                    scored.append({"match": other, "score": s,
                                   "overlap": f"{hops(me['origin'], other['origin'])}+{hops(me['destination'], other['destination'])} hops",
                                   "est_share": f"{min(90, 50 + s // 2)}%"})
            scored.sort(key=lambda x: -x["score"])
            return scored[:top]

    def snapshot(self):
        with self.lock:
            return {"total": len(self.commuters), "commuters": self.commuters[-40:]}


ride_matcher = RideMatcher()
