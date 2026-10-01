"""RaipurNetra AI - TrafficGPT: Hindi/English natural-language traffic assistant.

Rule+pattern NLU that works fully offline (no API key needed during the demo).
Understands Hindi (Devanagari), romanised Hindi (Hinglish) and English for:
traffic status, alternate routes, bus ETA, parking, ride matching, e-challan
queries, congestion prediction and emergency status — answered from LIVE data.
"""

import re
import datetime

from . import config
from .routing import shortest_path, route_eta_minutes
from .ridematch import ride_matcher

_LEVELS = [(0, "Clear / निर्विघ्न"), (30, "Light / हल्का"), (50, "Moderate / मध्यम"),
           (70, "Heavy / भारी"), (85, "Severe / अत्यधिक")]

_JUNCTION_ALIASES = {
    "jaistambh": ["jaistambh", "jai stambh", "जयस्तम्भ", "जय स्तंभ"],
    "pandri": ["pandri", "पांडरी", "पान्डरी"],
    "telibandha": ["telibandha", "तेलीबांधा", "तेलीबन्धा"],
    "fafadih": ["fafadih", "फफाड़ीह", "फफाडीह"],
    "marine": ["marine drive", "marine", "मरीन ड्राइव", "मरीन"],
    "shankar": ["shankar nagar", "shankar", "शंकर नगर", "शंकर"],
    "amlidih": ["amlidih", "अमलीडीह"],
    "devnagar": ["devendra nagar", "devnagar", "देवेंद्र नगर"],
    "mowa": ["mowa", "मोवा"],
    "pachpedi": ["pachpedi", "pachpedi naka", "पाचपेड़ी"],
    "bhatagaon": ["bhatagaon", "भटागांव", "भटगांव"],
    "vip": ["vip road", "vip junction", "vip"],
}

_PARKING_ALIASES = {
    "magneto": ["magneto", "मैग्नेटो"],
    "citycenter": ["city center", "city centre", "सिटी सेंटर"],
    "pandri": ["pandri market", "pandri parking", "पांडरी मार्केट"],
    "ambedkar": ["ambedkar", "hospital", "अंबेडकर", "अस्पताल"],
    "railway": ["railway", "station", "रेलवे", "स्टेशन"],
}

_CONGESTION_WORD_HINDI = {"Clear / निर्विघ्न": "साफ़", "Light / हल्का": "हल्का",
                          "Moderate / मध्यम": "मध्यम", "Heavy / भारी": "भारी",
                          "Severe / अत्यधिक": "बहुत ज़्यादा"}


def _level(cong):
    for thresh, label in reversed(_LEVELS):
        if cong >= thresh:
            return label
    return _LEVELS[0][1]


def _is_hindi(text):
    return bool(re.search(r"[\u0900-\u097F]", text))


def _find_junction(text):
    t = " " + text.lower() + " "
    best, best_len = None, 0
    for jid, aliases in _JUNCTION_ALIASES.items():
        for a in aliases:
            if a in t and len(a) > best_len:
                best, best_len = jid, len(a)
    return best


def _find_parking(text):
    t = text.lower()
    for pid, aliases in _PARKING_ALIASES.items():
        for a in aliases:
            if a in t:
                return pid
    return None


def _fmt_time(dt):
    return dt.strftime("%I:%M %p").lstrip("0")


