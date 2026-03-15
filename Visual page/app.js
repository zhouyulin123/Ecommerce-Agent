const stageLabels = {
  supervisor: "任务理解",
  planner: "任务规划",
  executor: "任务调度",
  data_agent: "数据智能体",
  writing_agent: "写作智能体",
  creative_agent: "创意智能体",
  response: "结果汇总",
};

const quickMessageFallback = "上海地区最近谁在关注羊毛衫，顺便生成一版文案和海报";
const SESSION_STORAGE_KEY = "marketing-workbench-sessions";
const ACTIVE_SESSION_STORAGE_KEY = "marketing-workbench-active-session-id";

const state = {
  activeSessionId: restoreActiveSessionId(),
  sessions: restoreSessionMetas(),
  sessionStore: {},
  health: null,
};

const els = {
  sessionInput: document.getElementById("session-id-input"),
  loadSessionBtn: document.getElementById("load-session-btn"),
  newSessionBtn: document.getElementById("new-session-btn"),
  sessionList: document.getElementById("session-list"),
  sessionCount: document.getElementById("session-count"),
  healthLlm: document.getElementById("health-llm"),
  healthImage: document.getElementById("health-image"),
  healthTextModel: document.getElementById("health-text-model"),
  healthImageModel: document.getElementById("health-image-model"),
  requestCount: document.getElementById("request-count"),
  messageList: document.getElementById("message-list"),
  chatForm: document.getElementById("chat-form"),
  messageInput: document.getElementById("message-input"),
  composerStatus: document.getElementById("composer-status"),
  traceBadge: document.getElementById("trace-badge"),
  timeline: document.getElementById("timeline"),
  queryPlanCard: document.getElementById("query-plan-card"),
  queryModeBadge: document.getElementById("query-mode-badge"),
  audienceCard: document.getElementById("audience-card"),
  audienceCountBadge: document.getElementById("audience-count-badge"),
  copyCard: document.getElementById("copy-card"),
  copyBadge: document.getElementById("copy-badge"),
  creativeCard: document.getElementById("creative-card"),
  creativeBadge: document.getElementById("creative-badge"),
  memoryCard: document.getElementById("memory-card"),
  timelineTemplate: document.getElementById("timeline-item-template"),
};

ensureActiveSession();
bindEvents();
renderAll();
loadHealth();
loadSessionList();
loadSession(state.activeSessionId, { silent: true });

function bindEvents() {
  els.chatForm.addEventListener("submit", handleSubmit);
  els.loadSessionBtn.addEventListener("click", () => {
    const raw = els.sessionInput.value.trim();
    if (!raw) {
      setComposerStatus("请输入会话 ID 再加载。", true);
      return;
    }
    activateSession(raw, { ensureMeta: true });
    loadSession(raw);
  });
  els.newSessionBtn.addEventListener("click", createNewSession);
  document.querySelectorAll(".quick-chip").forEach((button) => {
    button.addEventListener("click", () => {
      els.messageInput.value = button.dataset.message || quickMessageFallback;
      els.messageInput.focus();
    });
  });
}

function currentSessionState() {
  return ensureSessionState(state.activeSessionId);
}

function ensureSessionState(sessionId) {
  if (!state.sessionStore[sessionId]) {
    state.sessionStore[sessionId] = {
      messages: [
        {
          role: "assistant",
          content: "输入营销任务，我会展示规划、执行步骤、工具调用和产出结果。",
        },
      ],
      latestResponse: null,
      loading: false,
      pendingRequestId: null,
      loaded: false,
    };
  }
  return state.sessionStore[sessionId];
}

