const HOST = "com.ssdownloadmanager";
function notify(message, failed = false) {
  chrome.action.setBadgeBackgroundColor({color: failed ? "#b42318" : "#16794b"});
  chrome.action.setBadgeText({text: failed ? "!" : "OK"});
  chrome.action.setTitle({title: "Ss Download Manager: " + message});
  setTimeout(() => chrome.action.setBadgeText({text: ""}), 5000);
}
function isHttpUrl(url) {
  return typeof url === "string" && (url.startsWith("http://") || url.startsWith("https://"));
}
function sendUrl(url, source = "chromium", downloadId = null) {
  if (!isHttpUrl(url)) return;
  let port;
  try { port = chrome.runtime.connectNative(HOST); }
  catch (error) { notify(error.message, true); return; }
  let replied = false;
  port.onMessage.addListener(reply => {
    replied = true;
    if (reply?.ok) notify("Link sent to download queue.");
    else notify(reply?.error || "Could not send link.", true);
    port.disconnect();
  });
  port.onDisconnect.addListener(() => {
    if (!replied) notify(chrome.runtime.lastError?.message || "Desktop bridge unavailable.", true);
  });
  port.postMessage({url, source});
  // Native host persists the URL; cancel Chrome's copy immediately to prevent
  // the browser and desktop manager downloading the same file in parallel.
  if (downloadId !== null) chrome.downloads.cancel(downloadId, () => void chrome.runtime.lastError);
}
chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.set({ssdmActivatedAt: Date.now()});
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({id: "ssdm-link", title: "Download link with Ss Download Manager", contexts: ["link"]});
    chrome.contextMenus.create({id: "ssdm-page", title: "Send page to Ss Download Manager", contexts: ["page"]});
    chrome.contextMenus.create({id: "ssdm-selection", title: "Download selected URL with Ss Download Manager", contexts: ["selection"]});
  });
});
chrome.action.onClicked.addListener(tab => sendUrl(tab?.url, "chromium-toolbar"));
chrome.downloads.onCreated.addListener(item => {
  if (!item || !isHttpUrl(item.url) || item.id === undefined) return;
  chrome.storage.local.get("ssdmActivatedAt", data => {
    const startedAt = Date.parse(item.startTime || "");
    const cutoff = Number(data.ssdmActivatedAt || Date.now());
    // Ignore downloads that were already present when the extension was installed/updated.
    if (!Number.isFinite(startedAt) || startedAt < cutoff) return;
    sendUrl(item.url, "chromium-download", item.id);
  });
});
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "ssdm-link") sendUrl(info.linkUrl);
  if (info.menuItemId === "ssdm-page") sendUrl(tab?.url);
  if (info.menuItemId === "ssdm-selection") sendUrl(info.selectionText?.trim());
});
