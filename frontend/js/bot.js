/* RaipurNetra AI - TrafficGPT WhatsApp-style chat UI */
const Bot = (() => {
  let chatEl, sugEl, inputEl;

  function bubble(text, who, time) {
    const d = document.createElement("div");
    d.className = `msg ${who}`;
    d.textContent = text;
    const t = document.createElement("span");
    t.className = "t";
    t.textContent = time || now();
    d.appendChild(t);
    chatEl.appendChild(d);
    chatEl.scrollTop = chatEl.scrollHeight;
  }

  function now() {
    return new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
  }

  function setSuggestions(list) {
    sugEl.innerHTML = "";
    (list || []).forEach(s => {
      const b = document.createElement("button");
      b.textContent = s;
      b.onclick = () => send(s);
      sugEl.appendChild(b);
    });
  }

  async function send(text) {
    text = (text || inputEl.value).trim();
    if (!text) return;
    inputEl.value = "";
    bubble(text, "user");
    setSuggestions([]);
    try {
      const r = await fetch("/api/bot", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, user: "police-demo" })
      });
      const data = await r.json();
      bubble(data.reply, "bot");
      setSuggestions(data.suggestions);
    } catch (e) {
      bubble("Connection error: " + e.message, "bot");
    }
  }

  function init() {
    chatEl = document.getElementById("chat");
    sugEl = document.getElementById("chat-suggestions");
    inputEl = document.getElementById("chat-msg");
    document.getElementById("btn-send").onclick = () => send();
    inputEl.addEventListener("keydown", e => { if (e.key === "Enter") send(); });
    bubble(
      "Namaste! Main RaipurNetra Traffic Bot hoon. 🙏\n" +
      "Pocho kuch bhi - traffic, bus, parking, route, challan ya prediction:\n" +
      '"Jaistambh Chowk traffic kaisa hai?"', "bot");
    setSuggestions([
      "Jaistambh Chowk traffic kaisa hai?",
      "Bus 7 kab aayegi?",
      "Magneto Mall parking?",
      "Fastest route from Jaistambh to Telibandha",
      "Kal Republic Day hai, traffic ka kya hoga?"
    ]);
  }

  return { init, send };
})();
