const HOST = "com.ssdownloadmanager";
function notify(message, failed = false) {
  browser.browserAction.setBadgeBackgroundColor({color: failed ? "#b42318" : "#16794b"});
  browser.browserAction.setBadgeText({text: failed ? "!" : "OK"});
  browser.browserAction.setTitle({title: "Ss Download Manager: " + message});
  setTimeout(() => browser.browserAction.setBadgeText({text: ""}), 5000);
}
function isHttpUrl(url) {
  return typeof url === "string" && (url.startsWith("http://") || url.startsWith("https://"));
}
function sendUrl(url, source = "firefox", downloadId = null) {
  if (!isHttpUrl(url)) return;
  let port;
  try { port = browser.runtime.connectNative(HOST); }
  catch (error) { notify(error.message, true); return; }
  let replied = false;
  port.onMessage.addListener(reply => {
    replied = true;
    if (reply?.ok) {
      notify("Link sent to download queue.");
      if (downloadId !== null) browser.downloads.cancel(downloadId).catch(() => {});
    } else {
      notify(reply?.error || "Could not send link.", true);
    }
    port.disconnect();
  });
  port.onDisconnect.addListener(() => {
    if (!replied) notify("Native host disconnected. Check desktop installation.", true);
  });
  port.postMessage({url, source});
  // Cancel Firefox's copy only after the native host confirms it persisted the URL.
}
browser.runtime.onInstalled.addListener(async () => {
  await browser.storage.local.set({ssdmActivatedAt: Date.now()});
  await browser.contextMenus.removeAll();
  browser.contextMenus.create({id: "ssdm-link", title: "Download link with Ss Download Manager", contexts: ["link"]});
  browser.contextMenus.create({id: "ssdm-page", title: "Send page to Ss Download Manager", contexts: ["page"]});
  browser.contextMenus.create({id: "ssdm-selection", title: "Download selected URL with Ss Download Manager", contexts: ["selection"]});
});
browser.browserAction.onClicked.addListener(tab => sendUrl(tab?.url, "firefox-toolbar"));
browser.downloads.onCreated.addListener(async item => {
  if (!item || !isHttpUrl(item.url) || item.id === undefined) return;
  const data = await browser.storage.local.get("ssdmActivatedAt");
  const startedAt = Date.parse(item.startTime || "");
  const cutoff = Number(data.ssdmActivatedAt || Date.now());
  // Ignore downloads that existed before this extension install/update.
  if (!Number.isFinite(startedAt) || startedAt < cutoff) return;
  sendUrl(item.url, "firefox-download", item.id);
});
browser.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "ssdm-link") sendUrl(info.linkUrl);
  if (info.menuItemId === "ssdm-page") sendUrl(tab?.url);
  if (info.menuItemId === "ssdm-selection") sendUrl(info.selectionText?.trim());
});
