// Injects the content script on demand (activeTab) and forwards keyboard commands.

async function runInTab(tabId, action) {
  await chrome.scripting.executeScript({ target: { tabId }, files: ['content.js'] });
  return chrome.tabs.sendMessage(tabId, { action });
}

chrome.commands.onCommand.addListener(async (command, tab) => {
  if (!tab?.id) [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) return;
  try {
    await runInTab(tab.id, command);
  } catch (err) {
    console.warn('[Clean Reader]', err);
  }
});
