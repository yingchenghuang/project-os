const DEFAULTS = { theme: 'sepia', fontSize: 19, font: 'serif', lineHeight: 1.8, width: 700 };
const $ = (id) => document.getElementById(id);
const status = (msg) => ($('status').textContent = msg);

const ERRORS = {
  gated: '這頁顯示了訂閱或登入提示，請先用你的帳號登入。',
  'no-content': '這頁找不到足夠的文章內容。',
};

async function run(action) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !/^https?:/.test(tab.url || '')) {
    status('這個頁面無法使用純淨閱讀。');
    return null;
  }
  try {
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content.js'] });
    const res = await chrome.tabs.sendMessage(tab.id, { action });
    if (res && !res.ok) status(ERRORS[res.error] || `發生錯誤：${res.error}`);
    return res;
  } catch (err) {
    status('這個頁面無法使用純淨閱讀。');
    console.warn('[Clean Reader]', err);
    return null;
  }
}

$('reader').addEventListener('click', async () => {
  const res = await run('toggle-reader');
  if (res?.ok) window.close();
});

$('declutter').addEventListener('click', async () => {
  const res = await run('declutter');
  if (res?.ok) status(res.hidden ? `已隱藏 ${res.hidden} 個干擾元素。` : '沒有找到需要清除的干擾元素。');
});

$('restore').addEventListener('click', async () => {
  const res = await run('restore');
  if (res?.ok) status(res.restored ? `已還原 ${res.restored} 個元素。` : '沒有需要還原的元素。');
});

$('copy').addEventListener('click', async () => {
  const res = await run('markdown');
  if (!res?.ok) return;
  try {
    await navigator.clipboard.writeText(res.markdown);
    status('已複製 Markdown。');
  } catch {
    status('複製失敗，請在閱讀模式中使用「下載 .md」。');
  }
});

// ---------- settings ----------

const fmt = {
  fontSize: (v) => `${v}px`,
  lineHeight: (v) => Number(v).toFixed(2),
  width: (v) => `${v}px`,
};

async function initSettings() {
  const s = { ...DEFAULTS, ...(await chrome.storage.sync.get(DEFAULTS)) };
  for (const key of ['theme', 'font']) {
    $(key).value = s[key];
    $(key).addEventListener('change', () => chrome.storage.sync.set({ [key]: $(key).value }));
  }
  for (const key of ['fontSize', 'lineHeight', 'width']) {
    const input = $(key);
    const out = $(`${key}Out`);
    input.value = s[key];
    out.textContent = fmt[key](s[key]);
    input.addEventListener('input', () => {
      out.textContent = fmt[key](input.value);
      chrome.storage.sync.set({ [key]: Number(input.value) });
    });
  }
}

initSettings();