async function handleSubmit(event) {
  event.preventDefault();
  const message = els.messageInput.value.trim();
  const sessionId = state.activeSessionId;
  const sessionState = currentSessionState();
  if (!message) {
    return;
  }
  if (sessionState.loading) {
    setComposerStatus("当前会话仍在执行，请切换到其它会话或等待完成。", true);
    return;
  }

  const requestId = createSessionId();
  sessionState.loading = true;
  sessionState.pendingRequestId = requestId;
  sessionState.messages.push({ role: "user", content: message });
  updateSessionMeta(sessionId, {
    title: summarizeSessionTitle(message),
    preview: message,
    updatedAt: new Date().toISOString(),
  });
  els.messageInput.value = "";
  setComposerStatus(`会话 ${shortSessionId(sessionId)} 正在执行任务...`, false);
  renderAll();

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: sessionId }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || payload.error || "请求失败");
    }

    const targetSessionId = payload.session_id || sessionId;
    const targetSessionState = ensureSessionState(targetSessionId);
    if (targetSessionState.pendingRequestId !== requestId) {
      return;
    }

    targetSessionState.latestResponse = payload;
    targetSessionState.messages.push({ role: "assistant", content: payload.reply || "系统未返回回复。" });
    targetSessionState.loading = false;
    targetSessionState.pendingRequestId = null;
    targetSessionState.loaded = true;

    updateSessionMeta(targetSessionId, {
      title: summarizeSessionTitle(message),
      preview: payload.reply || message,
      updatedAt: new Date().toISOString(),
    });

    if (state.activeSessionId === targetSessionId) {
      setComposerStatus("任务执行完成。", false);
    }
    renderAll();
  } catch (error) {
    const targetSessionState = ensureSessionState(sessionId);
    if (targetSessionState.pendingRequestId !== requestId) {
      return;
    }
    targetSessionState.messages.push({ role: "assistant", content: `请求失败：${error.message}` });
    targetSessionState.loading = false;
    targetSessionState.pendingRequestId = null;
    if (state.activeSessionId === sessionId) {
      setComposerStatus(`请求失败：${error.message}`, true);
    }
    renderAll();
  }
}

async function loadHealth() {
  try {
    const response = await fetch("/health");
    const payload = await response.json();
    state.health = payload;
    renderHealth();
  } catch (error) {
    els.healthLlm.textContent = "不可用";
    els.healthImage.textContent = "不可用";
    els.healthTextModel.textContent = "健康检查失败";
    els.healthImageModel.textContent = "健康检查失败";
  }
}

async function loadSessionList() {
  try {
    const response = await fetch("/api/sessions?limit=20");
    const payload = await response.json();
    const sessions = Array.isArray(payload.sessions) ? payload.sessions : [];
    sessions.forEach((item) => {
      updateSessionMeta(item.session_id, {
        title: summarizeSessionTitle(item.last_message || item.session_id),
        preview: item.last_message || "暂无消息",
        updatedAt: item.updated_at || new Date().toISOString(),
        messageCount: Number(item.message_count || 0),
      });
    });
    persistSessionMetas();
    renderSessionList();
  } catch (error) {
    renderSessionList();
  }
}

