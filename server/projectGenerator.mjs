import crypto from "node:crypto";

const STEP_TEMPLATES = [
  {
    title: "開工前置",
    focus: "資格、範圍、硬約束與主戰場",
    flow: "確認限制 → 整理必要資料 → 鎖定策略",
  },
  {
    title: "資料研究",
    focus: "來源、案例、制度與在地脈絡",
    flow: "收斂問題 → 搜集 reference → 建立可引用資料",
  },
  {
    title: "匯整轉譯",
    focus: "把計畫書條件轉成設計原則與執行語言",
    flow: "分類重點 → 提煉原則 → 對應評分或驗收條件",
  },
  {
    title: "方案生成",
    focus: "概念、圖像、構件、場景與可行性推進",
    flow: "選基地/場景 → 生成方案 → 比較版本",
  },
  {
    title: "圖說與排版",
    focus: "文件頁面、附件、預算、時程與圖面",
    flow: "整理素材 → 補齊圖說 → 控制頁數與格式",
  },
  {
    title: "交付檢核",
    focus: "送件、同步、簽核、截止與備份",
    flow: "逐項打勾 → 匯出備份 → 同步 Notion",
  },
];

export function createSeedProject() {
  return {
    id: "goal-taichung-sample",
    title: "GOAL TAICHUNG 公共藝術提案",
    subtitle: "由既有六步提案工具轉成可編輯專案工作台",
    sourceFile: "Desktop/index.html",
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    status: "draft",
    deadline: "2026-08-28 17:00",
    budget: "12,789,000",
    owner: "臺中市政府運動局",
    tags: ["公共藝術", "提案", "送件管理"],
    summary:
      "六步直線流程，由上往下做完即可投件。平台保留原本進度、提示詞、圖說卡與送件檢核，並新增上傳解析、欄位編輯、保存與 Notion 同步。",
    extracted: {
      deadlines: ["2026-08-28 17:00 截止", "2026-08-26 前寄出"],
      budgetLines: ["總經費 12,789,000 含稅", "民眾參與上限 511,560"],
      contacts: ["洪嘉穗 04-22289111 分機 51215 devotion812@taichung.gov.tw"],
      requirements: [
        "企劃書不超過 50 頁",
        "一式 12 份印製完成",
        "標價總額需為 12,789,000",
      ],
    },
    steps: STEP_TEMPLATES.map((step, index) => ({
      id: `step-${index}`,
      number: String(index).padStart(2, "0"),
      title: step.title,
      focus: step.focus,
      flow: step.flow,
      done: false,
      tasks: defaultTasks(index),
      notes: index === 0 ? "先完成資格、基地與限制查核，再往下展開。" : "",
      prompts: [],
    })),
    checklist: [
      { id: "ck-1", text: "企劃書頁數、格式、附件與份數已確認", done: false },
      { id: "ck-2", text: "截止日、寄送方式與送達地址已確認", done: false },
      { id: "ck-3", text: "經費、時程、維護與民眾參與欄位已補齊", done: false },
      { id: "ck-4", text: "Notion 已同步或已產出待同步匯入檔", done: false },
    ],
    notion: {
      status: "not_configured",
      url: "",
      lastSyncedAt: "",
      message: "尚未設定 Notion token；可先使用本機匯出。",
    },
  };
}

