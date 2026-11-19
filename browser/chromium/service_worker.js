const HOST = "com.ssdownloadmanager";
function notify(message, failed = false) {
  chrome.action.setBadgeBackgroundColor({color: failed ? "#b42318" : "#16794b"});
  chrome.action.setBadgeText({text: failed ? "!" : "OK"});
  chrome.action.setTitle({title: "Ss Download Manager: " + message});
  setTimeout(() => chrome.action.setBadgeText({text: ""}), 5000);
}
function sendUrl(url, source = "chromium", downloadId = null) {
  if (!url || !/^https?:\\/\\//i.test(url)) return;
  let port;
  try { port = chrome.runtime.connectNative(HOST); }
  catch (error) { notify(error.message, true); return; }
  let replied = false;
  port.onMessage.addListener(reply => {
    replied = true;
    if (reply?.ok) {
      notify("Link sent to download queue.");
    } else {
      notify(reply?.error || "Could not send link.", true);
    }
    port.disconnect();
  });
  port.onDisconnect.addListener(() => {
    if (!replied) notify(chrome.runtime.lastError?.message || "Desktop bridge unavailable.", true);
  });
  port.postMessage({url, source});
  // Hand off immediately: do not let Chrome download the same file in parallel.
  // The native host persists the URL in the desktop inbox before acknowledging it.
  if (downloadId !== null) chrome.downloads.cancel(downloadId, () => void chrome.runtime.lastError);
}
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({id: "ssdm-link", title: "Download link with Ss Download Manager", contexts: ["link"]});
    chrome.contextMenus.create({id: "ssdm-page", title: "Send page to Ss Download Manager", contexts: ["page"]});
    chrome.contextMenus.create({id: "ssdm-selection", title: "Download selected URL with Ss Download Manager", contexts: ["selection"]});
  });
});
chrome.action.onClicked.addListener(tab => sendUrl(tab?.url, "chromium-toolbar"));
chrome.downloads.onCreated.addListener(item => {
  if (item?.id !== undefined && /^https?:\\/\\//i.test(item.url || "")) {
    sendUrl(item.url, "chromium-download", item.id);
  }
});
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "ssdm-link") sendUrl(info.linkUrl);
  if (info.menuItemId === "ssdm-page") sendUrl(tab?.url);
  if (info.menuItemId === "ssdm-selection") sendUrl(info.selectionText?.trim());
});
