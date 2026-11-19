const HOST = "com.ssdownloadmanager";
function notify(message, failed = false) {
  browser.browserAction.setBadgeBackgroundColor({color: failed ? "#b42318" : "#16794b"});
  browser.browserAction.setBadgeText({text: failed ? "!" : "OK"});
  browser.browserAction.setTitle({title: "Ss Download Manager: " + message});
  setTimeout(() => browser.browserAction.setBadgeText({text: ""}), 5000);
}
function sendUrl(url, source = "firefox") {
  if (!url || !/^https?:\/\//i.test(url)) return;
  let port;
  try { port = browser.runtime.connectNative(HOST); }
  catch (error) { notify(error.message, true); return; }
  let replied = false;
  port.onMessage.addListener(reply => {
    replied = true;
    notify(reply?.ok ? "Link sent to download queue." : (reply?.error || "Could not send link."), !reply?.ok);
    port.disconnect();
  });
  port.onDisconnect.addListener(() => {
    if (!replied) notify("Native host disconnected. Check desktop installation.", true);
  });
  port.postMessage({url, source});
}
browser.runtime.onInstalled.addListener(() => {
  browser.contextMenus.create({id: "ssdm-link", title: "Download link with Ss Download Manager", contexts: ["link"]});
  browser.contextMenus.create({id: "ssdm-page", title: "Send page to Ss Download Manager", contexts: ["page"]});
  browser.contextMenus.create({id: "ssdm-selection", title: "Download selected URL with Ss Download Manager", contexts: ["selection"]});
});
browser.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "ssdm-link") sendUrl(info.linkUrl);
  if (info.menuItemId === "ssdm-page") sendUrl(tab?.url);
  if (info.menuItemId === "ssdm-selection") sendUrl(info.selectionText?.trim());
});
