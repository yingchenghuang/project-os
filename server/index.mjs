import express from "express";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import crypto from "node:crypto";
import multer from "multer";
import mammoth from "mammoth";
import { createServer as createViteServer } from "vite";
import {
  createSeedProject,
  generateProjectFromText,
  projectToMarkdown,
  projectToNotionBlocks,
} from "./projectGenerator.mjs";

const require = createRequire(import.meta.url);
const pdfParse = require("pdf-parse");

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");
const dataDir = path.join(root, "data");
const exportDir = path.join(root, "exports");
const dataFile = path.join(dataDir, "projects.json");
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 20 * 1024 * 1024 } });
const liveClients = new Set();

await loadEnvFile(path.join(root, ".env.local"));
await loadEnvFile(path.join(root, ".env"));

await fs.mkdir(dataDir, { recursive: true });
await fs.mkdir(exportDir, { recursive: true });

const app = express();
app.disable("x-powered-by");
app.use(express.json({ limit: "4mb" }));

app.get("/api/health", (_req, res) => {
  res.json({
    ok: true,
    storage: githubStorageConfigured() ? "github" : "local",
    realtime: true,
    notionConfigured: Boolean(process.env.NOTION_TOKEN && (process.env.NOTION_PARENT_PAGE_ID || process.env.NOTION_DATABASE_ID)),
  });
});

app.use(basicAuth);

app.get("/api/events", (req, res) => {
  res.set({
    "Cache-Control": "no-cache, no-transform",
    Connection: "keep-alive",
    "Content-Type": "text/event-stream",
  });
  res.flushHeaders();
  res.write(`event: ready\ndata: ${JSON.stringify({ at: new Date().toISOString() })}\n\n`);
  liveClients.add(res);
  const keepAlive = setInterval(() => res.write(": keep-alive\n\n"), 25000);
  req.on("close", () => {
    clearInterval(keepAlive);
    liveClients.delete(res);
  });
});

app.get("/api/projects", async (_req, res) => {
  res.json(await readProjects());
});

app.get("/api/projects/:id", async (req, res) => {
  const project = (await readProjects()).find((item) => item.id === req.params.id);
  if (!project) return res.status(404).json({ error: "project_not_found" });
  res.json(project);
});

app.post("/api/import", upload.single("plan"), async (req, res) => {
  if (!req.file) return res.status(400).json({ error: "missing_file" });
  const parsed = await readUploadedText(req.file);
  const project = generateProjectFromText(parsed.text, req.file.originalname);
  project.importWarnings = parsed.warnings;
  const projects = await readProjects({ includeSeed: false });
  projects.unshift(project);
  await writeProjects(projects);
  res.json({ project, warnings: parsed.warnings });
});

app.put("/api/projects/:id", async (req, res) => {
  const projects = await readProjects();
  const index = projects.findIndex((item) => item.id === req.params.id);
  if (index === -1) return res.status(404).json({ error: "project_not_found" });
  projects[index] = {
    ...projects[index],
    ...req.body,
    id: projects[index].id,
    updatedAt: new Date().toISOString(),
  };
  await writeProjects(projects);
  res.json(projects[index]);
});

app.post("/api/projects/:id/export", async (req, res) => {
  const project = (await readProjects()).find((item) => item.id === req.params.id);
  if (!project) return res.status(404).json({ error: "project_not_found" });
  const file = await writeExport(project);
  res.json({ ok: true, file: path.relative(root, file), markdown: projectToMarkdown(project) });
});

app.post("/api/projects/:id/sync-notion", async (req, res) => {
  const projects = await readProjects();
  const index = projects.findIndex((item) => item.id === req.params.id);
  if (index === -1) return res.status(404).json({ error: "project_not_found" });

  const project = { ...projects[index], ...req.body, updatedAt: new Date().toISOString() };
  const token = process.env.NOTION_TOKEN;
  const parentPageId = process.env.NOTION_PARENT_PAGE_ID;
  const databaseId = process.env.NOTION_DATABASE_ID;

  if (!token || (!parentPageId && !databaseId)) {
    const file = await writeExport(project);
    project.notion = {
      status: "exported",
      url: "",
      lastSyncedAt: new Date().toISOString(),
      message: `尚未設定 Notion 連線，已產出 ${path.relative(root, file)}。`,
    };
    projects[index] = project;
    await writeProjects(projects);
    return res.json({ ok: false, mode: "export", project, file: path.relative(root, file) });
  }

  try {
    const result = databaseId
      ? await createNotionDatabasePage({ token, databaseId, project })
      : await createNotionChildPage({ token, parentPageId, project });
    project.notion = {
      status: "synced",
      url: result.url,
      lastSyncedAt: new Date().toISOString(),
      message: "已同步至 Notion。",
    };
    projects[index] = project;
    await writeProjects(projects);
    res.json({ ok: true, mode: "notion", project, notion: result });
  } catch (error) {
    const file = await writeExport(project);
    project.notion = {
      status: "failed_exported",
      url: "",
      lastSyncedAt: new Date().toISOString(),
      message: `Notion 同步失敗，已保留匯出檔：${path.relative(root, file)}。${error.message}`,
    };
    projects[index] = project;
    await writeProjects(projects);
    res.status(502).json({ ok: false, mode: "failed_export", project, file: path.relative(root, file), error: error.message });
  }
});

