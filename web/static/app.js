// Matdaan Mitra — chat-only frontend.
// All interactions go through /api/chat. The classifier on the server picks an intent
// and dispatches to the appropriate tool. The frontend just renders text + cards.

const $ = (sel) => document.querySelector(sel);
const escapeHtml = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const LANG_TO_BCP47 = {
  en: "en-IN", hi: "hi-IN", ta: "ta-IN", bn: "bn-IN", mr: "mr-IN",
  te: "te-IN", kn: "kn-IN", ml: "ml-IN", gu: "gu-IN", pa: "pa-IN",
};

const STORAGE_KEY = "mm:chat:v1";

const messages = $("#messages");
const messagesInner = messages.querySelector("div");
const welcome = $("#welcome");
const suggestions = $("#suggestions");
const form = $("#chat-form");
const input = $("#chat-input");
const sendBtn = $("#send-btn");
const micBtn = $("#mic-btn");
const langSel = $("#lang-select");
const resetBtn = $("#reset-btn");

let history = [];

// --------------------------------------------------------------------------
// Boot
// --------------------------------------------------------------------------

(async function init() {
  const params = new URLSearchParams(location.search);
  if (params.has("lang")) langSel.value = params.get("lang");

  // Restore prior conversation if recent
  const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
  if (saved && Date.now() - saved.savedAt < 24 * 60 * 60 * 1000 && saved.history?.length) {
    history = saved.history;
    welcome.classList.add("hidden");
    for (const m of history) {
      if (m.role === "user") renderUser(m.content);
      else if (m.role === "assistant") renderAssistant(m.content || "", m.payload || {});
    }
    scrollToBottom();
  }

  await loadSuggestions();
})();

form.addEventListener("submit", (e) => { e.preventDefault(); send(); });

input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 128) + "px";
});

input.addEventListener("keydown", (e) => {
  if ((e.key === "Enter" && !e.shiftKey) || ((e.metaKey || e.ctrlKey) && e.key === "Enter")) {
    e.preventDefault();
    send();
  }
});

langSel.addEventListener("change", loadSuggestions);
micBtn.addEventListener("click", startMic);
resetBtn.addEventListener("click", resetConversation);

document.body.addEventListener("click", (e) => {
  if (e.target.matches("[data-suggestion]")) {
    input.value = e.target.dataset.suggestion;
    send();
  }
  if (e.target.matches("[data-speak]")) {
    const node = e.target.closest("[data-speakable]");
    speak(node ? node.innerText : "", langSel.value);
  }
});

// --------------------------------------------------------------------------
// Suggestions
// --------------------------------------------------------------------------

async function loadSuggestions() {
  const r = await fetch(`/api/suggestions?lang=${encodeURIComponent(langSel.value)}`);
  const { suggestions: items } = await r.json();
  suggestions.innerHTML = items.map(
    (s) => `<button type="button" data-suggestion="${escapeHtml(s)}" class="text-sm border border-stone-300 hover:bg-stone-100 rounded-full px-3 py-1.5">${escapeHtml(s)}</button>`
  ).join("");
}

// --------------------------------------------------------------------------
// Send
// --------------------------------------------------------------------------

async function send() {
  const text = input.value.trim();
  if (!text) return;
  welcome.classList.add("hidden");
  renderUser(text);
  history.push({ role: "user", content: text });
  input.value = "";
  input.style.height = "auto";
  sendBtn.disabled = true;

  const thinking = renderThinking();
  scrollToBottom();

  try {
    const r = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, lang: langSel.value, history }),
    });
    const data = await r.json();
    thinking.remove();
    if (!r.ok) {
      renderError(data.error || "Something went wrong.");
      return;
    }
    renderAssistant(data.reply, data);
    history.push({ role: "assistant", content: data.reply, payload: data });
    persist();
  } catch (e) {
    thinking.remove();
    renderError(`Network error: ${e.message}`);
  } finally {
    sendBtn.disabled = false;
    scrollToBottom();
  }
}

function persist() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({
    history: history.slice(-30), savedAt: Date.now(),
  }));
}

