// VPN Disconnector – background service worker.
// Routes the domains you choose through the local helper (127.0.0.1:<port>),
// which sends them out via Wi-Fi/Ethernet instead of the VPN tunnel.

const DEFAULTS = { enabled: true, domains: [], port: 8899, failOpen: true };

async function getSettings() {
  return { ...DEFAULTS, ...(await chrome.storage.sync.get(DEFAULTS)) };
}

function buildPac({ domains, port, failOpen }) {
  const proxy = `PROXY 127.0.0.1:${port}` + (failOpen ? "; DIRECT" : "");
  return `
    var DOMAINS = ${JSON.stringify(domains)};
    function FindProxyForURL(url, host) {
      host = host.toLowerCase();
      for (var i = 0; i < DOMAINS.length; i++) {
        var d = DOMAINS[i];
        if (host === d || dnsDomainIs(host, "." + d)) return "${proxy}";
      }
      return "DIRECT";
    }`;
}

async function applyProxy() {
  const s = await getSettings();
  if (!s.enabled || s.domains.length === 0) {
    await chrome.proxy.settings.clear({ scope: "regular" });
  } else {
    await chrome.proxy.settings.set({
      value: { mode: "pac_script", pacScript: { data: buildPac(s) } },
      scope: "regular",
    });
  }
  await updateBadgeForActiveTab();
}

function matches(host, domains) {
  host = (host || "").toLowerCase();
  return domains.some((d) => host === d || host.endsWith("." + d));
}

async function updateBadge(tab) {
  if (!tab || !tab.id) return;
  const s = await getSettings();
  let host = "";
  try { host = new URL(tab.url).hostname; } catch {}
  const bypassed = s.enabled && matches(host, s.domains);
  await chrome.action.setBadgeText({ tabId: tab.id, text: bypassed ? "OFF" : "" });
  await chrome.action.setBadgeBackgroundColor({ tabId: tab.id, color: "#d97706" });
  await chrome.action.setTitle({
    tabId: tab.id,
    title: bypassed ? `VPN bypassed for ${host}` : "VPN Disconnector",
  });
}

async function updateBadgeForActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  await updateBadge(tab);
}

chrome.runtime.onInstalled.addListener(applyProxy);
chrome.runtime.onStartup.addListener(applyProxy);
chrome.storage.onChanged.addListener(applyProxy);
chrome.tabs.onActivated.addListener(({ tabId }) => chrome.tabs.get(tabId).then(updateBadge));
chrome.tabs.onUpdated.addListener((_id, info, tab) => { if (info.url || info.status) updateBadge(tab); });

chrome.proxy.onProxyError.addListener((e) => console.warn("Proxy error:", e));