if (process.env.NODE_ENV === "production") {
  app.use(express.static(path.join(root, "dist")));
  app.get("*", (_req, res) => res.sendFile(path.join(root, "dist", "index.html")));
} else {
  const vite = await createViteServer({
    root,
    server: { middlewareMode: true },
    appType: "spa",
  });
  app.use(vite.middlewares);
}

const port = Number(process.env.PORT || 5174);
const host = process.env.HOST || "0.0.0.0";
app.listen(port, host, () => {
  console.log(`PROJECT OS running at http://${host}:${port}/`);
});

async function readUploadedText(file) {
  const ext = path.extname(file.originalname || "").toLowerCase();
  const warnings = [];
  if ([".txt", ".md", ".csv"].includes(ext)) {
    return { text: file.buffer.toString("utf8"), warnings };
  }
  if ([".html", ".htm"].includes(ext)) {
    return { text: htmlToText(file.buffer.toString("utf8")), warnings };
  }
  if (ext === ".json") {
    return { text: JSON.stringify(JSON.parse(file.buffer.toString("utf8")), null, 2), warnings };
  }
  if (ext === ".docx") {
    const result = await mammoth.extractRawText({ buffer: file.buffer });
    return { text: result.value, warnings: result.messages?.map((item) => item.message) || warnings };
  }
  if (ext === ".pdf") {
    const result = await pdfParse(file.buffer);
    return { text: result.text, warnings };
  }
  warnings.push(`不熟悉的檔案格式 ${ext || "unknown"}，已用純文字嘗試解析。`);
  return { text: file.buffer.toString("utf8"), warnings };
}

async function readProjects({ includeSeed = true } = {}) {
  if (githubStorageConfigured()) {
    try {
      const projects = await readProjectsFromGitHub();
      return Array.isArray(projects) && projects.length ? projects : includeSeed ? [createSeedProject()] : [];
    } catch (error) {
      console.error(`GitHub storage read failed: ${error.message}`);
    }
  }
  try {
    const data = JSON.parse(await fs.readFile(dataFile, "utf8"));
    return Array.isArray(data) && data.length ? data : includeSeed ? [createSeedProject()] : [];
  } catch {
    return includeSeed ? [createSeedProject()] : [];
  }
}

async function writeProjects(projects) {
  if (githubStorageConfigured()) {
    await writeProjectsToGitHub(projects);
  } else {
    await fs.writeFile(dataFile, JSON.stringify(projects, null, 2));
  }
  broadcastProjectChange();
}

function githubStorageConfigured() {
  return Boolean(process.env.GITHUB_TOKEN && process.env.GITHUB_REPOSITORY);
}

function githubStorageTarget() {
  return {
    branch: process.env.GITHUB_DATA_BRANCH || "main",
    path: process.env.GITHUB_DATA_PATH || "data/projects.json",
    repository: process.env.GITHUB_REPOSITORY,
  };
}

async function readProjectsFromGitHub() {
  const target = githubStorageTarget();
  const result = await githubApi(
    `/repos/${target.repository}/contents/${encodePath(target.path)}?ref=${encodeURIComponent(target.branch)}`,
  );
  return JSON.parse(Buffer.from(result.content.replace(/\n/g, ""), "base64").toString("utf8"));
}

async function writeProjectsToGitHub(projects) {
  const target = githubStorageTarget();
  const content = Buffer.from(`${JSON.stringify(projects, null, 2)}\n`).toString("base64");

  for (let attempt = 0; attempt < 3; attempt += 1) {
    let current = null;
    try {
      current = await githubApi(
        `/repos/${target.repository}/contents/${encodePath(target.path)}?ref=${encodeURIComponent(target.branch)}`,
      );
    } catch (error) {
      if (error.status !== 404) throw error;
    }

    try {
      await githubApi(`/repos/${target.repository}/contents/${encodePath(target.path)}`, {
        method: "PUT",
        body: {
          branch: target.branch,
          content,
          message: `Update project data ${new Date().toISOString()}`,
          ...(current?.sha ? { sha: current.sha } : {}),
        },
      });
      return;
    } catch (error) {
      if (error.status !== 409 || attempt === 2) throw error;
    }
  }
}

