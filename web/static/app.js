// Matdaan Mitra — frontend logic.
// Day 1: Candidate Snapshot. Day 2: My Election + Voting Squad. Day 3: Manifesto Diff + TTS + Mic.

const $ = (sel) => document.querySelector(sel);
const escapeHtml = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const LANG_TO_BCP47 = {
  en: "en-IN", hi: "hi-IN", ta: "ta-IN", bn: "bn-IN", mr: "mr-IN",
  te: "te-IN", kn: "kn-IN", ml: "ml-IN", gu: "gu-IN", pa: "pa-IN",
};

// ---- Candidate Snapshot --------------------------------------------------
const stateSel = $("#state-select");
const constSel = $("#const-select");
const candSel = $("#cand-select");
const briefBtn = $("#brief-btn");
const sampleBtn = $("#sample-btn");
const briefOut = $("#brief-output");
const langSel = $("#lang-select");

// ---- My Election ---------------------------------------------------------
const electionStateSel = $("#election-state-select");
const electionBtn = $("#election-btn");
const electionOut = $("#election-output");

// ---- Voting Squad --------------------------------------------------------
const squadForm = $("#squad-form");
const squadStateSel = $("#squad-state");
const squadConstSel = $("#squad-const");
const squadOut = $("#squad-output");

// ---- Manifesto Diff ------------------------------------------------------
const partyA = $("#party-a");
const partyB = $("#party-b");
const issueSel = $("#issue-select");
const diffBtn = $("#diff-btn");
const diffSampleBtn = $("#diff-sample-btn");
const diffOut = $("#diff-output");

// ---- Mic -----------------------------------------------------------------
const micBtn = $("#mic-btn");

// --------------------------------------------------------------------------
// Boot
// --------------------------------------------------------------------------

(async function init() {
  const params = new URLSearchParams(location.search);
  if (params.has("lang")) langSel.value = params.get("lang");

  const [statesR, partiesR] = await Promise.all([
    fetch("/api/states").then((r) => r.json()),
    fetch("/api/parties").then((r) => r.json()),
  ]);
  populate(stateSel, statesR.states, "State…");
  populate(electionStateSel, statesR.states, "State…");
  populate(squadStateSel, statesR.states, "State…");

  populateParties(partyA, partiesR.parties);
  populateParties(partyB, partiesR.parties);
  populateIssues(issueSel, partiesR.issues);
})();

stateSel.addEventListener("change", onStateChange);
constSel.addEventListener("change", () => { briefBtn.disabled = !candSel.value; });
candSel.addEventListener("change", () => { briefBtn.disabled = !candSel.value; });
briefBtn.addEventListener("click", generateBrief);
sampleBtn.addEventListener("click", loadSample);

electionStateSel.addEventListener("change", () => { electionBtn.disabled = !electionStateSel.value; });
electionBtn.addEventListener("click", fetchElectionInfo);

squadStateSel.addEventListener("change", onSquadStateChange);
squadForm.addEventListener("submit", createSquad);

partyA.addEventListener("change", checkDiffReady);
partyB.addEventListener("change", checkDiffReady);
issueSel.addEventListener("change", checkDiffReady);
diffBtn.addEventListener("click", generateDiff);
diffSampleBtn.addEventListener("click", loadDiffSample);

micBtn.addEventListener("click", startMic);

document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && !briefBtn.disabled) generateBrief();
});

// Delegate TTS clicks (every speak button gets data-speak)
document.body.addEventListener("click", (e) => {
  if (e.target.matches("[data-speak]")) {
    const targetSel = e.target.dataset.speak;
    const node = targetSel ? document.querySelector(targetSel) : e.target.closest("[data-speakable]");
    speak(node ? node.innerText : "", langSel.value);
  }
});

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

function ttsButton(targetSelector) {
  return `<button data-speak="${targetSelector}" class="text-sm text-stone-500 hover:text-stone-900 ml-2" aria-label="Read aloud" title="Read aloud (Web Speech API)">🔊</button>`;
}

function startMic() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    alert("Voice input requires Chrome, Edge, or Safari.");
    return;
  }
  const rec = new SR();
  rec.lang = LANG_TO_BCP47[langSel.value] || "en-IN";
  rec.interimResults = false;
  rec.maxAlternatives = 1;
  micBtn.textContent = "🎙️…";
  rec.onresult = (e) => {
    const transcript = e.results[0][0].transcript;
    handleVoiceQuery(transcript);
  };
  rec.onerror = () => { micBtn.textContent = "🎤"; };
  rec.onend = () => { micBtn.textContent = "🎤"; };
  rec.start();
}

