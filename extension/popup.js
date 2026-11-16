const DEFAULTS = { enabled: true, domains: [], port: 8899, failOpen: true };
const $ = (id) => document.getElementById(id);

let settings = { ...DEFAULTS };
let tab = null;
let host = "";

function normalize(input) {
  let s = (input || "").trim().toLowerCase();
  if (!s) return "";
  try { if (s.includes("/")) s = new URL(s.includes("://") ? s : "http://" + s).hostname; } catch {}
  return s.replace(/^\*\./, "").replace(/^www\./, "").replace(/\.$/, "");
}

function matchedRule(h) {
  return settings.domains.find((d) => h === d || h.endsWith("." + d));
}

async function save(patch, reloadTab = false) {
  settings = { ...settings, ...patch };
  await chrome.storage.sync.set(settings);
  render();
  // Give the background a moment to apply the new proxy rules, then reload.
  if (reloadTab && tab?.id) setTimeout(() => chrome.tabs.reload(tab.id), 150);
}

function render() {
  $("enabled").checked = settings.enabled;
  $("port").value = settings.port;
  $("failOpen").checked = settings.failOpen;

  if (host) {
    $("current").hidden = false;
    $("host").textContent = host;
    const rule = matchedRule(host);
    const btn = $("toggleSite");
    btn.textContent = rule ? `Use VPN again (remove ${rule})` : "Skip VPN for this site";
    btn.className = rule ? "" : "add";
  }

  const list = $("list");
  list.replaceChildren();
  for (const d of [...settings.domains].sort()) {
    const li = document.createElement("li");
    const span = document.createElement("span");
    span.textContent = d;
    const rm = document.createElement("button");
    rm.textContent = "Remove";
    rm.onclick = () => save({ domains: settings.domains.filter((x) => x !== d) }, matchedRule(host) === d);
    li.append(span, rm);
    list.append(li);
  }
  $("empty").hidden = settings.domains.length > 0;
}

async function checkHelper() {
  const el = $("helper");
  try {
    const ctrl = new AbortController();
    setTimeout(() => ctrl.abort(), 1500);
    const r = await fetch(`http://127.0.0.1:${settings.port}/health`, { signal: ctrl.signal, cache: "no-store" });
    const j = await r.json();
    if (!j.interface) throw new Error("no interface");
    el.textContent = `● Helper running – bypassing via ${j.interface}`;
    el.className = "status ok";
  } catch {
    el.textContent = `● Helper not running on port ${settings.port}. Start helper/bypass_proxy.py`;
    el.className = "status bad";
  }
}

async function init() {
  settings = { ...DEFAULTS, ...(await chrome.storage.sync.get(DEFAULTS)) };
  [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  try {
    const u = new URL(tab.url);
    if (u.protocol === "http:" || u.protocol === "https:") host = u.hostname.toLowerCase();
  } catch {}

  $("enabled").onchange = (e) => save({ enabled: e.target.checked }, true);
  $("failOpen").onchange = (e) => save({ failOpen: e.target.checked });
  $("port").onchange = (e) => {
    const p = parseInt(e.target.value, 10);
    if (p > 0 && p < 65536) save({ port: p }).then(checkHelper);
  };
  $("toggleSite").onclick = () => {
    const rule = matchedRule(host);
    const domains = rule
      ? settings.domains.filter((d) => d !== rule)
      : [...settings.domains, normalize(host)];
    save({ domains }, true);
  };
  $("addForm").onsubmit = (e) => {
    e.preventDefault();
    const d = normalize($("newDomain").value);
    $("newDomain").value = "";
    if (d && !settings.domains.includes(d)) save({ domains: [...settings.domains, d] }, !!host && (host === d || host.endsWith("." + d)));
  };

  render();
  checkHelper();
}

init();