function resetConversation() {
  history = [];
  localStorage.removeItem(STORAGE_KEY);
  messagesInner.innerHTML = "";
  messagesInner.appendChild(welcome);
  welcome.classList.remove("hidden");
}

// --------------------------------------------------------------------------
// Rendering
// --------------------------------------------------------------------------

function renderUser(text) {
  const el = document.createElement("div");
  el.className = "flex justify-end";
  el.innerHTML = `<div class="max-w-[85%] bg-orange-600 text-white rounded-2xl rounded-br-sm px-4 py-2 whitespace-pre-line">${escapeHtml(text)}</div>`;
  messagesInner.appendChild(el);
}

function renderThinking() {
  const el = document.createElement("div");
  el.className = "flex justify-start";
  el.innerHTML = `<div class="max-w-[85%] bg-white border border-stone-200 rounded-2xl rounded-bl-sm px-4 py-3 text-stone-500 text-sm flex items-center gap-2">
    <span class="inline-block w-2 h-2 bg-stone-400 rounded-full animate-pulse"></span>
    <span class="inline-block w-2 h-2 bg-stone-400 rounded-full animate-pulse" style="animation-delay:0.2s"></span>
    <span class="inline-block w-2 h-2 bg-stone-400 rounded-full animate-pulse" style="animation-delay:0.4s"></span>
  </div>`;
  messagesInner.appendChild(el);
  return el;
}

function renderError(msg) {
  const el = document.createElement("div");
  el.className = "flex justify-start";
  el.innerHTML = `<div class="max-w-[85%] bg-red-50 border border-red-200 text-red-800 rounded-2xl rounded-bl-sm px-4 py-2 text-sm">${escapeHtml(msg)}</div>`;
  messagesInner.appendChild(el);
}

function renderAssistant(text, payload) {
  const wrap = document.createElement("div");
  wrap.className = "flex justify-start";
  const bubble = document.createElement("div");
  bubble.className = "max-w-[85%] bg-white border border-stone-200 rounded-2xl rounded-bl-sm px-4 py-3";
  bubble.setAttribute("data-speakable", "");

  const parts = [];
  if (text) parts.push(`<p class="whitespace-pre-line">${escapeHtml(text)}</p>`);

  const card = payload.card;
  if (card) parts.push(renderCard(card));

  if (payload.error) parts.push(`<p class="text-red-700 text-sm mt-2">${escapeHtml(payload.error)}</p>`);

  parts.push(`<div class="text-right mt-2">
    <button data-speak class="text-xs text-stone-400 hover:text-stone-700" aria-label="Read aloud">🔊</button>
  </div>`);

  bubble.innerHTML = parts.join("");
  wrap.appendChild(bubble);
  messagesInner.appendChild(wrap);
}

// --------------------------------------------------------------------------
// Card renderers
// --------------------------------------------------------------------------

function renderCard(card) {
  switch (card.type) {
    case "brief": return renderBriefCard(card);
    case "candidates": return renderCandidatesCard(card);
    case "constituencies": return renderConstituenciesCard(card);
    case "election": return renderElectionCard(card);
    case "diff": return renderDiffCard(card);
    case "squad": return renderSquadCard(card);
    default: return "";
  }
}

function renderBriefCard(card) {
  const d = card.data;
  const fallback = d.fallback_reason ? ` <span class="text-xs text-amber-700">(${d.fallback_reason})</span>` : "";
  return `
    <div class="mt-2 border border-stone-200 rounded-lg p-3 bg-stone-50">
      <div class="text-xs text-stone-500 mb-2">${escapeHtml(card.candidate)} · ${escapeHtml(card.party)} · ${escapeHtml(card.constituency)}, ${escapeHtml(card.state)}${fallback}</div>
      <ul class="space-y-1.5 text-sm">
        <li><strong>Background:</strong> ${escapeHtml(d.background)}</li>
        <li><strong>Disclosed assets:</strong> ${escapeHtml(d.disclosed_assets)}</li>
        <li><strong>Pending cases:</strong> ${escapeHtml(d.pending_cases)}</li>
      </ul>
      <p class="text-xs text-stone-500 mt-2">
        <a class="underline" href="${d.source_url || 'https://eci.gov.in'}" target="_blank" rel="noopener">official affidavit data</a>
      </p>
    </div>`;
}