class TrafficGPT:
    def __init__(self, simulator, predictor, anpr_engine):
        self.sim = simulator
        self.predictor = predictor
        self.anpr = anpr_engine
        self.history = []

    # ------------------------------------------------------------------ main
    def handle(self, message, user="citizen"):
        message = (message or "").strip()
        if not message:
            return {"reply": "Namaste! Kya jaanna hai? / नमस्ते! क्या जानना है?",
                    "suggestions": ["Jaistambh traffic", "Bus 7 kab aayegi?", "Magneto Mall parking?"]}
        self.history.append({"user": user, "msg": message, "t": datetime.datetime.now(config.IST).isoformat(timespec="seconds")})
        self.history = self.history[-50:]
        low = message.lower()
        hindi = _is_hindi(message)
        try:
            for handler in (self._h_route, self._h_bus, self._h_parking, self._h_ride,
                            self._h_challan, self._h_prediction, self._h_emergency,
                            self._h_report, self._h_traffic, self._h_help):
                out = handler(message, low, hindi)
                if out:
                    return out
        except Exception as exc:
            return {"reply": f"Sorry, technical glitch: {exc!r}. Please try again.", "suggestions": []}
        return self._fallback(hindi)

    # ------------------------------------------------------------- handlers
    def _h_traffic(self, msg, low, hindi):
        jid = _find_junction(msg)
        if not jid or not any(w in low for w in ("traffic", "jam", "congestion", "kaisa", "status", "road", "रास्ता", "ट्रैफिक", "जाम", "कैसा")):
            return None
        snap = self.sim.snapshot()
        jd = snap["junctions"][jid]
        cong, name = jd["congestion"], jd["name"]
        lvl = _level(cong)
        pred, _ = self.predictor.predict_junction(jid, snap)
        trend = "badhne ka" if pred > cong + 5 else ("kam hone ka" if pred < cong - 5 else "same rehne ka")
        if hindi:
            reply = (f"{name}: ट्रैफिक {(_CONGESTION_WORD_HINDI[lvl]).lower()} है (संकुलन {cong:.0f}%).\n"
                     f"अगले 30 मिनट में इसके {trend} अनुमान है (अनुमानित {pred:.0f}%).\n"
                     f"सुझाव: {'वैकल्पिक मार्ग लें' if cong > 60 else 'सामान्य यात्रा करें'}।")
        else:
            reply = (f"{name}: {lvl.split(' /')[0]} traffic right now (congestion {cong:.0f}%).\n"
                     f"Prediction: expected to {trend.split(' ')[0]} over next 30 min (forecast {pred:.0f}%).\n"
                     + ("Suggest alternate route - type 'fastest route from <X> to <Y>'." if cong > 60 else "No action needed."))
        return {"reply": reply, "junction": jid, "congestion": cong, "predicted": pred,
                "suggestions": [f"Fastest route from Jaistambh to {name}" if jid != "jaistambh" else "Fastest route from Jaistambh to Telibandha",
                                f"{name} prediction", "Bus timings"]}

    def _h_route(self, msg, low, hindi):
        if not any(w in low for w in ("route", "jana", "jaana", "jau", "reach", "se ", "to ", "fastest", "मार्ग", "कैसे", "पहुंच")):
            return None
        # parse "X se Y" / "from X to Y" / "X to Y"
        m = re.search(r"(?:from\s+)?([a-z\s]+?)\s+(?:se|to|tak)\s+([a-z\s]+)", low)
        if not m:
            return None
        src = _find_junction(m.group(1)) or ("jaistambh" if "jaistambh" in low else None)
        dst = _find_junction(m.group(2)) or _find_junction(low.split(m.group(1))[-1])
        if not src or not dst or src == dst:
            return None
        snap = self.sim.snapshot()
        r = shortest_path(src, dst, snap["roads"])
        if not r:
            return None
        path, rpath, cost = r
        eta = route_eta_minutes(snap["roads"], rpath)
        names = [config.JUNCTIONS[j]["name"] for j in path]
        roads_used = [snap["roads"][rid]["name"] for rid in rpath]
        alt = shortest_path(src, dst, {**snap["roads"], **{rid: {**snap["roads"][rid], "closed": True} for rid in rpath}})
        alt_line = ""
        if alt:
            alt_eta = route_eta_minutes(snap["roads"], alt[1])
            alt_line = ("\nAlternate (avoiding above): " + " -> ".join(config.JUNCTIONS[j]["name"] for j in alt[0]) +
                        f" ~{alt_eta} min.")
        reply = (f"Fastest route ({_fmt_time(datetime.datetime.now(config.IST))}):\n"
                 f"{' -> '.join(names)}\nvia " + " + ".join(roads_used) + f"\nETA: ~{eta} min.") + alt_line
        if hindi:
            reply = f"सबसे तेज़ मार्ग: {' -> '.join(names)}\nअनुमानित समय: ~{eta} मिनट।" + alt_line
        return {"reply": reply, "route": path, "roads": roads_used, "eta_min": eta,
                "suggestions": [f"{dst} traffic kaisa hai?", "Bus timings", "Parking nearby"]}

    def _h_bus(self, msg, low, hindi):
        if not any(w in low for w in ("bus", "buses", "बस")):
            return None
        snap = self.sim.snapshot()
        m = re.search(r"bus\s*(?:number\s*)?(\d+)", low)
        buses = snap["buses"]
        label = "Bus"
        if m:
            num = m.group(1)
            label = f"Bus {num}"
            route = f"R{num}" if f"R{num}" in config.BUS_ROUTES else None
            if route:
                buses = [b for b in buses if b["route"] == route]
            else:
                # no exact match: answer with the nearest live bus (demo GPS pool)
                buses = [buses[0]] if buses else []
        if not buses:
            return {"reply": "No live bus found for that query. Routes: R1 (GE Road), R2 (City Loop), R3 (North-South)." if not hindi else
                             "उस क्वेरी के लिए कोई बस नहीं मिली। रूट: R1 (GE रोड), R2 (सिटी लूप), R3 (नॉर्थ-साउथ)।",
                    "suggestions": ["Bus 1 kab aayegi?", "Bus 2 kab aayegi?"]}
        b = buses[0]
        delay = b["delay_min"]
        if abs(delay) < 3:
            delay_hi, delay_en = "समय पर", "on time"
        else:
            word_hi = "देर" if delay > 0 else "जल्दी"
            delay_hi = f"{abs(delay):.0f} मिनट {word_hi}"
            delay_en = f"{abs(delay):.0f} min " + ("late" if delay > 0 else "early")
        if hindi:
            reply = (f"{label} ({b['route']} - {b['route_name']}): अभी {config.JUNCTIONS[b['from']]['name']} के पास है.\n"
                     f"अगला स्टॉप: {b['next_stop']} — ETA {b['eta_min']} मिनट.\n"
                     f"{delay_hi}. भीड़: {b['occupancy']} यात्री।")
        else:
            reply = (f"{label} ({b['route']} - {b['route_name']}) is near {config.JUNCTIONS[b['from']]['name']}.\n"
                     f"Next stop: {b['next_stop']} — ETA {b['eta_min']} min ({delay_en}). "
                     f"Occupancy: {b['occupancy']} passengers.")
        return {"reply": reply, "bus": b,
                "suggestions": ["Bus 2 kab aayegi?", "Parking at Magneto?", "Jaistambh traffic"]}

    def _h_parking(self, msg, low, hindi):
        if not any(w in low for w in ("parking", "park", "slot", "पार्किंग")):
            return None
        snap = self.sim.snapshot()
        pid = _find_parking(msg)
        lots = {pid: snap["parking"][pid]} if pid else snap["parking"]
        lines = []
        for p, lot in lots.items():
            lvl = "available" if lot["free"] > 15 else ("filling fast" if lot["free"] > 5 else "almost full")
            lines.append(f"{lot['name']}: {lot['free']}/{lot['total']} slots free ({lvl})")
        reply = "\n".join(lines)
        if hindi:
            reply = "\n".join(l.replace("slots free", "स्लॉट खाली").replace("almost full", "लगभग पूरा")
                              .replace("filling fast", "जल्दी भर रहा").replace("available", "उपलब्ध") for l in lines)
        return {"reply": reply, "parking": lots,
                "suggestions": ["Magneto Mall parking?", "Railway station parking?"]}

    def _h_ride(self, msg, low, hindi):
        if any(w in low for w in ("main daily", "mai daily", "मैं रोज़", "मै रोज", "register")) and \
           any(w in low for w in ("ride", "share", "carpool", "साझा")):
            m = re.search(r"([a-z\s]+?)\s*(?:se|from|से)\s+([a-z\s]+?)(?:\s|$)", low)
            src = _find_junction(m.group(1)) if m else None
            dst = _find_junction(m.group(2)) if m else None
            rec = ride_matcher.register("You (WhatsApp user)", "wa-user", src or "jaistambh",
                                        dst or "telibandha", "09:00")
            matches = ride_matcher.matches_for(rec["id"])
            names = [f"{x['match']['name']} ({x['match']['time']}, score {x['score']})" for x in matches]
            reply = ("Registered! Your ride matches:\n" + "\n".join(names)) if names else "Registered! No match yet - we'll ping you when a commuter on your route joins."
            if hindi:
                reply = "रजिस्टर हो गया! आपके रूट पर ये सह-यात्री मिले:\n" + "\n".join(names) if names else \
                    "रजिस्टर हो गया! आपके रूट पर कोई सह-यात्री मिलने पर हम WhatsApp पर बताएंगे।"
            return {"reply": reply, "registration": rec, "matches": matches,
                    "suggestions": ["Ride match list", "Traffic at Telibandha"]}
        if any(w in low for w in ("ride match", "carpool", "ride kaise", "ride match list", "साझा यात्रा")):
            snap = ride_matcher.snapshot()
            lines = [f"{c['name']}: {c['origin_name']} -> {c['destination_name']} at {c['time']}"
                     for c in snap["commuters"][:5]]
            reply = f"{snap['total']} commuters registered. Top daily carpools:\n" + "\n".join(lines) + \
                    "\nTo join: 'Main daily 9am Shankar Nagar se IT Park jaata hoon' (demo: any origin-destination)."
            return {"reply": reply, "suggestions": ["Main daily 9am Pandri se VIP Road jaata hoon ride share"]}
        return None

    def _h_challan(self, msg, low, hindi):
        if not any(w in low for w in ("challan", "fine", "e-challan", "चालान", "जुर्माना")):
            return None
        plate_m = re.search(r"CG[-\s]0\d[-\s][A-Z]{2}[-\s]?\d{4}", msg.upper().replace(" ", ""))
        if plate_m:
            res = self.anpr.process_plate_text(plate_m.group(0))
            rec = res.get("owner_record", {})
            hist = res.get("challan_history", [])
            reply = f"Plate {res['plate']} - Owner: {rec.get('owner')}, Vehicle: {rec.get('model')} ({rec.get('vehicle_type')})."
            reply += f"\nPending e-challans: {rec.get('challans_pending', 0)}; this session: {len(hist)}."
            if hindi:
                reply = f"प्लेट {res['plate']} - स्वामी: {rec.get('owner')}, वाहन: {rec.get('model')}.\nलंबित ई-चालान: {rec.get('challans_pending', 0)}।"
            return {"reply": reply, "plate_lookup": res, "suggestions": ["Aaj ke challan stats", "Violation hotspot"]}
        s = self.anpr.snapshot()
        reply = (f"Today: {s['counters']['challans']} auto e-challans issued from {s['counters']['violations']} detected violations "
                 f"({s['counters']['detections']} vehicles scanned).\n"
                 f"Revenue generated: Rs. {s['revenue']['generated']:,} (collected Rs. {s['revenue']['collected']:,}).\n"
                 f"Hotspot: {config.JUNCTIONS[s['hotspot']]['name'] if s['hotspot'] else '-'}")
        if hindi:
            reply = (f"आज: {s['counters']['violations']} उल्लंघन पकड़े गए, {s['counters']['challans']} ई-चालान भेजे गए.\n"
                     f"राजस्व: रु. {s['revenue']['generated']:,}.\nहॉटस्पॉट: {config.JUNCTIONS[s['hotspot']]['name'] if s['hotspot'] else '-'}")
        return {"reply": reply, "stats": s, "suggestions": ["Violation hotspot details", "Kal ka traffic prediction"]}

    def _h_prediction(self, msg, low, hindi):
        if not any(w in low for w in ("predict", "prediction", "kya hoga", "forecast", "30 min", "kal", "aaj", "अनुमान", "क्या होगा", "कल")):
            return None
        jid = _find_junction(msg)
        preds = self.predictor.predict_all()
        if jid:
            p = preds["predictions"][jid]
            if hindi:
                reply = (f"{p['name']} का 30-मिनट अनुमान: {p['predicted_30min']:.0f}% "
                         f"(अभी {p['current']:.0f}%) — जोखिम: {p['risk']}.\n"
                         + ("\nएहतियाती कदम:\n- " + "\n- ".join(p.get("actions", [])) if p.get("actions") else "कोई विशेष कदम ज़रूरी नहीं।"))
            else:
                reply = (f"{p['name']} 30-min forecast: {p['predicted_30min']:.0f}% (now {p['current']:.0f}%) — risk: {p['risk']}.\n"
                         + ("\nPreemptive actions:\n- " + "\n- ".join(p.get("actions", [])) if p.get("actions") else "No action needed."))
            return {"reply": reply, "prediction": p, "suggestions": [f"{p['name']} traffic", "City prediction"]}
        high = [p for p in preds["predictions"].values() if p["risk"] == "high"]
        med = [p for p in preds["predictions"].values() if p["risk"] == "medium"]
        lines = [f"- {p['name']}: {p['predicted_30min']:.0f}% ({p['risk']})" for p in (high + med)[:5]]
        reply = ("30-min city forecast (top risks):\n" + "\n".join(lines)) if lines else \
            "30-min city forecast: all junctions predicted LOW risk. Smooth evening ahead."
        if hindi:
            reply = "30-मिनट शहर अनुमान (ज़्यादा जोखिम):\n" + "\n".join(lines) if lines else \
                "30-मिनट अनुमान: सभी चौकों पर जोखिम कम है।"
        return {"reply": reply, "predictions": preds["predictions"],
                "suggestions": ["Jaistambh prediction", "Kal Republic Day hai, traffic ka kya hoga?"]}

    def _h_emergency(self, msg, low, hindi):
        if not any(w in low for w in ("ambulance", "emergency", "fire", "एम्बुलेंस", "आपातकाल")):
            return None
        em = self.sim.signal_net.emergency
        if em["active"]:
            reply = (f"EMERGENCY GREEN CORRIDOR ACTIVE for {em['vehicle']}.\n"
                     f"Route: {' -> '.join(em['route'])}\nAll signals ahead forced GREEN - est. 8-12 min saved.")
        else:
            reply = ("No active emergency. To trigger the demo corridor, open the Emergency panel "
                     "or POST /api/emergency with a route (e.g., Jaistambh -> Telibandha -> Marine Drive).")
        if hindi:
            reply = "कोई सक्रिय आपातकाल नहीं। डेमो के लिए Emergency पैनल से कॉरिडोर चालू करें।" if not em["active"] else reply
        return {"reply": reply, "emergency": em, "suggestions": ["Jaistambh traffic"]}

    def _h_report(self, msg, low, hindi):
        if not any(w in low for w in ("report", "analytics", "summary", "रिपोर्ट", "आंकड़े")):
            return None
        s = self.sim.snapshot()
        a = self.anpr.snapshot()
        reply = (f"Daily summary ({s['kpis']['time'][:16]}):\n"
                 f"- City congestion: {s['kpis']['city_congestion']:.0f}%\n"
                 f"- Avg signal wait: {s['kpis']['avg_wait_adaptive']:.0f}s (fixed-timer baseline {s['kpis']['avg_wait_fixed']:.0f}s -> {s['kpis']['wait_reduction_pct']:.0f}% saved)\n"
                 f"- Vehicles analysed today: {s['kpis']['vehicles_today']:,}\n"
                 f"- e-Challans: {a['counters']['challans']} (Rs. {a['revenue']['generated']:,})")
        return {"reply": reply, "suggestions": ["Violation hotspot", "Bus punctuality"]}

    def _h_help(self, msg, low, hindi):
        if any(w in low for w in ("hello", "hi", "namaste", "namaskar", "नमस्ते", "नमस्कार", "help", "madad", "मदद")):
            if hindi:
                reply = ("नमस्ते! मैं TrafficGPT हूँ - रायपुर का ट्रैफिक सहायक. पूछें:\n"
                         "- 'जयस्तम्भ चौक ट्रैफिक कैसा है?'\n- 'बस 2 कब आएगी?'\n- 'मैग्नेटो माल पार्किंग?'\n"
                         "- 'जयस्तम्भ से तेलीबांधा मार्ग'\n- 'कल का ट्रैफिक अनुमान'")
            else:
                reply = ("Namaste! I'm TrafficGPT - Raipur's traffic assistant. Ask me:\n"
                         "- 'Jaistambh Chowk traffic kaisa hai?'\n- 'Bus 7 kab aayegi?'\n- 'Magneto Mall parking?'\n"
                         "- 'Fastest route from Jaistambh to Telibandha'\n- 'Kal Republic Day hai, traffic ka kya hoga?'")
            return {"reply": reply,
                    "suggestions": ["Jaistambh traffic kaisa hai?", "Bus 7 kab aayegi?",
                                    "Magneto Mall parking?", "Kal ka prediction"]}
        return None

    def _fallback(self, hindi):
        reply = ("Samajh nahi aaya. Aap pooch sakte hain: traffic status, bus ETA, parking, "
                 "route, ride matching, e-challan, ya prediction.") if not hindi else \
                ("समझ नहीं आया। आप पूछ सकते हैं: ट्रैफिक स्थिति, बस समय, पार्किंग, मार्ग, "
                 "राइड मैचिंग, ई-चालान, या अनुमान।")
        return {"reply": reply,
                "suggestions": ["Jaistambh traffic kaisa hai?", "Bus 7 kab aayegi?", "Magneto Mall parking?"]}
