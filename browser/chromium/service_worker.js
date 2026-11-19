const HOST = "com.ssdownloadmanager";
const notify = (title, message) => chrome.notifications.create({
  type: "basic", iconUrl: "icon.png", title, message
});

function sendUrl(url, source = "chromium") {
  if (!url || !/^https?:\/\//i.test(url)) return;
  const port = chrome.runtime.connectNative(HOST);
  let replied = false;
  port.onMessage.addListener(reply => {
    replied = true;
    if (!reply?.ok) notify("Ss Download Manager", reply?.error || "Could not send link.");
    else notify("Ss Download Manager", "Link sent to the download queue.");
    port.disconnect();
  });
  port.onDisconnect.addListener(() => {
    if (!replied) notify("Ss Download Manager", chrome.runtime.lastError?.message || "Desktop app bridge unavailable.");
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
chrome.downloads.onCreated.addListener(item => {
  if (item.url && /^https?:\/\//i.test(item.url)) sendUrl(item.url);
});