function renderCandidatesCard(card) {
  const items = card.candidates.slice(0, 25).map(
    (c) => `<button data-suggestion="Tell me about ${escapeHtml(c.name)}" class="text-left text-sm border border-stone-200 hover:bg-stone-100 rounded px-2 py-1.5">
      <span class="font-medium">${escapeHtml(c.name)}</span>
      <span class="text-stone-500"> (${escapeHtml(c.party)})${c.winner ? " ✓" : ""}</span>
    </button>`
  ).join("");
  return `
    <div class="mt-2 border border-stone-200 rounded-lg p-3 bg-stone-50">
      <div class="text-xs text-stone-500 mb-2">${card.candidates.length} candidates in ${escapeHtml(card.constituency)}, ${escapeHtml(card.state)}</div>
      <div class="grid sm:grid-cols-2 gap-1.5">${items}</div>
      ${card.candidates.length > 25 ? `<p class="text-xs text-stone-500 mt-2">Showing 25 of ${card.candidates.length}.</p>` : ""}
    </div>`;
}

function renderConstituenciesCard(card) {
  const items = card.constituencies.slice(0, 60).map(
    (c) => `<button data-suggestion="Who's running in ${escapeHtml(c)}" class="text-left text-sm border border-stone-200 hover:bg-stone-100 rounded px-2 py-1">${escapeHtml(c)}</button>`
  ).join("");
  return `
    <div class="mt-2 border border-stone-200 rounded-lg p-3 bg-stone-50">
      <div class="text-xs text-stone-500 mb-2">${card.constituencies.length} constituencies in ${escapeHtml(card.state)}</div>
      <div class="grid sm:grid-cols-3 gap-1.5">${items}</div>
    </div>`;
}

function renderElectionCard(card) {
  const d = card.data;
  const cites = (d.citations || []).slice(0, 5).map(
    (c) => `<li><a class="underline" href="${escapeHtml(c.url)}" target="_blank" rel="noopener">${escapeHtml(c.title || c.url)}</a></li>`
  ).join("");
  const fallback = d.fallback ? ` <span class="text-xs text-amber-700">(${d.fallback})</span>` : "";
  return `
    <div class="mt-2 border border-stone-200 rounded-lg p-3 bg-stone-50">
      <div class="text-xs text-stone-500 mb-2">${escapeHtml(d.state)}${fallback}</div>
      <p class="whitespace-pre-line text-sm">${escapeHtml(d.summary)}</p>
      ${cites ? `<details class="mt-2"><summary class="text-xs cursor-pointer">Sources (${(d.citations || []).length})</summary><ul class="list-disc pl-5 mt-1.5 text-xs">${cites}</ul></details>` : ""}
      <p class="text-xs mt-2"><a class="text-orange-700 underline" href="${d.registration_url}" target="_blank" rel="noopener">Check your voter registration on the ECI portal →</a></p>
    </div>`;
}