async function loadSession(sessionId, options = {}) {
  if (!sessionId) {
    return;
  }
  const sessionState = ensureSessionState(sessionId);
  if (sessionState.loading) {
    return;
  }
  try {
    const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`);
    const payload = await response.json();
    const targetSessionId = payload.session_id || sessionId;
    const targetSessionState = ensureSessionState(targetSessionId);
    const history = Array.isArray(payload.history) ? payload.history : [];
    targetSessionState.messages = history.length
      ? history
          .slice()
          .reverse()
          .map((item) => ({
            role: item.role === "user" ? "user" : "assistant",
            content: item.content || "",
          }))
      : [
          {
            role: "assistant",
            content: "当前会话暂无历史消息，可以直接开始新任务。",
          },
        ];
    targetSessionState.loaded = true;
    updateSessionMeta(targetSessionId, {
      updatedAt: new Date().toISOString(),
      messageCount: history.length,
      preview: history[0]?.content || "暂无消息",
    });
    if (!options.silent) {
      setComposerStatus("会话已加载。", false);
    }
    renderAll();
  } catch (error) {
    if (!options.silent) {
      setComposerStatus(`加载会话失败：${error.message}`, true);
    }
  }
}

function createNewSession() {
  const sessionId = createSessionId();
  activateSession(sessionId, { ensureMeta: true, focusInput: true });
  const sessionState = ensureSessionState(sessionId);
  sessionState.latestResponse = null;
  sessionState.messages = [
    {
      role: "assistant",
      content: "已创建新会话。这个会话可以独立发起任务，不会覆盖其它会话。",
    },
  ];
  sessionState.loading = false;
  sessionState.pendingRequestId = null;
  sessionState.loaded = true;
  updateSessionMeta(sessionId, {
    title: "新任务",
    preview: "等待输入任务",
    updatedAt: new Date().toISOString(),
    messageCount: 1,
  });
  els.messageInput.value = "";
  setComposerStatus("已切换到新会话。", false);
  renderAll();
}

function activateSession(sessionId, options = {}) {
  state.activeSessionId = sessionId;
  persistActiveSessionId(sessionId);
  ensureSessionState(sessionId);
  if (options.ensureMeta) {
    updateSessionMeta(sessionId, {
      title: "新任务",
      preview: "等待输入任务",
      updatedAt: new Date().toISOString(),
      messageCount: 0,
    });
  }
  if (options.focusInput) {
    els.messageInput.focus();
  }
  renderAll();
}

function ensureActiveSession() {
  if (!state.activeSessionId) {
    state.activeSessionId = createSessionId();
  }
  ensureSessionState(state.activeSessionId);
  updateSessionMeta(state.activeSessionId, {
    title: "当前任务",
    preview: "等待输入任务",
    updatedAt: new Date().toISOString(),
    messageCount: 0,
  });
  persistActiveSessionId(state.activeSessionId);
}

function renderAll() {
  els.sessionInput.value = state.activeSessionId;
  renderHealth();
  renderSessionList();
  renderMessages();
  renderTimeline();
  renderResultCards();
}

function renderHealth() {
  const health = state.health;
  if (!health) {
    return;
  }
  els.healthLlm.textContent = health.llm_enabled ? "可用" : "关闭";
  els.healthLlm.style.color = health.llm_enabled ? "var(--success)" : "var(--warning)";
  els.healthImage.textContent = health.image_enabled ? "可用" : "关闭";
  els.healthImage.style.color = health.image_enabled ? "var(--success)" : "var(--warning)";
  els.healthTextModel.textContent = health.text_model || "-";
  els.healthImageModel.textContent = health.image_model || "-";
}

function renderSessionList() {
  const sessions = state.sessions
    .slice()
    .sort((a, b) => new Date(b.updatedAt || 0).getTime() - new Date(a.updatedAt || 0).getTime());

  els.sessionCount.textContent = `${sessions.length} 个会话`;
  els.sessionList.innerHTML = "";
  if (!sessions.length) {
    const empty = document.createElement("div");
    empty.className = "session-list-empty";
    empty.textContent = "暂无会话";
    els.sessionList.appendChild(empty);
    return;
  }

  sessions.forEach((session) => {
    const sessionState = ensureSessionState(session.id);
    const item = document.createElement("button");
    item.type = "button";
    item.className = `session-item ${session.id === state.activeSessionId ? "active" : ""}`;
    item.innerHTML = `
      <div class="session-item-head">
        <strong>${escapeHtml(session.title || shortSessionId(session.id))}</strong>
        <span class="session-item-badge ${sessionState.loading ? "loading" : ""}">${sessionState.loading ? "执行中" : shortSessionId(session.id)}</span>
      </div>
      <div class="session-item-preview">${escapeHtml(session.preview || "暂无消息")}</div>
    `;
    item.addEventListener("click", () => {
      activateSession(session.id);
      if (!ensureSessionState(session.id).loaded) {
        loadSession(session.id, { silent: true });
      }
    });
    els.sessionList.appendChild(item);
  });
}

function renderMessages() {
  const sessionState = currentSessionState();
  const messages = sessionState.messages || [];
  els.requestCount.textContent = `${messages.length} 条消息`;
  els.messageList.innerHTML = "";
  messages.forEach((message) => {
    const node = document.createElement("div");
    node.className = `message ${message.role}`;
    node.innerHTML = `
      <div class="message-role">${message.role === "user" ? "你" : "系统"}</div>
      <div class="message-body"></div>
    `;
    node.querySelector(".message-body").textContent = message.content;
    els.messageList.appendChild(node);
  });
  els.messageList.scrollTop = els.messageList.scrollHeight;
}

function renderTimeline() {
  const response = currentSessionState().latestResponse;
  const steps = response?.execution_steps || [];
  const trace = response?.trace || [];
  const loading = currentSessionState().loading;
  els.traceBadge.textContent = loading ? "执行中" : trace.length ? `${trace.length} 个执行节点` : "等待执行";
  els.timeline.innerHTML = "";

  if (!steps.length) {
    const empty = document.createElement("div");
    empty.className = "timeline-empty";
    empty.textContent = loading ? "当前会话正在执行，结果返回后这里会展示步骤。" : "任务执行后，这里会显示 Planner 计划、Executor 调度和 Agent 输出。";
    els.timeline.appendChild(empty);
    return;
  }

  steps.forEach((step, index) => {
    const fragment = els.timelineTemplate.content.cloneNode(true);
    fragment.querySelector(".timeline-title").textContent = stageLabels[step.stage] || step.stage;
    fragment.querySelector(".timeline-index").textContent = `STEP ${String(index + 1).padStart(2, "0")}`;
    fragment.querySelector(".timeline-detail").textContent = formatStepDetail(step);
    els.timeline.appendChild(fragment);
  });
}

function renderResultCards() {
  renderQueryPlan();
  renderAudience();
  renderCopy();
  renderCreative();
  renderMemory();
}

function renderQueryPlan() {
  const plan = currentSessionState().latestResponse?.query_plan;
  els.queryPlanCard.innerHTML = "";
  els.queryModeBadge.textContent = plan?.query_mode || "未规划";

  if (!plan) {
    els.queryPlanCard.className = "definition-list empty-card";
    els.queryPlanCard.textContent = "暂无查询计划";
    return;
  }

  els.queryPlanCard.className = "definition-list";
  appendDefinition(els.queryPlanCard, "查询目标", plan.query_goal || "-");
  appendDefinition(els.queryPlanCard, "数据表", (plan.tables || []).join("、") || "-");
  appendDefinition(els.queryPlanCard, "行为范围", (plan.behavior_scope || []).join(" / ") || "-");
  appendDefinition(els.queryPlanCard, "筛选条件", formatFilterMap(plan.filters || {}));
  appendDefinition(els.queryPlanCard, "SQL 来源", plan.sql_source || "未使用");
}

function renderAudience() {
  const targetUsers = currentSessionState().latestResponse?.target_users || [];
  els.audienceCountBadge.textContent = `${targetUsers.length} 人`;
  if (!targetUsers.length) {
    els.audienceCard.className = "empty-card";
    els.audienceCard.textContent = "暂无人群结果";
    return;
  }

  const rows = targetUsers.slice(0, 8);
  els.audienceCard.className = "";
  els.audienceCard.innerHTML = `
    <table class="audience-table">
      <thead>
        <tr>
          <th>用户</th>
          <th>地区</th>
          <th>购买</th>
          <th>浏览</th>
        </tr>
      </thead>
      <tbody>
        ${rows
          .map(
            (row) => `
              <tr>
                <td>${escapeHtml(row.user_name || "-")}</td>
                <td>${escapeHtml(row.address || "-")}</td>
                <td>${row.buy_count ?? 0}</td>
                <td>${row.view_count ?? 0}</td>
              </tr>
            `,
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function renderCopy() {
  const copy = currentSessionState().latestResponse?.ad_copy;
  els.copyBadge.textContent = copy ? "已生成" : "未生成";
  if (!copy) {
    els.copyCard.className = "empty-card";
    els.copyCard.textContent = "暂无文案结果";
    return;
  }

  els.copyCard.className = "copy-block";
  els.copyCard.innerHTML = `
    <div class="copy-line"><strong>标题</strong><br>${escapeHtml(copy.title || "-")}</div>
    <div class="copy-line"><strong>副标题</strong><br>${escapeHtml(copy.subtitle || "-")}</div>
    <div class="copy-line"><strong>行动按钮</strong><br>${escapeHtml(copy.cta || "-")}</div>
  `;
}

function renderCreative() {
  const response = currentSessionState().latestResponse;
  const posterSpec = response?.poster_spec;
  const generatedImage = response?.generated_image;
  els.creativeBadge.textContent = generatedImage?.url || generatedImage?.local_path ? "图片已生成" : posterSpec ? "已生成海报方案" : "未生成";

  if (!posterSpec && !generatedImage) {
    els.creativeCard.className = "empty-card";
    els.creativeCard.textContent = "暂无海报或图片结果";
    return;
  }

  const styleKeywords = (posterSpec?.style_keywords || [])
    .map((item) => `<span class="json-chip">${escapeHtml(item)}</span>`)
    .join("");

  els.creativeCard.className = "creative-block";
  els.creativeCard.innerHTML = `
    ${posterSpec ? `<div class="creative-line"><strong>建议配色</strong><br>${escapeHtml(posterSpec.color_palette || "-")}</div>` : ""}
    ${posterSpec ? `<div class="creative-line"><strong>风格关键词</strong><br>${styleKeywords || "无"}</div>` : ""}
    ${posterSpec ? `<div class="creative-line"><strong>海报提示词</strong><br>${escapeHtml(posterSpec.poster_prompt || "-")}</div>` : ""}
    ${generatedImage?.url ? `<img class="image-preview" src="${generatedImage.url}" alt="生成图片预览">` : ""}
    ${generatedImage?.local_path ? `<div class="creative-line"><strong>本地文件</strong><br>${escapeHtml(generatedImage.local_path)}</div>` : ""}
  `;
}

function renderMemory() {
  const memory = currentSessionState().latestResponse?.memory;
  if (!memory) {
    els.memoryCard.className = "definition-list empty-card";
    els.memoryCard.textContent = "暂无记忆状态";
    return;
  }

  els.memoryCard.className = "definition-list";
  els.memoryCard.innerHTML = "";
  appendDefinition(els.memoryCard, "待确认产物", memory.pending_artifact || "无");
  appendDefinition(els.memoryCard, "上一轮实体", formatFilterMap(memory.last_entities || {}));
  appendDefinition(els.memoryCard, "偏好记忆", formatFilterMap(memory.preference_memory || {}));
}

function formatStepDetail(step) {
  const detail = { ...step };
  delete detail.stage;
  const lines = Object.entries(detail)
    .filter(([, value]) => value !== null && value !== "" && !(Array.isArray(value) && value.length === 0) && !(typeof value === "object" && !Array.isArray(value) && Object.keys(value).length === 0))
    .map(([key, value]) => `${translateStepKey(key)}：${formatValue(value)}`);
  return lines.join("\n") || "无详细信息";
}

function translateStepKey(key) {
  const mapping = {
    mode: "模式",
    intent_type: "意图",
    requested_tasks: "请求任务",
    entities: "识别实体",
    feedback: "反馈解析",
    tasks: "任务列表",
    execution_plan: "执行计划",
    query_plan: "查询计划",
    next_agent: "下一执行智能体",
    current_task: "当前任务",
    remaining_tasks: "剩余任务",
    dispatch_reason: "调度理由",
    selection_reason: "选择理由",
    task: "任务",
    tool_call: "工具调用",
    query_result: "查询结果",
    insight: "用户洞察",
    target_users: "目标人群",
    ad_copy: "文案结果",
    poster_spec: "海报方案",
    generated_image: "图片结果",
    error: "错误",
    reply_preview: "回复预览",
  };
  return mapping[key] || key;
}

function formatValue(value) {
  if (Array.isArray(value)) {
    return value.join(" -> ");
  }
  if (typeof value === "object" && value !== null) {
    return JSON.stringify(value, null, 2);
  }
  return String(value);
}

function appendDefinition(container, key, value) {
  const dt = document.createElement("dt");
  dt.textContent = key;
  const dd = document.createElement("dd");
  dd.textContent = value;
  container.append(dt, dd);
}

function formatFilterMap(obj) {
  const entries = Object.entries(obj || {}).filter(([, value]) => value !== null && value !== undefined && value !== "");
  return entries.length ? entries.map(([key, value]) => `${key}=${value}`).join("，") : "无";
}

function setComposerStatus(text, isError) {
  els.composerStatus.textContent = text;
  els.composerStatus.style.color = isError ? "var(--accent-deep)" : "var(--muted)";
}

function createSessionId() {
  if (window.crypto?.randomUUID) {
    return window.crypto.randomUUID();
  }
  return `session-${Date.now()}`;
}

function restoreActiveSessionId() {
  return window.localStorage.getItem(ACTIVE_SESSION_STORAGE_KEY) || "";
}

function persistActiveSessionId(sessionId) {
  window.localStorage.setItem(ACTIVE_SESSION_STORAGE_KEY, sessionId);
}

function restoreSessionMetas() {
  try {
    const raw = window.localStorage.getItem(SESSION_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function persistSessionMetas() {
  window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(state.sessions));
}

function updateSessionMeta(sessionId, patch) {
  const existing = state.sessions.find((item) => item.id === sessionId);
  if (existing) {
    Object.assign(existing, patch);
  } else {
    state.sessions.push({
      id: sessionId,
      title: patch.title || shortSessionId(sessionId),
      preview: patch.preview || "暂无消息",
      updatedAt: patch.updatedAt || new Date().toISOString(),
      messageCount: patch.messageCount || 0,
    });
  }
  persistSessionMetas();
}

function shortSessionId(sessionId) {
  return String(sessionId || "").slice(0, 8) || "未命名";
}

function summarizeSessionTitle(text) {
  const normalized = String(text || "").replace(/\s+/g, " ").trim();
  return normalized ? normalized.slice(0, 18) : "新任务";
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
