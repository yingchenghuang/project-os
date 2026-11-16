# PROJECT OS

計畫書上傳後，自動產生可編輯的專案工作台，提供即時刷新、GitHub 持久化與 Notion 同步。

## 啟動

```bash
cd /Users/huangyingcheng/Documents/Codex/2026-07-08/new-chat/outputs/project-os
PATH="/Users/huangyingcheng/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/Users/huangyingcheng/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback:$PATH" pnpm dev
```

開啟：

```text
http://127.0.0.1:5174/
```

## 支援格式

PDF、DOCX、TXT、MD、HTML、JSON、CSV。

## Notion 同步

複製 `.env.example` 成 `.env.local`，填入：

```bash
NOTION_TOKEN=
NOTION_PARENT_PAGE_ID=
NOTION_DATABASE_ID=
```

二擇一即可：

- `NOTION_PARENT_PAGE_ID`：把專案同步成該頁面底下的新子頁。
- `NOTION_DATABASE_ID`：把專案同步成資料庫的一筆頁面，並自動偵測 title 欄位。

若沒有設定 Notion 連線，平台會改成產出 `exports/*.md`，介面會顯示「已匯出待同步」，不會誤報同步成功。

## 室內設計專案（空間設計工作台）

在「黃英誠 空間設計工作台」按「專案 JSON」匯出的檔案，直接拖進「計畫書上傳」即可。平台辨識到工作台格式（`format: "hansun-space"`）時，不套用公共藝術提案範本，改產生七階段室內設計計畫：

1. 現場複丈與圖面核定：工作台列出的每一項待確認事項都變成核對任務。
2. 需求訪談與方案選定：每個 AI 配置方案一項比較任務，附家具櫃體件數與配置檢核結果。
3. 設計深化、4. 施工圖與圖說（帶入門窗數量）、5. 估價與發包、6. 施工與監造（帶入衛浴防水間數）、7. 驗收與交屋。

專案頁上方多一個「空間與方案」區塊：方案卡片可「選定這個方案」（保存後記住）、各空間圖比面積，以及可貼上工作台網址的連結欄。匯出 Markdown 與 Notion 同步都會附上方案與採用標記。

範例：`samples/B01-workbench-project.json` 是德鑫泰極 B 戶標準層的工作台專案（讀圖重繪平面與三個方案），上傳後得到的結果見 `samples/B01-project-os.json`。

## GitHub 與線上部署

專案包含 `render.yaml`，GitHub 倉庫連接 Render 後會自動建置與部署。正式環境請設定：

```bash
APP_USERNAME=project-os
APP_PASSWORD=請使用長密碼
GITHUB_TOKEN=GitHub fine-grained token
GITHUB_REPOSITORY=yingchenghuang/project-os
GITHUB_DATA_BRANCH=project-data
GITHUB_DATA_PATH=data/projects.json
```

`GITHUB_TOKEN` 僅需該倉庫的 Contents 讀寫權限。啟用後，每次保存或匯入都會寫回獨立的 `project-data` 分支，不會觸發網站重建；介面透過即時事件與 30 秒校正刷新同步不同視窗的變更。

Notion 相關金鑰與 GitHub token 只能設定在部署平台的環境變數，不可提交到倉庫。

## 已驗證

- 上傳 `/Users/huangyingcheng/Desktop/index.html` 產生 6 步專案流程。
- 本機保存可用。
- Notion 未設定時會產出 `exports/2026-07-08-GOAL-TAICHUNG-提案平台.md`。
- 桌面與手機寬度瀏覽器檢查通過。