export function generateProjectFromText(text, sourceFile = "uploaded-plan") {
  const clean = normalize(text);
  const title = extractTitle(clean, sourceFile);
  const deadline = extractDeadline(clean);
  const budget = extractBudget(clean);
  const requirements = unique([
    ...pickLines(clean, /(不得|必須|須|上限|下限|不超過|一式|份|加蓋|密封|附件|資格|投標|檢核|送件)/, 10),
  ]);
  const deadlines = unique(pickLines(clean, /(截止|送達|投件|繳交|開標|寄出|日曆天|工作天)/, 8));
  const budgetLines = unique(pickLines(clean, /(經費|預算|金額|標價|總價|費用|營業稅|萬元|元)/, 8));
  const contacts = unique(pickLines(clean, /(聯絡|分機|電話|信箱|Email|E-mail|@|地址)/i, 8));
  const headings = extractHeadings(clean);

  const generatedSteps = STEP_TEMPLATES.map((step, index) => ({
    id: `step-${index}`,
    number: String(index).padStart(2, "0"),
    title: inferStepTitle(index, headings) || step.title,
    focus: step.focus,
    flow: step.flow,
    done: false,
    tasks: buildStepTasks(index, { requirements, deadlines, budgetLines, contacts, headings }),
    notes: summarizeForStep(index, clean),
    prompts: buildPrompts(index, title),
  }));

  return {
    id: crypto.randomUUID(),
    title,
    subtitle: "由上傳計畫書自動產生",
    sourceFile,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    status: "draft",
    deadline: deadline || "待補",
    budget: budget || "待補",
    owner: inferOwner(clean),
    tags: inferTags(clean),
    summary: summarize(clean),
    extracted: {
      deadlines,
      budgetLines,
      contacts,
      requirements,
    },
    steps: generatedSteps,
    checklist: buildChecklist(requirements, deadlines),
    notion: {
      status: "not_synced",
      url: "",
      lastSyncedAt: "",
      message: "尚未同步。",
    },
  };
}

export function projectToMarkdown(project) {
  const doneCount = project.steps.filter((step) => step.done).length;
  const lines = [
    `# ${project.title}`,
    "",
    project.subtitle || "",
    "",
    `狀態：${project.status || "draft"}`,
    `進度：${doneCount}/${project.steps.length}`,
    `截止：${project.deadline || "待補"}`,
    `經費：${project.budget || "待補"}`,
    `來源：${project.sourceFile || "未記錄"}`,
    "",
    "## 專案摘要",
    project.summary || "待補",
    "",
    "## 擷取重點",
    ...sectionList("時程", project.extracted?.deadlines),
    ...sectionList("經費", project.extracted?.budgetLines),
    ...sectionList("聯絡與地址", project.extracted?.contacts),
    ...sectionList("限制與檢核", project.extracted?.requirements),
    "",
    "## 專案流程",
    ...project.steps.flatMap((step) => [
      "",
      `### ${step.number}｜${step.title}`,
      `完成：${step.done ? "是" : "否"}`,
      `重點：${step.focus || "待補"}`,
      `流程：${step.flow || "待補"}`,
      "",
      ...(step.tasks || []).map((task) => `- [${task.done ? "x" : " "}] ${task.text}`),
      step.notes ? `\n補充：${step.notes}` : "",
    ]),
    "",
    "## 最終檢核",
    ...(project.checklist || []).map((item) => `- [${item.done ? "x" : " "}] ${item.text}`),
  ];
  return lines.filter((line) => line !== null && line !== undefined).join("\n");
}

export function projectToNotionBlocks(project) {
  const blocks = [
    heading(2, "專案摘要"),
    paragraph(project.summary || "待補"),
    heading(2, "基本資訊"),
    bulleted(`狀態：${project.status || "draft"}`),
    bulleted(`截止：${project.deadline || "待補"}`),
    bulleted(`經費：${project.budget || "待補"}`),
    bulleted(`來源：${project.sourceFile || "未記錄"}`),
    heading(2, "擷取重點"),
    ...listGroup("時程", project.extracted?.deadlines),
    ...listGroup("經費", project.extracted?.budgetLines),
    ...listGroup("限制與檢核", project.extracted?.requirements),
    heading(2, "專案流程"),
  ];

  for (const step of project.steps || []) {
    blocks.push(heading(3, `${step.number}｜${step.title}`));
    blocks.push(paragraph(`${step.focus || ""} ${step.flow ? `｜${step.flow}` : ""}`.trim() || "待補"));
    for (const task of step.tasks || []) {
      blocks.push(toDo(task.text, Boolean(task.done)));
    }
    if (step.notes) blocks.push(paragraph(step.notes));
  }

  blocks.push(heading(2, "最終檢核"));
  for (const item of project.checklist || []) {
    blocks.push(toDo(item.text, Boolean(item.done)));
  }

  return blocks.slice(0, 95);
}