function renderDiffCard(card) {
  const d = card.data;
  const aShort = escapeHtml(d.party_a_short || d.party_a_slug);
  const bShort = escapeHtml(d.party_b_short || d.party_b_slug);
  const fallback = d.fallback_reason ? ` <span class="text-xs text-amber-700">(${d.fallback_reason})</span>`
    : (d.cached ? ` <span class="text-xs text-stone-500">(cached)</span>` : "");

  const rows = (d.rows || []).map((row) => `
    <tr class="border-b border-stone-100 align-top">
      <td class="py-1.5 pr-2 font-medium text-xs">${escapeHtml(row.point)}</td>
      <td class="py-1.5 pr-2 text-xs">
        ${escapeHtml(row.party_a_position)}
        ${row.party_a_page ? `<div class="text-[10px] text-stone-500">page ${row.party_a_page}</div>` : ""}
      </td>
      <td class="py-1.5 text-xs">
        ${escapeHtml(row.party_b_position)}
        ${row.party_b_page ? `<div class="text-[10px] text-stone-500">page ${row.party_b_page}</div>` : ""}
      </td>
    </tr>`).join("");

  const sources = (d.party_a_source && d.party_b_source) ? `
    <p class="text-xs text-stone-500 mt-2">
      Sources:
      <a class="underline" href="${escapeHtml(d.party_a_source)}" target="_blank" rel="noopener">${aShort} manifesto</a>
      ·
      <a class="underline" href="${escapeHtml(d.party_b_source)}" target="_blank" rel="noopener">${bShort} manifesto</a>
    </p>` : "";

  return `
    <div class="mt-2 border border-stone-200 rounded-lg overflow-x-auto bg-stone-50">
      <div class="px-3 pt-2 text-xs text-stone-500">${escapeHtml(d.issue)}${fallback}</div>
      <table class="w-full text-left mt-1">
        <thead><tr class="text-[10px] text-stone-500 border-b border-stone-200">
          <th class="px-3 py-1">Sub-topic</th>
          <th class="px-3 py-1">${aShort}</th>
          <th class="px-3 py-1">${bShort}</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
      <div class="px-3 pb-2">${sources}</div>
    </div>`;
}

function renderSquadCard(card) {
  const d = card.data;
  const joinUrl = `${location.origin}/squad/${d.id}`;
  const waUrl = `https://wa.me/?text=${encodeURIComponent(`Join my Voting Squad: ${d.name}\n${d.constituency}, ${d.state} — polling on ${d.polling_date}\n${joinUrl}`)}`;
  return `
    <div class="mt-2 border border-green-300 bg-green-50 rounded-lg p-3">
      <p class="font-medium text-sm">✅ Squad created: ${escapeHtml(d.name)}</p>
      <p class="text-xs text-stone-700 mt-1">${escapeHtml(d.constituency)}, ${escapeHtml(d.state)} · polling ${escapeHtml(d.polling_date)}</p>
      <div class="flex flex-wrap gap-2 mt-2">
        <a href="${joinUrl}" target="_blank" class="bg-stone-900 text-white px-3 py-1 rounded text-xs">Open squad</a>
        <a href="${waUrl}" target="_blank" class="bg-green-600 text-white px-3 py-1 rounded text-xs">Share via WhatsApp</a>
      </div>
    </div>`;
}

// --------------------------------------------------------------------------
// Web Speech API — TTS + recognition
// --------------------------------------------------------------------------

function speak(text, lang) {
  if (!text || !("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = LANG_TO_BCP47[lang] || "en-IN";
  u.rate = 1.0;
  window.speechSynthesis.speak(u);
}

function startMic() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const status = document.getElementById("mic-status");
  if (!SR) {
    renderError("Voice input requires Chrome, Edge, or Safari.");
    if (status) status.textContent = "Voice input not supported in this browser.";
    return;
  }
  const rec = new SR();
  rec.lang = LANG_TO_BCP47[langSel.value] || "en-IN";
  rec.interimResults = false;
  rec.maxAlternatives = 1;
  micBtn.textContent = "🎙️";
  micBtn.setAttribute("aria-pressed", "true");
  if (status) status.textContent = "Listening… speak your question.";
  rec.onresult = (e) => {
    input.value = e.results[0][0].transcript;
    if (status) status.textContent = `Heard: ${input.value}. Sending.`;
    send();
  };
  rec.onerror = (e) => {
    micBtn.textContent = "🎤";
    micBtn.setAttribute("aria-pressed", "false");
    if (status) status.textContent = `Voice input failed: ${e.error || "unknown"}.`;
  };
  rec.onend = () => {
    micBtn.textContent = "🎤";
    micBtn.setAttribute("aria-pressed", "false");
  };
  rec.start();
}

// --------------------------------------------------------------------------
// Utility
// --------------------------------------------------------------------------

function scrollToBottom() {
  messages.scrollTop = messages.scrollHeight;
}
