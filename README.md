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