function normalize(text) {
  return String(text || "")
    .replace(/\r/g, "\n")
    .replace(/\t/g, " ")
    .replace(/[ 　]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function extractTitle(text, sourceFile) {
  const named = firstMatch(text, [
    /(?:計畫名稱|案名|專案名稱|標案名稱|Project)\s*[：:]\s*(.{4,80})/,
    /「([^」]{4,80}(?:計畫|提案|工程|專案|徵選|設置)[^」]*)」/,
  ]);
  if (named) return cleanupTitle(named);

  const firstReadable = text
    .split("\n")
    .map((line) => line.trim())
    .find((line) => line.length >= 4 && line.length <= 42 && !/^(第|一、|二、|\d+[.、])/.test(line));
  return cleanupTitle(firstReadable || sourceFile.replace(/\.[^.]+$/, ""));
}

function cleanupTitle(title) {
  return String(title || "未命名專案").replace(/[。；;]+$/, "").trim().slice(0, 72);
}

function firstMatch(text, patterns) {
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match?.[1]) return match[1].trim();
  }
  return "";
}

function extractBudget(text) {
  const match = text.match(/(?:總經費|預算|標價|總價|經費)[^\n\d]{0,12}([\d,]+(?:\.\d+)?)(\s*(?:萬|元))?/);
  if (!match) return "";
  return `${match[1]}${match[2] || ""}`.trim();
}

function extractDeadline(text) {
  const deadlineLine = text
    .split("\n")
    .map((line) => line.trim())
    .find((line) => /(截止|送達|投件|繳交|開標|寄出)/.test(line) && /(20\d{2}|\d{1,2}[/-]\d{1,2}|\d{1,2}\s*月\s*\d{1,2}\s*日)/.test(line));
  if (deadlineLine) return deadlineLine.replace(/^[-–—\s]+/, "").slice(0, 90);

  const iso = firstMatch(text, [/(20\d{2}-\d{2}-\d{2})T(\d{2}:\d{2})/]);
  if (iso) return iso;

  return firstMatch(text, [
    /(20\d{2}[/-]\d{1,2}[/-]\d{1,2}(?:\s*[（(]?[一二三四五六日週周A-Za-z]*[)）]?)?(?:\s*\d{1,2}[:：]\d{2})?)/,
    /(\d{1,2}[/-]\d{1,2}(?:\s*[（(]?[一二三四五六日週周A-Za-z]*[)）]?)?(?:\s*\d{1,2}[:：]\d{2})?)/,
  ]);
}

function inferOwner(text) {
  return firstMatch(text, [/(?:主辦|設置|招標|管理|執行)機關\s*[：:]\s*(.{2,40})/, /((?:市政府|縣政府|文化局|運動局|基金會|公司).{0,18})/]) || "待補";
}

function inferTags(text) {
  const candidates = [
    ["公共藝術", /公共藝術/],
    ["工程", /工程|施工|工期/],
    ["設計", /設計|圖說|概念/],
    ["展覽", /展覽|策展/],
    ["補助", /補助|申請/],
    ["投標", /投標|標案|徵選/],
  ];
  return candidates.filter(([, pattern]) => pattern.test(text)).map(([label]) => label).slice(0, 4);
}

function pickLines(text, pattern, limit) {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length >= 6 && line.length <= 160 && pattern.test(line))
    .slice(0, limit);
}

function extractHeadings(text) {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length <= 48)
    .filter((line) => /^(第[一二三四五六七八九十]+章|[壹貳參肆伍陸柒捌玖拾]+、|\d+[.、]|[一二三四五六七八九十]+、)/.test(line))
    .slice(0, 18);
}

function inferStepTitle(index, headings) {
  const dictionary = [
    /(資格|基地|限制|前置|概述|基本)/,
    /(資料|案例|研究|背景|脈絡)/,
    /(理念|原則|策略|轉譯|分析)/,
    /(方案|作品|設計|圖像|概念)/,
    /(圖說|排版|經費|預算|進度|維護)/,
    /(送件|檢核|附件|投標|交付)/,
  ];
  const title = headings
    .find((heading) => dictionary[index].test(heading))
    ?.replace(/^[\d一二三四五六七八九十壹貳參肆伍陸柒捌玖拾第章.、 ]+/, "")
    .trim();
  return title && title.length <= 24 ? title : "";
}

