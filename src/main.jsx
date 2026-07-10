import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronRight,
  ClipboardCheck,
  Database,
  Download,
  Edit3,
  FileText,
  Loader2,
  RefreshCw,
  Save,
  Send,
  Upload,
} from "lucide-react";
import "./styles.css";

const emptyStatus = {
  type: "idle",
  message: "等待上傳計畫書。",
};

function App() {
  const [projects, setProjects] = useState([]);
  const [activeId, setActiveId] = useState("");
  const [activeStep, setActiveStep] = useState(0);
  const [status, setStatus] = useState(emptyStatus);
  const [saving, setSaving] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef(null);

  const loadProjects = useCallback(async ({ initial = false } = {}) => {
    const res = await fetch("/api/projects", { cache: "no-store" });
    if (!res.ok) throw new Error("projects_unavailable");
    const incoming = await res.json();
    setProjects((current) => (initial ? incoming : mergeProjectsByUpdatedAt(current, incoming)));
    setActiveId((current) => current || incoming[0]?.id || "");
  }, []);

  const project = useMemo(
    () => projects.find((item) => item.id === activeId) || projects[0] || null,
    [projects, activeId],
  );

  const progress = useMemo(() => {
    if (!project?.steps?.length) return 0;
    return Math.round((project.steps.filter((step) => step.done).length / project.steps.length) * 100);
  }, [project]);

  useEffect(() => {
    loadProjects({ initial: true })
      .catch(() => setStatus({ type: "error", message: "讀取專案失敗，請確認伺服器已啟動。" }));

    const events = new EventSource("/api/events");
    events.addEventListener("projects-changed", () => loadProjects().catch(() => {}));
    const refresh = setInterval(() => loadProjects().catch(() => {}), 30000);
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") loadProjects().catch(() => {});
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      clearInterval(refresh);
      events.close();
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [loadProjects]);

  function replaceProject(nextProject) {
    setProjects((items) => items.map((item) => (item.id === nextProject.id ? nextProject : item)));
  }

  function updateProject(patch) {
    if (!project) return;
    replaceProject({ ...project, ...patch, updatedAt: new Date().toISOString() });
  }

  function updateStep(index, patch) {
    if (!project) return;
    const steps = project.steps.map((step, stepIndex) => (stepIndex === index ? { ...step, ...patch } : step));
    replaceProject({ ...project, steps, updatedAt: new Date().toISOString() });
  }

  function updateTask(stepIndex, taskIndex, patch) {
    if (!project) return;
    const steps = project.steps.map((step, index) => {
      if (index !== stepIndex) return step;
      return {
        ...step,
        tasks: step.tasks.map((task, taskIdx) => (taskIdx === taskIndex ? { ...task, ...patch } : task)),
      };
    });
    replaceProject({ ...project, steps, updatedAt: new Date().toISOString() });
  }

  function updateChecklist(index, patch) {
    if (!project) return;
    const checklist = project.checklist.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item));
    replaceProject({ ...project, checklist, updatedAt: new Date().toISOString() });
  }

  async function handleUpload(file) {
    if (!file) return;
    setStatus({ type: "working", message: `正在解析 ${file.name}...` });
    const form = new FormData();
    form.append("plan", file);
    try {
      const res = await fetch("/api/import", { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "import_failed");
      setProjects((items) => [data.project, ...items]);
      setActiveId(data.project.id);
      setActiveStep(0);
      const warning = data.warnings?.length ? `；${data.warnings.join("；")}` : "";
      setStatus({ type: "success", message: `已產生「${data.project.title}」${warning}` });
    } catch (error) {
      setStatus({ type: "error", message: `上傳解析失敗：${error.message}` });
    }
  }

  async function saveProject() {
    if (!project) return;
    setSaving(true);
    setStatus({ type: "working", message: "正在保存專案..." });
    try {
      const res = await fetch(`/api/projects/${project.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(project),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "save_failed");
      replaceProject(data);
      setStatus({ type: "success", message: "已保存到本機專案資料庫。" });
    } catch (error) {
      setStatus({ type: "error", message: `保存失敗：${error.message}` });
    } finally {
      setSaving(false);
    }
  }

  async function syncNotion() {
    if (!project) return;
    setSyncing(true);
    setStatus({ type: "working", message: "正在同步 Notion..." });
    try {
      const res = await fetch(`/api/projects/${project.id}/sync-notion`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(project),
      });
      const data = await res.json();
      if (!res.ok && data.mode !== "export") throw new Error(data.error || "sync_failed");
      replaceProject(data.project);
      setStatus({
        type: data.ok ? "success" : "warning",
        message: data.ok ? "已同步到 Notion。" : data.project.notion.message,
      });
    } catch (error) {
      setStatus({ type: "error", message: `同步失敗：${error.message}` });
    } finally {
      setSyncing(false);
    }
  }

  async function exportMarkdown() {
    if (!project) return;
    setStatus({ type: "working", message: "正在產出 Markdown..." });
    const res = await fetch(`/api/projects/${project.id}/export`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) {
      setStatus({ type: "error", message: "匯出失敗。" });
      return;
    }
    const blob = new Blob([data.markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${project.title}.md`;
    link.click();
    URL.revokeObjectURL(url);
    setStatus({ type: "success", message: `已產出 ${data.file}` });
  }

  if (!project) {
    return <EmptyShell status={status} onUpload={handleUpload} fileInputRef={fileInputRef} dragging={dragging} setDragging={setDragging} />;
  }

  const selectedStep = project.steps[activeStep] || project.steps[0];

  return (
    <div className="app">
      <aside className="side">
        <div className="brand">
          <div>
            <strong>PROJECT OS</strong>
            <span>計畫書轉專案平台</span>
          </div>
          <button className="iconButton" onClick={() => loadProjects().catch(() => {})} title="重新整理">
            <RefreshCw size={17} />
          </button>
        </div>

        <UploadBox
          fileInputRef={fileInputRef}
          onUpload={handleUpload}
          dragging={dragging}
          setDragging={setDragging}
        />

        <div className="projectList">
          <div className="listLabel">專案</div>
          {projects.map((item) => (
            <button
              key={item.id}
              className={`projectItem ${item.id === project.id ? "on" : ""}`}
              onClick={() => {
                setActiveId(item.id);
                setActiveStep(0);
              }}
            >
              <FileText size={16} />
              <span>{item.title}</span>
              <ChevronRight size={15} />
            </button>
          ))}
        </div>

        <StatusBox status={status} />
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <input
              className="titleInput"
              value={project.title}
              onChange={(event) => updateProject({ title: event.target.value })}
            />
            <textarea
              className="summaryInput"
              value={project.summary}
              onChange={(event) => updateProject({ summary: event.target.value })}
            />
          </div>
          <div className="actions">
            <button className="btn ghost" onClick={exportMarkdown}>
              <Download size={17} />
              匯出
            </button>
            <button className="btn ghost" onClick={saveProject} disabled={saving}>
              {saving ? <Loader2 className="spin" size={17} /> : <Save size={17} />}
              保存
            </button>
            <button className="btn" onClick={syncNotion} disabled={syncing}>
              {syncing ? <Loader2 className="spin" size={17} /> : <Database size={17} />}
              同步 Notion
            </button>
          </div>
        </header>

        <section className="projectMeta">
          <MetaField
            icon={<CalendarDays size={18} />}
            label="截止"
            value={project.deadline}
            onChange={(value) => updateProject({ deadline: value })}
          />
          <MetaField label="經費" value={project.budget} onChange={(value) => updateProject({ budget: value })} />
          <MetaField label="主辦/對象" value={project.owner} onChange={(value) => updateProject({ owner: value })} />
          <div className="progressBox">
            <div>
              <span>進度</span>
              <b>{progress}%</b>
            </div>
            <i>
              <em style={{ width: `${progress}%` }} />
            </i>
          </div>
        </section>

        <section className="flowColumn">
          {project.steps.map((step, index) => (
            <StepCard
              key={step.id}
              step={step}
              index={index}
              active={index === activeStep}
              onSelect={() => setActiveStep(index)}
              onToggle={(done) => updateStep(index, { done })}
              onTaskToggle={(taskIndex, done) => updateTask(index, taskIndex, { done })}
            />
          ))}
        </section>
      </main>

      <aside className="inspector">
        <div className="inspectorHead">
          <div>
            <span>編輯模式</span>
            <strong>{selectedStep?.number}｜{selectedStep?.title}</strong>
          </div>
          <Edit3 size={18} />
        </div>

        <Field label="步驟名稱" value={selectedStep.title} onChange={(value) => updateStep(activeStep, { title: value })} />
        <Field label="工作重點" value={selectedStep.focus} onChange={(value) => updateStep(activeStep, { focus: value })} />
        <Field label="流程描述" value={selectedStep.flow} onChange={(value) => updateStep(activeStep, { flow: value })} />
        <Field
          label="補充筆記"
          value={selectedStep.notes || ""}
          multi
          onChange={(value) => updateStep(activeStep, { notes: value })}
        />

        <div className="panelBlock">
          <div className="panelTitle">
            <ClipboardCheck size={17} />
            任務檢核
          </div>
          {selectedStep.tasks.map((task, taskIndex) => (
            <EditableCheck
              key={task.id}
              item={task}
              onToggle={(done) => updateTask(activeStep, taskIndex, { done })}
              onChange={(text) => updateTask(activeStep, taskIndex, { text })}
            />
          ))}
        </div>

        <div className="panelBlock">
          <div className="panelTitle">
            <CheckCircle2 size={17} />
            最終檢核
          </div>
          {project.checklist.map((item, index) => (
            <EditableCheck
              key={item.id}
              item={item}
              onToggle={(done) => updateChecklist(index, { done })}
              onChange={(text) => updateChecklist(index, { text })}
            />
          ))}
        </div>

        <div className={`notionState ${project.notion?.status || "idle"}`}>
          <div>
            <Database size={18} />
            <span>同步狀態</span>
          </div>
          <strong>{notionLabel(project.notion?.status)}</strong>
          <p>{project.notion?.message || "尚未同步。"}</p>
          {project.notion?.url ? (
            <a href={project.notion.url} target="_blank" rel="noreferrer">
              開啟 Notion
            </a>
          ) : null}
        </div>
      </aside>
    </div>
  );
}

function EmptyShell({ status, onUpload, fileInputRef, dragging, setDragging }) {
  return (
    <div className="emptyShell">
      <div className="emptyPanel">
        <strong>PROJECT OS</strong>
        <p>上傳計畫書後，自動產生可編輯的專案介面。</p>
        <UploadBox fileInputRef={fileInputRef} onUpload={onUpload} dragging={dragging} setDragging={setDragging} large />
        <StatusBox status={status} />
      </div>
    </div>
  );
}

function UploadBox({ fileInputRef, onUpload, dragging, setDragging, large = false }) {
  return (
    <div
      className={`uploadBox ${dragging ? "dragging" : ""} ${large ? "large" : ""}`}
      onDragEnter={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        onUpload(event.dataTransfer.files?.[0]);
      }}
      onClick={() => fileInputRef.current?.click()}
    >
      <Upload size={22} />
      <b>計畫書上傳</b>
      <span>PDF、DOCX、TXT、MD、HTML、JSON</span>
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.docx,.txt,.md,.html,.htm,.json,.csv"
        onChange={(event) => onUpload(event.target.files?.[0])}
      />
    </div>
  );
}

function StatusBox({ status }) {
  return (
    <div className={`statusBox ${status.type}`}>
      {status.type === "working" ? <Loader2 className="spin" size={16} /> : <Check size={16} />}
      <span>{status.message}</span>
    </div>
  );
}

function MetaField({ icon, label, value, onChange }) {
  return (
    <label className="metaField">
      <span>{icon || label}</span>
      <small>{label}</small>
      <input value={value || ""} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function StepCard({ step, index, active, onSelect, onToggle, onTaskToggle }) {
  return (
    <article className={`stepCard ${step.done ? "done" : ""} ${active ? "active" : ""}`} onClick={onSelect}>
      <div className="stepRail">
        <button
          className="stepNo"
          onClick={(event) => {
            event.stopPropagation();
            onToggle(!step.done);
          }}
          title={step.done ? "標記未完成" : "標記完成"}
        >
          {step.done ? <Check size={20} /> : step.number}
        </button>
      </div>
      <div className="stepBody">
        <div className="stepHead">
          <div>
            <h2>{step.title}</h2>
            <p>{step.flow}</p>
          </div>
          <span>{step.focus}</span>
        </div>
        <div className="taskList">
          {step.tasks.map((task, taskIndex) => (
            <label key={task.id} className={task.done ? "checked taskLine" : "taskLine"} onClick={(event) => event.stopPropagation()}>
              <input type="checkbox" checked={task.done} onChange={(event) => onTaskToggle(taskIndex, event.target.checked)} />
              <span>{task.text}</span>
            </label>
          ))}
        </div>
        {step.notes ? <pre>{step.notes}</pre> : null}
      </div>
    </article>
  );
}

function Field({ label, value, onChange, multi = false }) {
  return (
    <label className="field">
      <span>{label}</span>
      {multi ? (
        <textarea value={value || ""} onChange={(event) => onChange(event.target.value)} />
      ) : (
        <input value={value || ""} onChange={(event) => onChange(event.target.value)} />
      )}
    </label>
  );
}

function EditableCheck({ item, onToggle, onChange }) {
  const rows = Math.min(5, Math.max(1, Math.ceil((item.text || "").length / 22)));
  return (
    <label className={`editableCheck ${item.done ? "done" : ""}`}>
      <input type="checkbox" checked={item.done} onChange={(event) => onToggle(event.target.checked)} />
      <textarea value={item.text} onChange={(event) => onChange(event.target.value)} rows={rows} />
    </label>
  );
}

function notionLabel(status) {
  const labels = {
    synced: "已同步",
    exported: "已匯出待同步",
    failed_exported: "同步失敗，已保留匯出",
    not_configured: "尚未設定",
    not_synced: "尚未同步",
  };
  return labels[status] || "待同步";
}

function mergeProjectsByUpdatedAt(current, incoming) {
  const localById = new Map(current.map((project) => [project.id, project]));
  return incoming.map((remote) => {
    const local = localById.get(remote.id);
    if (!local) return remote;
    return Date.parse(local.updatedAt || 0) > Date.parse(remote.updatedAt || 0) ? local : remote;
  });
}

createRoot(document.getElementById("root")).render(<App />);