async function githubApi(endpoint, { method = "GET", body } = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetch(`https://api.github.com${endpoint}`, {
      method,
      signal: controller.signal,
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${process.env.GITHUB_TOKEN}`,
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.message || `GitHub API ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return data;
  } finally {
    clearTimeout(timeout);
  }
}

function encodePath(value) {
  return value.split("/").map(encodeURIComponent).join("/");
}

function broadcastProjectChange() {
  const message = `event: projects-changed\ndata: ${JSON.stringify({ at: new Date().toISOString() })}\n\n`;
  liveClients.forEach((client) => client.write(message));
}

function basicAuth(req, res, next) {
  const username = process.env.APP_USERNAME;
  const password = process.env.APP_PASSWORD;
  if (!password) return next();

  const [scheme, encoded] = String(req.headers.authorization || "").split(" ");
  const decoded = scheme === "Basic" && encoded ? Buffer.from(encoded, "base64").toString("utf8") : "";
  const separator = decoded.indexOf(":");
  const suppliedUser = separator >= 0 ? decoded.slice(0, separator) : "";
  const suppliedPassword = separator >= 0 ? decoded.slice(separator + 1) : "";
  const expectedUser = username || "project-os";

  if (safeEqual(suppliedUser, expectedUser) && safeEqual(suppliedPassword, password)) return next();
  res.set("WWW-Authenticate", 'Basic realm="PROJECT OS", charset="UTF-8"');
  return res.status(401).send("需要登入 PROJECT OS");
}

function safeEqual(left, right) {
  const leftBuffer = Buffer.from(String(left));
  const rightBuffer = Buffer.from(String(right));
  return leftBuffer.length === rightBuffer.length && crypto.timingSafeEqual(leftBuffer, rightBuffer);
}

async function writeExport(project) {
  const safeName = project.title.replace(/[^\p{L}\p{N}-]+/gu, "-").replace(/^-|-$/g, "").slice(0, 64) || "project";
  const file = path.join(exportDir, `${todayTaipei()}-${safeName}.md`);
  await fs.writeFile(file, projectToMarkdown(project));
  return file;
}

async function createNotionChildPage({ token, parentPageId, project }) {
  const body = {
    parent: { page_id: parentPageId },
    properties: {
      title: [{ type: "text", text: { content: project.title.slice(0, 120) } }],
    },
    children: projectToNotionBlocks(project),
  };
  return notionFetch(token, "https://api.notion.com/v1/pages", { method: "POST", body });
}

async function createNotionDatabasePage({ token, databaseId, project }) {
  const database = await notionFetch(token, `https://api.notion.com/v1/databases/${databaseId}`, { method: "GET" });
  const titleProp = Object.entries(database.properties || {}).find(([, prop]) => prop.type === "title")?.[0] || "Name";
  const properties = {
    [titleProp]: { title: [{ type: "text", text: { content: project.title.slice(0, 120) } }] },
  };
  assignIfProperty(database.properties, properties, ["狀態", "Status"], project.status, "select");
  assignIfProperty(database.properties, properties, ["截止", "截止日", "Due Date"], project.deadline, "date");
  assignIfProperty(database.properties, properties, ["經費", "預算", "Budget"], numericBudget(project.budget), "number");
  const body = {
    parent: { database_id: databaseId },
    properties,
    children: projectToNotionBlocks(project),
  };
  return notionFetch(token, "https://api.notion.com/v1/pages", { method: "POST", body });
}

async function notionFetch(token, url, { method, body }) {
  const response = await fetch(url, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      "Notion-Version": "2022-06-28",
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.message || `Notion API ${response.status}`);
  }
  return data;
}

function assignIfProperty(schema, properties, names, value, type) {
  if (value === undefined || value === null || value === "") return;
  const name = names.find((candidate) => schema?.[candidate]);
  if (!name) return;
  if (type === "select") properties[name] = { select: { name: String(value) } };
  if (type === "number" && Number.isFinite(value)) properties[name] = { number: value };
  if (type === "date" && /^\d{4}-\d{2}-\d{2}/.test(String(value))) {
    properties[name] = { date: { start: String(value).slice(0, 10) } };
  }
}

function numericBudget(value) {
  const number = Number(String(value || "").replace(/[^\d.]/g, ""));
  return Number.isFinite(number) ? number : null;
}

function todayTaipei() {
  return new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Taipei",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

function htmlToText(html) {
  return String(html)
    .replace(/<script[\s\S]*?<\/script>/gi, "\n")
    .replace(/<style[\s\S]*?<\/style>/gi, "\n")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/(p|div|section|article|header|main|footer|li|tr|h[1-6]|details|summary)>/gi, "\n")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

async function loadEnvFile(file) {
  try {
    const content = await fs.readFile(file, "utf8");
    for (const line of content.split("\n")) {
      const match = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
      if (!match || process.env[match[1]]) continue;
      process.env[match[1]] = match[2].replace(/^["']|["']$/g, "");
    }
  } catch {
    // Optional local env files are allowed to be absent.
  }
}
