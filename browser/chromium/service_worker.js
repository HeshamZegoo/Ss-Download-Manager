const HOST = "com.ssdownloadmanager";
function notify(message, failed = false) {
  chrome.action.setBadgeBackgroundColor({color: failed ? "#b42318" : "#16794b"});
  chrome.action.setBadgeText({text: failed ? "!" : "OK"});
  chrome.action.setTitle({title: "Ss Download Manager: " + message});
  setTimeout(() => chrome.action.setBadgeText({text: ""}), 5000);
}
function sendUrl(url, source = "chromium") {
  if (!url || !/^https?:\/\//i.test(url)) return;
  let port;
  try { port = chrome.runtime.connectNative(HOST); }
  catch (error) { notify(error.message, true); return; }
  let replied = false;
  port.onMessage.addListener(reply => {
    replied = true;
    notify(reply?.ok ? "Link sent to download queue." : (reply?.error || "Could not send link."), !reply?.ok);
    port.disconnect();
  });
  port.onDisconnect.addListener(() => {
    if (!replied) notify(chrome.runtime.lastError?.message || "Desktop bridge unavailable.", true);
  });
  port.postMessage({url, source});
}
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({id: "ssdm-link", title: "Download link with Ss Download Manager", contexts: ["link"]});
  chrome.contextMenus.create({id: "ssdm-page", title: "Send page to Ss Download Manager", contexts: ["page"]});
  chrome.contextMenus.create({id: "ssdm-selection", title: "Download selected URL with Ss Download Manager", contexts: ["selection"]});
});
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "ssdm-link") sendUrl(info.linkUrl);
  if (info.menuItemId === "ssdm-page") sendUrl(tab?.url);
  if (info.menuItemId === "ssdm-selection") sendUrl(info.selectionText?.trim());
});