function handleVoiceQuery(transcript) {
  // Quick router: if it mentions a state we know, jump to election or candidate flow.
  const upper = transcript.toUpperCase();
  let matchedState = null;
  for (const opt of stateSel.options) {
    if (opt.value && upper.includes(opt.value)) { matchedState = opt.value; break; }
  }
  if (matchedState) {
    electionStateSel.value = matchedState;
    electionBtn.disabled = false;
    fetchElectionInfo();
    electionOut.scrollIntoView({ behavior: "smooth", block: "center" });
  } else {
    setStatus(electionOut, `Heard: "${transcript}". Try saying a state name.`, "loading");
  }
}

// --------------------------------------------------------------------------
// Candidate Snapshot
// --------------------------------------------------------------------------

function populate(sel, items, placeholder) {
  sel.innerHTML = `<option value="">${placeholder}</option>`;
  for (const it of items) {
    const opt = document.createElement("option");
    opt.value = it; opt.textContent = it;
    sel.appendChild(opt);
  }
  sel.disabled = items.length === 0;
}

function populateParties(sel, parties) {
  sel.innerHTML = `<option value="">${sel.getAttribute("aria-label") || "Party"}…</option>`;
  for (const p of parties) {
    const opt = document.createElement("option");
    opt.value = p.slug;
    opt.textContent = `${p.short} — ${p.name}`;
    sel.appendChild(opt);
  }
}

function populateIssues(sel, issues) {
  sel.innerHTML = `<option value="">Issue…</option>`;
  for (const i of issues) {
    const opt = document.createElement("option");
    opt.value = i.key; opt.textContent = i.label;
    sel.appendChild(opt);
  }
}

async function onStateChange() {
  resetBrief();
  candSel.disabled = true; candSel.innerHTML = '<option value="">Candidate…</option>';
  briefBtn.disabled = true;
  if (!stateSel.value) { constSel.disabled = true; return; }
  const r = await fetch(`/api/constituencies?state=${encodeURIComponent(stateSel.value)}`);
  const { constituencies } = await r.json();
  populate(constSel, constituencies, "Constituency…");
  constSel.addEventListener("change", onConstChange, { once: true });
}

async function onConstChange() {
  resetBrief();
  briefBtn.disabled = true;
  if (!constSel.value) { candSel.disabled = true; return; }
  const r = await fetch(`/api/candidates?state=${encodeURIComponent(stateSel.value)}&constituency=${encodeURIComponent(constSel.value)}`);
  const { candidates } = await r.json();
  candSel.innerHTML = '<option value="">Candidate…</option>';
  for (const c of candidates) {
    const opt = document.createElement("option");
    opt.value = c.name;
    opt.textContent = `${c.name} (${c.party})${c.winner ? " ✓" : ""}`;
    candSel.appendChild(opt);
  }
  candSel.disabled = false;
  constSel.addEventListener("change", onConstChange, { once: true });
}

async function generateBrief() {
  setStatus(briefOut, "Generating brief… (Gemini)", "loading");
  briefBtn.disabled = true;
  const t0 = performance.now();
  try {
    const r = await fetch("/api/brief", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        state: stateSel.value, constituency: constSel.value,
        name: candSel.value, lang: langSel.value,
      }),
    });
    const data = await r.json();
    if (!r.ok) { setStatus(briefOut, `Error: ${data.error || "unknown"}`, "error"); return; }
    renderBrief(data, Math.round(performance.now() - t0));
  } catch (e) {
    setStatus(briefOut, `Network error: ${e.message}`, "error");
  } finally {
    briefBtn.disabled = false;
  }
}

function renderBrief(data, ms) {
  const fallback = data.fallback_reason ? ` <span class="text-xs text-amber-700">(fallback: ${data.fallback_reason})</span>` : "";
  briefOut.innerHTML = `
    <div class="border border-stone-200 rounded p-4 bg-stone-50" data-speakable>
      <div class="text-sm text-stone-500 mb-2 flex items-center justify-between">
        <span>${escapeHtml(data.candidate)} · ${escapeHtml(data.party)} · generated in ${ms}ms${fallback}</span>
        ${ttsButton("#brief-output [data-speakable]")}
      </div>
      <ul class="space-y-2">
        <li><strong>Background:</strong> ${escapeHtml(data.background)}</li>
        <li><strong>Disclosed assets:</strong> ${escapeHtml(data.disclosed_assets)}</li>
        <li><strong>Pending cases:</strong> ${escapeHtml(data.pending_cases)}</li>
      </ul>
      <p class="text-xs text-stone-500 mt-3">
        Source: <a class="underline" href="${data.source_url || 'https://eci.gov.in'}" target="_blank" rel="noopener">official affidavit data</a>
      </p>
    </div>`;
}

