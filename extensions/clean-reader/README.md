# 純淨閱讀 Clean Reader

Chrome 擴充功能（Manifest V3）。把你**本來就能讀**的文章整理成乾淨的閱讀版面，清除彈窗、Cookie 橫幅與廣告，並可一鍵存成 Markdown。

## 安裝（開發者模式）

1. 開啟 `chrome://extensions`
2. 右上角打開「開發人員模式」
3. 點「載入未封裝項目」，選擇 `extensions/clean-reader` 資料夾
4. 把「純淨閱讀」釘選到工具列

## 功能

| 動作 | 方式 |
| --- | --- |
| 閱讀模式（開／關） | 工具列按鈕，或 `Alt+Shift+R` |
| 清除干擾 | 工具列按鈕，或 `Alt+Shift+D` |
| 還原被隱藏的元素 | 工具列「還原頁面」，或重新整理 |
| 複製 Markdown | 工具列或閱讀模式工具列 |
| 下載 `.md` | 閱讀模式工具列 |
| 列印乾淨版本 | 閱讀模式工具列「列印」 |

閱讀模式可調整主題（米色、白色、深色）、字體（明體、黑體）、字級、行距與版寬，設定會透過 `chrome.storage.sync` 在你的裝置之間同步。

Markdown 匯出包含 YAML front matter（標題、來源網址、網站、作者、發布日期、存檔時間），可直接放進 Obsidian 或 Notion。

快捷鍵可在 `chrome://extensions/shortcuts` 修改。

## 設計原則

這個擴充功能只重新排版頁面上**已經可見**的內容：

- 只擷取畫面上可見的元素，隱藏的文字一律略過。
- 頁面出現訂閱或登入提示時，閱讀模式、清除干擾與 Markdown 匯出都會停止並提示你先登入。
- 清除干擾只隱藏小型浮動列與已知的廣告、Cookie、電子報元素，大型遮罩一律不動，也不會解除頁面捲動鎖定。
- 不讀寫 Cookie、不攔截網路請求、不需要任何網站的常駐權限，只在你點擊或按快捷鍵時透過 `activeTab` 存取當前分頁。

## 檔案

```
manifest.json   權限與快捷鍵
background.js   處理快捷鍵，按需注入 content.js
content.js      擷取、閱讀模式介面（Shadow DOM）、清除干擾、Markdown 轉換
popup.*         工具列面板與閱讀設定
icons/          圖示
```