function buildStepTasks(index, extracted) {
  const base = defaultTasks(index);
  const sourceMap = [
    [...extracted.requirements.slice(0, 3), ...extracted.contacts.slice(0, 1)],
    extracted.headings.slice(0, 4),
    extracted.requirements.slice(3, 7),
    extracted.headings.slice(4, 8),
    extracted.budgetLines.slice(0, 4),
    [...extracted.deadlines.slice(0, 4), ...extracted.requirements.slice(0, 2)],
  ];
  const merged = unique([...base.map((task) => task.text), ...(sourceMap[index] || [])]).slice(0, 6);
  return merged.map((text, taskIndex) => ({
    id: `task-${index}-${taskIndex}`,
    text,
    done: false,
  }));
}

function defaultTasks(index) {
  const groups = [
    ["確認資格與迴避限制", "整理基地、附件與評分條件", "鎖定主策略與必要證據"],
    ["整理官方來源與核心案例", "建立可引用 reference 清單", "標記可靠性與轉譯價值"],
    ["把條件轉成設計原則", "建立基地與原則適配矩陣", "對應評分項目"],
    ["產生概念方向與視覺提示", "確認日景、夜景與尺度", "挑選可深化版本"],
    ["補齊圖說、三視圖、預算、時程與維護", "控制頁數與附件格式", "產出最終版面"],
    ["逐項完成送件檢核", "保存最終備份", "同步 Notion 並確認狀態"],
  ];
  return groups[index].map((text, taskIndex) => ({
    id: `task-${index}-${taskIndex}`,
    text,
    done: false,
  }));
}

function summarize(text) {
  const firstParagraph = text.split(/\n\n+/).find((chunk) => chunk.length > 40) || text;
  return firstParagraph.replace(/\n/g, " ").slice(0, 220) || "已建立專案，請補充摘要。";
}

function summarizeForStep(index, text) {
  const keywords = [
    /(資格|限制|基地|現勘|迴避)/,
    /(reference|案例|研究|資料|來源)/i,
    /(原則|策略|理念|評分|分析)/,
    /(方案|作品|圖像|生成|概念)/,
    /(圖說|經費|預算|維護|進度|頁)/,
    /(送件|截止|投件|附件|封|份)/,
  ];
  return pickLines(text, keywords[index], 3).join("\n");
}

function buildPrompts(index, title) {
  if (index === 1) {
    return [`請針對「${title}」整理官方來源、案例、制度與在地脈絡，輸出可引用 reference 清單。`];
  }
  if (index === 2) {
    return [`請把「${title}」的硬約束、評分項目與場域條件，轉成可執行的設計原則與矩陣。`];
  }
  if (index === 3) {
    return [`請依「${title}」生成 3 組方案方向，包含日景、夜景、材質、尺度與互動描述。`];
  }
  return [];
}

function buildChecklist(requirements, deadlines) {
  const items = unique([
    ...requirements.slice(0, 8),
    ...deadlines.slice(0, 4),
    "最終資料已保存並同步 Notion",
  ]).slice(0, 10);
  return (items.length ? items : ["計畫書內容已確認", "任務、時程、經費已補齊", "同步 Notion 或產出匯入檔"]).map((text, index) => ({
    id: `ck-${index}`,
    text,
    done: false,
  }));
}

function sectionList(label, list = []) {
  if (!list?.length) return [`### ${label}`, "- 待補"];
  return [`### ${label}`, ...list.map((item) => `- ${item}`)];
}

function listGroup(label, list = []) {
  if (!list?.length) return [bulleted(`${label}：待補`)];
  return [paragraph(`${label}`), ...list.slice(0, 8).map((item) => bulleted(item))];
}

function unique(items) {
  const seen = new Set();
  return items
    .map((item) => String(item || "").trim())
    .filter((item) => {
      const key = item.replace(/\s+/g, "");
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

function paragraph(text) {
  return {
    object: "block",
    type: "paragraph",
    paragraph: { rich_text: rich(text) },
  };
}

function heading(level, text) {
  const type = `heading_${level}`;
  return {
    object: "block",
    type,
    [type]: { rich_text: rich(text) },
  };
}

function bulleted(text) {
  return {
    object: "block",
    type: "bulleted_list_item",
    bulleted_list_item: { rich_text: rich(text) },
  };
}

function toDo(text, checked) {
  return {
    object: "block",
    type: "to_do",
    to_do: { rich_text: rich(text), checked },
  };
}

function rich(text) {
  return [{ type: "text", text: { content: String(text || "").slice(0, 1900) } }];
}
