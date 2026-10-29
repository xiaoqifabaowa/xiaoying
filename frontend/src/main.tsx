import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Alert,
  Button,
  ConfigProvider,
  Drawer,
  Empty,
  Input,
  Select,
  Spin,
  Tag,
  Tooltip,
  message,
} from "antd";
import {
  ArrowUpOutlined,
  BookOutlined,
  CheckCircleOutlined,
  DownloadOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  MessageOutlined,
  PlusOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import type {
  Answer,
  Citation,
  Conversation,
  Document,
  Run,
  Scenario,
  Trace,
} from "./types";
import "./style.css";

const labels: Record<string, string> = {
  answered: "已核验回答",
  needs_clarification: "等待补充",
  conflict_unresolved: "制度存在冲突",
  insufficient_evidence: "资料不足",
  incomplete: "尚未完成",
  failed: "运行失败",
  queued: "等待运行",
  running: "正在查证",
};
const colors: Record<string, string> = {
  answered: "green",
  conflict_unresolved: "orange",
  failed: "red",
  incomplete: "gold",
  insufficient_evidence: "default",
  needs_clarification: "blue",
};
async function api<T>(url: string, body?: unknown): Promise<T> {
  const r = await fetch(
    "/api" + url,
    body === undefined
      ? undefined
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  if (!r.ok) {
    const e = await r.json().catch(() => ({}));
    throw new Error(
      typeof e.detail === "string" ? e.detail : `请求失败 (${r.status})`,
    );
  }
  return r.json();
}

function App() {
  const [page, setPage] = useState("chat");
  const [mode, setMode] = useState<"live" | "mock">("live");
  const [scenario, setScenario] = useState("normal");
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [cid, setCid] = useState<string>();
  const [runs, setRuns] = useState<Run[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [trace, setTrace] = useState<Trace[]>([]);
  const [selected, setSelected] = useState<Run>();
  const [tab, setTab] = useState("evidence");
  const [documents, setDocuments] = useState<Document[]>([]);
  const [docFilter, setDocFilter] = useState("");
  const [opened, setOpened] = useState<{ doc: Document; quote?: string }>();
  const [configured, setConfigured] = useState(false);
  const [mobileTrace, setMobileTrace] = useState(false);
  const [msg, contextHolder] = message.useMessage();
  const bottom = useRef<HTMLDivElement>(null);
  const stream = useRef<EventSource | null>(null);
  const activeId = useRef<string | undefined>(undefined);

  const refresh = async () =>
    setConversations(await api<Conversation[]>("/conversations"));
  useEffect(() => {
    Promise.all([
      refresh(),
      api<Scenario[]>("/scenarios").then(setScenarios),
      api<{ live_configured: boolean }>("/health").then((h) =>
        setConfigured(h.live_configured),
      ),
    ]).catch((e) => msg.error(e.message));
    return () => stream.current?.close();
  }, []);
  useEffect(() => {
    api<{ documents: Document[] }>(`/documents?scenario=${scenario}`)
      .then((d) => setDocuments(d.documents))
      .catch((e) => msg.error(e.message));
  }, [scenario]);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [runs, busy]);

  async function inspect(run: Run) {
    setSelected(run);
    const text = await fetch(`/api/runs/${run.id}/trace`).then((r) => {
      if (!r.ok) throw new Error("无法读取执行记录");
      return r.text();
    });
    if (activeId.current === run.id || !activeId.current)
      setTrace(
        text.trim()
          ? text
              .trim()
              .split("\n")
              .map((s) => JSON.parse(s))
          : [],
      );
  }
  async function loadConversation(id: string) {
    if (busy) return;
    const c = await api<Conversation>(`/conversations/${id}`);
    setCid(id);
    setRuns(c.runs || []);
    setPage("chat");
    setTrace([]);
    setSelected(undefined);
    const latest = c.runs?.at(-1);
    if (latest) {
      setScenario(latest.scenario);
      setMode(latest.mode as "live" | "mock");
      await inspect(latest);
      if (!latest.result) {
        setBusy(true);
        try {
          await observe(latest);
        } finally {
          setBusy(false);
        }
      }
    }
  }
  function newChat() {
    if (busy) return;
    setCid(undefined);
    setRuns([]);
    setTrace([]);
    setSelected(undefined);
    setQuestion("");
    setPage("chat");
  }

  function observe(run: Run): Promise<Run> {
    activeId.current = run.id;
    return new Promise((resolve, reject) => {
      const source = new EventSource(`/api/runs/${run.id}/events`);
      stream.current = source;
      source.onmessage = (e) => {
        const v = JSON.parse(e.data);
        setTrace((t) =>
          t.some((x) => x.sequence === v.sequence) ? t : [...t, v],
        );
      };
      source.addEventListener("result", (e) => {
        const done = JSON.parse((e as MessageEvent).data) as Run;
        source.close();
        activeId.current = undefined;
        setRuns((rs) => rs.map((r) => (r.id === done.id ? done : r)));
        setSelected(done);
        refresh().catch(() => {});
        resolve(done);
      });
      source.onerror = () => {
        source.close();
        activeId.current = undefined;
        reject(
          new Error("事件连接中断；任务可能仍在运行，可重新打开会话查看。"),
        );
      };
    });
  }
  async function execute(
    q: string,
    conversationId: string,
    scenarioId: string,
  ) {
    const run = await api<Run>(`/conversations/${conversationId}/runs`, {
      question: q,
      mode,
      scenario: scenarioId,
    });
    setRuns((rs) => [...rs, run]);
    setSelected(run);
    setTrace([]);
    setTab("trace");
    const done = await observe(run);
    setTab("evidence");
    return done;
  }
  async function send(preset?: Scenario) {
    const q = preset?.question || question.trim();
    if (!q || busy) return;
    setBusy(true);
    setQuestion("");
    setPage("chat");
    try {
      let id = preset ? undefined : cid;
      if (!id) {
        const c = await api<Conversation>("/conversations", {});
        id = c.id;
        setCid(id);
        setRuns([]);
      }
      const s = preset?.id || scenario;
      if (preset) setScenario(s);
      if (preset?.history_question)
        await execute(preset.history_question, id, s);
      await execute(q, id, s);
    } catch (e) {
      msg.error((e as Error).message);
    } finally {
      setBusy(false);
      refresh().catch(() => {});
    }
  }
  async function showCitation(c: Citation, answer: Answer) {
    try {
      const doc = await api<Document>(
        `/documents/${encodeURIComponent(c.doc_id)}?dataset_version=${encodeURIComponent(answer.dataset_version)}`,
      );
      setOpened({ doc, quote: c.quote });
    } catch (e) {
      msg.error((e as Error).message);
    }
  }
  const result = selected?.result;
  const currentScenario = scenarios.find((s) => s.id === scenario);
  return (
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: "#167365",
          borderRadius: 10,
          fontFamily: 'Inter, "Microsoft YaHei", sans-serif',
          colorText: "#253b37",
        },
      }}
    >
      {contextHolder}
      <div className="app-shell">
        <aside className="sidebar">
          <div className="brand">
            <div className="brand-mark">知</div>
            <div>
              <strong>知据</strong>
              <span>EVIDENCE WORKSPACE</span>
            </div>
          </div>
          <div className="nav-caption">工作空间</div>
          {[
            ["chat", "知识问答", <MessageOutlined />],
            ["library", "知识库", <BookOutlined />],
            ["evaluation", "评审用例", <ExperimentOutlined />],
          ].map(([id, title, icon]) => (
            <button
              key={String(id)}
              aria-label={String(title)}
              className={`nav-item ${page === id ? "active" : ""}`}
              onClick={() => setPage(String(id))}
            >
              {icon}
              <span>{title}</span>
              {page === id && <i />}
            </button>
          ))}
          <div className="sidebar-divider" />
          <div className="history-heading">
            <span>最近会话</span>
            <button aria-label="新建会话" disabled={busy} onClick={newChat}>
              <PlusOutlined />
            </button>
          </div>
          <div className="history-list">
            {conversations.length === 0 ? (
              <p className="muted">你的查证记录将保存在这里</p>
            ) : (
              conversations.map((c) => (
                <button
                  disabled={busy}
                  title={c.title}
                  className={`history-item ${cid === c.id ? "chosen" : ""}`}
                  key={c.id}
                  onClick={() =>
                    loadConversation(c.id).catch((e) => msg.error(e.message))
                  }
                >
                  <MessageOutlined />
                  {c.title}
                </button>
              ))
            )}
          </div>
          <div className="sidebar-foot">
            <span className="status-dot" />
            <div>
              本地知识工作台<small>合成资料 · 可追溯回答</small>
            </div>
            <span className="version">v0.1</span>
          </div>
        </aside>
        <main className="main">
          <header className="topbar">
            <div className="breadcrumb">
              工作空间 <span>/</span>{" "}
              <b>
                {page === "chat"
                  ? "知识问答"
                  : page === "library"
                    ? "知识库"
                    : "评审用例"}
              </b>
            </div>
            <div className="top-controls">
              <span className="model-name">DeepSeek V4 Pro</span>
              <Select
                aria-label="运行模式"
                value={mode}
                disabled={busy}
                onChange={setMode}
                options={[
                  { value: "live", label: "● 真实模型" },
                  { value: "mock", label: "◌ 离线 Mock" },
                ]}
              />
            </div>
          </header>
          {mode === "mock" && (
            <Alert
              banner
              type="warning"
              message="离线 Mock：脚本只验证流程，不证明真实模型决策与语义审核效果。"
            />
          )}
          {mode === "live" && !configured && (
            <Alert
              banner
              type="warning"
              message="尚未配置 DeepSeek 密钥。请在本地 .env 配置后重启，或主动选择离线 Mock。"
            />
          )}
          {page === "chat" ? (
            <div className="workbench">
              <section className="chat-pane">
                <div className="chat-toolbar">
                  <div>
                    <span className="eyebrow">KNOWLEDGE ASSISTANT</span>
                    <h2>让每个答案，都有据可查。</h2>
                  </div>
                  <Tooltip title="开始新会话">
                    <Button
                      icon={<PlusOutlined />}
                      disabled={busy}
                      onClick={newChat}
                    />
                  </Tooltip>
                </div>
                <div className="messages">
                  {runs.length === 0 ? (
                    <div className="welcome">
                      <div className="welcome-emblem">
                        <BookOutlined />
                      </div>
                      <h1>从一个问题，找到可靠依据</h1>
                      <p>
                        查找企业制度与产品资料，核验原文。
                        <br />
                        遇到资料缺口或冲突，我们会明确告诉你。
                      </p>
                      <div className="suggestions">
                        {scenarios.slice(0, 4).map((s) => (
                          <button
                            key={s.id}
                            onClick={() => {
                              setScenario(s.id);
                              setQuestion(s.question);
                            }}
                          >
                            <span>{s.title}</span>
                            <b>{s.question}</b>
                            <span className="suggestion-arrow">↗</span>
                          </button>
                        ))}
                      </div>
                      <div className="trust-line">
                        <CheckCircleOutlined /> 引用可核验 <span>·</span>{" "}
                        冲突不猜测 <span>·</span> 过程可追溯
                      </div>
                    </div>
                  ) : (
                    runs.map((run) => (
                      <article className="exchange" key={run.id}>
                        <div className="user-question">
                          <span className="avatar user-avatar">你</span>
                          <div>{run.question}</div>
                        </div>
                        <div
                          className={`assistant-answer ${selected?.id === run.id ? "selected-answer" : ""}`}
                        >
                          <div className="answer-header">
                            <span className="avatar agent-avatar">知</span>
                            <b>知据</b>
                            <Tag
                              color={run.mode === "mock" ? "orange" : "cyan"}
                            >
                              {run.mode === "mock" ? "MOCK" : "LIVE"}
                            </Tag>
                            <Tag
                              color={colors[run.result?.status || run.status]}
                            >
                              {labels[run.result?.status || run.status]}
                            </Tag>
                          </div>
                          {run.result ? (
                            <>
                              <div className="answer-text">
                                {run.result.answer}
                              </div>
                              {!!run.result.conflicts.length && (
                                <div className="conflict-box">
                                  <b>需要确认的制度冲突</b>
                                  {run.result.conflicts.map((c, i) => (
                                    <p key={i}>{c.explanation}</p>
                                  ))}
                                </div>
                              )}
                              {run.result.citations.length > 0 && (
                                <div className="inline-citations">
                                  {run.result.citations.map((c, i) => (
                                    <button
                                      key={i}
                                      onClick={() =>
                                        showCitation(c, run.result!)
                                      }
                                    >
                                      <FileTextOutlined />
                                      {c.doc_id}
                                      <span>{c.version_date}</span>
                                    </button>
                                  ))}
                                </div>
                              )}
                              {!!run.result.knowledge_gaps.length && (
                                <div className="gaps">
                                  <b>资料缺口</b>{" "}
                                  {run.result.knowledge_gaps.join("；")}
                                </div>
                              )}
                              {run.result.clarification && (
                                <div className="clarification">
                                  {run.result.clarification}
                                </div>
                              )}
                              <div className="answer-footer">
                                <span>
                                  {run.result.tool_calls ?? "—"} 次工具调用 ·{" "}
                                  {run.result.steps ?? "—"} 次模型调用
                                </span>
                                <button
                                  onClick={() => {
                                    inspect(run).catch((e) =>
                                      msg.error(e.message),
                                    );
                                    setTab("trace");
                                    if (window.innerWidth <= 900)
                                      setMobileTrace(true);
                                  }}
                                >
                                  查看查证过程 ↗
                                </button>
                              </div>
                            </>
                          ) : (
                            <div className="thinking">
                              <Spin size="small" /> 正在检索资料、核验依据…
                            </div>
                          )}
                        </div>
                      </article>
                    ))
                  )}
                  <div ref={bottom} />
                </div>
                <div className="composer-wrap">
                  <div className="scenario-selector">
                    <span>资料场景</span>
                    <Select
                      aria-label="资料场景"
                      value={scenario}
                      disabled={busy}
                      onChange={setScenario}
                      options={scenarios.map((s) => ({
                        value: s.id,
                        label: s.title,
                      }))}
                    />
                    <span className="scenario-help">
                      {currentScenario?.description}
                    </span>
                  </div>
                  <div className="composer">
                    <Input.TextArea
                      aria-label="输入问题"
                      placeholder="询问制度、流程或产品问题…"
                      autoSize={{ minRows: 2, maxRows: 5 }}
                      value={question}
                      disabled={busy}
                      onChange={(e) => setQuestion(e.target.value)}
                      onPressEnter={(e) => {
                        if (!e.shiftKey && !e.nativeEvent.isComposing) {
                          e.preventDefault();
                          send();
                        }
                      }}
                    />
                    <div className="composer-bottom">
                      <span>Enter 发送 · Shift + Enter 换行</span>
                      <Button
                        aria-label="发送问题"
                        type="primary"
                        icon={<ArrowUpOutlined />}
                        loading={busy}
                        disabled={!question.trim()}
                        onClick={() => send()}
                      />
                    </div>
                  </div>
                  <p className="composer-note">
                    回答仅依据当前合成资料。引用和适用范围请一并查看。
                  </p>
                </div>
              </section>
              <aside className="evidence-pane">
                <div className="evidence-tabs">
                  <button
                    className={tab === "evidence" ? "tab-active" : ""}
                    onClick={() => setTab("evidence")}
                  >
                    参考依据 <span>{result?.citations.length || 0}</span>
                  </button>
                  <button
                    className={tab === "trace" ? "tab-active" : ""}
                    onClick={() => setTab("trace")}
                  >
                    执行记录 <span>{trace.length}</span>
                  </button>
                </div>
                {tab === "evidence" ? (
                  <div className="evidence-content">
                    {result?.citations.length ? (
                      <>
                        <p className="panel-note">
                          以下原文支撑本次回答，点击查看完整文档。
                        </p>
                        {result.citations.map((c, i) => (
                          <button
                            className="evidence-card"
                            key={i}
                            onClick={() => showCitation(c, result)}
                          >
                            <div>
                              <span className="doc-number">
                                {String(i + 1).padStart(2, "0")}
                              </span>
                              <b>{c.doc_id}</b>
                              <FileTextOutlined />
                            </div>
                            <blockquote>{c.quote}</blockquote>
                            <footer>
                              {c.version_date}
                              <span>查看原文 ↗</span>
                            </footer>
                          </button>
                        ))}
                        <div className="snapshot">
                          <CheckCircleOutlined /> 已绑定资料快照
                          <code>{result.dataset_version}</code>
                        </div>
                      </>
                    ) : (
                      <div className="panel-empty">
                        <FileTextOutlined />
                        <h3>答案背后的依据</h3>
                        <p>
                          提问后，引用的文档与原文片段
                          <br />
                          将在这里展示。
                        </p>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="trace-content">
                    {selected && (
                      <a
                        className="download"
                        href={`/api/runs/${selected.id}/trace`}
                      >
                        <DownloadOutlined /> 下载完整 Trace
                      </a>
                    )}
                    {trace.length === 0 ? (
                      <Empty
                        image={Empty.PRESENTED_IMAGE_SIMPLE}
                        description="暂无执行记录"
                      />
                    ) : (
                      <ol className="trace-list">
                        {trace.map((e) => (
                          <li key={e.sequence}>
                            <div className="trace-dot" />
                            <div>
                              <small>
                                STEP {String(e.sequence).padStart(2, "0")}
                              </small>
                              <b>
                                {e.kind === "decision"
                                  ? {
                                      search_documents: "检索文档",
                                      read_document: "读取原文",
                                      finish: "提交回答",
                                      ask_user: "请求澄清",
                                    }[e.action!] || e.action
                                  : {
                                      started: "开始查证",
                                      tool: "工具返回",
                                      audit: "证据审核",
                                      validation: "校验反馈",
                                      model_error: "模型错误",
                                      completed: "运行结束",
                                    }[e.kind] || e.kind}
                              </b>
                              <p>
                                {e.reason ||
                                  e.summary ||
                                  e.code ||
                                  (e.kind === "audit"
                                    ? e.supported
                                      ? "审核通过"
                                      : "审核未通过"
                                    : labels[e.status || ""])}
                              </p>
                              {!!e.arguments && (
                                <details>
                                  <summary>参数与返回</summary>
                                  <pre>
                                    {JSON.stringify(
                                      {
                                        arguments: e.arguments,
                                        output: e.output,
                                      },
                                      null,
                                      2,
                                    )}
                                  </pre>
                                </details>
                              )}
                              {e.issues?.length ? (
                                <p>{e.issues.join("；")}</p>
                              ) : null}
                            </div>
                          </li>
                        ))}
                      </ol>
                    )}
                  </div>
                )}
              </aside>
            </div>
          ) : page === "library" ? (
            <section className="page-content">
              <span className="eyebrow">KNOWLEDGE LIBRARY</span>
              <h1>每一条知识，都有出处</h1>
              <p className="page-description">
                合成制度与 FAQ，可按当前场景查看内容与适用范围。
              </p>
              <div className="library-controls">
                <Input
                  prefix={<SearchOutlined />}
                  placeholder="搜索标题或文档 ID"
                  value={docFilter}
                  onChange={(e) => setDocFilter(e.target.value)}
                />
                <Select
                  aria-label="知识库场景"
                  value={scenario}
                  onChange={setScenario}
                  options={scenarios.map((s) => ({
                    value: s.id,
                    label: s.title,
                  }))}
                />
              </div>
              <div className="document-grid">
                {documents
                  .filter((d) => (d.title + d.doc_id).includes(docFilter))
                  .map((d) => (
                    <button
                      className="document-card"
                      key={d.doc_id}
                      onClick={() => setOpened({ doc: d })}
                    >
                      <div className="document-icon">
                        <FileTextOutlined />
                      </div>
                      <Tag>{d.doc_id}</Tag>
                      <h3>{d.title}</h3>
                      <p>{d.content.slice(0, 65)}…</p>
                      <footer>
                        <span>{d.version_date}</span>
                        <span>阅读原文 ↗</span>
                      </footer>
                      <div className="scope-label">
                        适用范围：{d.scope || "资料未明确"}
                      </div>
                    </button>
                  ))}
              </div>
            </section>
          ) : (
            <section className="page-content">
              <span className="eyebrow">EVALUATION LAB</span>
              <h1>用真实路径，检验回答质量</h1>
              <p className="page-description">
                覆盖题目验收点。每次运行建立独立会话，保留输入、证据与完整执行记录。
              </p>
              <div className="evaluation-banner">
                <ExperimentOutlined />
                <div>
                  <b>评审关注行为与证据</b>
                  <p>
                    运行结果由工具与模型实时产生；下方“预期”用于核对，不代表已通过测试。
                  </p>
                </div>
                <Tag color={mode === "live" ? "cyan" : "orange"}>
                  {mode === "live" ? "真实模型评审" : "Mock 流程演示"}
                </Tag>
              </div>
              <div className="scenario-grid">
                {scenarios.map((s, i) => (
                  <div className="scenario-card" key={s.id}>
                    <div className="scenario-card-top">
                      <span>CASE {String(i + 1).padStart(2, "0")}</span>
                      <Tag>{labels[s.expected]}</Tag>
                    </div>
                    <h3>{s.title}</h3>
                    <p>{s.description}</p>
                    <div className="scenario-question">“{s.question}”</div>
                    <Button disabled={busy} onClick={() => send(s)}>
                      运行场景 ↗
                    </Button>
                  </div>
                ))}
              </div>
            </section>
          )}
        </main>
      </div>
      <Drawer
        title="执行记录"
        open={mobileTrace}
        onClose={() => setMobileTrace(false)}
        width="100%"
      >
        {selected && (
          <a href={`/api/runs/${selected.id}/trace`}>下载完整 Trace</a>
        )}
        {trace.map((e) => (
          <div className="source-paragraph" key={e.sequence}>
            <small>
              STEP {e.sequence} · {e.kind}
            </small>
            {e.reason || e.summary || e.code || e.status || "—"}
          </div>
        ))}
      </Drawer>
      <Drawer
        title={opened ? `${opened.doc.doc_id} · ${opened.doc.title}` : ""}
        width={570}
        open={!!opened}
        onClose={() => setOpened(undefined)}
      >
        {opened && (
          <>
            <div className="document-meta">
              <Tag>版本 {opened.doc.version_date}</Tag>
              <Tag>适用范围：{opened.doc.scope || "未明确"}</Tag>
            </div>
            {opened.doc.chunks.map((ch) => (
              <p
                className={`source-paragraph ${opened.quote && ch.text.includes(opened.quote) ? "highlighted" : ""}`}
                key={ch.chunk_id}
              >
                <small>{ch.chunk_id}</small>
                {ch.text}
              </p>
            ))}
            <Alert
              type="info"
              message="此处展示引用所绑定的文档内容；版本日期不等同于制度优先级。"
            />
          </>
        )}
      </Drawer>
    </ConfigProvider>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