function setStatus(el, msg, kind) {
  const cls = kind === "error" ? "text-red-700" : "text-stone-600";
  el.innerHTML = `<div class="${cls} text-sm" role="status">${escapeHtml(msg)}</div>`;
}

function resetBrief() { briefOut.innerHTML = ""; }

async function loadSample() {
  const sample = { state: "TAMIL NADU", constituency: "CHENNAI CENTRAL", candidatePrefix: "Dayanidhi" };
  stateSel.value = sample.state;
  await onStateChange();
  constSel.value = sample.constituency;
  await onConstChange();
  let chosen = "";
  for (const opt of candSel.options) {
    if (opt.value.toLowerCase().includes(sample.candidatePrefix.toLowerCase())) { chosen = opt.value; break; }
  }
  candSel.value = chosen || (candSel.options[1] && candSel.options[1].value) || "";
  briefBtn.disabled = !candSel.value;
  if (candSel.value) generateBrief();
}

// --------------------------------------------------------------------------
// My Election
// --------------------------------------------------------------------------

async function fetchElectionInfo() {
  setStatus(electionOut, "Searching for live election dates… (Gemini + Google Search)", "loading");
  electionBtn.disabled = true;
  const t0 = performance.now();
  try {
    const r = await fetch(`/api/election-info?state=${encodeURIComponent(electionStateSel.value)}&lang=${encodeURIComponent(langSel.value)}`);
    const data = await r.json();
    if (!r.ok) { setStatus(electionOut, `Error: ${data.error || "unknown"}`, "error"); return; }
    renderElection(data, Math.round(performance.now() - t0));
  } catch (e) {
    setStatus(electionOut, `Network error: ${e.message}`, "error");
  } finally {
    electionBtn.disabled = false;
  }
}

function renderElection(data, ms) {
  const cites = (data.citations || []).slice(0, 5).map(
    (c) => `<li><a class="underline" href="${escapeHtml(c.url)}" target="_blank" rel="noopener">${escapeHtml(c.title || c.url)}</a></li>`
  ).join("");
  const fallback = data.fallback ? ` <span class="text-xs text-amber-700">(${data.fallback})</span>` : "";
  electionOut.innerHTML = `
    <div class="border border-stone-200 rounded p-4 bg-stone-50" data-speakable>
      <div class="text-sm text-stone-500 mb-2 flex items-center justify-between">
        <span>${escapeHtml(data.state)} · ${ms}ms${fallback}</span>
        ${ttsButton("#election-output [data-speakable] .election-summary-text")}
      </div>
      <p class="whitespace-pre-line election-summary-text">${escapeHtml(data.summary)}</p>
      ${cites ? `<details class="mt-3"><summary class="text-sm cursor-pointer">Sources (${(data.citations || []).length})</summary><ul class="list-disc pl-5 mt-2 text-sm">${cites}</ul></details>` : ""}
      <p class="text-sm mt-3"><a class="text-orange-700 underline" href="${data.registration_url}" target="_blank" rel="noopener">Check your voter registration on the ECI portal →</a></p>
    </div>`;
}

// --------------------------------------------------------------------------
// Voting Squad
// --------------------------------------------------------------------------

async function onSquadStateChange() {
  squadConstSel.disabled = true;
  squadConstSel.innerHTML = '<option value="">Constituency…</option>';
  if (!squadStateSel.value) return;
  const r = await fetch(`/api/constituencies?state=${encodeURIComponent(squadStateSel.value)}`);
  const { constituencies } = await r.json();
  populate(squadConstSel, constituencies, "Constituency…");
}

async function createSquad(e) {
  e.preventDefault();
  setStatus(squadOut, "Creating squad…", "loading");
  const body = {
    name: $("#squad-name").value.trim(),
    creator: $("#squad-creator").value.trim(),
    state: squadStateSel.value,
    constituency: squadConstSel.value,
    polling_date: $("#squad-date").value,
  };
  const r = await fetch("/api/squad", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await r.json();
  if (!r.ok) { setStatus(squadOut, `Error: ${data.error || "unknown"}`, "error"); return; }
  squadOut.innerHTML = `
    <div class="border border-green-300 bg-green-50 rounded p-4">
      <p class="font-medium">✅ Squad created.</p>
      <p class="text-sm mt-2">Share this link with your squad:</p>
      <div class="flex gap-2 mt-1">
        <input class="border border-stone-300 rounded px-2 py-1 flex-1 text-sm" value="${escapeHtml(data.join_url)}" readonly>
        <a href="${data.join_url}" target="_blank" class="bg-stone-900 text-white px-3 py-1 rounded text-sm">Open</a>
        <a href="${data.whatsapp_share_url}" target="_blank" class="bg-green-600 text-white px-3 py-1 rounded text-sm">WhatsApp</a>
      </div>
    </div>`;
}

// --------------------------------------------------------------------------
// Manifesto Diff
// --------------------------------------------------------------------------

function checkDiffReady() {
  diffBtn.disabled = !(partyA.value && partyB.value && issueSel.value && partyA.value !== partyB.value);
}

async function generateDiff() {
  setStatus(diffOut, "Reading both manifestos… (Gemini Flash, ~5–10s)", "loading");
  diffBtn.disabled = true;
  const t0 = performance.now();
  try {
    const r = await fetch("/api/manifesto-diff", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        a: partyA.value, b: partyB.value,
        issue: issueSel.value, lang: langSel.value,
      }),
    });
    const data = await r.json();
    if (!r.ok) { setStatus(diffOut, `Error: ${data.error || "unknown"}`, "error"); return; }
    renderDiff(data, Math.round(performance.now() - t0));
  } catch (e) {
    setStatus(diffOut, `Network error: ${e.message}`, "error");
  } finally {
    checkDiffReady();
  }
}

function renderDiff(data, ms) {
  const aShort = escapeHtml(data.party_a_short || data.party_a_slug || partyA.value);
  const bShort = escapeHtml(data.party_b_short || data.party_b_slug || partyB.value);
  const fallback = data.fallback_reason ? ` <span class="text-xs text-amber-700">(${data.fallback_reason})</span>`
    : (data.cached ? ` <span class="text-xs text-stone-500">(cached)</span>` : "");

  const rows = (data.rows || []).map((row) => `
    <tr class="border-b border-stone-100 align-top" data-speakable>
      <td class="py-2 pr-2 font-medium">${escapeHtml(row.point)}</td>
      <td class="py-2 pr-2 text-sm">
        ${escapeHtml(row.party_a_position)}
        ${row.party_a_page ? `<div class="text-xs text-stone-500 mt-1">page ${row.party_a_page}</div>` : ""}
      </td>
      <td class="py-2 pr-2 text-sm">
        ${escapeHtml(row.party_b_position)}
        ${row.party_b_page ? `<div class="text-xs text-stone-500 mt-1">page ${row.party_b_page}</div>` : ""}
      </td>
      <td class="py-2 text-center">${ttsButton("")}</td>
    </tr>
  `).join("");

  const sources = (data.party_a_source && data.party_b_source) ? `
    <p class="text-xs text-stone-500 mt-3">
      Sources:
      <a class="underline" href="${escapeHtml(data.party_a_source)}" target="_blank" rel="noopener">${aShort} manifesto</a>
      ·
      <a class="underline" href="${escapeHtml(data.party_b_source)}" target="_blank" rel="noopener">${bShort} manifesto</a>
    </p>
  ` : "";

  diffOut.innerHTML = `
    <div class="border border-stone-200 rounded overflow-x-auto bg-stone-50">
      <div class="px-4 pt-3 text-sm text-stone-500 flex items-center justify-between">
        <span>Issue: <strong>${escapeHtml(data.issue)}</strong> · ${ms}ms${fallback}</span>
      </div>
      <table class="w-full text-left mt-2">
        <thead>
          <tr class="text-xs text-stone-500 border-b border-stone-200">
            <th class="px-4 py-2">Sub-topic</th>
            <th class="px-4 py-2">${aShort}</th>
            <th class="px-4 py-2">${bShort}</th>
            <th class="px-4 py-2 text-center">🔊</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
      <div class="px-4 pb-3">${sources}</div>
    </div>`;
}

async function loadDiffSample() {
  partyA.value = "dmk"; partyB.value = "bjp"; issueSel.value = "women_safety";
  checkDiffReady();
  if (!diffBtn.disabled) generateDiff();
}
