const state = {
  projects: [],
  selectedProject: "",
  jobs: [],
  tableTab: "characters",
  mainTab: "characters",
  storyboardChapterTab: "",
  storyboardTableChapterTab: "",
  videoChapterTab: "",
  selectedVideoPath: "",
  selectedVideoFenjingId: "",
  autoSelectProject: false,
  pendingTab: "",
  savedProject: "",
  selectedFenjingId: "",
  selectedFenjingItem: null,
  selectedCandidatePath: "",
  selectedCharacterId: "",
  selectedCharacterItem: null,
  selectedCharacterCandidatePath: "",
  selectedClothChangedId: "",
  selectedClothChangedItem: null,
  selectedClothChangedCandidatePath: "",
  selectedLocationPath: "",
  assetsCache: null,
  assetStats: null,
  assetStatsLoading: false,
  jobsWithStats: [],
  jobsWithStatsLoading: false,
  statsActiveTab: "overview",
  failedAssetItems: {
    items: [],
    counts: {},
    activeFilter: "",
    jobId: "",
  },
  fenjingPromptCache: {},
  fenjingPromptLoading: {},
  videoPromptCache: {},
  videoPromptLoading: {},
  mediaVersion: 0,
  jobPolling: {},
  configItems: [],
  configGlobalItems: [],
  authItems: [],
  authGlobalItems: [],
  configScope: "project",
  autoStoryboardConfig: {},
  logPageCache: {},
  logPageLoading: {},
  flowStatus: null,
  flowTouched: {},
  flowStatusPolling: null,
};

const STAGE_TYPES = ["auto_storyboard", "visual_audio_assets", "fenjing_generate", "video"];
const JOB_CACHE_PREFIX = "manju_jobs_cache_";
const FLOW_TOUCHED_KEY = "manju_flow_touched";

function qs(id) {
  return document.getElementById(id);
}

async function apiGet(path) {
  const res = await fetch(path);
  if (!res.ok) {
    throw new Error(await res.text());
  }
  return res.json();
}

function getFlowStatus(flow) {
  if (!state.flowStatus || !state.flowStatus.flows) {
    return "";
  }
  const flowState = state.flowStatus.flows[flow];
  if (!flowState) {
    return "";
  }
  return flowState.status || "";
}

function getFlowStepStatus(flow, step) {
  if (!state.flowStatus || !state.flowStatus.flows) {
    return "";
  }
  const flowState = state.flowStatus.flows[flow];
  if (!flowState || !flowState.steps) {
    return "";
  }
  return flowState.steps[step] || "";
}

function getFlowActionLabel(flow, step) {
  const status = step ? getFlowStepStatus(flow, step) : getFlowStatus(flow);
  if (status === "completed") {
    return "重生";
  }
  if (status === "waiting" || status === "running") {
    return "执行";
  }
  return "运行";
}

async function apiPost(path, payload) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  if (!res.ok) {
    throw new Error(await res.text());
  }
  return res.json();
}

async function apiPatch(path, payload) {
  const res = await fetch(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  if (!res.ok) {
    throw new Error(await res.text());
  }
  return res.json();
}

function mediaUrl(path) {
  if (!path) {
    return "";
  }
  const base = `/media/${state.selectedProject}/${path}`;
  if (!state.mediaVersion) {
    return base;
  }
  return `${base}?v=${state.mediaVersion}`;
}

function bumpMediaVersion() {
  state.mediaVersion = Date.now();
}

function loadMainTabPreference() {
  const value = localStorage.getItem("manju.mainTab");
  return normalizeMainTab(value || "");
}

function saveMainTabPreference(tabName) {
  if (!tabName) {
    return;
  }
  localStorage.setItem("manju.mainTab", tabName);
}

function loadProjectPreference() {
  const value = localStorage.getItem("manju.project");
  return value || "";
}

function saveProjectPreference(projectName) {
  if (!projectName) {
    return;
  }
  localStorage.setItem("manju.project", projectName);
}

function normalizeMainTab(tabName) {
  const validTabs = new Set([
    "batch",
    "characters",
    "cloth-changed",
    "cloth",
    "locations",
    "storyboards",
    "videos",
    "tables",
  ]);
  return validTabs.has(tabName) ? tabName : "";
}

function loadUrlState() {
  const params = new URLSearchParams(window.location.search);
  return {
    project: params.get("project") || "",
    tab: normalizeMainTab(params.get("tab") || ""),
  };
}

function syncUrlState(usePush) {
  const params = new URLSearchParams();
  if (state.selectedProject) {
    params.set("project", state.selectedProject);
    if (state.mainTab) {
      params.set("tab", state.mainTab);
    }
  }
  const query = params.toString();
  const url = query ? `${window.location.pathname}?${query}` : window.location.pathname;
  if (usePush) {
    window.history.pushState(null, "", url);
  } else {
    window.history.replaceState(null, "", url);
  }
}

function parseJsonLines(text) {
  const items = [];
  String(text)
    .split("\n")
    .forEach((line) => {
      const trimmed = line.trim();
      if (!trimmed) {
        return;
      }
      try {
        items.push(JSON.parse(trimmed));
      } catch (err) {
        return;
      }
    });
  return items;
}

function parsePositiveIntValue(raw) {
  const num = Number(raw);
  if (!Number.isFinite(num) || num <= 0) {
    return null;
  }
  return Math.floor(num);
}

function buildAutoStoryboardPayload(config) {
  const payload = {};
  if (!config) {
    return payload;
  }
  if (config.chapter_size) {
    payload.chapter_size = config.chapter_size;
  }
  if (config.target_chapters) {
    payload.target_chapters = config.target_chapters;
  }
  if (config.per_chapter_shots) {
    payload.per_chapter_shots = config.per_chapter_shots;
  }
  if (config.previous_response_id) {
    payload.previous_response_id = config.previous_response_id;
  }
  return payload;
}

function buildAutoStoryboardConfigSection(initialConfig, options) {
  const settings = document.createElement("div");
  settings.className = "modal-settings";
  const fields = (options && options.fields) || [
    "chapter_size",
    "target_chapters",
    "per_chapter_shots"
  ];
  const chapterSizeInput = document.createElement("input");
  chapterSizeInput.type = "number";
  chapterSizeInput.min = "1";
  chapterSizeInput.placeholder = "例如 2500";
  const targetChaptersInput = document.createElement("input");
  targetChaptersInput.type = "number";
  targetChaptersInput.min = "1";
  targetChaptersInput.placeholder = "例如 12";
  const perChapterShotsInput = document.createElement("input");
  perChapterShotsInput.type = "number";
  perChapterShotsInput.min = "1";
  perChapterShotsInput.placeholder = "例如 8";
  const previousResponseInput = document.createElement("input");
  previousResponseInput.placeholder = "可选";
  const appendField = (labelText, inputEl, full) => {
    const field = document.createElement("div");
    field.className = full ? "modal-field full" : "modal-field";
    const label = document.createElement("div");
    label.className = "label";
    label.textContent = labelText;
    field.appendChild(label);
    field.appendChild(inputEl);
    settings.appendChild(field);
  };

  const fieldActions = {
    chapter_size: () => appendField("章节字数", chapterSizeInput, false),
    target_chapters: () => appendField("目标章节数", targetChaptersInput, false),
    per_chapter_shots: () => appendField("每章分镜数", perChapterShotsInput, false)
  };

  fields.forEach((field) => {
    const action = fieldActions[field];
    if (action) {
      action();
    }
  });

  const config = initialConfig || {};
  if (config.chapter_size) {
    chapterSizeInput.value = String(config.chapter_size);
  }
  if (config.target_chapters) {
    targetChaptersInput.value = String(config.target_chapters);
  }
  if (config.per_chapter_shots) {
    perChapterShotsInput.value = String(config.per_chapter_shots);
  }
  const getConfig = () => {
    const nextConfig = {};
    if (fields.includes("chapter_size")) {
      const value = parsePositiveIntValue(chapterSizeInput.value);
      if (value) {
        nextConfig.chapter_size = value;
      }
    }
    if (fields.includes("target_chapters")) {
      const value = parsePositiveIntValue(targetChaptersInput.value);
      if (value) {
        nextConfig.target_chapters = value;
      }
    }
    if (fields.includes("per_chapter_shots")) {
      const value = parsePositiveIntValue(perChapterShotsInput.value);
      if (value) {
        nextConfig.per_chapter_shots = value;
      }
    }
    return nextConfig;
  };

  return { settings, getConfig };
}

function openAutoStoryboardPhaseDialog(phase) {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "modal-backdrop";
    overlay.style.position = "fixed";
    overlay.style.inset = "0";
    overlay.style.display = "flex";
    overlay.style.alignItems = "center";
    overlay.style.justifyContent = "center";
    const card = document.createElement("div");
    card.className = "modal-card";
    const title = document.createElement("div");
    title.className = "modal-title";
    // 支持新的 step 命名和旧的 phase 命名
    const isStep2 = phase === "step_storyboard" || phase === "step2" || phase === "phase2";
    const isStep3 = phase === "step_upload" || phase === "step3_upload";
    title.textContent = isStep2 ? "运行步骤 2" : (isStep3 ? "上传资产" : "运行步骤 1");
    const fields = isStep2
      ? ["per_chapter_shots"]
    : ["chapter_size"];
    const configSection = buildAutoStoryboardConfigSection(state.autoStoryboardConfig || {}, { fields });
    const warning = document.createElement("div");
    warning.className = "status-inline warning";
    warning.textContent = "运行步骤 1 会删除已有拆解文件，请确认";
    const status = document.createElement("div");
    status.className = "status-inline hidden";
    const actions = document.createElement("div");
    actions.className = "modal-actions";
    const cancel = document.createElement("button");
    cancel.textContent = "取消";
    cancel.className = "button-secondary";
    const confirm = document.createElement("button");
    confirm.textContent = isStep2 ? "运行步骤 2" : (isStep3 ? "确认上传" : "确认并运行步骤 1");
    actions.appendChild(cancel);
    actions.appendChild(confirm);
    card.appendChild(title);
    // step3_upload 不需要配置参数
    if (!isStep3) {
      card.appendChild(configSection.settings);
    }
    if (!isStep2 && !isStep3) {
      card.appendChild(warning);
    }
    card.appendChild(status);
    card.appendChild(actions);
    overlay.appendChild(card);
    document.body.appendChild(overlay);
    const cleanup = () => {
      overlay.remove();
    };
    cancel.onclick = () => {
      cleanup();
      resolve(null);
    };
    overlay.onclick = (event) => {
      if (event.target === overlay) {
        cleanup();
        resolve(null);
      }
    };
    confirm.onclick = () => {
      const nextConfig = isStep3 ? {} : configSection.getConfig();
      state.autoStoryboardConfig = nextConfig;
      cleanup();
      resolve(nextConfig);
    };
  });
}

async function runAutoStoryboardPhase(phase) {
  const config = await openAutoStoryboardPhaseDialog(phase);
  if (!config) {
    return;
  }
  await submitFlowPhase("auto_storyboard", phase);
}

async function loadFenjingPromptMap(chapterName, chapterInfo) {
  if (!chapterName || !chapterInfo || !chapterInfo.fenjing_prompts) {
    return;
  }
  if (state.fenjingPromptCache[chapterName] || state.fenjingPromptLoading[chapterName]) {
    return;
  }
  state.fenjingPromptLoading[chapterName] = true;
  try {
    const res = await fetch(`/media/${state.selectedProject}/${chapterInfo.fenjing_prompts}`);
    if (!res.ok) {
      return;
    }
    const text = await res.text();
    const items = parseJsonLines(text);
    const promptMap = {};
    items.forEach((item) => {
      if (item && item.fenjing_id && item.prompt) {
        promptMap[String(item.fenjing_id)] = String(item.prompt);
      }
    });
    state.fenjingPromptCache[chapterName] = promptMap;
  } finally {
    state.fenjingPromptLoading[chapterName] = false;
  }
  if (state.assetsCache) {
    renderStoryboardsPanel(state.assetsCache);
  }
}

async function loadVideoPromptMap(chapterName, chapterInfo) {
  if (!chapterName || !chapterInfo || !chapterInfo.shipin_prompts) {
    return;
  }
  if (state.videoPromptCache[chapterName] || state.videoPromptLoading[chapterName]) {
    return;
  }
  state.videoPromptLoading[chapterName] = true;
  try {
    const res = await fetch(`/media/${state.selectedProject}/${chapterInfo.shipin_prompts}`);
    if (!res.ok) {
      return;
    }
    const text = await res.text();
    const items = parseJsonLines(text);
    const promptMap = {};
    items.forEach((item) => {
      if (item && item.fenjing_id && item.prompt) {
        promptMap[String(item.fenjing_id)] = String(item.prompt);
      }
    });
    state.videoPromptCache[chapterName] = promptMap;
  } finally {
    state.videoPromptLoading[chapterName] = false;
  }
  if (state.assetsCache) {
    renderVideosPanel(state.assetsCache);
  }
}

function renderProjects() {
  const container = qs("projectList");
  container.innerHTML = "";
  state.projects.forEach((name) => {
    const item = document.createElement("div");
    item.className = "list-item" + (state.selectedProject === name ? " active" : "");
    item.textContent = name;
    item.onclick = async () => {
      Object.values(state.jobPolling).forEach((timer) => clearInterval(timer));
      state.jobPolling = {};
      state.jobs = [];
      renderJobs();
      state.selectedProject = name;
      saveProjectPreference(name);
      state.autoStoryboardConfig = {};
      showProjectView();
      renderProjects();
      syncUrlState(true);
      await refreshAssets();
      await loadJobsForProject();
    };
    container.appendChild(item);
  });
}

function formatJobStatus(status) {
  if (status === "pending") {
    return "等待执行";
  }
  if (status === "running") {
    return "运行中";
  }
  if (status === "success") {
    return "成功";
  }
  if (status === "error") {
    return "失败";
  }
  return status || "未知";
}

function formatJobType(type) {
  const map = {
    run_auto_storyboard: "剧本拆解",
    run_visual_audio_assets: "角色与素材生成",
  run_fenjing: "分镜图生成",
  run_fenjing_generate: "分镜图生成",
  run_fenjing_upload: "上传分镜图",
  run_video: "视频生成",
    regenerate_character: "重生角色图",
    regenerate_cloth: "重生服装图",
    regenerate_cloth_changed: "重生换装图",
    regenerate_fenjing: "重生分镜图",
    regenerate_location_image: "重生地点图",
    regenerate_video: "重生视频",
  };
  return map[type] || type || "未知任务";
}

function formatJobTime(ts) {
  if (!ts) {
    return "";
  }
  return new Date(ts * 1000).toLocaleString();
}

function getFlowFromJob(job) {
  if (!job || !job.type || !String(job.type).startsWith("run_")) {
    return "";
  }
  const flow = String(job.type).replace("run_", "");
  if (STAGE_TYPES.includes(flow)) {
    return flow;
  }
  return "";
}

function getJobTimestamp(job) {
  if (!job) {
    return 0;
  }
  return job.updated_at || job.created_at || 0;
}

function mergeJobsById(jobs) {
  const map = {};
  (jobs || []).forEach((job) => {
    if (!job || !job.id) {
      return;
    }
    const existing = map[job.id];
    if (!existing || getJobTimestamp(job) >= getJobTimestamp(existing)) {
      map[job.id] = job;
    }
  });
  return Object.values(map);
}

function getJobCacheKey(project) {
  if (!project) {
    return "";
  }
  return `${JOB_CACHE_PREFIX}${project}`;
}

function loadJobCache(project) {
  const key = getJobCacheKey(project);
  if (!key) {
    return [];
  }
  try {
    const raw = localStorage.getItem(key);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter((job) => job && job.id);
  } catch (err) {
    return [];
  }
}

function saveJobCache(project, jobs) {
  const key = getJobCacheKey(project);
  if (!key) {
    return;
  }
  const cached = loadJobCache(project);
  const finished = (jobs || []).filter((job) => job && job.id && (job.status === "success" || job.status === "error"));
  const merged = mergeJobsById([...cached, ...finished]);
  localStorage.setItem(key, JSON.stringify(merged));
}

function clearJobCache(project) {
  const key = getJobCacheKey(project);
  if (!key) {
    return;
  }
  localStorage.removeItem(key);
}

function loadFlowTouchedMap() {
  try {
    const raw = localStorage.getItem(FLOW_TOUCHED_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") {
      return {};
    }
    return parsed;
  } catch (err) {
    return {};
  }
}

function saveFlowTouchedMap(map) {
  localStorage.setItem(FLOW_TOUCHED_KEY, JSON.stringify(map || {}));
}

function getFlowTouchedForProject(project) {
  if (!project) {
    return {};
  }
  if (!state.flowTouched[project]) {
    state.flowTouched[project] = {};
  }
  return state.flowTouched[project];
}

function isFlowTouched(project, flow) {
  if (!project || !flow) {
    return false;
  }
  return Boolean(getFlowTouchedForProject(project)[flow]);
}

function setFlowTouched(project, flow) {
  if (!project || !flow) {
    return;
  }
  const projectState = getFlowTouchedForProject(project);
  if (!projectState[flow]) {
    projectState[flow] = true;
    saveFlowTouchedMap(state.flowTouched);
  }
}

function clearFlowTouchedForProject(project) {
  if (!project) {
    return;
  }
  if (state.flowTouched[project]) {
    delete state.flowTouched[project];
    saveFlowTouchedMap(state.flowTouched);
  }
}

function cleanFlowTouchedByProjects(projects) {
  const next = {};
  (projects || []).forEach((name) => {
    if (state.flowTouched[name]) {
      next[name] = state.flowTouched[name];
    }
  });
  state.flowTouched = next;
  saveFlowTouchedMap(state.flowTouched);
}

function syncFlowTouchedFromFlowStatus(project) {
  if (!project || !state.flowStatus || !state.flowStatus.flows) {
    return;
  }
  Object.entries(state.flowStatus.flows).forEach(([flow, flowState]) => {
    const status = flowState && flowState.status ? String(flowState.status) : "";
    if (["pending", "running", "completed", "error", "partial_returned", "partial_completed"].includes(status)) {
      setFlowTouched(project, flow);
    }
  });
}

function syncFlowTouchedFromJobs(project, jobs) {
  (jobs || []).forEach((job) => {
    const flow = getFlowFromJob(job);
    if (flow) {
      setFlowTouched(project, flow);
    }
  });
}

function areAllFlowsWaiting(flowStatus) {
  const flows = flowStatus && flowStatus.flows ? flowStatus.flows : null;
  if (!flows || Object.keys(flows).length === 0) {
    return true;
  }
  return Object.values(flows).every((flowState) => flowState && flowState.status === "waiting");
}

function getLatestFlowJobs(jobs) {
  const result = {};
  (jobs || []).forEach((job) => {
    const flow = getFlowFromJob(job);
    if (!flow) {
      return;
    }
    const current = result[flow];
    if (!current || (job.updated_at || 0) > (current.updated_at || 0)) {
      result[flow] = job;
    }
  });
  return result;
}

function aggregateJobs(jobs) {
  const groups = {};
  (jobs || []).forEach((job) => {
    const flow = getFlowFromJob(job);
    if (!flow) {
      return;
    }
    if (!groups[flow]) {
      groups[flow] = {
        stageType: flow,
        latestJob: null,
        failedJobs: [],
        successCount: 0,
        hasPending: false,
      };
    }
    const group = groups[flow];
    if (job.status === "pending") {
      group.hasPending = true;
      if (!group.latestJob || group.latestJob.status !== "pending") {
        if (group.latestJob && group.latestJob.status !== "pending") {
          if (group.latestJob.status === "error") {
            group.failedJobs.push(group.latestJob);
          } else if (group.latestJob.status === "success") {
            group.successCount++;
          }
        }
        group.latestJob = job;
      }
      return;
    }
    if (!group.latestJob || (group.latestJob.status !== "pending" && (job.updated_at || 0) > (group.latestJob.updated_at || 0))) {
      if (group.latestJob && group.latestJob.status !== "pending") {
        if (group.latestJob.status === "error") {
          group.failedJobs.push(group.latestJob);
        } else if (group.latestJob.status === "success") {
          group.successCount++;
        }
      }
      group.latestJob = job;
    } else {
      if (job.status === "error") {
        group.failedJobs.push(job);
      } else if (job.status === "success") {
        group.successCount++;
      }
    }
  });
  return Object.values(groups)
    .filter((g) => g.latestJob)
    .sort((a, b) => {
      if (a.hasPending && !b.hasPending) return -1;
      if (!a.hasPending && b.hasPending) return 1;
      return (b.latestJob.updated_at || 0) - (a.latestJob.updated_at || 0);
    });
}

function parseStructuredLogLine(line) {
  if (!line || typeof line !== "string") {
    return null;
  }
  const trimmed = line.trim();
  if (!trimmed.startsWith("{") || !trimmed.endsWith("}")) {
    return null;
  }
  try {
    return JSON.parse(trimmed);
  } catch (err) {
    return null;
  }
}

function extractStructuredEvents(logs, flow) {
  const events = [];
  (logs || []).forEach((line) => {
    const parsed = parseStructuredLogLine(line);
    if (!parsed) {
      return;
    }
    if (flow && parsed.flow && parsed.flow !== flow) {
      return;
    }
    events.push(parsed);
  });
  return events;
}

function findLastEvent(events, predicate) {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    if (predicate(events[i])) {
      return events[i];
    }
  }
  return null;
}

function appendTreeAction(container, label, buttonLabel, onClick, options) {
  const row = document.createElement("div");
  row.className = "tree-action-row";
  const text = document.createElement("div");
  text.className = "tree-action-label";
  text.textContent = label;
  const btn = document.createElement("button");
  btn.className = "tree-action-btn";
  btn.textContent = buttonLabel || "重试";
  if (options && options.title) {
    btn.title = options.title;
  }
  if (options && options.disabled) {
    btn.disabled = true;
  }
  if (options && options.breathing) {
    btn.classList.add("status-breathing");
  }
  btn.onclick = onClick;
  row.appendChild(text);
  row.appendChild(btn);
  container.appendChild(row);
}

function appendAutoStoryboardPhaseButtons(job, container) {
  const disabled = job && job.status === "running";
  appendTreeAction(container, "步骤 1", getFlowActionLabel("auto_storyboard", "step_extract"), () => runAutoStoryboardPhase("step1"), {
    disabled
  });
  appendTreeAction(container, "步骤 2", getFlowActionLabel("auto_storyboard", "step_storyboard"), () => runAutoStoryboardPhase("step2"), {
    disabled
  });
  appendTreeAction(container, "上传资产", getFlowActionLabel("auto_storyboard", "step_upload"), () => runAutoStoryboardPhase("step3_upload"), {
    disabled
  });
}

function appendVisualAudioPhaseButtons(job, container) {
  const disabled = job && job.status === "running";
  const flowState = state.flowStatus?.flows?.visual_audio_assets;

  appendTreeAction(container, "一键到底", "执行", () => executeFlowFull("visual_audio_assets"), { disabled });

  const steps = [
    {
      label: "第一步：提示词",
      phases: ["build_prompts"],
      checkSteps: ["step_character_prompts", "step_location_prompts", "step_fenjing_prompts"]
    },
    {
      label: "第二步：生成",
      phases: ["generate_images"],
      checkSteps: ["step_character_images", "step_location_images"]
    },
    {
      label: "第二步：TTS语音",
      phases: ["generate_tts"],
      checkSteps: ["step_tts"]
    },
    {
      label: "第三步：上传",
      phases: ["upload_assets"],
      checkSteps: ["step_upload"]
    },
    {
      label: "第四步：换装",
      phases: ["cloth_images", "cloth_changed"],
      checkSteps: ["step_cloth_images", "step_cloth_changed"]
    }
  ];

  const stepStates = steps.map((config) => {
    const completed = isStepCompleted(flowState, config.checkSteps);
    const failed = isStepFailed(flowState, config.checkSteps);
    const running = isStepRunning(flowState, config.checkSteps);
    return {
      config,
      completed,
      failed,
      running,
    };
  });
  const lastCompletedIndex = stepStates.reduce((acc, item, idx) => item.completed ? idx : acc, -1);
  const lastRunningIndex = stepStates.reduce((acc, item, idx) => item.running ? Math.max(acc, idx) : acc, -1);
  void lastCompletedIndex;
  void lastRunningIndex;

  stepStates.forEach((item, idx) => {
    const { config, completed, failed, running } = item;
    const isPrompt = config.phases[0] === "build_prompts" || config.phases[0] === "step_character_prompts";
    const stepDisabled = disabled || completed || running;
    const label = completed ? `${config.label} ✓` : config.label;
    let actionLabel = "执行";
    if (running) {
      actionLabel = "执行中";
    } else if (completed) {
      actionLabel = "已完成";
    } else if (failed && isPrompt) {
      actionLabel = "重生";
    }

    appendTreeAction(container, label, actionLabel, () => {
      if (config.phases.length > 0) {
        const phasesStr = config.phases.join(",");
        submitFlowPhase("visual_audio_assets", phasesStr);
      }
    }, { disabled: stepDisabled });
  });
}

function isStepCompleted(flowState, checkSteps) {
  if (!flowState || !flowState.steps) return false;
  return checkSteps.every(step => flowState.steps[step] === "completed");
}

function isStepFailed(flowState, checkSteps) {
  if (!flowState || !flowState.steps) return false;
  return checkSteps.some(step => ["error", "partial_returned", "partial_completed"].includes(flowState.steps[step]));
}

function isStepRunning(flowState, checkSteps) {
  if (!flowState || !flowState.steps) return false;
  return checkSteps.some(step => flowState.steps[step] === "running");
}

function appendFenjingPhaseButtons(job, container) {
  const isPending = job && job.status === "pending";
  const disabled = job && job.status === "running";
  const flowState = state.flowStatus?.flows;
  
  const generateStatus = flowState?.fenjing_generate?.status || "waiting";
  const uploadStatus = flowState?.fenjing_upload?.status || "waiting";
  
  const generateCompleted = generateStatus === "completed" || generateStatus === "partial_completed";
  const generateRunning = generateStatus === "running";
  const generateDisabled = disabled || generateRunning || generateCompleted;
  const generateLabel = generateCompleted ? "第一步：分镜图生成 ✓" : "第一步：分镜图生成";
  let generateActionLabel = "执行";
  if (isPending) {
    generateActionLabel = "执行";
  } else if (generateRunning) {
    generateActionLabel = "执行中";
  } else if (generateCompleted) {
    generateActionLabel = "已完成";
  }
  
  appendTreeAction(container, generateLabel, generateActionLabel, () => {
    if (generateCompleted) return;
    executeFlowFull("fenjing_generate");
  }, { disabled: isPending ? false : generateDisabled, breathing: generateRunning });
  
  if (generateCompleted) {
    const uploadCompleted = uploadStatus === "completed";
    const uploadRunning = uploadStatus === "running";
    const uploadDisabled = disabled || uploadRunning || uploadCompleted;
    const uploadLabel = uploadCompleted ? "第二步：上传 ✓" : "第二步：上传";
    let uploadActionLabel = "执行";
    if (uploadRunning) {
      uploadActionLabel = "执行中";
    } else if (uploadCompleted) {
      uploadActionLabel = "已完成";
    }
    
    appendTreeAction(container, uploadLabel, uploadActionLabel, () => {
      if (uploadCompleted) return;
      executeFlowFull("fenjing_upload");
    }, { disabled: uploadDisabled, breathing: uploadRunning });
  }
}

function appendVideoPhaseButtons(job, container) {
  const isPending = job && job.status === "pending";
  const disabled = job && job.status === "running";
  const flowState = state.flowStatus?.flows;
  const videoFlow = flowState?.video;

  const phases = [
    { label: "第一步：视频提示词生成", phase: "prepare_prompts", stepKey: "step_video_prompts" },
    { label: "第二步：视频生成", phase: "generate_videos", stepKey: "step_video_generation" },
    { label: "第三步：上传", phase: "upload_videos", stepKey: "step_video_upload" },
  ];

  for (const p of phases) {
    const stepStatus = videoFlow?.steps?.[p.stepKey] || "waiting";
    const completed = stepStatus === "completed" || stepStatus === "partial_completed";
    const running = stepStatus === "running";
    const btnDisabled = disabled || running || completed;
    const btnLabel = completed ? `${p.label} ✓` : p.label;
    let actionLabel = "执行";
    if (isPending) {
      actionLabel = "执行";
    } else if (running) {
      actionLabel = "执行中";
    } else if (completed) {
      actionLabel = "已完成";
    }
    appendTreeAction(container, btnLabel, actionLabel, () => {
      if (completed) return;
      executeFlowFull("video", { phase: p.phase });
    }, { disabled: isPending ? false : btnDisabled, breathing: running });
  }
}

function resolveVisualAudioRetryPhase(errorEvent) {
  if (!errorEvent) {
    return "";
  }
  const step = errorEvent.step || errorEvent.phase || "";
  if (!step) {
    return "";
  }
  if (step === "step_character_prompts" || step === "step_location_prompts" || step === "step_fenjing_prompts" || step === "build_prompts") {
    return "build_prompts";
  }
  if (step === "step_character_images" || step === "step_location_images" || step === "generate_images") {
    return "generate_images";
  }
  if (step === "step_tts" || step === "generate_tts") {
    return "generate_tts";
  }
  if (step === "step_cloth_changed") {
    return "cloth_changed";
  }
  if (step === "step_cloth_images" || step === "cloth_images") {
    return "cloth_images";
  }
  if (step === "step_upload" || step === "upload_assets") {
    return "upload_assets";
  }
  return "";
}

function buildVisualAudioPhaseLabel(phase) {
  const labels = {
    build_prompts: "提示词",
    generate_images: "生成",
    generate_tts: "TTS 语音",
    cloth_images: "换装",
    cloth_changed: "换装",
    upload_assets: "上传",
  };
  if (!phase) {
    return "阶段";
  }
  if (phase.includes(",")) {
    return "提示词";
  }
  return labels[phase] || phase;
}

function collectFailedAssetItems(events) {
  const items = [];
  const seen = new Set();
  (events || []).forEach((event) => {
    if (!event || event.event !== "upload_progress") {
      return;
    }
    const data = event.data || {};
    if (data.ok !== false) {
      return;
    }
    const type = data.image_type ? String(data.image_type) : "";
    const imageId = data.image_id ? String(data.image_id) : "";
    const outfitId = data.outfit_id ? String(data.outfit_id) : "";
    const characterId = data.character_id ? String(data.character_id) : "";
    const bgType = data.bg_type ? String(data.bg_type) : "";
    if (!type) {
      return;
    }
    const key = `${type}:${imageId}:${outfitId}:${characterId}:${bgType}`;
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    if (type === "cloth" && imageId) {
      items.push({
        type,
        label: `服装图 ${imageId}`,
        payload: { outfit_id: imageId }
      });
      return;
    }
    if (type === "cloth_changed" && characterId && outfitId) {
      items.push({
        type,
        label: `换装图 ${characterId}_${outfitId}`,
        payload: { character_id: characterId, outfit_id: outfitId }
      });
      return;
    }
    if (type === "location" && imageId) {
      items.push({
        type,
        label: `地点图 ${imageId}${bgType ? ` (${bgType})` : ""}`,
        payload: { location_id: imageId, bg_type: bgType || "standing" }
      });
    }
  });
  return items;
}

function updateTreeActions(job, container) {
  if (!job || !container) {
    return;
  }
  const wrap = container.querySelector(".tree-actions");
  if (!wrap) {
    return;
  }
  wrap.innerHTML = "";
  wrap.classList.add("hidden");
  const flow = getFlowFromJob(job);
  const logs = Array.isArray(job.log_tail) ? job.log_tail : [];
  const events = extractStructuredEvents(logs, flow);
  const isRunning = job && job.status === "running";
  if (flow === "auto_storyboard") {
    appendAutoStoryboardPhaseButtons(job, wrap);
    if (!isRunning) {
      const config = getTreeConfig(flow);
      const failure = config ? resolveTreeFailure(events, config) : null;
      const failedStep = failure ? failure.stepId : "";
      const failedStepMappings = {
        "step_extract": { label: "步骤 1", newStep: "step_extract" },
        "step_storyboard": { label: "步骤 2", newStep: "step_storyboard" },
        "step_upload": { label: "上传资产", newStep: "step_upload" }
      };
      const mapping = failedStepMappings[failedStep];
      if (mapping) {
        appendTreeAction(wrap, `重试${mapping.label}`, "重试", () => submitFlowPhase("auto_storyboard", mapping.newStep));
      }
    }
  }
  if (flow === "visual_audio_assets") {
    appendVisualAudioPhaseButtons(job, wrap);
    if (!isRunning) {
      const phases = new Set();
      events.forEach((event) => {
        if (!event || event.event !== "flow_error") {
          return;
        }
        const phase = resolveVisualAudioRetryPhase(event);
        if (phase) {
          phases.add(phase);
        }
      });
      phases.forEach((phase) => {
        const label = buildVisualAudioPhaseLabel(phase);
        appendTreeAction(wrap, `重试${label}`, "重试", () => submitFlowPhase("visual_audio_assets", phase));
      });
    }
  }
  if (flow === "fenjing_generate") {
    appendFenjingPhaseButtons(job, wrap);
  }
  if (flow === "video") {
    appendVideoPhaseButtons(job, wrap);
  }
  if (wrap.childElementCount > 0) {
    wrap.classList.remove("hidden");
  }
}

function parseAutoStoryboardProgressFromEvents(events) {
  const uploadComplete = findLastEvent(events, (e) => e.event === "upload_complete");
  if (uploadComplete) {
    return "资产上传完成";
  }

  const uploadProgressEvents = events.filter((e) => e.event === "upload_progress");
  const uploadStart = findLastEvent(events, (e) => e.event === "upload_start");
  if (uploadStart || uploadProgressEvents.length > 0) {
    const latestUpload = uploadProgressEvents[uploadProgressEvents.length - 1];
    const count = latestUpload && latestUpload.data && latestUpload.data.uploaded ? latestUpload.data.uploaded : uploadProgressEvents.length;
    return `正在上传资产 (${count}个文件)`;
  }

  const phase2Complete = findLastEvent(events, (e) => e.event === "phase_complete" && (e.phase === "step_storyboard" || e.phase === "phase2"));
  if (phase2Complete) {
    return "阶段 2 完成：正在上传资产";
  }

  const phase2Start = findLastEvent(events, (e) => e.event === "phase_start" && (e.phase === "step_storyboard" || e.phase === "phase2"));
  const phase2BatchEvents = events.filter((e) => e.event === "step_progress" && (e.step === "step_storyboard" || e.step === "phase2_batch_progress") && e.data && e.data.status === "completed");
  if (phase2Start || phase2BatchEvents.length > 0) {
    if (phase2BatchEvents.length > 0) {
      return `阶段 2：正在生成分镜 (${phase2BatchEvents.length}批次完成)`;
    }
    return "阶段 2：正在生成分镜";
  }

  const phase1Complete = findLastEvent(events, (e) => e.event === "phase_complete" && (e.phase === "step_extract" || e.phase === "phase1"));
  if (phase1Complete) {
    return "阶段 1 完成：等待你的操作，进入阶段 2";
  }

  const phase1Api = findLastEvent(events, (e) => e.event === "step_progress" && (e.step === "step_extract" || e.step === "phase1_api_call"));
  if (phase1Api) {
    return "阶段 1：正在调用 API";
  }

  const phase1Start = findLastEvent(events, (e) => e.event === "phase_start" && (e.phase === "step_extract" || e.phase === "phase1"));
  if (phase1Start) {
    return "阶段 1：提取人物、摘要和地点";
  }

  const flowStart = findLastEvent(events, (e) => e.event === "flow_start");
  if (flowStart) {
    return "正在读取小说文件";
  }

  const lastEvent = events[events.length - 1];
  if (lastEvent && lastEvent.message) {
    return String(lastEvent.message);
  }

  return "正在处理...";
}

function buildTreeStepElement(step) {
  const stepEl = document.createElement("div");
  stepEl.className = "tree-step";
  stepEl.dataset.step = step.id;
  const node = document.createElement("div");
  node.className = "tree-node";
  const content = document.createElement("div");
  content.className = "tree-content";
  const label = document.createElement("div");
  label.className = "tree-label";
  label.textContent = step.label;
  const desc = document.createElement("div");
  desc.className = "tree-desc";
  desc.textContent = step.desc;
  const status = document.createElement("div");
  status.className = "tree-status";
  status.textContent = "等待中";
  content.appendChild(label);
  content.appendChild(desc);
  content.appendChild(status);
  stepEl.appendChild(node);
  stepEl.appendChild(content);
  return { stepEl, statusEl: status };
}

function buildVisualAudioTreeElement(config) {
  const container = document.createElement("div");
  container.className = "flow-tree flow-tree-parallel";
  const header = document.createElement("div");
  header.className = "tree-header";
  const headerTitle = document.createElement("span");
  headerTitle.className = "tree-header-title";
  headerTitle.textContent = config.title;
  const logButton = document.createElement("button");
  logButton.className = "flow-log-btn";
  logButton.textContent = "查看日志";
  header.appendChild(headerTitle);
  header.appendChild(logButton);
  container.appendChild(header);

  const stepLabelMap = {};
  (config.steps || []).forEach((step) => {
    stepLabelMap[step.id] = step.label || step.id;
  });

  const stepsWrap = document.createElement("div");
  stepsWrap.className = "tree-steps tree-steps-parallel";

  const itemLabelMap = {};
  (config.parallel ? config.parallel.groups : []).forEach((group) => {
    (group.items || []).forEach((item) => {
      itemLabelMap[item.id] = item.label || item.id;
    });
  });

  if (config.tree && Array.isArray(config.tree.levels)) {
    const diagram = document.createElement("div");
    diagram.className = "tree-diagram";
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.classList.add("tree-diagram-lines");
    diagram.appendChild(svg);
    config.tree.levels.forEach((level) => {
      const levelEl = document.createElement("div");
      levelEl.className = "tree-level";
      levelEl.dataset.level = level.id;
      const levelLabel = document.createElement("div");
      levelLabel.className = "tree-level-label";
      levelLabel.textContent = level.label || "";
      const nodesWrap = document.createElement("div");
      nodesWrap.className = "tree-level-nodes";
      (level.nodes || []).forEach((node) => {
        const nodeEl = document.createElement("div");
        nodeEl.className = "tree-node-card";
        nodeEl.dataset.node = node.id;
        if (node.item) {
          nodeEl.dataset.kind = "item";
        } else if (node.step) {
          nodeEl.dataset.kind = "step";
        }
        const connector = document.createElement("div");
        connector.className = "tree-node-connector";
        const title = document.createElement("div");
        title.className = "tree-node-title";
        if (node.label) {
          title.textContent = node.label;
        } else if (node.item) {
          title.textContent = itemLabelMap[node.item] || node.item;
        } else if (node.step) {
          title.textContent = stepLabelMap[node.step] || node.step;
        } else {
          title.textContent = node.id;
        }
        const status = document.createElement("div");
        status.className = "tree-node-status";
        status.textContent = "等待中";
        nodeEl.appendChild(connector);
        nodeEl.appendChild(title);
        nodeEl.appendChild(status);
        nodesWrap.appendChild(nodeEl);
      });
      levelEl.appendChild(levelLabel);
      levelEl.appendChild(nodesWrap);
      diagram.appendChild(levelEl);
    });
    stepsWrap.appendChild(diagram);
    container.appendChild(stepsWrap);
  } else {
    const tailStep = config.steps[config.steps.length - 1] || null;

    const parallelWrap = document.createElement("div");
    parallelWrap.className = "tree-parallel";
    const parallelHeader = document.createElement("div");
    parallelHeader.className = "tree-parallel-header";
    parallelHeader.textContent = config.parallel ? config.parallel.label : "并行阶段";
    parallelWrap.appendChild(parallelHeader);
    const groupsWrap = document.createElement("div");
    groupsWrap.className = "tree-parallel-groups";
    (config.parallel ? config.parallel.groups : []).forEach((group) => {
      const groupEl = document.createElement("div");
      groupEl.className = "tree-parallel-group";
      groupEl.dataset.group = group.id;
      const groupTitle = document.createElement("div");
      groupTitle.className = "tree-parallel-title";
      groupTitle.textContent = group.label;
      const groupDesc = document.createElement("div");
      groupDesc.className = "tree-parallel-desc";
      groupDesc.textContent = group.desc || "";
      const itemsWrap = document.createElement("div");
      itemsWrap.className = "tree-parallel-items";
      (group.items || []).forEach((item) => {
        const itemEl = document.createElement("div");
        itemEl.className = "tree-parallel-item";
        itemEl.dataset.item = item.id;
        if (item.dependsOn && item.dependsOn.length > 0) {
          itemEl.classList.add("has-deps");
        }
        const itemLabel = document.createElement("div");
        itemLabel.className = "tree-parallel-label";
        itemLabel.textContent = item.label;
        const itemStatus = document.createElement("div");
        itemStatus.className = "tree-parallel-status";
        itemStatus.textContent = "等待中";
        itemEl.appendChild(itemLabel);
        if (item.dependsOn && item.dependsOn.length > 0) {
          const depsRow = document.createElement("div");
          depsRow.className = "tree-parallel-deps";
          const depsLabel = document.createElement("span");
          depsLabel.className = "tree-parallel-deps-label";
          depsLabel.textContent = "前置";
          depsRow.appendChild(depsLabel);
          const depsWrap = document.createElement("div");
          depsWrap.className = "tree-parallel-deps-wrap";
          const labels = item.dependsOn.map((dep) => itemLabelMap[dep] || dep);
          labels.forEach((label, idx) => {
            const pill = document.createElement("span");
            pill.className = "tree-parallel-dep-pill";
            pill.textContent = label;
            depsWrap.appendChild(pill);
            if (idx < labels.length - 1) {
              const arrow = document.createElement("span");
              arrow.className = "tree-parallel-dep-arrow";
              arrow.textContent = "→";
              depsWrap.appendChild(arrow);
            }
          });
          depsRow.appendChild(depsWrap);
          itemEl.appendChild(depsRow);
        }
        itemEl.appendChild(itemStatus);
        itemsWrap.appendChild(itemEl);
      });
      groupEl.appendChild(groupTitle);
      if (group.desc) {
        groupEl.appendChild(groupDesc);
      }
      groupEl.appendChild(itemsWrap);
      groupsWrap.appendChild(groupEl);
    });
    parallelWrap.appendChild(groupsWrap);
    stepsWrap.appendChild(parallelWrap);

    const connectorTail = document.createElement("div");
    connectorTail.className = "tree-connector";
    connectorTail.dataset.connector = "tail";
    stepsWrap.appendChild(connectorTail);

    if (tailStep) {
      const tail = buildTreeStepElement(tailStep);
      stepsWrap.appendChild(tail.stepEl);
    }

    container.appendChild(stepsWrap);
  }

  const nextWrap = document.createElement("div");
  nextWrap.className = "tree-next";
  const nextLabel = document.createElement("div");
  nextLabel.className = "tree-next-label";
  nextLabel.textContent = "下一步";
  const nextDesc = document.createElement("div");
  nextDesc.className = "tree-next-desc";
  nextDesc.textContent = "等待中...";
  nextWrap.appendChild(nextLabel);
  nextWrap.appendChild(nextDesc);
  container.appendChild(nextWrap);
  const actionWrap = document.createElement("div");
  actionWrap.className = "tree-actions hidden";
  container.appendChild(actionWrap);
  return container;
}

function computeStepStates(steps, logs, events) {
  const useEvents = events.length > 0;
  const states = steps.map((step, idx) => {
    const started = useEvents ? hasMatchingEvent(events, step.startEvents) : hasFallbackLog(logs, step.fallbackStart);
    const completed = useEvents ? hasMatchingEvent(events, step.completeEvents) : hasFallbackLog(logs, step.fallbackComplete);
    return { started, completed, step, idx };
  });
  return states.map((state, idx) => {
    const later = states.slice(idx + 1);
    const laterStarted = later.some((item) => item.started || item.completed);
    const completed = state.completed || (state.started && laterStarted);
    return { ...state, completed };
  });
}

function resolveVisualAudioItemState(item, baseState, logs, events, flowStepStatus) {
  let started = false;
  let completed = false;
  let failed = false;
  const statusKey = item.step || item.id;
  if (flowStepStatus && statusKey) {
    const status = flowStepStatus[statusKey] || "";
    started = status === "running" || status === "completed" || status === "error";
    completed = status === "completed";
    failed = status === "error";
  }
  return { started, completed, failed };
}

function buildVisualAudioConnections(config) {
  const edges = [];
  const levels = config.tree && Array.isArray(config.tree.levels) ? config.tree.levels : [];
  const itemDeps = {};
  (config.parallel ? config.parallel.groups : []).forEach((group) => {
    (group.items || []).forEach((item) => {
      itemDeps[item.id] = item.dependsOn || [];
    });
  });
  Object.keys(itemDeps).forEach((target) => {
    (itemDeps[target] || []).forEach((dep) => {
      edges.push({ from: dep, to: target });
    });
  });
  const tailLevelIndex = levels.length - 1;
  const uploadLevelIndex = levels.findIndex((level) => (level.nodes || []).some((node) => node.step === "step_upload"));
  if (uploadLevelIndex > 0) {
    const prevLevel = levels[uploadLevelIndex - 1];
    const uploadNode = levels[uploadLevelIndex].nodes.find((node) => node.step === "step_upload");
    if (prevLevel && uploadNode) {
      (prevLevel.nodes || []).forEach((node) => {
        edges.push({ from: node.id, to: uploadNode.id });
      });
    }
  }
  return edges;
}

function updateVisualAudioTreeConnections(container, config, itemStatesWithDeps, stepStateMap) {
  const diagram = container.querySelector(".tree-diagram");
  const svg = diagram ? diagram.querySelector(".tree-diagram-lines") : null;
  if (!diagram || !svg) {
    return;
  }
  const rect = diagram.getBoundingClientRect();
  const nodes = {};
  diagram.querySelectorAll(".tree-node-card").forEach((node) => {
    const id = node.dataset.node;
    if (!id) {
      return;
    }
    const nodeRect = node.getBoundingClientRect();
    nodes[id] = {
      left: nodeRect.left - rect.left,
      right: nodeRect.right - rect.left,
      top: nodeRect.top - rect.top,
      bottom: nodeRect.bottom - rect.top,
      node
    };
  });
  const width = Math.max(1, diagram.clientWidth);
  const height = Math.max(1, diagram.clientHeight);
  svg.setAttribute("width", String(width));
  svg.setAttribute("height", String(height));
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.innerHTML = "";
  const itemStateMap = {};
  (itemStatesWithDeps || []).forEach((state) => {
    itemStateMap[state.item.id] = state;
  });
  const edges = buildVisualAudioConnections(config);
  edges.forEach((edge) => {
    const from = nodes[edge.from];
    const to = nodes[edge.to];
    if (!from || !to) {
      return;
    }
    const x1 = from.right;
    const y1 = (from.top + from.bottom) / 2;
    const x2 = to.left;
    const y2 = (to.top + to.bottom) / 2;
    const dx = Math.max(20, Math.abs(x2 - x1) * 0.4);
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`);
    path.setAttribute("class", "tree-diagram-line");
    const toState = itemStateMap[edge.to];
    const toStepState = stepStateMap[edge.to];
    if (toState && toState.completed) {
      path.classList.add("completed");
    } else if (toState && toState.started) {
      path.classList.add("running");
    } else if (toState && toState.failed) {
      path.classList.add("error");
    } else if (toState && toState.blocked) {
      path.classList.add("blocked");
    } else if (toStepState && toStepState.completed) {
      path.classList.add("completed");
    } else if (toStepState && toStepState.started) {
      path.classList.add("running");
    }
    svg.appendChild(path);
  });
}

function updateVisualAudioTreeDiagram(logs, events, config, container) {
  const flowSteps = (state.flowStatus && state.flowStatus.flows && state.flowStatus.flows.visual_audio_assets)
    ? state.flowStatus.flows.visual_audio_assets.steps || {}
    : {};
  const mergedSteps = { ...flowSteps };
  if ("step_cloth_changed" in mergedSteps || "step_cloth_images" in mergedSteps) {
    const clothStatus = mergedSteps.step_cloth_images || "";
    const clothChangedStatus = mergedSteps.step_cloth_changed || "";
    const statuses = [clothStatus, clothChangedStatus].filter((item) => item);
    const hasError = statuses.some((item) => item === "error");
    const allCompleted = statuses.length > 0 && statuses.every((item) => item === "completed");
    const anyRunning = statuses.some((item) => item === "running");
    const anyPartial = statuses.some((item) => item === "partial_returned" || item === "partial_completed");
    if (hasError) {
      mergedSteps.step_cloth_images = "error";
    } else if (allCompleted) {
      mergedSteps.step_cloth_images = "completed";
    } else if (anyRunning || anyPartial) {
      mergedSteps.step_cloth_images = "running";
    } else if (statuses.length > 0) {
      mergedSteps.step_cloth_images = "waiting";
    }
  }
  const stepNodes = Array.from(container.querySelectorAll(".tree-step"));
  const connectorNodes = Array.from(container.querySelectorAll(".tree-connector"));
  const parallelItems = Array.from(container.querySelectorAll(".tree-parallel-item"));
  const nodeCardsAll = Array.from(container.querySelectorAll(".tree-node-card"));
  const nextDesc = container.querySelector(".tree-next-desc");
  if (!nextDesc) {
    return;
  }
  if (Object.keys(flowSteps).length === 0) {
    stepNodes.forEach((node) => {
      node.className = "tree-step";
      const status = node.querySelector(".tree-status");
      if (status) {
        status.textContent = "等待中";
      }
    });
    connectorNodes.forEach((node) => {
      node.className = "tree-connector";
    });
    parallelItems.forEach((node) => {
      node.className = "tree-parallel-item";
      const status = node.querySelector(".tree-parallel-status");
      if (status) {
        status.textContent = "等待中";
      }
    });
    nodeCardsAll.forEach((node) => {
      node.className = "tree-node-card";
      const status = node.querySelector(".tree-node-status");
      if (status) {
        status.textContent = "等待中";
      }
    });
    nextDesc.textContent = "等待中";
    return;
  }
  const stepStates = config.steps.map((step) => {
    const status = mergedSteps[step.id] || "";
    const started = status === "running" || status === "completed" || status === "error";
    const completed = status === "completed";
    const failed = status === "error";
    return { started, completed, failed, step };
  });
  const stepStateMap = {};
  stepStates.forEach((state) => {
    stepStateMap[state.step.id] = state;
  });
  const tailKey = (config.steps[config.steps.length - 1] || {}).id;
  const tailState = tailKey ? stepStateMap[tailKey] : null;
  const tailStepEl = tailKey ? container.querySelector(`.tree-step[data-step="${tailKey}"]`) : null;
  const tailStatus = tailStepEl ? tailStepEl.querySelector(".tree-status") : null;
  const connectorTail = container.querySelector('.tree-connector[data-connector="tail"]');

  if (tailStepEl) {
    tailStepEl.className = "tree-step";
  }
  if (connectorTail) {
    connectorTail.className = "tree-connector";
  }

  if (tailState && tailStepEl && tailStatus) {
    if (tailState.failed) {
      tailStepEl.classList.add("error");
      tailStatus.textContent = "失败";
    } else if (tailState.completed) {
      tailStepEl.classList.add("completed");
      tailStatus.textContent = "已完成";
    } else if (tailState.started) {
      tailStepEl.classList.add("running");
      tailStatus.textContent = "进行中";
    } else {
      tailStatus.textContent = "等待中";
    }
  }

  const failureStepId = null;

  const itemLabelMap = {};
  const itemStateMap = {};
  const itemStates = [];
  (config.parallel ? config.parallel.groups : []).forEach((group) => {
    (group.items || []).forEach((item) => {
      itemLabelMap[item.id] = item.label || item.id;
      const baseState = item.step ? stepStateMap[item.step] : null;
  const itemState = resolveVisualAudioItemState(item, baseState, logs, events, mergedSteps);
      let failed = itemState.failed;
      if (failureStepId) {
        const errorSteps = item.errorSteps || [];
        failed = errorSteps.includes(failureStepId) || failureStepId === item.step || failureStepId === item.id;
      }
      const resolved = { ...itemState, item, failed };
      itemStateMap[item.id] = resolved;
      itemStates.push(resolved);
    });
  });

  const itemStatesWithDeps = itemStates.map((state) => {
    const deps = state.item.dependsOn || [];
    if (state.started || state.completed || state.failed || deps.length === 0) {
      return { ...state, blocked: false, depFailed: false, depLabels: [] };
    }
    const depStates = deps.map((dep) => itemStateMap[dep]).filter(Boolean);
    const depFailed = depStates.some((dep) => dep.failed);
    const depIncomplete = depStates.some((dep) => !dep.completed);
    const blocked = depFailed || depIncomplete;
    const depLabels = deps.map((dep) => itemLabelMap[dep] || dep);
    return { ...state, blocked, depFailed, depLabels };
  });

  itemStatesWithDeps.forEach((state) => {
    const item = state.item;
    const itemEl = container.querySelector(`.tree-parallel-item[data-item="${item.id}"]`);
    const statusEl = itemEl ? itemEl.querySelector(".tree-parallel-status") : null;
    if (!itemEl || !statusEl) {
      return;
    }
    itemEl.className = "tree-parallel-item";
    if (state.failed) {
      itemEl.classList.add("error");
      statusEl.textContent = "失败";
    } else if (state.completed) {
      itemEl.classList.add("completed");
      statusEl.textContent = "已完成";
    } else if (state.started) {
      itemEl.classList.add("running");
      statusEl.textContent = "进行中";
    } else if (state.blocked) {
      itemEl.classList.add("blocked");
      const prefix = state.depFailed ? "前置失败" : "等待前置";
      statusEl.textContent = `${prefix}：${state.depLabels.join("、")}`;
    } else {
      statusEl.textContent = "等待中";
    }
  });

  nodeCardsAll.forEach((card) => {
    const kind = card.dataset.kind || "";
    const nodeId = card.dataset.node || "";
    const statusEl = card.querySelector(".tree-node-status");
    if (!statusEl) {
      return;
    }
    card.className = "tree-node-card";
    if (kind === "step") {
      const stepState = stepStateMap[nodeId];
      if (stepState && stepState.completed) {
        card.classList.add("completed");
        statusEl.textContent = "已完成";
      } else if (stepState && stepState.started) {
        card.classList.add("running");
        statusEl.textContent = "进行中";
      } else {
        statusEl.textContent = "等待中";
      }
      return;
    }
    const itemState = itemStatesWithDeps.find((state) => state.item.id === nodeId);
    if (!itemState) {
      statusEl.textContent = "等待中";
      return;
    }
    if (itemState.failed) {
      card.classList.add("error");
      statusEl.textContent = "失败";
    } else if (itemState.completed) {
      card.classList.add("completed");
      statusEl.textContent = "已完成";
    } else if (itemState.started) {
      card.classList.add("running");
      statusEl.textContent = "进行中";
    } else if (itemState.blocked) {
      card.classList.add("blocked");
      const prefix = itemState.depFailed ? "前置失败" : "等待前置";
      statusEl.textContent = `${prefix}：${itemState.depLabels.join("、")}`;
    } else {
      statusEl.textContent = "等待中";
    }
  });

  updateVisualAudioTreeConnections(container, config, itemStatesWithDeps, stepStateMap);

  const parallelCompleted = itemStatesWithDeps.length > 0 && itemStatesWithDeps.every((state) => state.completed || state.failed);
  if (connectorTail && parallelCompleted) {
    connectorTail.classList.add("completed");
  }

  const runningItem = itemStatesWithDeps.find((state) => state.started && !state.completed && !state.failed);
  const pendingItem = itemStatesWithDeps.find((state) => !state.started && !state.completed && !state.failed && !state.blocked);
  const blockedItem = itemStatesWithDeps.find((state) => state.blocked);
  if (itemStatesWithDeps.some((state) => state.failed) || stepStates.some((state) => state.failed)) {
    nextDesc.textContent = "执行失败";
  } else if (runningItem) {
    nextDesc.textContent = `并行处理中：${runningItem.item.label}`;
  } else if (tailState && tailState.started && !tailState.completed) {
    const tailDef = config.steps[config.steps.length - 1] || {};
    nextDesc.textContent = tailDef.label || "处理中";
  } else if (pendingItem) {
    nextDesc.textContent = `等待：${pendingItem.item.label}`;
  } else if (blockedItem) {
    nextDesc.textContent = `等待前置：${blockedItem.depLabels.join("、")}`;
  } else if (tailState && tailState.completed) {
    nextDesc.textContent = "全部完成";
  } else if (headState && !headState.started) {
    nextDesc.textContent = "准备资产";
  } else {
    nextDesc.textContent = "处理中";
  }
}

function parseGenericProgressFromEvents(events) {
  const lastEvent = events[events.length - 1];
  if (lastEvent && lastEvent.message) {
    return String(lastEvent.message);
  }
  return "正在处理...";
}

const FLOW_TREE_CONFIG = {
  auto_storyboard: {
    title: "剧本拆解进度",
    steps: [
      {
        id: "step_extract",
        label: "步骤 1",
        desc: "提取人物、摘要和地点",
        startEvents: [
          { event: "phase_start", phase: "step_extract" },
          { event: "step_progress", step: "step_extract" }
        ],
        completeEvents: [{ event: "phase_complete", phase: "step_extract" }],
        fallbackStart: ["阶段 1:", "步骤 1:"],
        fallbackComplete: ["阶段 1 完成", "步骤 1 完成"]
      },
      {
        id: "step_storyboard",
        label: "步骤 2",
        desc: "生成分镜",
        startEvents: [
          { event: "phase_start", phase: "step_storyboard" },
          { event: "step_progress", step: "step_storyboard" }
        ],
        completeEvents: [{ event: "phase_complete", phase: "step_storyboard" }],
        fallbackStart: ["阶段 2:", "步骤 2:"],
        fallbackComplete: ["并行生成完成", "步骤 2 完成"]
      },
      {
        id: "step_upload",
        label: "上传资产",
        desc: "上传到 TOS",
        startEvents: [{ event: "upload_start" }, { event: "upload_progress" }],
        completeEvents: [{ event: "upload_complete" }],
        fallbackStart: ["开始上传资产", "Uploaded:"],
        fallbackComplete: ["资产上传完成"]
      }
    ],
    fallbackStart: ["开始处理小说"]
  },
  visual_audio_assets: {
    title: "角色与素材生成",
    steps: [
      {
        id: "step_prompts",
        label: "构建提示词",
        desc: "角色/地点/分镜提示词",
        startEvents: [
          { event: "step_progress", step: "step_character_prompts" },
          { event: "step_progress", step: "step_location_prompts" },
          { event: "step_progress", step: "step_fenjing_prompts" }
        ],
        completeEvents: [
          { event: "phase_complete", step: "step_character_prompts" },
          { event: "phase_complete", step: "step_location_prompts" },
          { event: "phase_complete", step: "step_fenjing_prompts" }
        ],
        fallbackStart: ["Building Character Prompts", "Building Location Prompts", "Building Fenjing Prompts"],
        fallbackComplete: [],
        errorPatterns: ["prompt"]
      },
      {
        id: "step_images",
        label: "生成图片",
        desc: "角色形象图生成",
        startEvents: [
          { event: "step_progress", step: "step_character_images" },
          { event: "step_progress", step: "step_location_images" },
          { event: "phase_start", phase: "step_cloth_images" },
          { event: "step_progress", step: "step_cloth_images" }
        ],
        completeEvents: [
          { event: "phase_complete", step: "step_character_images" },
          { event: "phase_complete", step: "step_location_images" },
          { event: "phase_complete", phase: "step_cloth_images" }
        ],
        fallbackStart: ["Generating Character Images"],
        fallbackComplete: [],
        errorPatterns: ["image"]
      },
      {
        id: "step_tts",
        label: "生成语音",
        desc: "TTS 语音生成",
        startEvents: [{ event: "step_progress", step: "step_tts" }],
        completeEvents: [{ event: "phase_complete", step: "step_tts" }],
        fallbackStart: ["Generating TTS Audios"],
        fallbackComplete: [],
        errorPatterns: ["TTS"]
      },
      {
        id: "step_upload",
        label: "上传资产",
        desc: "上传到 TOS",
        startEvents: [{ event: "upload_start" }, { event: "upload_progress" }],
        completeEvents: [{ event: "upload_complete" }],
        fallbackStart: ["Uploaded - File:", "upload_assets"],
        fallbackComplete: ["upload_assets completed"],
        errorPatterns: ["upload", "Uploaded"]
      }
    ],
    fallbackStart: ["Starting Asset Generation Workflow"],
    stepAliases: { start: "step_character_prompts" },
    parallel: {
      label: "并行阶段",
      groups: [
        {
          id: "prompts",
          label: "提示词并行",
          desc: "角色 / 地点 / 分镜提示词",
          items: [
            {
              id: "step_character_prompts",
              label: "角色提示词",
              step: "step_character_prompts",
              startEvents: [{ event: "step_progress", step: "step_character_prompts" }],
              completeEvents: [{ event: "phase_complete", step: "step_character_prompts" }],
              fallbackStart: ["Starting Character Workflow", "Building Character Prompts"],
              fallbackComplete: ["Character Prompts saved"],
              errorSteps: ["step_character_prompts"]
            },
            {
              id: "step_location_prompts",
              label: "地点提示词",
              step: "step_location_prompts",
              startEvents: [{ event: "step_progress", step: "step_location_prompts" }],
              completeEvents: [{ event: "phase_complete", step: "step_location_prompts" }],
              fallbackStart: ["Starting Location Workflow", "Building Location Prompts"],
              fallbackComplete: ["Location Prompts saved"],
              errorSteps: ["step_location_prompts"]
            },
            {
              id: "step_fenjing_prompts",
              label: "分镜提示词",
              step: "step_fenjing_prompts",
              startEvents: [{ event: "step_progress", step: "step_fenjing_prompts" }],
              completeEvents: [{ event: "phase_complete", step: "step_fenjing_prompts" }],
              fallbackStart: ["Starting Fenjing Prompt Workflow", "Building Fenjing Prompts"],
              fallbackComplete: ["Fenjing Prompts saved"],
              errorSteps: ["step_fenjing_prompts"]
            }
          ]
        },
        {
          id: "images",
          label: "图片并行",
          desc: "角色 / 地点 / 换装图",
          items: [
            {
              id: "step_character_images",
              label: "角色图",
              step: "step_character_images",
              dependsOn: ["step_character_prompts"],
              startEvents: [{ event: "step_progress", step: "step_character_images" }],
              completeEvents: [{ event: "phase_complete", step: "step_character_images" }],
              fallbackStart: ["Generating Character Images"],
              fallbackComplete: [],
              errorSteps: ["step_character_images"]
            },
            {
              id: "step_location_images",
              label: "地点图",
              step: "step_location_images",
              dependsOn: ["step_location_prompts", "step_fenjing_prompts"],
              startEvents: [{ event: "step_progress", step: "step_location_images" }],
              completeEvents: [{ event: "phase_complete", step: "step_location_images" }],
              fallbackStart: ["Generating Location Images"],
              fallbackComplete: [],
              errorSteps: ["step_location_images"]
            },
            {
              id: "step_cloth_images",
              label: "服装与换装",
              step: "step_cloth_images",
              dependsOn: ["step_character_images"],
              startEvents: [
                { event: "phase_start", phase: "step_cloth_images" },
                { event: "step_progress", step: "step_cloth_images" }
              ],
              completeEvents: [{ event: "phase_complete", phase: "step_cloth_images" }],
              fallbackStart: ["generate_cloth_images", "generate_cloth_changed_images"],
              fallbackComplete: ["generate_cloth_images: generated", "generate_cloth_changed_images: generated"],
              errorSteps: ["step_cloth_images"]
            }
          ]
        },
        {
          id: "tts",
          label: "语音并行",
          desc: "TTS 语音",
          items: [
            {
              id: "step_tts",
              label: "TTS 语音",
              step: "step_tts",
              startEvents: [{ event: "step_progress", step: "step_tts" }],
              completeEvents: [{ event: "phase_complete", step: "step_tts" }],
              fallbackStart: ["Generating TTS Audios"],
              fallbackComplete: [],
              errorSteps: ["step_tts"]
            }
          ]
        }
      ]
    },
    tree: {
      levels: [
        {
          id: "prompts",
          label: "提示词",
          nodes: [
            { id: "step_character_prompts", item: "step_character_prompts" },
            { id: "step_location_prompts", item: "step_location_prompts" },
            { id: "step_fenjing_prompts", item: "step_fenjing_prompts" }
          ]
        },
        {
          id: "generate",
          label: "生成",
          nodes: [
            { id: "step_character_images", item: "step_character_images" },
            { id: "step_location_images", item: "step_location_images" },
            { id: "step_tts", item: "step_tts" }
          ]
        },
        {
          id: "upload",
          label: "上传",
          nodes: [
            { id: "step_upload", step: "step_upload" }
          ]
        },
        {
          id: "cloth",
          label: "换装",
          nodes: [
            { id: "step_cloth_images", item: "step_cloth_images" }
          ]
        }
      ]
    }
  },
  fenjing: {
    title: "分镜图生成",
    steps: [
      {
        id: "step_download",
        label: "下载资产",
        desc: "下载提示词与参考图",
        startEvents: [{ event: "phase_start", phase: "step_download" }],
        completeEvents: [{ event: "phase_complete", phase: "step_download" }],
        fallbackStart: ["download_assets"],
        fallbackComplete: ["step_download completed"],
        errorPatterns: ["download_assets", "characters.jsonl", "location_prompts.jsonl"]
      },
      {
        id: "step_generate",
        label: "生成分镜图",
        desc: "分镜与换装图生成",
        startEvents: [
          { event: "phase_start", phase: "step_generate" },
          { event: "step_progress", step: "step_generate" }
        ],
        completeEvents: [{ event: "phase_complete", phase: "step_generate" }],
        fallbackStart: ["generate_cloth_images", "generate_cloth_changed_images", "chapter_completed"],
        fallbackComplete: ["step_generate completed"],
        errorPatterns: ["fenjing", "generate_images", "chapter"]
      },
      {
        id: "step_upload",
        label: "上传资产",
        desc: "上传到 TOS",
        startEvents: [{ event: "upload_start" }, { event: "upload_progress" }],
        completeEvents: [{ event: "upload_complete" }],
        fallbackStart: ["upload_assets start", "image uploaded"],
        fallbackComplete: ["upload_assets completed"],
        errorPatterns: ["upload", "uploaded"]
      }
    ],
    fallbackStart: ["fenjing workflow start"],
    stepAliases: { error: "step_generate" }
  },
  fenjing_generate: {
    title: "分镜图生成",
    steps: [
      {
        id: "step_download",
        label: "下载资产",
        desc: "下载提示词与参考图",
        startEvents: [{ event: "fenjing_generate_start" }, { event: "phase_start", phase: "step_download" }],
        completeEvents: [{ event: "phase_complete", phase: "step_download" }],
        fallbackStart: ["download_assets"],
        fallbackComplete: ["step_download completed"],
        errorPatterns: ["download_assets", "characters.jsonl", "location_prompts.jsonl"]
      },
      {
        id: "step_generate",
        label: "生成分镜图",
        desc: "分镜图生成到本地",
        startEvents: [
          { event: "phase_start", phase: "step_generate" },
          { event: "step_progress", step: "step_generate" }
        ],
        completeEvents: [{ event: "fenjing_generate_complete" }],
        fallbackStart: ["fenjing_image_start", "fenjing_image_attempt"],
        fallbackComplete: ["fenjing_generate completed"],
        errorPatterns: ["fenjing", "generate_images", "chapter"]
      },
      {
        id: "step_upload",
        label: "上传分镜图",
        desc: "上传分镜图到云存储",
        startEvents: [{ event: "fenjing_upload_start" }],
        completeEvents: [{ event: "fenjing_upload_complete" }],
        fallbackStart: ["fenjing_upload start"],
        fallbackComplete: ["fenjing_upload completed"],
        errorPatterns: ["upload", "uploaded"]
      }
    ],
    fallbackStart: ["fenjing_generate workflow start"],
    stepAliases: { error: "step_generate" }
  },
  fenjing_upload: {
    title: "上传分镜图",
    steps: [
      {
        id: "step_upload",
        label: "上传到 TOS",
        desc: "上传分镜图到云存储",
        startEvents: [{ event: "fenjing_upload_start" }],
        completeEvents: [{ event: "fenjing_upload_complete" }],
        fallbackStart: ["fenjing_upload start"],
        fallbackComplete: ["fenjing_upload completed"],
        errorPatterns: ["upload", "uploaded"]
      }
    ],
    fallbackStart: ["fenjing_upload workflow start"],
    stepAliases: { error: "step_upload" }
  },
  video: {
    title: "视频生成",
    steps: [
      {
        id: "step_prepare",
        label: "准备素材",
        desc: "检查分镜提示词",
        startEvents: [{ event: "flow_start" }],
        completeEvents: [],
        fallbackStart: ["video workflow start", "Prepared"],
        fallbackComplete: [],
        errorPatterns: ["No storyboard", "fenjing_prompts"]
      },
      {
        id: "step_video_prompts",
        label: "分镜提示词",
        desc: "生成视频分镜提示词",
        startEvents: [{ event: "phase_start", phase: "step_video_prompts" }],
        completeEvents: [{ event: "phase_complete", phase: "step_video_prompts" }],
        fallbackStart: ["PHASE 1", "Audio Durations"],
        fallbackComplete: ["step_video_prompts completed"],
        errorPatterns: ["audio", "duration", "video prompts"]
      },
      {
        id: "step_video_generation",
        label: "视频生成",
        desc: "提交任务并轮询",
        startEvents: [
          { event: "phase_start", phase: "step_video_generation" },
          { event: "step_progress", step: "step_video_generation" }
        ],
        completeEvents: [{ event: "phase_complete", phase: "step_video_generation" }],
        fallbackStart: ["PHASE 2", "video task submission", "Waiting for all"],
        fallbackComplete: ["step_video_generation completed"],
        errorPatterns: ["video task", "polling", "download"]
      },
      {
        id: "step_video_upload",
        label: "上传视频",
        desc: "上传到 TOS",
        startEvents: [{ event: "fenjing_video_upload_start" }, { event: "fenjing_video_uploaded" }],
        completeEvents: [{ event: "upload_complete" }],
        fallbackStart: ["fenjing_video_upload"],
        fallbackComplete: ["video upload completed"],
        errorPatterns: ["upload"]
      }
    ],
    fallbackStart: ["Video Workflow Started"],
    stepAliases: { start: "step_prepare", step_prepare: "step_prepare" }
  }
};

function getTreeConfig(flow) {
  return FLOW_TREE_CONFIG[flow] || null;
}

function getFlowStepLabel(flow, stepId) {
  const config = getTreeConfig(flow);
  if (!config || !stepId) {
    return stepId || "";
  }
  const step = (config.steps || []).find((item) => item.id === stepId);
  if (step) {
    return step.label || step.id || stepId;
  }
  const groups = config.parallel && Array.isArray(config.parallel.groups) ? config.parallel.groups : [];
  for (let i = 0; i < groups.length; i += 1) {
    const group = groups[i];
    const items = group && Array.isArray(group.items) ? group.items : [];
    const found = items.find((item) => item.id === stepId);
    if (found) {
      return found.label || found.id || stepId;
    }
  }
  return stepId;
}

function getPartialCompletedSteps(flow) {
  const steps = state.flowStatus?.flows?.[flow]?.steps || {};
  return Object.keys(steps).filter((stepId) => steps[stepId] === "partial_completed");
}

function shouldRenderFlowCard(flow) {
  if (flow === "fenjing_upload") {
    return false;
  }
  const status = getFlowStatus(flow);
  if (["pending", "running", "completed", "error", "partial_completed", "partial_returned"].includes(status)) {
    return true;
  }
  if (status === "waiting") {
    return isFlowTouched(state.selectedProject, flow);
  }
  return false;
}

function hasFallbackLog(logs, patterns) {
  return (patterns || []).some((pattern) => logs.some((line) => line.includes(pattern)));
}

function matchEventRule(event, rule) {
  if (!event || !rule) {
    return false;
  }
  if (event.event !== rule.event) {
    return false;
  }
  if (rule.step && event.step !== rule.step) {
    return false;
  }
  if (rule.phase && event.phase !== rule.phase) {
    return false;
  }
  return true;
}

function findLastMatchingEvent(events, rule) {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    if (matchEventRule(events[i], rule)) {
      return events[i];
    }
  }
  return null;
}

function hasMatchingEvent(events, rules) {
  return (rules || []).some((rule) => Boolean(findLastMatchingEvent(events, rule)));
}

function findLastEventIndex(events, predicate) {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    if (predicate(events[i], i)) {
      return i;
    }
  }
  return -1;
}

function getLatestRetryInfo(events) {
  if (!events || events.length === 0) {
    return null;
  }
  const idx = findLastEventIndex(events, (event) => {
    if (!event || !event.data) {
      return false;
    }
    const attempt = Number(event.data.attempt);
    const max = Number(event.data.max);
    return Number.isFinite(attempt) && Number.isFinite(max) && max > 0;
  });
  if (idx < 0) {
    return null;
  }
  const event = events[idx];
  return {
    event,
    attempt: Number(event.data.attempt),
    max: Number(event.data.max),
    step: event.step,
    phase: event.phase
  };
}

function isRetryForStep(step, retryInfo, config) {
  if (!step || !retryInfo) {
    return false;
  }
  if (retryInfo.step) {
    if (retryInfo.step === step.id) {
      return true;
    }
    const mapped = config && config.stepAliases ? config.stepAliases[retryInfo.step] : null;
    if (mapped && mapped === step.id) {
      return true;
    }
  }
  if (retryInfo.phase) {
    if (step.phase && step.phase === retryInfo.phase) {
      return true;
    }
    if (step.id === retryInfo.phase) {
      return true;
    }
  }
  return false;
}

function formatRetryStatus(retryInfo) {
  if (!retryInfo) {
    return "";
  }
  if (Number.isFinite(retryInfo.attempt) && Number.isFinite(retryInfo.max) && retryInfo.max > 0) {
    if (retryInfo.attempt <= 1) {
      return "进行中";
    }
    return `重试中 (${retryInfo.attempt}/${retryInfo.max})`;
  }
  return "重试中";
}

function getLastSuccessEventIndex(events, config) {
  if (!events || events.length === 0) {
    return -1;
  }
  let lastIndex = -1;
  const hasConfigMatch = (event) =>
    config && Array.isArray(config.steps)
      ? config.steps.some((step) => (step.completeEvents || []).some((rule) => matchEventRule(event, rule)))
      : false;
  events.forEach((event, idx) => {
    if (
      event.event === "flow_complete" ||
      event.event === "phase_complete" ||
      event.event === "upload_complete" ||
      hasConfigMatch(event)
    ) {
      lastIndex = idx;
    }
  });
  return lastIndex;
}

function resolveTreeFailure(events, config) {
  if (events.length > 0) {
    const lastSuccessIndex = getLastSuccessEventIndex(events, config);
    const errorIndex = findLastEventIndex(events, (e) => e.event === "flow_error");
    if (errorIndex > lastSuccessIndex) {
      const errorEvent = events[errorIndex];
      const mappedStepId = config.stepAliases ? config.stepAliases[errorEvent.step] : null;
      const stepById = config.steps.find((s) => s.id === (mappedStepId || errorEvent.step));
      const stepByPhase = config.steps.find((s) => s.phase && s.phase === errorEvent.phase);
      const stepId = (stepById || stepByPhase) ? (stepById ? stepById.id : stepByPhase.id) : null;
      return { stepId, message: errorEvent.message || "执行失败" };
    }
  }
  return null;
}

function parseJobProgress(job) {
  if (!job) {
    return "";
  }
  const flow = getFlowFromJob(job);
  if (!flow) {
    return "";
  }
  const flowState = state.flowStatus && state.flowStatus.flows ? state.flowStatus.flows[flow] : null;
  if (!flowState || !flowState.steps) {
    return "";
  }
  const steps = flowState.steps || {};
  const config = getTreeConfig(flow);
  const stepOrder = config ? config.steps.map((step) => step.id) : Object.keys(steps);
  const states = stepOrder.map((id) => {
    const status = steps[id] || "";
    const started = status === "running" || status === "completed" || status === "error";
    const completed = status === "completed";
    const failed = status === "error";
    return { id, started, completed, failed };
  });
  if (states.some((item) => item.failed)) {
    return "执行失败";
  }
  if (states.length > 0 && states.every((item) => item.completed)) {
    return "全部完成";
  }
  const running = states.find((item) => item.started && !item.completed);
  const next = states.find((item) => !item.started && !item.completed);
  if (config && running) {
    const runningStep = config.steps.find((step) => step.id === running.id);
    return runningStep ? (runningStep.desc || runningStep.label) : "进行中";
  }
  if (config && next) {
    const nextStep = config.steps.find((step) => step.id === next.id);
    return nextStep ? (nextStep.desc || nextStep.label) : "等待中";
  }
  return "等待中";
}

function buildTreeProgressElement(flow) {
  const config = getTreeConfig(flow || "auto_storyboard");
  if (!config) {
    return document.createElement("div");
  }
  if (flow === "visual_audio_assets") {
    return buildVisualAudioTreeElement(config);
  }
  const container = document.createElement("div");
  container.className = "flow-tree";
  const header = document.createElement("div");
  header.className = "tree-header";
  const headerTitle = document.createElement("span");
  headerTitle.className = "tree-header-title";
  headerTitle.textContent = config.title;
  const logButton = document.createElement("button");
  logButton.className = "flow-log-btn";
  logButton.textContent = "查看日志";
  header.appendChild(headerTitle);
  header.appendChild(logButton);
  container.appendChild(header);

  const stepsWrap = document.createElement("div");
  stepsWrap.className = "tree-steps";
  config.steps.forEach((step, index) => {
    const stepEl = document.createElement("div");
    stepEl.className = "tree-step";
    stepEl.dataset.step = step.id;
    const node = document.createElement("div");
    node.className = "tree-node";
    const content = document.createElement("div");
    content.className = "tree-content";
    const label = document.createElement("div");
    label.className = "tree-label";
    label.textContent = step.label;
    const desc = document.createElement("div");
    desc.className = "tree-desc";
    desc.textContent = step.desc;
    const status = document.createElement("div");
    status.className = "tree-status";
    status.textContent = "等待中";
    content.appendChild(label);
    content.appendChild(desc);
    content.appendChild(status);
    stepEl.appendChild(node);
    stepEl.appendChild(content);
    stepsWrap.appendChild(stepEl);
    if (index < config.steps.length - 1) {
      const connector = document.createElement("div");
      connector.className = "tree-connector";
      stepsWrap.appendChild(connector);
    }
  });
  container.appendChild(stepsWrap);

  const nextWrap = document.createElement("div");
  nextWrap.className = "tree-next";
  const nextLabel = document.createElement("div");
  nextLabel.className = "tree-next-label";
  nextLabel.textContent = "下一步";
  const nextDesc = document.createElement("div");
  nextDesc.className = "tree-next-desc";
  nextDesc.textContent = "等待中...";
  nextWrap.appendChild(nextLabel);
  nextWrap.appendChild(nextDesc);
  container.appendChild(nextWrap);
  const actionWrap = document.createElement("div");
  actionWrap.className = "tree-actions hidden";
  container.appendChild(actionWrap);
  return container;
}

function updateTreeDiagram(job, container) {
  if (!job) {
    return;
  }

  const logs = Array.isArray(job.log_tail) ? job.log_tail : [];
  const flow = getFlowFromJob(job);
  
  const config = getTreeConfig(flow);
  if (!config) {
    return;
  }
  const events = extractStructuredEvents(logs, flow);
  
  if (!container) {
    return;
  }
  if (job.status === "pending") {
    const treeContent = container.querySelector(".tree-content");
    if (treeContent) {
      treeContent.style.display = "none";
    }
    updateTreeActions(job, container);
    return;
  }
  if (flow === "visual_audio_assets") {
    updateVisualAudioTreeDiagram(logs, events, config, container);
    updateTreeActions(job, container);
    return;
  }
  if (flow !== "auto_storyboard") {
    updateTreeDiagramGeneric(flow, logs, events, config, container);
    updateTreeActions(job, container);
    return;
  }
  
  const steps = container.querySelectorAll(".tree-step");
  const connectors = container.querySelectorAll(".tree-connector");
  const nextDesc = container.querySelector(".tree-next-desc");
  const stepElements = {};
  config.steps.forEach((step) => {
    const stepEl = container.querySelector(`.tree-step[data-step="${step.id}"]`);
    if (stepEl) {
      stepElements[step.id] = {
        stepEl,
        statusEl: stepEl.querySelector(".tree-status")
      };
    }
  });
  const step1Step = stepElements.step_extract ? stepElements.step_extract.stepEl : null;
  const step2Step = stepElements.step_storyboard ? stepElements.step_storyboard.stepEl : null;
  const step3UploadStep = stepElements.step_upload ? stepElements.step_upload.stepEl : null;
  const step1Status = stepElements.step_extract ? stepElements.step_extract.statusEl : null;
  const step2Status = stepElements.step_storyboard ? stepElements.step_storyboard.statusEl : null;
  const step3UploadStatus = stepElements.step_upload ? stepElements.step_upload.statusEl : null;
  const connector1 = connectors[0];
  const connector2 = connectors[1];
  if (!step1Step || !step2Step || !step3UploadStep || !nextDesc || !step1Status || !step2Status || !step3UploadStatus) {
    return;
  }
  
  steps.forEach((step) => {
    step.className = "tree-step";
  });
  connectors.forEach((connector) => {
    connector.className = "tree-connector";
  });
  
  const flowSteps = (state.flowStatus && state.flowStatus.flows && state.flowStatus.flows[flow])
    ? state.flowStatus.flows[flow].steps || {}
    : {};
  const useFlowStatus = Object.keys(flowSteps).length > 0;

  if (useFlowStatus) {
    const stepOrder = config.steps.map((step) => step.id);
    const stepMap = {
      step_extract: stepElements.step_extract,
      step_storyboard: stepElements.step_storyboard,
      step_upload: stepElements.step_upload,
    };
    const stepStates = stepOrder.map((id) => {
      const status = flowSteps[id] || "";
      const started = status === "running" || status === "completed" || status === "error";
      const completed = status === "completed";
      const failed = status === "error";
      return { id, started, completed, failed };
    });
    stepStates.forEach((stateItem, idx) => {
      const stepEl = stepMap[stateItem.id];
      if (!stepEl || !stepEl.stepEl || !stepEl.statusEl) {
        return;
      }
      if (stateItem.failed) {
        stepEl.stepEl.classList.add("error");
        stepEl.statusEl.textContent = "失败";
      } else if (stateItem.completed) {
        stepEl.stepEl.classList.add("completed");
        stepEl.statusEl.textContent = "已完成";
        if (connectors[idx]) {
          connectors[idx].classList.add("completed");
        }
      } else if (stateItem.started) {
        stepEl.stepEl.classList.add("running");
        stepEl.statusEl.textContent = "进行中";
      } else {
        stepEl.statusEl.textContent = "等待中";
      }
    });
    const failedStep = stepStates.find((item) => item.failed);
    if (failedStep) {
      nextDesc.textContent = "执行失败";
    } else if (stepStates.every((item) => item.completed)) {
      nextDesc.textContent = "全部完成";
    } else {
      const running = stepStates.find((item) => item.started && !item.completed);
      const next = stepStates.find((item) => !item.started && !item.completed);
      if (running) {
        const runningStep = config.steps.find((step) => step.id === running.id);
        nextDesc.textContent = runningStep ? (runningStep.desc || runningStep.label) : "进行中";
      } else if (next) {
        const nextStep = config.steps.find((step) => step.id === next.id);
        nextDesc.textContent = nextStep ? (nextStep.desc || nextStep.label) : "等待中";
      }
    }
    updateTreeActions(job, container);
    return;
  }

  [step1Step, step2Step, step3UploadStep].forEach((stepEl) => {
    if (stepEl) {
      stepEl.className = "tree-step";
    }
  });
  if (step1Status) {
    step1Status.textContent = "等待中";
  }
  if (step2Status) {
    step2Status.textContent = "等待中";
  }
  if (step3UploadStatus) {
    step3UploadStatus.textContent = "等待中";
  }
  if (connector1) {
    connector1.className = "tree-connector";
    connector1.style.display = "";
  }
  if (connector2) {
    connector2.className = "tree-connector";
    connector2.style.display = "";
  }
  step2Step.style.display = "";
  step3UploadStep.style.display = "";
  nextDesc.textContent = "等待中...";
  updateTreeActions(job, container);
  return;
}

function updateTreeDiagramGeneric(flow, logs, events, config, container) {
  const steps = Array.from(container.querySelectorAll(".tree-step"));
  const connectors = Array.from(container.querySelectorAll(".tree-connector"));
  const nextDesc = container.querySelector(".tree-next-desc");
  if (!nextDesc) {
    return;
  }
  const stepElements = {};
  config.steps.forEach((step) => {
    const stepEl = container.querySelector(`.tree-step[data-step="${step.id}"]`);
    if (stepEl) {
      stepElements[step.id] = {
        stepEl,
        statusEl: stepEl.querySelector(".tree-status")
      };
    }
  });
  steps.forEach((step) => {
    step.className = "tree-step";
  });
  connectors.forEach((connector) => {
    connector.className = "tree-connector";
  });
  let flowSteps = (state.flowStatus && state.flowStatus.flows && state.flowStatus.flows[flow])
    ? state.flowStatus.flows[flow].steps || {}
    : {};
  if (flow === "fenjing_generate") {
    const uploadSteps = (state.flowStatus && state.flowStatus.flows && state.flowStatus.flows.fenjing_upload)
      ? state.flowStatus.flows.fenjing_upload.steps || {}
      : {};
    flowSteps = Object.assign({}, flowSteps, uploadSteps);
  }
  const useFlowStatus = Object.keys(flowSteps).length > 0;
  if (!useFlowStatus) {
    config.steps.forEach((step) => {
      const stepEl = stepElements[step.id];
      if (stepEl && stepEl.statusEl) {
        stepEl.stepEl.className = "tree-step";
        stepEl.statusEl.textContent = "等待中";
      }
    });
    connectors.forEach((connector) => {
      connector.className = "tree-connector";
    });
    nextDesc.textContent = "等待中...";
  } else {
    const stepStates = config.steps.map((step) => {
      const status = flowSteps[step.id] || "";
      const started = status === "running" || status === "completed" || status === "error";
      const completed = status === "completed";
      const failed = status === "error";
      return { step, started, completed, failed };
    });
    stepStates.forEach((stateItem, idx) => {
      const stepEl = stepElements[stateItem.step.id];
      if (!stepEl || !stepEl.statusEl) {
        return;
      }
      if (stateItem.failed) {
        stepEl.stepEl.classList.add("error");
        stepEl.statusEl.textContent = "失败";
      } else if (stateItem.completed) {
        stepEl.stepEl.classList.add("completed");
        stepEl.statusEl.textContent = "已完成";
        if (connectors[idx]) {
          connectors[idx].classList.add("completed");
        }
      } else if (stateItem.started) {
        stepEl.stepEl.classList.add("running");
        stepEl.statusEl.textContent = "进行中";
      } else {
        stepEl.statusEl.textContent = "等待中";
      }
    });
    if (stepStates.some((item) => item.failed)) {
      nextDesc.textContent = "执行失败";
    } else if (stepStates.length > 0 && stepStates.every((item) => item.completed)) {
      nextDesc.textContent = "全部完成";
    } else {
      const running = stepStates.find((item) => item.started && !item.completed);
      const next = stepStates.find((item) => !item.started && !item.completed);
      if (running) {
        nextDesc.textContent = running.step.desc || running.step.label || "进行中";
      } else if (next) {
        nextDesc.textContent = next.step.desc || next.step.label || "等待中";
      } else {
        nextDesc.textContent = "等待中...";
      }
    }
  }
  if (flow !== "auto_storyboard") {
    config.steps.forEach((step) => {
      const stepEl = stepElements[step.id] ? stepElements[step.id].stepEl : null;
      if (stepEl) {
        stepEl.style.display = "";
      }
    });
    connectors.forEach((connector) => {
      connector.style.display = "";
    });
  }
}

function renderJobs() {
  const container = qs("jobList");
  container.innerHTML = "";
  const aggregated = aggregateJobs(state.jobs).filter((group) => shouldRenderFlowCard(group.stageType)).slice(0, 4);
  if (aggregated.length === 0) {
    const empty = document.createElement("div");
    empty.className = "status-tag";
    empty.textContent = "暂无任务";
    container.appendChild(empty);
    updateBatchFlowButtons(state.assetsCache);
    return;
  }
  aggregated.forEach((group) => {
    const job = group.latestJob;
    const item = document.createElement("div");
    item.className = "job-item";
    let effectiveStatus = job.status || "";
    if (group.stageType === "fenjing_generate") {
      const uploadFlowStatus = state.flowStatus && state.flowStatus.flows && state.flowStatus.flows.fenjing_upload;
      if (uploadFlowStatus && uploadFlowStatus.status === "running") {
        effectiveStatus = "running";
      }
    }
    item.dataset.status = effectiveStatus;
    const header = document.createElement("div");
    header.className = "job-meta";
    const stageLabel = formatJobType(`run_${group.stageType}`);
    const statusLabel = formatJobStatus(job.status);
    const timeLabel = formatJobTime(job.updated_at || job.created_at);
    let metaText = `${stageLabel} · ${statusLabel} · ${timeLabel}`;
    if (group.successCount > 0 && job.status !== "success") {
      metaText += ` · 历史${group.successCount}次成功`;
    }
    header.textContent = metaText;
    item.appendChild(header);
    const project = document.createElement("div");
    project.className = "job-project";
    project.textContent = `项目：${job.project || "-"}`;
    item.appendChild(project);
    
    const progress = parseJobProgress(job);
    if (progress) {
      const progressDiv = document.createElement("div");
      progressDiv.className = "job-progress";
      progressDiv.textContent = progress;
      item.appendChild(progressDiv);
    }

    const flow = group.stageType;
    if (getTreeConfig(flow)) {
      const tree = buildTreeProgressElement(flow);
      const logButton = tree.querySelector(".flow-log-btn");
      if (logButton) {
        logButton.onclick = showLogModal;
      }
      updateTreeDiagram(job, tree);
      item.appendChild(tree);
    }

    const partialSteps = getPartialCompletedSteps(flow);
    if (partialSteps.length > 0) {
      const hint = document.createElement("div");
      hint.className = "job-partial-hint";
      const labels = partialSteps.map((stepId) => getFlowStepLabel(flow, stepId)).filter(Boolean);
      const labelText = labels.length > 0 ? `（${labels.join("、")}）` : "";
      hint.textContent = `阶段部分完成${labelText}，请关注并手动触发剩余 phase`;
      item.appendChild(hint);
    }
    
    if (job.error) {
      const err = document.createElement("div");
      err.className = "job-error";
      err.textContent = `错误：${job.error}`;
      item.appendChild(err);
    }
    if (job.status === "success" && job.partial_failed && job.partial_failed_count > 0) {
      const failTag = document.createElement("div");
      failTag.className = "job-partial-fail";
      const typeLabels = {
        character: "角色",
        location: "场景",
        fenjing: "分镜",
        video: "视频",
        cloth: "服装",
        cloth_changed: "换装",
      };
      const typeNames = (job.partial_failed_types || []).map((t) => typeLabels[t] || t).join("、");
      failTag.textContent = `局部失败 ${job.partial_failed_count} 项（${typeNames}）`;
      failTag.style.cursor = "pointer";
      failTag.onclick = () => {
        applyFailedAssetFilter(job.id);
      };
      item.appendChild(failTag);
    }
    if (group.failedJobs.length > 0) {
      const historyDiv = document.createElement("div");
      historyDiv.className = "job-history-toggle";
      historyDiv.textContent = `查看 ${group.failedJobs.length} 条失败记录`;
      historyDiv.style.cursor = "pointer";
      historyDiv.style.color = "#666";
      historyDiv.style.fontSize = "12px";
      historyDiv.style.marginTop = "8px";
      let expanded = false;
      const historyList = document.createElement("div");
      historyList.className = "job-history-list";
      historyList.style.display = "none";
      historyList.style.marginTop = "8px";
      historyList.style.paddingLeft = "12px";
      historyList.style.borderLeft = "2px solid #eee";
      group.failedJobs.forEach((failedJob) => {
        const failedItem = document.createElement("div");
        failedItem.className = "job-history-item";
        failedItem.style.fontSize = "12px";
        failedItem.style.color = "#888";
        failedItem.style.marginBottom = "4px";
        const failedTime = formatJobTime(failedJob.updated_at || failedJob.created_at);
        failedItem.textContent = `${failedTime} · ${failedJob.error || "未知错误"}`;
        historyList.appendChild(failedItem);
      });
      historyDiv.onclick = () => {
        expanded = !expanded;
        historyList.style.display = expanded ? "block" : "none";
        historyDiv.textContent = expanded ? `收起失败记录` : `查看 ${group.failedJobs.length} 条失败记录`;
      };
      item.appendChild(historyDiv);
      item.appendChild(historyList);
    }
    container.appendChild(item);
  });
  updateBatchFlowButtons(state.assetsCache);
  const logModal = qs("logModal");
  if (logModal && !logModal.classList.contains("hidden")) {
    filterLogContent();
  }
}

function assetItem(path, options) {
  const div = document.createElement("div");
  div.className = "asset-item";
  const img = document.createElement("img");
  img.src = mediaUrl(path);
  img.loading = "lazy";
  div.appendChild(img);
  const label = document.createElement("div");
  label.textContent = path.split("/").slice(-1)[0];
  div.appendChild(label);
  return div;
}

function videoItem(path) {
  const div = document.createElement("div");
  div.className = "asset-item";
  const video = document.createElement("video");
  video.src = mediaUrl(path);
  video.controls = true;
  div.appendChild(video);
  const label = document.createElement("div");
  label.textContent = path.split("/").slice(-1)[0];
  div.appendChild(label);
  return div;
}

function videoListItem(path, isActive, onSelect, isGenerating) {
  const card = document.createElement("div");
  card.className = "video-card" + (isActive ? " active" : "");
  const title = document.createElement("div");
  title.className = "video-title";
  const name = path.split("/").slice(-1)[0];
  const match = name.match(/fenjing_(\d+)(?:_video|_\d+)\.mp4/i);
  const isCandidate = /fenjing_\d+_\d+\.mp4/i.test(name);
  if (match) {
    title.textContent = isCandidate ? `分镜 ${match[1]} (候选)` : `分镜 ${match[1]}`;
  } else {
    title.textContent = name;
  }
  card.appendChild(title);
  card.onclick = onSelect;
  return card;
}

function renderTable(container, columns, rows) {
  container.innerHTML = "";
  if (!rows || rows.length === 0) {
    const empty = document.createElement("div");
    empty.className = "status-tag";
    empty.textContent = "暂无数据";
    container.appendChild(empty);
    return;
  }
  const table = document.createElement("table");
  table.className = "data-table";
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  columns.forEach((col) => {
    const th = document.createElement("th");
    th.textContent = col.label;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);
  const tbody = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    columns.forEach((col) => {
      const td = document.createElement("td");
      const val = row[col.key];
      td.textContent = val === undefined || val === null ? "" : String(val);
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  container.appendChild(table);
}

function renderTables(data) {
  const charContainer = qs("tableCharacters");
  const locContainer = qs("tableLocations");
  const sbContainer = qs("tableStoryboardsBody");
  const storyboards = data.storyboard_table || [];
  const chapters = data.chapters || [];
  const tableChapters =
    chapters.length > 0
      ? chapters
      : Array.from(
          new Set(storyboards.map((row) => row && row.chapter).filter((name) => name))
        ).map((name) => ({ name }));
  if (tableChapters.length > 0) {
    const current = renderChapterTabs(
      "storyboardTableTabs",
      tableChapters,
      state.storyboardTableChapterTab,
      (name) => {
        state.storyboardTableChapterTab = name;
        renderTables(data);
      }
    );
    state.storyboardTableChapterTab = current;
  } else {
    const tabBox = qs("storyboardTableTabs");
    if (tabBox) {
      tabBox.innerHTML = "";
    }
    state.storyboardTableChapterTab = "";
  }
  const filteredStoryboards = state.storyboardTableChapterTab
    ? storyboards.filter((row) => row.chapter === state.storyboardTableChapterTab)
    : storyboards;
  renderTable(
    charContainer,
    [
      { key: "Character_Id", label: "角色ID" },
      { key: "Character_name", label: "角色名" },
      { key: "Alias", label: "别名" },
      { key: "attribute", label: "属性" },
      { key: "Age_group", label: "年龄段" },
      { key: "Sex", label: "性别" },
      { key: "Appearance", label: "外观" },
      { key: "Default_Outfit_id", label: "默认服装ID" },
      { key: "Default_Outfit_Description", label: "默认服装描述" },
      { key: "Default_Shoes", label: "默认鞋子" },
    ],
    data.character_table || []
  );
  renderTable(
    locContainer,
    [
      { key: "Location_ID", label: "地点ID" },
      { key: "Location", label: "地点名" },
      { key: "Location_description", label: "地点描述" },
    ],
    data.location_table || []
  );
  renderTable(
    sbContainer,
    [
      { key: "chapter", label: "章节" },
      { key: "zhangjie_id", label: "章节ID" },
      { key: "Storyboard_id", label: "分镜ID" },
      { key: "Era", label: "时代" },
      { key: "Time", label: "时间" },
      { key: "Location", label: "地点" },
      { key: "Location_Id", label: "地点ID" },
      { key: "Characters", label: "角色" },
      { key: "Action", label: "动作" },
    ],
    filteredStoryboards
  );
}

function showConfigStatus(message, isError) {
  const box = qs("configStatus");
  if (!box) {
    return;
  }
  if (!message) {
    box.classList.add("hidden");
    box.classList.remove("error");
    box.textContent = "";
    return;
  }
  box.classList.remove("hidden");
  box.classList.toggle("error", Boolean(isError));
  box.textContent = message;
}

function showAuthConfigStatus(message, isError) {
  const box = qs("authConfigStatus");
  if (!box) {
    return;
  }
  if (!message) {
    box.classList.add("hidden");
    box.classList.remove("error");
    box.textContent = "";
    return;
  }
  box.classList.remove("hidden");
  box.classList.toggle("error", Boolean(isError));
  box.textContent = message;
}

function getConfigScope() {
  const select = qs("configScope");
  const value = select ? select.value : state.configScope;
  state.configScope = value || "project";
  return state.configScope;
}

function getConfigItemsForScope() {
  const scope = getConfigScope();
  return scope === "global" ? state.configGlobalItems : state.configItems;
}

function getAuthItemsForScope() {
  const scope = getConfigScope();
  return scope === "global" ? state.authGlobalItems : state.authItems;
}

function getGlobalConfigValue(id) {
  const item = (state.configGlobalItems || []).find((entry) => entry.id === id);
  return item ? item.value : undefined;
}

function renderConfigTable() {
  const table = qs("configTable");
  if (!table) {
    return;
  }
  const tbody = table.querySelector("tbody");
  if (!tbody) {
    return;
  }
  tbody.innerHTML = "";
  const items = getConfigItemsForScope();
  if (!items || items.length === 0) {
    return;
  }
  const scope = getConfigScope();
  const disableInput = scope === "project" && !state.selectedProject;
  items.forEach((item) => {
    const tr = document.createElement("tr");
    const stageCell = document.createElement("td");
    stageCell.textContent = item.stage || "";
    tr.appendChild(stageCell);
    const keyCell = document.createElement("td");
    keyCell.textContent = item.key || item.id || "";
    tr.appendChild(keyCell);
    const valueCell = document.createElement("td");
    const input = document.createElement("input");
    input.type = "number";
    input.step = item.type === "int" ? "1" : "any";
    input.value = item.value !== undefined && item.value !== null ? String(item.value) : "";
    input.dataset.configId = item.id;
    input.dataset.configType = item.type || "float";
    if (disableInput) {
      input.disabled = true;
    }
    valueCell.appendChild(input);
    tr.appendChild(valueCell);
    const sourceCell = document.createElement("td");
    sourceCell.textContent = item.source || "";
    tr.appendChild(sourceCell);
    const defaultCell = document.createElement("td");
    defaultCell.textContent = item.default !== undefined && item.default !== null ? String(item.default) : "";
    tr.appendChild(defaultCell);
    const rangeCell = document.createElement("td");
    const minText = item.min !== undefined && item.min !== null ? String(item.min) : "";
    const maxText = item.max !== undefined && item.max !== null ? String(item.max) : "";
    rangeCell.textContent = minText || maxText ? `${minText}-${maxText}` : "";
    tr.appendChild(rangeCell);
    const descCell = document.createElement("td");
    descCell.textContent = item.description || "";
    tr.appendChild(descCell);
    tbody.appendChild(tr);
  });
}

function renderAuthTable() {
  const table = qs("authConfigTable");
  if (!table) {
    return;
  }
  const tbody = table.querySelector("tbody");
  if (!tbody) {
    return;
  }
  tbody.innerHTML = "";
  const items = getAuthItemsForScope();
  if (!items || items.length === 0) {
    return;
  }
  const scope = getConfigScope();
  const disableInput = scope === "project" && !state.selectedProject;
  items.forEach((item) => {
    const tr = document.createElement("tr");
    const stageCell = document.createElement("td");
    stageCell.textContent = item.stage || "";
    tr.appendChild(stageCell);
    const keyCell = document.createElement("td");
    keyCell.textContent = item.key || item.id || "";
    tr.appendChild(keyCell);
    const valueCell = document.createElement("td");
    const input = document.createElement("input");
    input.type = item.sensitive ? "password" : "text";
    input.value = item.value !== undefined && item.value !== null ? String(item.value) : "";
    if (item.sensitive && item.stored && !input.value) {
      input.placeholder = "已设置";
    }
    input.dataset.authId = item.id;
    if (disableInput) {
      input.disabled = true;
    }
    valueCell.appendChild(input);
    tr.appendChild(valueCell);
    const sourceCell = document.createElement("td");
    sourceCell.textContent = item.source || "";
    tr.appendChild(sourceCell);
    const defaultCell = document.createElement("td");
    defaultCell.textContent = item.default !== undefined && item.default !== null ? String(item.default) : "";
    tr.appendChild(defaultCell);
    const descCell = document.createElement("td");
    descCell.textContent = item.description || "";
    tr.appendChild(descCell);
    tbody.appendChild(tr);
  });
}

async function loadConfigData() {
  showConfigStatus("加载中", false);
  try {
    const globalData = await apiGet("/api/config/concurrency");
    state.configGlobalItems = globalData.items || [];
    if (state.selectedProject) {
      const project = encodeURIComponent(state.selectedProject);
      const projectData = await apiGet(`/api/config/concurrency?project=${project}`);
      state.configItems = projectData.items || [];
    } else {
      state.configItems = [];
      if (getConfigScope() === "project") {
        state.configScope = "global";
        const select = qs("configScope");
        if (select) {
          select.value = "global";
        }
      }
    }
    renderConfigTable();
    if (!state.selectedProject && getConfigScope() === "project") {
      showConfigStatus("请选择项目以查看项目覆盖", true);
    } else {
      showConfigStatus("已刷新", false);
    }
  } catch (err) {
    showConfigStatus("加载失败", true);
  }
}

async function loadAuthConfigData() {
  showAuthConfigStatus("加载中", false);
  try {
    const globalData = await apiGet("/api/config/auth");
    state.authGlobalItems = globalData.items || [];
    if (state.selectedProject) {
      const project = encodeURIComponent(state.selectedProject);
      const projectData = await apiGet(`/api/config/auth?project=${project}`);
      state.authItems = projectData.items || [];
    } else {
      state.authItems = [];
      if (getConfigScope() === "project") {
        state.configScope = "global";
        const select = qs("configScope");
        if (select) {
          select.value = "global";
        }
      }
    }
    renderAuthTable();
    if (!state.selectedProject && getConfigScope() === "project") {
      showAuthConfigStatus("请选择项目以查看项目覆盖", true);
    } else {
      showAuthConfigStatus("已刷新", false);
    }
  } catch (err) {
    showAuthConfigStatus("加载失败", true);
  }
}

function collectConfigUpdates() {
  const scope = getConfigScope();
  const items = getConfigItemsForScope();
  const updates = {};
  items.forEach((item) => {
    const input = document.querySelector(`input[data-config-id="${item.id}"]`);
    if (!input) {
      return;
    }
    const raw = input.value.trim();
    if (!raw) {
      return;
    }
    const isInt = (input.dataset.configType || item.type) === "int";
    const parsed = isInt ? parseInt(raw, 10) : parseFloat(raw);
    if (Number.isNaN(parsed)) {
      return;
    }
    const baseValue = scope === "global" ? item.default : getGlobalConfigValue(item.id);
    if (baseValue !== undefined && baseValue !== null && Number(baseValue) === Number(parsed)) {
      return;
    }
    updates[item.id] = parsed;
  });
  return updates;
}

function collectAuthUpdates() {
  const items = getAuthItemsForScope();
  const updates = {};
  items.forEach((item) => {
    const input = document.querySelector(`input[data-auth-id="${item.id}"]`);
    if (!input) {
      return;
    }
    const raw = input.value.trim();
    if (!raw) {
      return;
    }
    updates[item.id] = raw;
  });
  return updates;
}

function collectResetUpdates() {
  const scope = getConfigScope();
  const items = getConfigItemsForScope();
  const updates = {};
  items.forEach((item) => {
    if (item.source === scope) {
      updates[item.id] = null;
    }
  });
  return updates;
}

function collectAuthResetUpdates() {
  const scope = getConfigScope();
  const items = getAuthItemsForScope();
  const updates = {};
  items.forEach((item) => {
    if (item.source === scope) {
      updates[item.id] = null;
    }
  });
  return updates;
}

async function saveConfigOverrides() {
  const scope = getConfigScope();
  if (scope === "project" && !state.selectedProject) {
    showConfigStatus("请先选择项目", true);
    return;
  }
  const updates = collectConfigUpdates();
  if (!updates || Object.keys(updates).length === 0) {
    showConfigStatus("没有需要保存的变更", false);
    return;
  }
  try {
    const project = encodeURIComponent(state.selectedProject || "");
    await apiPatch(`/api/config/concurrency?project=${project}`, { scope, items: updates });
    await loadConfigData();
    showConfigStatus("已保存", false);
  } catch (err) {
    showConfigStatus("保存失败", true);
  }
}

async function saveAuthConfigOverrides() {
  const scope = getConfigScope();
  if (scope === "project" && !state.selectedProject) {
    showAuthConfigStatus("请先选择项目", true);
    return;
  }
  const updates = collectAuthUpdates();
  if (!updates || Object.keys(updates).length === 0) {
    showAuthConfigStatus("没有需要保存的变更", false);
    return;
  }
  try {
    const project = encodeURIComponent(state.selectedProject || "");
    await apiPatch(`/api/config/auth?project=${project}`, { scope, items: updates });
    await loadAuthConfigData();
    showAuthConfigStatus("已保存", false);
  } catch (err) {
    showAuthConfigStatus("保存失败", true);
  }
}

async function resetConfigOverrides() {
  const scope = getConfigScope();
  if (scope === "project" && !state.selectedProject) {
    showConfigStatus("请先选择项目", true);
    return;
  }
  const updates = collectResetUpdates();
  if (!updates || Object.keys(updates).length === 0) {
    showConfigStatus("没有可重置的覆盖", false);
    return;
  }
  try {
    const project = encodeURIComponent(state.selectedProject || "");
    await apiPatch(`/api/config/concurrency?project=${project}`, { scope, items: updates });
    await loadConfigData();
    showConfigStatus("已重置", false);
  } catch (err) {
    showConfigStatus("重置失败", true);
  }
}

async function resetAuthConfigOverrides() {
  const scope = getConfigScope();
  if (scope === "project" && !state.selectedProject) {
    showAuthConfigStatus("请先选择项目", true);
    return;
  }
  const updates = collectAuthResetUpdates();
  if (!updates || Object.keys(updates).length === 0) {
    showAuthConfigStatus("没有可重置的覆盖", false);
    return;
  }
  try {
    const project = encodeURIComponent(state.selectedProject || "");
    await apiPatch(`/api/config/auth?project=${project}`, { scope, items: updates });
    await loadAuthConfigData();
    showAuthConfigStatus("已重置", false);
  } catch (err) {
    showAuthConfigStatus("重置失败", true);
  }
}

function setActiveTableTab(tabName) {
  state.tableTab = tabName;
  const tabs = document.querySelectorAll("#tableTabs .tab");
  tabs.forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.tab === tabName);
  });
  qs("tableCharacters").classList.toggle("hidden", tabName !== "characters");
  qs("tableLocations").classList.toggle("hidden", tabName !== "locations");
  qs("tableStoryboards").classList.toggle("hidden", tabName !== "storyboards");
}

function setActiveMainTab(tabName) {
  state.mainTab = tabName;
  saveMainTabPreference(tabName);
  syncUrlState(false);
  document.querySelectorAll(".project-main-tabs .tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.mainTab === tabName);
  });
  qs("tabBatch").classList.toggle("hidden", tabName !== "batch");
  qs("tabCharacters").classList.toggle("hidden", tabName !== "characters");
  qs("tabClothChanged").classList.toggle("hidden", tabName !== "cloth-changed");
  qs("tabCloth").classList.toggle("hidden", tabName !== "cloth");
  qs("tabLocations").classList.toggle("hidden", tabName !== "locations");
  qs("tabStoryboards").classList.toggle("hidden", tabName !== "storyboards");
  qs("tabVideos").classList.toggle("hidden", tabName !== "videos");
  qs("tabTables").classList.toggle("hidden", tabName !== "tables");
  const projectBottom = document.querySelector(".project-bottom");
  if (projectBottom) {
    projectBottom.classList.toggle("hidden", tabName !== "batch");
  }
  const projectContent = document.querySelector(".project-content");
  if (projectContent) {
    projectContent.classList.toggle("batch-mode", tabName === "batch");
  }
}

function renderChapterTabs(containerId, chapters, activeName, onSelect) {
  const tabBox = qs(containerId);
  tabBox.innerHTML = "";
  if (!chapters || chapters.length === 0) {
    return "";
  }
  let current = activeName;
  if (!current || !chapters.find((c) => c.name === current)) {
    current = chapters[0].name;
  }
  chapters.forEach((chapter, index) => {
    const btn = document.createElement("button");
    btn.className = "tab" + (chapter.name === current ? " active" : "");
    btn.dataset.tab = chapter.name;
    btn.textContent = formatChapterTitle(chapter.name, index);
    btn.onclick = () => onSelect(chapter.name);
    tabBox.appendChild(btn);
  });
  return current;
}

function showHomeView() {
  qs("homeView").classList.remove("hidden");
  qs("projectView").classList.add("hidden");
  qs("homeActions").classList.remove("hidden");
}

function showProjectView() {
  qs("homeView").classList.add("hidden");
  qs("projectView").classList.remove("hidden");
  qs("homeActions").classList.add("hidden");
  qs("projectTitle").textContent = state.selectedProject ? `项目：${state.selectedProject}` : "";
}

async function refreshProjects() {
  const data = await apiGet("/api/projects");
  state.projects = data.projects || [];
  cleanFlowTouchedByProjects(state.projects);
  if (state.selectedProject && !state.projects.includes(state.selectedProject)) {
    state.selectedProject = "";
  }
  if (!state.selectedProject && state.autoSelectProject && state.projects.length > 0) {
    const preferred =
      state.savedProject && state.projects.includes(state.savedProject)
        ? state.savedProject
        : "";
    state.selectedProject = preferred || data.default_project || state.projects[0];
  }
  if (state.selectedProject) {
    saveProjectPreference(state.selectedProject);
  }
  renderProjects();
  if (state.selectedProject) {
    showProjectView();
    if (state.pendingTab) {
      state.mainTab = state.pendingTab;
      state.pendingTab = "";
    }
    await refreshAssets();
    await loadJobsForProject();
    syncUrlState(false);
  } else {
    showHomeView();
    state.jobs = [];
    renderJobs();
    syncUrlState(false);
    state.autoStoryboardConfig = {};
  }
}

function setJobs(jobs) {
  state.jobs = (jobs || []).slice().sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0));
  if (state.selectedProject) {
    saveJobCache(state.selectedProject, state.jobs);
  }
}

async function loadJobsForProject() {
  if (!state.selectedProject) {
    return;
  }
  try {
    const data = await apiGet(`/api/projects/${state.selectedProject}/jobs`);
    await loadFlowStatus();
    syncFlowTouchedFromFlowStatus(state.selectedProject);
    const hasServerJobs = Array.isArray(data.jobs) && data.jobs.length > 0;
    const projectFresh = areAllFlowsWaiting(state.flowStatus) && !hasServerJobs;
    if (projectFresh) {
      clearFlowTouchedForProject(state.selectedProject);
      clearJobCache(state.selectedProject);
    }
    const pendingFlows = Object.entries(state.flowStatus?.flows || {})
      .filter(([flow, flowData]) => flowData?.status === "pending")
      .map(([flow]) => flow);
    const pendingJobs = [];
    pendingFlows.forEach((flow) => {
      if (!data.jobs?.some((j) => j.type === `run_${flow}`)) {
        pendingJobs.push({
          id: `pending_${flow}_${Date.now()}`,
          type: `run_${flow}`,
          project: state.selectedProject,
          status: "pending",
          created_at: Date.now() / 1000,
          updated_at: Date.now() / 1000,
        });
      }
    });
    const cachedJobs = projectFresh ? [] : loadJobCache(state.selectedProject);
    const mergedJobs = mergeJobsById([...(data.jobs || []), ...cachedJobs]);
    setJobs(mergeJobsById([...pendingJobs, ...mergedJobs]));
    if (!projectFresh) {
      syncFlowTouchedFromJobs(state.selectedProject, mergedJobs);
    }
    renderJobs();
    state.jobs.forEach((job) => {
      if (job.status === "running") {
        pollJob(job.id);
      }
    });
    ensureFlowStatusPolling();
  } catch (err) {
    renderJobs();
    ensureFlowStatusPolling();
  }
}

async function loadFlowStatus() {
  if (!state.selectedProject) {
    state.flowStatus = null;
    return;
  }
  try {
    const data = await apiGet(`/api/projects/${state.selectedProject}/flow-status`);
    state.flowStatus = data;
    syncFlowTouchedFromFlowStatus(state.selectedProject);
  } catch (err) {
    state.flowStatus = null;
  }
}

function hasRunningFlowStatus() {
  const flows = state.flowStatus && state.flowStatus.flows ? state.flowStatus.flows : null;
  if (!flows) {
    return false;
  }
  return Object.values(flows).some((flow) => flow && flow.status === "running");
}

function hasRunningJobs() {
  return (state.jobs || []).some((job) => job && job.status === "running");
}

function stopFlowStatusPolling() {
  if (state.flowStatusPolling) {
    clearInterval(state.flowStatusPolling);
    state.flowStatusPolling = null;
  }
}

function ensureFlowStatusPolling() {
  if (!state.selectedProject) {
    stopFlowStatusPolling();
    return;
  }
  const shouldPoll = hasRunningJobs() || hasRunningFlowStatus();
  if (shouldPoll && !state.flowStatusPolling) {
    state.flowStatusPolling = setInterval(async () => {
      await loadFlowStatus();
      renderJobs();
    }, 4000);
    return;
  }
  if (!shouldPoll) {
    stopFlowStatusPolling();
  }
}

function isFlowBusy(flow) {
  const status = getFlowStatus(flow);
  return status === "running";
}

function getFlowStepStatus(flow, stepId) {
  if (!flow || !stepId) {
    return "";
  }
  const flows = state.flowStatus && state.flowStatus.flows ? state.flowStatus.flows : null;
  if (!flows || !flows[flow] || !flows[flow].steps) {
    return "";
  }
  return flows[flow].steps[stepId] || "";
}

function isAssetGenerating(assetType) {
  const map = {
    character: { flow: "visual_audio_assets", steps: ["step_character_images"], regenJobs: ["regenerate_character"] },
    location: { flow: "visual_audio_assets", steps: ["step_location_images"], regenJobs: ["regenerate_location_image"] },
    fenjing: { flow: "fenjing_generate", steps: ["step_generate"], regenJobs: ["regenerate_fenjing"] },
    video: { flow: "video", steps: ["step_video_generation"], regenJobs: ["regenerate_video"] },
    cloth: { flow: "visual_audio_assets", steps: ["step_cloth_images"], regenJobs: ["regenerate_cloth"] },
    cloth_changed: { flow: "visual_audio_assets", steps: ["step_cloth_images"], regenJobs: ["regenerate_cloth_changed"] }
  };
  const config = map[assetType];
  if (!config) {
    return false;
  }
  const stepRunning = (config.steps || []).some((stepId) => getFlowStepStatus(config.flow, stepId) === "running");
  if (stepRunning) {
    return true;
  }
  if (assetType === "fenjing") {
    const uploadFlowStatus = state.flowStatus && state.flowStatus.flows && state.flowStatus.flows.fenjing_upload;
    if (uploadFlowStatus && uploadFlowStatus.status === "running") {
      return true;
    }
  }
  const jobs = Array.isArray(state.jobs) ? state.jobs : [];
  const regenJobs = config.regenJobs || [];
  if (regenJobs.length === 0 || jobs.length === 0) {
    return false;
  }
  return jobs.some((job) => job && job.status === "running" && regenJobs.includes(job.type));
}

function getBatchFlowStatus(data) {
  if (!data) {
    return {
      auto_storyboard: false,
      visual_audio_assets: false,
      fenjing_generate: false,
      video: false,
    };
  }
  const hasStoryboardTable = Array.isArray(data.storyboard_table) && data.storyboard_table.length > 0;
  const hasCharacterAssets =
    (data.character_details || []).length > 0 ||
    (data.locations || []).length > 0 ||
    (data.cloth || []).length > 0 ||
    (data.cloth_changed || []).length > 0;
  const hasFenjingFromChapters = (data.chapters || []).some(
    (chapter) => (chapter.fenjing_images || []).length > 0
  );
  const hasFenjingFromDetails = Object.values(data.fenjing_details || {}).some((items) =>
    (items || []).some((item) => item && item.image_path)
  );
  const hasVideos = (data.videos || []).some((group) => (group.videos || []).length > 0);
  return {
    auto_storyboard: hasStoryboardTable,
    visual_audio_assets: hasCharacterAssets,
    fenjing_generate: hasFenjingFromChapters || hasFenjingFromDetails,
    video: hasVideos,
  };
}

function updateBatchFlowButtons(data) {
  const status = getBatchFlowStatus(data);
  const latestJobs = getLatestFlowJobs(state.jobs);
  document.querySelectorAll("[data-flow]").forEach((btn) => {
    const flow = btn.dataset.flow;
    const done = Boolean(status[flow]);
    const job = latestJobs[flow];
    btn.classList.remove("flow-complete", "flow-incomplete", "flow-running", "flow-error");
    const flowStatus = getFlowStatus(flow);
    if (flowStatus === "pending" || flowStatus === "running") {
      btn.disabled = true;
      btn.title = "任务进行中/已触发";
    } else {
      btn.disabled = false;
      btn.title = "";
    }
    if (job && job.status === "running") {
      btn.classList.add("flow-running");
      return;
    }
    if (job && job.status === "error") {
      btn.classList.add("flow-error");
      return;
    }
    if (done) {
      btn.classList.add("flow-complete");
    } else {
      btn.classList.add("flow-incomplete");
    }
  });
  updateFlowProgress(status, latestJobs);
}

function updateFlowProgress(status, latestJobs) {
  const steps = ["auto_storyboard", "visual_audio_assets", "fenjing_generate", "video"];
  const stepNames = {
    auto_storyboard: "剧本拆解",
    visual_audio_assets: "角色与素材生成",
    fenjing_generate: "分镜图生成",
    video: "视频生成"
  };
  
  steps.forEach((step) => {
    const stepEl = document.querySelector(`.flow-step[data-step="${step}"]`);
    if (!stepEl) {
      return;
    }
    
    const statusEl = stepEl.querySelector(".step-status");
    const done = Boolean(status[step]);
    const job = latestJobs[step];
    
    stepEl.classList.remove("running", "completed", "error");
    
    if (job && job.status === "running") {
      stepEl.classList.add("running");
      statusEl.textContent = "执行中";
    } else if (job && job.status === "error") {
      stepEl.classList.add("error");
      statusEl.textContent = "执行失败";
    } else if (done) {
      stepEl.classList.add("completed");
      statusEl.textContent = "已完成";
    } else {
      statusEl.textContent = "等待中";
    }
  });
}

function renderAssetsFromData(data) {
  const clothBox = qs("clothAssets");
  clothBox.innerHTML = "";
  renderCharactersPanel(data);
  renderClothChangedPanel(data);
  renderLocationsPanel(data);
  const clothGenerating = isAssetGenerating("cloth");
  (data.cloth || []).forEach((p) => clothBox.appendChild(assetItem(p)));
  renderStoryboardsPanel(data);
  renderVideosPanel(data);
  renderTables(data);
  setActiveTableTab(state.tableTab);
  setActiveMainTab(state.mainTab);
  updateBatchFlowButtons(data);
}

function buildCharacterNameMap(data) {
  const map = {};
  (data.character_table || []).forEach((row) => {
    if (!row || typeof row !== "object") {
      return;
    }
    const id = row.Character_Id || row.Character_id || row.character_id || "";
    const name = row.Character_name || row.Character_Name || row.character_name || "";
    if (id && name) {
      map[id] = name;
    }
  });
  return map;
}

function buildLocationNameMap(data) {
  const map = {};
  (data.location_table || []).forEach((row) => {
    if (!row || typeof row !== "object") {
      return;
    }
    const id = row.Location_ID || row.Location_id || row.location_id || "";
    const name = row.Location || row.Location_name || row.location_name || "";
    if (id && name) {
      map[id] = name;
    }
  });
  return map;
}

function normalizeLocationId(path) {
  if (!path) {
    return "";
  }
  const name = path.split("/").slice(-1)[0] || "";
  const stem = name.replace(/\.[^.]+$/, "");
  const match = stem.match(/^(.+?)_(standing|sitting)$/i);
  return match ? match[1] : stem;
}

function formatChapterTitle(name, index) {
  const raw = name || "";
  const match = raw.match(/(\d+)/);
  if (match) {
    return `章节 ${match[1]}`;
  }
  return `章节 ${index + 1}`;
}

function formatRefLabel(ref, characterNameMap, locationNameMap) {
  const typeMap = {
    location: "场景",
    character: "角色",
    cloth: "服装",
    cloth_changed: "换装",
  };
  const typeLabel = typeMap[ref.type] || "参考";
  if (ref.type === "location") {
    const name = locationNameMap[ref.id] || "";
    return name && ref.id ? `${typeLabel}：${name}（${ref.id}）` : name || `${typeLabel}：${ref.id || "未知"}`;
  }
  if (ref.type === "character") {
    const name = characterNameMap[ref.id] || "";
    return name && ref.id ? `${typeLabel}：${name}（${ref.id}）` : name || `${typeLabel}：${ref.id || "未知"}`;
  }
  return `${typeLabel}：${ref.id || "未知"}`;
}

function formatTime(seconds) {
  if (isNaN(seconds) || seconds === 0) {
    return "0:00";
  }
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

function renderCharactersPanel(data) {
  const listBox = qs("characterList");
  if (!listBox) {
    return;
  }
  listBox.innerHTML = "";
  let details = data.character_details || [];
  details = filterAssetsByFailedItems(details, "character", (item) => item.character_id);
  const nameMap = buildCharacterNameMap(data);
  const breathing = isAssetGenerating("character");
  if (!details || details.length === 0) {
    const empty = document.createElement("div");
    empty.className = "status-tag";
    empty.textContent = "暂无角色图";
    listBox.appendChild(empty);
    renderCharacterDetail(null);
    return;
  }
  details.forEach((item, index) => {
    const card = document.createElement("div");
    card.className = "character-card" + (item.character_id === state.selectedCharacterId ? " active" : "");
    if (!item.image_path) {
      card.classList.add("missing-asset");
    }
    card.dataset.characterId = item.character_id || "";
    const thumb = document.createElement("div");
    thumb.className = "character-thumb";
    if (item.image_path) {
      const img = document.createElement("img");
      img.src = mediaUrl(item.image_path);
      img.loading = "lazy";
      thumb.appendChild(img);
    } else {
      const placeholder = document.createElement("div");
      placeholder.className = "asset-placeholder";
      placeholder.innerHTML = `<span class="placeholder-icon">🖼️</span><span class="placeholder-text">待生成</span>`;
      thumb.appendChild(placeholder);
    }
    const meta = document.createElement("div");
    meta.className = "character-meta";
    const title = document.createElement("div");
    title.className = "character-title";
    const charId = item.character_id || "";
    const charName = nameMap[charId] || "";
    if (charName && charId) {
      title.textContent = `${charName}（${charId}）`;
    } else if (charName) {
      title.textContent = charName;
    } else if (charId) {
      title.textContent = `角色 ${charId}`;
    }
    meta.appendChild(title);
    card.appendChild(thumb);
    card.appendChild(meta);
    card.onclick = () => {
      state.selectedCharacterId = item.character_id;
      state.selectedCharacterCandidatePath = "";
      renderCharactersPanel(data);
    };
    listBox.appendChild(card);
  });
  const selected =
    details.find((item) => item.character_id === state.selectedCharacterId) || details[0] || null;
  if (selected && selected.character_id) {
    state.selectedCharacterId = selected.character_id;
  }
  renderCharacterDetail(selected);
  centerActiveCharacterCard("auto");
}

function renderCharacterDetail(item) {
  const preview = qs("characterPreview");
  const promptBox = qs("characterPromptInput");
  const statusBox = qs("characterPublishStatus");
  const titleBox = qs("characterTitle");
  const breathing = isAssetGenerating("character");
  if (!preview || !promptBox) {
    return;
  }
  preview.innerHTML = "";
  preview.classList.remove("vertical");
  if (statusBox) {
    statusBox.classList.add("hidden");
    statusBox.classList.remove("error");
  }
  if (titleBox) {
    titleBox.classList.add("hidden");
    titleBox.classList.remove("status-breathing");
  }
  state.selectedCharacterItem = item || null;
  if (!item) {
    promptBox.value = "";
    state.selectedCharacterCandidatePath = "";
    return;
  }
  if (titleBox) {
    const charName = item.character_name || item.character_id || "角色";
    titleBox.textContent = charName;
    titleBox.classList.remove("hidden");
    if (breathing) {
      titleBox.classList.add("status-breathing");
    }
  }
  const candidateImages = [];
  if (item.image_path) {
    candidateImages.push(item.image_path);
  }
  (item.candidate_images || []).forEach((p) => {
    if (p && !candidateImages.includes(p)) {
      candidateImages.push(p);
    }
  });
  if (!state.selectedCharacterCandidatePath || !candidateImages.includes(state.selectedCharacterCandidatePath)) {
    state.selectedCharacterCandidatePath = candidateImages[0] || "";
  }
  if (candidateImages.length === 0) {
    const empty = document.createElement("div");
    empty.className = "status-tag";
    empty.textContent = "暂无角色图";
    preview.appendChild(empty);
  } else {
    const slots = candidateImages.slice(0, 4);
    slots.forEach((p, idx) => {
      const cell = document.createElement("div");
      cell.className =
        "preview-item landscape" + (p === state.selectedCharacterCandidatePath ? " active" : "");
      if (idx === 0) {
        cell.classList.add("main");
      }
      if (breathing) {
        cell.classList.add("preview-breathing");
      }
      const img = document.createElement("img");
      img.src = mediaUrl(p);
      img.loading = "lazy";
      img.onload = () => {
        const ratio = img.naturalWidth > 0 ? img.naturalWidth / img.naturalHeight : 1;
        if (img.naturalHeight > img.naturalWidth) {
          cell.classList.add("portrait");
          cell.classList.remove("landscape");
        } else {
          cell.classList.add("landscape");
        }
      };
      cell.appendChild(img);
      cell.onclick = () => {
        state.selectedCharacterCandidatePath = p;
        renderCharacterDetail(item);
      };
      preview.appendChild(cell);
    });
    for (let i = slots.length; i < 4; i += 1) {
      const cell = document.createElement("div");
      cell.className = "preview-item";
      const empty = document.createElement("div");
      empty.className = "status-tag";
      empty.textContent = "空位";
      cell.appendChild(empty);
      preview.appendChild(cell);
    }
  }
  promptBox.value = item.prompt || "";
}

function renderClothChangedPanel(data) {
  const listBox = qs("clothChangedList");
  if (!listBox) {
    return;
  }
  listBox.innerHTML = "";
  const details = data.cloth_changed_details || [];
  const breathing = isAssetGenerating("cloth_changed");
  if (!details || details.length === 0) {
    const empty = document.createElement("div");
    empty.className = "status-tag";
    empty.textContent = "暂无换装图";
    listBox.appendChild(empty);
    renderClothChangedDetail(null);
    return;
  }
  details.forEach((item) => {
    const card = document.createElement("div");
    card.className =
      "character-card" + (item.cloth_changed_id === state.selectedClothChangedId ? " active" : "");
    card.dataset.clothChangedId = item.cloth_changed_id || "";
    const thumb = document.createElement("div");
    thumb.className = "character-thumb";
    if (item.image_path) {
      const img = document.createElement("img");
      img.src = mediaUrl(item.image_path);
      img.loading = "lazy";
      thumb.appendChild(img);
    } else {
      const empty = document.createElement("div");
      empty.className = "status-tag";
      empty.textContent = "暂无图片";
      thumb.appendChild(empty);
    }
    const meta = document.createElement("div");
    meta.className = "character-meta";
    const title = document.createElement("div");
    title.className = "character-title";
    const namePart = item.character_name || item.character_id || "未命名角色";
    title.textContent = `${namePart} / ${item.outfit_id || "未命名服装"}`;
    meta.appendChild(title);
    card.appendChild(thumb);
    card.appendChild(meta);
    card.onclick = () => {
      state.selectedClothChangedId = item.cloth_changed_id;
      state.selectedClothChangedCandidatePath = "";
      renderClothChangedPanel(data);
    };
    listBox.appendChild(card);
  });
  const selected =
    details.find((item) => item.cloth_changed_id === state.selectedClothChangedId) || details[0] || null;
  if (selected && selected.cloth_changed_id) {
    state.selectedClothChangedId = selected.cloth_changed_id;
  }
  renderClothChangedDetail(selected);
}

function renderClothChangedDetail(item) {
  const preview = qs("clothChangedPreview");
  const promptBox = qs("clothChangedPromptInput");
  const statusBox = qs("clothChangedPublishStatus");
  const titleBox = qs("clothChangedTitle");
  const breathing = isAssetGenerating("cloth");
  if (!preview || !promptBox) {
    return;
  }
  preview.innerHTML = "";
  preview.classList.remove("vertical");
  if (statusBox) {
    statusBox.classList.add("hidden");
    statusBox.classList.remove("error");
  }
  if (titleBox) {
    titleBox.classList.add("hidden");
    titleBox.classList.remove("status-breathing");
  }
  state.selectedClothChangedItem = item || null;
  if (!item) {
    promptBox.value = "";
    state.selectedClothChangedCandidatePath = "";
    return;
  }
  if (titleBox) {
    const namePart = item.character_name || item.character_id || "未命名角色";
    const outfit = item.outfit_id || "未命名服装";
    titleBox.textContent = `${namePart} / ${outfit}`;
    titleBox.classList.remove("hidden");
    if (breathing) {
      titleBox.classList.add("status-breathing");
    }
  }
  const candidateImages = [];
  if (item.image_path) {
    candidateImages.push(item.image_path);
  }
  (item.candidate_images || []).forEach((p) => {
    if (p && !candidateImages.includes(p)) {
      candidateImages.push(p);
    }
  });
  if (
    !state.selectedClothChangedCandidatePath ||
    !candidateImages.includes(state.selectedClothChangedCandidatePath)
  ) {
    state.selectedClothChangedCandidatePath = candidateImages[0] || "";
  }
  if (candidateImages.length === 0) {
    const empty = document.createElement("div");
    empty.className = "status-tag";
    empty.textContent = "暂无换装图";
    preview.appendChild(empty);
  } else {
    const slots = candidateImages.slice(0, 4);
    slots.forEach((p, idx) => {
      const cell = document.createElement("div");
      cell.className =
        "preview-item landscape" + (p === state.selectedClothChangedCandidatePath ? " active" : "");
      if (idx === 0) {
        cell.classList.add("main");
      }
      if (breathing) {
        cell.classList.add("preview-breathing");
      }
      const img = document.createElement("img");
      img.src = mediaUrl(p);
      img.loading = "lazy";
      img.onload = () => {
        const ratio = img.naturalWidth > 0 ? img.naturalWidth / img.naturalHeight : 1;
        if (img.naturalHeight > img.naturalWidth) {
          cell.classList.add("portrait");
          cell.classList.remove("landscape");
        } else {
          cell.classList.add("landscape");
        }
        if (p === state.selectedClothChangedCandidatePath && ratio >= 1.6) {
          preview.classList.add("vertical");
        }
      };
      cell.appendChild(img);
      cell.onclick = () => {
        state.selectedClothChangedCandidatePath = p;
        renderClothChangedDetail(item);
      };
      preview.appendChild(cell);
    });
  }
  promptBox.value = item.prompt || "";
}

function renderLocationsPanel(data) {
  const listBox = qs("locationList");
  const preview = qs("locationPreview");
  const titleBox = qs("locationTitle");
  if (!listBox || !preview) {
    return;
  }
  listBox.innerHTML = "";
  preview.innerHTML = "";
  const breathing = isAssetGenerating("location");
  if (titleBox) {
    titleBox.classList.add("hidden");
    titleBox.classList.remove("status-breathing");
  }
  const expectedLocations = data.expected_locations || [];
  const existingPaths = data.locations || [];
  const pathMap = buildLocationPathMap(existingPaths);
  const failedFilter = state.failedAssetItems.activeFilter;
  const failedItems = state.failedAssetItems.items || [];
  const failedIds = new Set(failedItems.filter((f) => f.asset_type === "location").map((f) => f.asset_id));
  if (expectedLocations.length === 0) {
    const empty = document.createElement("div");
    empty.className = "status-tag";
    empty.textContent = "暂无场景图";
    listBox.appendChild(empty);
    return;
  }
  let hasValidSelection = false;
  expectedLocations.forEach((loc) => {
    const locId = loc.location_id || "";
    const locName = loc.location_name || "";
    const hasImage = loc.has_image;
    const isFailed = loc.is_failed;
    const failReason = loc.fail_reason || "";
    if (failedFilter === "location" && !failedIds.has(locId)) {
      return;
    }
    const path = pathMap[locId] || "";
    const card = document.createElement("div");
    card.className = "character-card" + (path === state.selectedLocationPath ? " active" : "");
    if (!hasImage) {
      card.classList.add("missing-asset");
      if (isFailed) {
        card.classList.add("failed-asset");
      }
    }
    card.dataset.locationId = locId;
    const thumb = document.createElement("div");
    thumb.className = "character-thumb";
    if (hasImage && path) {
      const img = document.createElement("img");
      img.src = mediaUrl(path);
      img.loading = "lazy";
      thumb.appendChild(img);
    } else {
      const placeholder = document.createElement("div");
      placeholder.className = "asset-placeholder";
      if (isFailed) {
        placeholder.innerHTML = `<span class="placeholder-icon">❌</span><span class="placeholder-text failed">生成失败</span>`;
      } else {
        placeholder.innerHTML = `<span class="placeholder-icon">🖼️</span><span class="placeholder-text">待生成</span>`;
      }
      thumb.appendChild(placeholder);
    }
    const meta = document.createElement("div");
    meta.className = "character-meta";
    const title = document.createElement("div");
    title.className = "character-title";
    if (locName && locId) {
      title.textContent = `${locName}（${locId}）`;
    } else if (locName) {
      title.textContent = locName;
    } else if (locId) {
      title.textContent = `场景 ${locId}`;
    }
    meta.appendChild(title);
    if (isFailed && failReason) {
      const reasonTag = document.createElement("div");
      reasonTag.className = "fail-reason-tag";
      reasonTag.textContent = failReason;
      meta.appendChild(reasonTag);
    }
    card.appendChild(thumb);
    card.appendChild(meta);
    if (hasImage && path) {
      card.onclick = () => {
        state.selectedLocationPath = path;
        renderLocationsPanel(data);
      };
    }
    listBox.appendChild(card);
    if (path && path === state.selectedLocationPath) {
      hasValidSelection = true;
    }
  });
  const firstWithPath = expectedLocations.find((loc) => loc.has_image && pathMap[loc.location_id]);
  if (!hasValidSelection) {
    state.selectedLocationPath = firstWithPath && pathMap[firstWithPath.location_id] ? pathMap[firstWithPath.location_id] : "";
  }
  if (state.selectedLocationPath) {
    const cell = document.createElement("div");
    cell.className = "preview-item location-main";
    if (breathing) {
      cell.classList.add("preview-breathing");
    }
    const img = document.createElement("img");
    img.src = mediaUrl(state.selectedLocationPath);
    img.loading = "lazy";
    cell.appendChild(img);
    preview.appendChild(cell);
    if (titleBox) {
      const selectedLoc = expectedLocations.find((loc) => pathMap[loc.location_id] === state.selectedLocationPath);
      const locName = selectedLoc ? (selectedLoc.location_name || selectedLoc.location_id || "场景") : "场景";
      titleBox.textContent = locName;
      titleBox.classList.remove("hidden");
      if (breathing) {
        titleBox.classList.add("status-breathing");
      }
    }
  } else {
    const empty = document.createElement("div");
    empty.className = "status-tag";
    empty.textContent = "暂无场景图预览";
    preview.appendChild(empty);
  }
  centerActiveLocationCard("auto");
}

function buildLocationPathMap(paths) {
  const result = {};
  (paths || []).forEach((path) => {
    const name = path.split("/").slice(-1)[0] || "";
    const stem = name.replace(/\.[^.]+$/, "");
    const match = stem.match(/^(.+?)_(standing|sitting)$/i);
    const locId = match ? match[1] : stem;
    if (locId && !result[locId]) {
      result[locId] = path;
    }
  });
  return result;
}

function buildFenjingListForChapter(data, chapterName) {
  const chapters = data.chapters || [];
  const chapterMap = {};
  chapters.forEach((ch) => {
    if (ch && ch.name) {
      chapterMap[ch.name] = ch;
    }
  });
  const detailsByChapter = data.fenjing_details || {};
  let fenjingList = chapterName ? detailsByChapter[chapterName] || [] : [];
  const chapterInfo = chapterName ? chapterMap[chapterName] : null;
  if (chapterName && fenjingList.length === 0) {
    const fallback = (chapterInfo && chapterInfo.fenjing_images) || [];
    fenjingList = fallback
      .map((path) => {
        const match = String(path).match(/fenjing(\d+)/i);
        return {
          fenjing_id: match ? match[1] : "",
          image_path: path,
          prompt: "",
          ref_images: [],
          candidate_images: [],
        };
      })
      .sort((a, b) => Number(a.fenjing_id || 0) - Number(b.fenjing_id || 0));
  }
  return fenjingList;
}

function renderStoryboardsPanel(data) {
  const chapters = data.chapters || [];
  const chapterMap = {};
  chapters.forEach((ch) => {
    if (ch && ch.name) {
      chapterMap[ch.name] = ch;
    }
  });
  const breathing = isAssetGenerating("fenjing");
  const chapterName = renderChapterTabs("chapterTabs", chapters, state.storyboardChapterTab, (name) => {
    state.storyboardChapterTab = name;
    state.selectedFenjingId = "";
    if (state.assetsCache) {
      renderStoryboardsPanel(state.assetsCache);
    }
  });
  state.storyboardChapterTab = chapterName;
  const listBox = qs("fenjingList");
  listBox.innerHTML = "";
  const detailsByChapter = data.fenjing_details || {};
  let fenjingList = chapterName ? detailsByChapter[chapterName] || [] : [];
  const chapterInfo = chapterName ? chapterMap[chapterName] : null;
  const promptMap = chapterName ? state.fenjingPromptCache[chapterName] || {} : {};
  if (chapterName && fenjingList.length === 0) {
    const fallback = (chapterInfo && chapterInfo.fenjing_images) || [];
    fenjingList = fallback
      .map((path) => {
        const match = String(path).match(/fenjing(\d+)/i);
        return {
          fenjing_id: match ? match[1] : "",
          image_path: path,
          prompt: "",
          ref_images: [],
          candidate_images: [],
        };
      })
      .sort((a, b) => Number(a.fenjing_id || 0) - Number(b.fenjing_id || 0));
  }
  if (chapterName && Object.keys(promptMap).length === 0) {
    loadFenjingPromptMap(chapterName, chapterInfo);
  }
  fenjingList = fenjingList.map((item) => {
    if (!item || item.prompt) {
      return item;
    }
    const id = item.fenjing_id ? String(item.fenjing_id) : "";
    return {
      ...item,
      prompt: promptMap[id] || "",
    };
  });
  if (!chapterName || fenjingList.length === 0) {
    const empty = document.createElement("div");
    empty.className = "status-tag";
    empty.textContent = "暂无分镜";
    listBox.appendChild(empty);
    renderFenjingDetail(null);
    return;
  }
  fenjingList = filterAssetsByFailedItems(fenjingList, "fenjing", (item) => item.fenjing_id);
  fenjingList.forEach((item) => {
    const card = document.createElement("div");
    card.className = "fenjing-card" + (item.fenjing_id === state.selectedFenjingId ? " active" : "");
    if (!item.image_path) {
      card.classList.add("missing-asset");
      if (item.is_failed) {
        card.classList.add("failed-asset");
      }
    }
    card.dataset.fenjingId = item.fenjing_id || "";
    const thumb = document.createElement("div");
    thumb.className = "fenjing-thumb";
    if (item.image_path) {
      const img = document.createElement("img");
      img.src = mediaUrl(item.image_path);
      img.loading = "lazy";
      thumb.appendChild(img);
    } else {
      const placeholder = document.createElement("div");
      placeholder.className = "asset-placeholder";
      if (item.is_failed) {
        placeholder.innerHTML = `<span class="placeholder-icon">❌</span><span class="placeholder-text failed">生成失败</span>`;
      } else {
        placeholder.innerHTML = `<span class="placeholder-icon">🖼️</span><span class="placeholder-text">待生成</span>`;
      }
      thumb.appendChild(placeholder);
    }
    const meta = document.createElement("div");
    meta.className = "fenjing-meta";
    const title = document.createElement("div");
    title.className = "fenjing-title";
    title.textContent = `分镜 ${item.fenjing_id || ""}`;
    const prompt = document.createElement("div");
    prompt.className = "fenjing-prompt-snippet";
    prompt.textContent = item.prompt || "暂无分镜提示词";
    meta.appendChild(title);
    meta.appendChild(prompt);
    if (item.is_failed && item.fail_reason) {
      const reasonTag = document.createElement("div");
      reasonTag.className = "fail-reason-tag";
      reasonTag.textContent = item.fail_reason;
      meta.appendChild(reasonTag);
    }
    card.appendChild(thumb);
    card.appendChild(meta);
    card.onclick = () => {
      state.selectedFenjingId = item.fenjing_id;
      state.selectedCandidatePath = "";
      renderStoryboardsPanel(data);
    };
    listBox.appendChild(card);
  });
  const selected = fenjingList.find((f) => f.fenjing_id === state.selectedFenjingId) || fenjingList[0];
  if (selected && selected.fenjing_id) {
    state.selectedFenjingId = selected.fenjing_id;
  }
  renderFenjingDetail(selected || null);
  centerActiveFenjingCard("auto");
}

function renderFenjingDetail(item) {
  const preview = qs("fenjingPreview");
  const promptBox = qs("fenjingPromptInput");
  const refsBox = qs("fenjingRefs");
  const titleBox = qs("fenjingTitle");
  const breathing = isAssetGenerating("fenjing");
  preview.innerHTML = "";
  refsBox.innerHTML = "";
  state.selectedFenjingItem = item || null;
  if (titleBox) {
    titleBox.classList.add("hidden");
    titleBox.classList.remove("status-breathing");
  }
  if (!item) {
    promptBox.value = "";
    state.selectedCandidatePath = "";
    return;
  }
  if (titleBox) {
    titleBox.textContent = `分镜 ${item.fenjing_id || ""}`;
    titleBox.classList.remove("hidden");
    if (breathing) {
      titleBox.classList.add("status-breathing");
    }
  }
  const candidateImages = [];
  if (item.image_path) {
    candidateImages.push(item.image_path);
  }
  (item.candidate_images || []).forEach((p) => {
    if (p && !candidateImages.includes(p)) {
      candidateImages.push(p);
    }
  });
  if (!state.selectedCandidatePath || !candidateImages.includes(state.selectedCandidatePath)) {
    state.selectedCandidatePath = candidateImages[0] || "";
  }
  if (candidateImages.length === 0) {
    const empty = document.createElement("div");
    empty.className = "status-tag";
    empty.textContent = "暂无分镜图片";
    preview.appendChild(empty);
  } else {
    const slots = candidateImages.slice(0, 4);
    slots.forEach((p, idx) => {
      const cell = document.createElement("div");
      cell.className = "preview-item" + (p === state.selectedCandidatePath ? " active" : "");
      if (idx === 0) {
        cell.classList.add("main");
      }
      if (breathing) {
        cell.classList.add("preview-breathing");
      }
      const img = document.createElement("img");
      img.src = mediaUrl(p);
      img.loading = "lazy";
      cell.appendChild(img);
      cell.onclick = () => {
        state.selectedCandidatePath = p;
        renderFenjingDetail(item);
      };
      preview.appendChild(cell);
    });
    for (let i = slots.length; i < 4; i += 1) {
      const cell = document.createElement("div");
      cell.className = "preview-item";
      const empty = document.createElement("div");
      empty.className = "status-tag";
      empty.textContent = "空位";
      cell.appendChild(empty);
      preview.appendChild(cell);
    }
  }
  promptBox.value = item.prompt || "";
  const refs = item.ref_images || [];
  const characterNameMap = buildCharacterNameMap(state.assetsCache || {});
  const locationNameMap = buildLocationNameMap(state.assetsCache || {});
  if (refs.length === 0) {
    const emptyRef = document.createElement("div");
    emptyRef.className = "status-tag";
    emptyRef.textContent = "暂无参考图";
    refsBox.appendChild(emptyRef);
  } else {
    refs.forEach((ref) => {
      if (!ref.path) {
        return;
      }
      const div = document.createElement("div");
      div.className = "asset-item";
      const img = document.createElement("img");
      img.src = mediaUrl(ref.path);
      img.loading = "lazy";
      div.appendChild(img);
      const label = document.createElement("div");
      label.textContent = formatRefLabel(ref, characterNameMap, locationNameMap);
      div.appendChild(label);
      refsBox.appendChild(div);
    });
  }
}

function renderVideoDetail(videoPath, chapterName, data) {
  const preview = qs("videoPreview");
  const refsBox = qs("videoRefs");
  const promptBox = qs("videoPromptInput");
  const titleBox = qs("videoTitle");
  const playButton = qs("playTtsAudio");
  const audioPlayer = qs("ttsAudioPlayer");
  const progressFill = qs("ttsAudioProgress");
  const currentTimeDisplay = qs("ttsCurrentTime");
  const durationDisplay = qs("ttsDuration");
  const syncToggle = qs("syncVideoTts");
  const breathing = isAssetGenerating("video");
  
  if (preview) {
    preview.innerHTML = "";
  }
  if (refsBox) {
    refsBox.innerHTML = "";
  }
  if (titleBox) {
    titleBox.classList.add("hidden");
    titleBox.classList.remove("status-breathing");
  }
  state.selectedVideoFenjingId = "";
  
  if (audioPlayer) {
    audioPlayer.pause();
    audioPlayer.currentTime = 0;
    if (progressFill) {
      progressFill.style.width = "0%";
    }
    if (currentTimeDisplay) {
      currentTimeDisplay.textContent = "0:00";
    }
    if (durationDisplay) {
      durationDisplay.textContent = "0:00";
    }
  }
  
  if (!videoPath) {
    if (promptBox) {
      promptBox.value = "";
    }
    return;
  }
  const name = videoPath.split("/").slice(-1)[0];
  const match = name.match(/fenjing_(\d+)_video/i);
  if (titleBox) {
    titleBox.textContent = match ? `分镜 ${match[1]}` : name;
    titleBox.classList.remove("hidden");
    if (breathing) {
      titleBox.classList.add("status-breathing");
    }
  }
  const fenjingId = extractVideoFenjingId(videoPath);
  state.selectedVideoFenjingId = fenjingId;
  const promptMap = chapterName ? state.videoPromptCache[chapterName] || {} : {};
  const promptText = fenjingId ? promptMap[String(fenjingId)] || "" : "";
  if (promptBox) {
    promptBox.value = promptText;
  }
  
  if (audioPlayer && fenjingId) {
    const ttsCandidates = [];
    if (chapterName) {
      ttsCandidates.push(`visual_audio_assets/tts_audio/${chapterName}/fenjing_${fenjingId}_tts.mp3`);
      ttsCandidates.push(`storyboard_assets/tts_audio/${chapterName}/fenjing_${fenjingId}_tts.mp3`);
      ttsCandidates.push(`storyboard_assets/tts_audios/${chapterName}/fenjing_${fenjingId}_tts.mp3`);
      ttsCandidates.push(`tts_audio/${chapterName}/fenjing_${fenjingId}_tts.mp3`);
    }
    ttsCandidates.push(`visual_audio_assets/tts_audio/fenjing_${fenjingId}_tts.mp3`);
    ttsCandidates.push(`storyboard_assets/tts_audio/fenjing_${fenjingId}_tts.mp3`);
    ttsCandidates.push(`storyboard_assets/tts_audios/fenjing_${fenjingId}_tts.mp3`);
    ttsCandidates.push(`tts_audio/fenjing_${fenjingId}_tts.mp3`);
    ttsCandidates.push(`tts_audios/fenjing_${fenjingId}_tts.mp3`);
    let audioIndex = 0;
    const handleFailure = () => {
      if (playButton) {
        playButton.textContent = "音频加载失败";
        playButton.disabled = true;
      }
      if (progressFill) {
        progressFill.style.width = "0%";
      }
      if (currentTimeDisplay) {
        currentTimeDisplay.textContent = "0:00";
      }
      if (durationDisplay) {
        durationDisplay.textContent = "0:00";
      }
    };
    const tryLoadAudio = () => {
      if (audioIndex >= ttsCandidates.length) {
        handleFailure();
        return;
      }
      const candidate = ttsCandidates[audioIndex];
      audioPlayer.src = mediaUrl(candidate);
      audioPlayer.load();
    };
    if (playButton) {
      playButton.textContent = "加载中...";
      playButton.disabled = true;
      playButton.onclick = () => {
        if (audioPlayer.paused) {
          audioPlayer.play();
          playButton.textContent = "暂停";
        } else {
          audioPlayer.pause();
          playButton.textContent = "播放";
        }
      };
    }
    audioPlayer.onerror = () => {
      audioIndex += 1;
      tryLoadAudio();
    };
    audioPlayer.oncanplay = () => {
      if (playButton) {
        playButton.textContent = "播放";
        playButton.disabled = false;
      }
      if (durationDisplay) {
        durationDisplay.textContent = formatTime(audioPlayer.duration);
      }
    };
    audioPlayer.ontimeupdate = () => {
      if (progressFill && durationDisplay) {
        const progress = (audioPlayer.currentTime / audioPlayer.duration) * 100;
        progressFill.style.width = `${progress}%`;
        currentTimeDisplay.textContent = formatTime(audioPlayer.currentTime);
        durationDisplay.textContent = formatTime(audioPlayer.duration);
      }
    };
    audioPlayer.onended = () => {
      if (playButton) {
        playButton.textContent = "播放";
      }
      if (progressFill) {
        progressFill.style.width = "0%";
      }
      if (currentTimeDisplay) {
        currentTimeDisplay.textContent = "0:00";
      }
    };
    tryLoadAudio();
  }
  const chapterDetails =
    data && data.fenjing_details && chapterName && data.fenjing_details[chapterName]
      ? data.fenjing_details[chapterName]
      : [];
  const detailItem = chapterDetails.find((item) => String(item.fenjing_id) === String(fenjingId));
  const refs = detailItem && Array.isArray(detailItem.ref_images) ? detailItem.ref_images : [];
  const characterNameMap = buildCharacterNameMap(state.assetsCache || {});
  const locationNameMap = buildLocationNameMap(state.assetsCache || {});
  if (refsBox) {
    if (!refs || refs.length === 0) {
      const emptyRef = document.createElement("div");
      emptyRef.className = "status-tag";
      emptyRef.textContent = "暂无参考图";
      refsBox.appendChild(emptyRef);
    } else {
      refs.forEach((ref) => {
        if (!ref.path) {
          return;
        }
        const div = document.createElement("div");
        div.className = "asset-item";
        const img = document.createElement("img");
        img.src = mediaUrl(ref.path);
        img.loading = "lazy";
        div.appendChild(img);
        const label = document.createElement("div");
        label.textContent = formatRefLabel(ref, characterNameMap, locationNameMap);
        div.appendChild(label);
        refsBox.appendChild(div);
      });
    }
  }
  const videos = (data.videos || []).find((v) => v.chapter === chapterName);
  const allVideos = videos && videos.videos ? videos.videos : [];
  const fenjingVideos = allVideos.filter((v) => {
    const m = v.match(/fenjing_(\d+)(?:_video|_\d+)\.mp4/i);
    return m && Number(m[1]) === Number(fenjingId);
  });
  fenjingVideos.sort((a, b) => {
    const aIsCandidate = /fenjing_\d+_\d+\.mp4/i.test(a);
    const bIsCandidate = /fenjing_\d+_\d+\.mp4/i.test(b);
    if (aIsCandidate && !bIsCandidate) return -1;
    if (!aIsCandidate && bIsCandidate) return 1;
    if (aIsCandidate && bIsCandidate) {
      const aMatch = a.match(/fenjing_\d+_(\d+)\.mp4/i);
      const bMatch = b.match(/fenjing_\d+_(\d+)\.mp4/i);
      if (aMatch && bMatch) {
        return Number(bMatch[1]) - Number(aMatch[1]);
      }
    }
    return a.localeCompare(b);
  });
    if (!fenjingVideos || fenjingVideos.length === 0) {
    const empty = document.createElement("div");
    empty.className = "status-tag";
    empty.textContent = "暂无视频";
    preview.appendChild(empty);
  } else {
    const slots = fenjingVideos.slice(0, 4);
    slots.forEach((p, idx) => {
      const cell = document.createElement("div");
      cell.className = "preview-item" + (p === state.selectedVideoPath ? " active" : "");
      if (idx === 0) {
        cell.classList.add("main");
      }
      if (breathing) {
        cell.classList.add("preview-breathing");
      }
      const video = document.createElement("video");
      video.src = mediaUrl(p);
      video.controls = true;
      video.className = "video-player";
        if (audioPlayer) {
          video.addEventListener("play", () => {
            if (syncToggle && syncToggle.checked && !(playButton && playButton.disabled)) {
              const videoTime = video.currentTime || 0;
              const audioTime = audioPlayer.currentTime || 0;
              if (Math.abs(videoTime - audioTime) > 0.3) {
                audioPlayer.currentTime = videoTime;
              }
              if (audioPlayer.paused) {
                audioPlayer.play();
                if (playButton) {
                  playButton.textContent = "暂停";
                }
              }
            }
          });
          video.addEventListener("pause", () => {
            if (syncToggle && syncToggle.checked && !audioPlayer.paused) {
              audioPlayer.pause();
              if (playButton) {
                playButton.textContent = "播放";
              }
            }
          });
        }
      cell.appendChild(video);
      cell.onclick = () => {
        state.selectedVideoPath = p;
        renderVideoDetail(p, chapterName, data);
      };
      preview.appendChild(cell);
    });
    for (let i = slots.length; i < 4; i += 1) {
      const cell = document.createElement("div");
      cell.className = "preview-item";
      const empty = document.createElement("div");
      empty.className = "status-tag";
      empty.textContent = "空位";
      cell.appendChild(empty);
      preview.appendChild(cell);
    }
  }
}

function centerActiveFenjingCard(behavior) {
  const listBox = qs("fenjingList");
  const container = document.querySelector("#tabStoryboards .storyboard-left");
  if (!listBox || !container) {
    return;
  }
  const card = listBox.querySelector(".fenjing-card.active");
  if (!card) {
    return;
  }
  const containerRect = container.getBoundingClientRect();
  const cardRect = card.getBoundingClientRect();
  const delta = cardRect.top - containerRect.top - (containerRect.height / 2 - cardRect.height / 2);
  const targetTop = Math.max(0, Math.min(container.scrollHeight - container.clientHeight, container.scrollTop + delta));
  container.scrollTo({ top: targetTop, behavior: behavior || "smooth" });
}

function centerActiveVideoCard(behavior) {
  const listBox = qs("videoList");
  const container = document.querySelector("#tabVideos .storyboard-left");
  if (!listBox || !container) {
    return;
  }
  const card = listBox.querySelector(".video-card.active");
  if (!card) {
    return;
  }
  const containerRect = container.getBoundingClientRect();
  const cardRect = card.getBoundingClientRect();
  const delta = cardRect.top - containerRect.top - (containerRect.height / 2 - cardRect.height / 2);
  const targetTop = Math.max(0, Math.min(container.scrollHeight - container.clientHeight, container.scrollTop + delta));
  container.scrollTo({ top: targetTop, behavior: behavior || "smooth" });
}

function centerActiveLocationCard(behavior) {
  const listBox = qs("locationList");
  const container = document.querySelector("#tabLocations .storyboard-left");
  if (!listBox || !container) {
    return;
  }
  const card = listBox.querySelector(".character-card.active");
  if (!card) {
    return;
  }
  const containerRect = container.getBoundingClientRect();
  const cardRect = card.getBoundingClientRect();
  const delta = cardRect.top - containerRect.top - (containerRect.height / 2 - cardRect.height / 2);
  const targetTop = Math.max(0, Math.min(container.scrollHeight - container.clientHeight, container.scrollTop + delta));
  container.scrollTo({ top: targetTop, behavior: behavior || "smooth" });
}

function centerActiveCharacterCard(behavior) {
  const listBox = qs("characterList");
  const container = document.querySelector("#tabCharacters .storyboard-left");
  if (!listBox || !container) {
    return;
  }
  const card = listBox.querySelector(".character-card.active");
  if (!card) {
    return;
  }
  const containerRect = container.getBoundingClientRect();
  const cardRect = card.getBoundingClientRect();
  const delta = cardRect.top - containerRect.top - (containerRect.height / 2 - cardRect.height / 2);
  const targetTop = Math.max(0, Math.min(container.scrollHeight - container.clientHeight, container.scrollTop + delta));
  container.scrollTo({ top: targetTop, behavior: behavior || "smooth" });
}

function isEditableTarget(target) {
  if (!target) {
    return false;
  }
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
    return true;
  }
  return Boolean(target.isContentEditable);
}

function selectFenjingByOffset(delta) {
  if (!state.assetsCache) {
    return;
  }
  const chapters = state.assetsCache.chapters || [];
  let chapterName = state.storyboardChapterTab;
  if (!chapterName && chapters.length > 0) {
    chapterName = chapters[0].name;
    state.storyboardChapterTab = chapterName;
  }
  if (!chapterName) {
    return;
  }
  const list = buildFenjingListForChapter(state.assetsCache, chapterName);
  if (!list || list.length === 0) {
    return;
  }
  const currentIndex = list.findIndex((item) => String(item.fenjing_id) === String(state.selectedFenjingId));
  const baseIndex = currentIndex >= 0 ? currentIndex : 0;
  const nextIndex = Math.max(0, Math.min(list.length - 1, baseIndex + delta));
  const nextItem = list[nextIndex];
  if (!nextItem) {
    return;
  }
  state.selectedFenjingId = nextItem.fenjing_id;
  state.selectedCandidatePath = "";
  renderStoryboardsPanel(state.assetsCache);
  centerActiveFenjingCard("smooth");
  const rightPanel = document.querySelector("#tabStoryboards .storyboard-right");
  if (rightPanel && rightPanel.scrollHeight > rightPanel.clientHeight) {
    rightPanel.scrollTo({ top: 0, behavior: "smooth" });
  }
}

function extractVideoFenjingId(path) {
  if (!path) {
    return "";
  }
  const name = path.split("/").slice(-1)[0] || "";
  const match = name.match(/fenjing_(\d+)(?:_video|_\d+)\.mp4/i);
  return match ? match[1] : "";
}

function buildVideoListForChapter(data, chapterName) {
  if (!chapterName) {
    return [];
  }
  const videos = (data.videos || []).find((v) => v.chapter === chapterName);
  if (!videos || !videos.videos || videos.videos.length === 0) {
    return [];
  }
  return [...videos.videos].sort((a, b) => {
    const am = a.match(/fenjing_(\d+)(?:_video|_\d+)\.mp4/i);
    const bm = b.match(/fenjing_(\d+)(?:_video|_\d+)\.mp4/i);
    const ai = am ? Number(am[1]) : Number.MAX_SAFE_INTEGER;
    const bi = bm ? Number(bm[1]) : Number.MAX_SAFE_INTEGER;
    if (ai !== bi) {
      return ai - bi;
    }
    const aIsCandidate = /fenjing_\d+_\d+\.mp4/i.test(a);
    const bIsCandidate = /fenjing_\d+_\d+\.mp4/i.test(b);
    if (aIsCandidate && !bIsCandidate) return -1;
    if (!aIsCandidate && bIsCandidate) return 1;
    if (aIsCandidate && bIsCandidate) {
      const aMatch = a.match(/fenjing_\d+_(\d+)\.mp4/i);
      const bMatch = b.match(/fenjing_\d+_(\d+)\.mp4/i);
      if (aMatch && bMatch) {
        return Number(bMatch[1]) - Number(aMatch[1]);
      }
    }
    return a.localeCompare(b);
  });
}

function selectVideoByOffset(delta) {
  if (!state.assetsCache) {
    return;
  }
  const chapters = state.assetsCache.chapters || [];
  let chapterName = state.videoChapterTab;
  if (!chapterName && chapters.length > 0) {
    chapterName = chapters[0].name;
    state.videoChapterTab = chapterName;
  }
  if (!chapterName) {
    return;
  }
  const list = buildVideoListForChapter(state.assetsCache, chapterName);
  if (!list || list.length === 0) {
    return;
  }
  const currentIndex = list.findIndex((item) => String(item) === String(state.selectedVideoPath));
  const baseIndex = currentIndex >= 0 ? currentIndex : 0;
  const nextIndex = Math.max(0, Math.min(list.length - 1, baseIndex + delta));
  const nextItem = list[nextIndex];
  if (!nextItem) {
    return;
  }
  state.selectedVideoPath = nextItem;
  renderVideosPanel(state.assetsCache);
  centerActiveVideoCard("smooth");
  const rightPanel = document.querySelector("#tabVideos .storyboard-right");
  if (rightPanel && rightPanel.scrollHeight > rightPanel.clientHeight) {
    rightPanel.scrollTo({ top: 0, behavior: "smooth" });
  }
}

function selectLocationByOffset(delta) {
  if (!state.assetsCache) {
    return;
  }
  const expectedLocations = state.assetsCache.expected_locations || [];
  if (!expectedLocations || expectedLocations.length === 0) {
    return;
  }
  const currentIndex = expectedLocations.findIndex((loc) => {
    const pathMap = buildLocationPathMap(state.assetsCache.locations || []);
    const path = pathMap[loc.location_id] || "";
    return path === state.selectedLocationPath;
  });
  const baseIndex = currentIndex >= 0 ? currentIndex : 0;
  const nextIndex = Math.max(0, Math.min(expectedLocations.length - 1, baseIndex + delta));
  const nextLoc = expectedLocations[nextIndex];
  if (!nextLoc) {
    return;
  }
  const pathMap = buildLocationPathMap(state.assetsCache.locations || []);
  const nextPath = pathMap[nextLoc.location_id] || "";
  state.selectedLocationPath = nextPath;
  renderLocationsPanel(state.assetsCache);
  centerActiveLocationCard("smooth");
}

function selectCharacterByOffset(delta) {
  if (!state.assetsCache) {
    return;
  }
  const details = state.assetsCache.character_details || [];
  if (!details || details.length === 0) {
    return;
  }
  const currentIndex = details.findIndex((item) => String(item.character_id) === String(state.selectedCharacterId));
  const baseIndex = currentIndex >= 0 ? currentIndex : 0;
  const nextIndex = Math.max(0, Math.min(details.length - 1, baseIndex + delta));
  const nextItem = details[nextIndex];
  if (!nextItem) {
    return;
  }
  state.selectedCharacterId = nextItem.character_id;
  state.selectedCharacterCandidatePath = "";
  renderCharactersPanel(state.assetsCache);
  centerActiveCharacterCard("smooth");
  const rightPanel = document.querySelector("#tabCharacters .storyboard-right");
  if (rightPanel && rightPanel.scrollHeight > rightPanel.clientHeight) {
    rightPanel.scrollTo({ top: 0, behavior: "smooth" });
  }
}

function renderVideosPanel(data) {
  const chapters = data.chapters || [];
  const chapterName = renderChapterTabs("videoChapterTabs", chapters, state.videoChapterTab, (name) => {
    state.videoChapterTab = name;
    state.selectedVideoPath = "";
    state.selectedVideoFenjingId = "";
    if (state.assetsCache) {
      renderVideosPanel(state.assetsCache);
    }
  });
  state.videoChapterTab = chapterName;
  const breathing = isAssetGenerating("video");
  const chapterInfo = chapters.find((chapter) => chapter.name === chapterName);
  if (chapterName && chapterInfo && !state.videoPromptCache[chapterName]) {
    loadVideoPromptMap(chapterName, chapterInfo);
  }
  const listBox = qs("videoList");
  listBox.innerHTML = "";
  if (!chapterName) {
    const empty = document.createElement("div");
    empty.className = "status-tag";
    empty.textContent = "暂无章节";
    listBox.appendChild(empty);
    renderVideoDetail(null, chapterName, data);
    return;
  }
  const videos = (data.videos || []).find((v) => v.chapter === chapterName);
  if (!videos || !videos.videos || videos.videos.length === 0) {
    const empty = document.createElement("div");
    empty.className = "status-tag";
    empty.textContent = "暂无视频";
    listBox.appendChild(empty);
    renderVideoDetail(null, chapterName, data);
    return;
  }
  let items = [...videos.videos].sort((a, b) => {
    const am = a.match(/fenjing_(\d+)(?:_video|_\d+)\.mp4/i);
    const bm = b.match(/fenjing_(\d+)(?:_video|_\d+)\.mp4/i);
    const ai = am ? Number(am[1]) : Number.MAX_SAFE_INTEGER;
    const bi = bm ? Number(bm[1]) : Number.MAX_SAFE_INTEGER;
    if (ai !== bi) {
      return ai - bi;
    }
    const aIsCandidate = /fenjing_\d+_\d+\.mp4/i.test(a);
    const bIsCandidate = /fenjing_\d+_\d+\.mp4/i.test(b);
    if (aIsCandidate && !bIsCandidate) return -1;
    if (!aIsCandidate && bIsCandidate) return 1;
    if (aIsCandidate && bIsCandidate) {
      const aMatch = a.match(/fenjing_\d+_(\d+)\.mp4/i);
      const bMatch = b.match(/fenjing_\d+_(\d+)\.mp4/i);
      if (aMatch && bMatch) {
        return Number(bMatch[1]) - Number(aMatch[1]);
      }
    }
    return a.localeCompare(b);
  });
  items = filterAssetsByFailedItems(items, "video", (path) => {
    const match = path.match(/fenjing_(\d+)(?:_video|_\d+)\.mp4/i);
    return match ? match[1] : "";
  });
  if (!state.selectedVideoPath || !items.includes(state.selectedVideoPath)) {
    state.selectedVideoPath = items[0] || "";
  }
  items.forEach((p) => {
    listBox.appendChild(
      videoListItem(p, p === state.selectedVideoPath, () => {
        state.selectedVideoPath = p;
        renderVideosPanel(data);
      })
    );
  });
  renderVideoDetail(state.selectedVideoPath, chapterName, data);
  centerActiveVideoCard("auto");
}

async function refreshAssets() {
  if (!state.selectedProject) {
    return;
  }
  const data = await apiGet(`/api/projects/${state.selectedProject}/assets`);
  state.assetsCache = data;
  renderAssetsFromData(data);
}

async function loadFailedAssetItems(jobId) {
  if (!state.selectedProject || !jobId) {
    return;
  }
  try {
    const data = await apiGet(`/api/jobs/${jobId}/partial-failures`);
    state.failedAssetItems = {
      items: data.items || [],
      counts: data.counts || {},
      activeFilter: "",
      jobId: jobId,
    };
  } catch (err) {
    state.failedAssetItems = {
      items: [],
      counts: {},
      activeFilter: "",
      jobId: jobId,
    };
  }
}

function applyFailedAssetFilter(jobId) {
  if (state.failedAssetItems.jobId !== jobId) {
    loadFailedAssetItems(jobId).then(() => {
      renderAssetsFromData(state.assetsCache);
      renderFailedFilterBar();
    });
  } else {
    renderAssetsFromData(state.assetsCache);
    renderFailedFilterBar();
  }
}

function renderFailedFilterBar() {
  const container = qs("failedFilterBar");
  if (!container) {
    return;
  }
  container.innerHTML = "";
  const items = state.failedAssetItems.items || [];
  const counts = state.failedAssetItems.counts || {};
  if (items.length === 0) {
    return;
  }
  const typeLabels = {
    character: "角色",
    location: "场景",
    fenjing: "分镜",
    video: "视频",
    cloth: "服装",
    cloth_changed: "换装",
  };
  const bar = document.createElement("div");
  bar.className = "failed-filter-bar";
  const label = document.createElement("span");
  label.textContent = "筛选失败项：";
  bar.appendChild(label);
  const types = Object.keys(counts).filter((t) => counts[t] > 0);
  types.forEach((t) => {
    const btn = document.createElement("button");
    btn.className = "filter-btn" + (state.failedAssetItems.activeFilter === t ? " active" : "");
    btn.textContent = `${typeLabels[t] || t} (${counts[t]})`;
    btn.onclick = () => {
      state.failedAssetItems.activeFilter = state.failedAssetItems.activeFilter === t ? "" : t;
      renderAssetsFromData(state.assetsCache);
      renderFailedFilterBar();
    };
    bar.appendChild(btn);
  });
  const clearBtn = document.createElement("button");
  clearBtn.className = "filter-clear-btn";
  clearBtn.textContent = "清除筛选";
  clearBtn.onclick = () => {
    state.failedAssetItems = {
      items: [],
      counts: {},
      activeFilter: "",
      jobId: "",
    };
    renderAssetsFromData(state.assetsCache);
    renderFailedFilterBar();
  };
  bar.appendChild(clearBtn);
  container.appendChild(bar);
}

function filterAssetsByFailedItems(items, assetType, idExtractor) {
  const filter = state.failedAssetItems.activeFilter;
  const failedItems = state.failedAssetItems.items || [];
  if (!filter || filter !== assetType) {
    return items;
  }
  const failedIds = new Set(failedItems.filter((f) => f.asset_type === assetType).map((f) => f.asset_id));
  return items.filter((item) => {
    const id = idExtractor(item);
    return id && failedIds.has(id);
  });
}

async function loadAssetStats() {
  if (!state.selectedProject) {
    return;
  }
  state.assetStatsLoading = true;
  try {
    const data = await apiGet(`/api/projects/${state.selectedProject}/asset-stats`);
    state.assetStats = data;
  } catch (err) {
    state.assetStats = null;
  } finally {
    state.assetStatsLoading = false;
  }
  renderStatsContent();
}

async function loadJobsWithStats() {
  if (!state.selectedProject) {
    return;
  }
  state.jobsWithStatsLoading = true;
  try {
    const data = await apiGet(`/api/projects/${state.selectedProject}/jobs?type=run_visual_audio_assets`);
    state.jobsWithStats = data.jobs || [];
  } catch (err) {
    state.jobsWithStats = [];
  } finally {
    state.jobsWithStatsLoading = false;
  }
  renderStatsContent();
}

function switchStatsTab(tab) {
  state.statsActiveTab = tab;
  document.querySelectorAll(".stats-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tab);
  });
  renderStatsContent();
}

function renderStatsContent() {
  const container = qs("statsContent");
  if (!container) {
    return;
  }
  container.innerHTML = "";
  if (state.statsActiveTab === "overview") {
    renderOverviewTab(container);
  } else if (state.statsActiveTab === "jobs") {
    renderJobsTab(container);
  }
}

function renderOverviewTab(container) {
  if (state.assetStatsLoading) {
    const loading = document.createElement("div");
    loading.className = "stats-loading";
    loading.textContent = "加载统计中...";
    container.appendChild(loading);
    return;
  }
  const stats = state.assetStats;
  if (!stats) {
    const empty = document.createElement("div");
    empty.className = "stats-empty";
    empty.textContent = "暂无统计数据";
    container.appendChild(empty);
    return;
  }
  const summary = stats.summary || {};
  const byType = stats.by_type || {};
  const byChapter = stats.by_chapter || {};
  const panel = document.createElement("div");
  panel.className = "stats-panel";
  const header = document.createElement("div");
  header.className = "stats-header";
  const title = document.createElement("h3");
  title.textContent = "生图成本统计";
  header.appendChild(title);
  const refreshBtn = document.createElement("button");
  refreshBtn.className = "stats-refresh-btn";
  refreshBtn.textContent = "刷新";
  refreshBtn.onclick = loadAssetStats;
  header.appendChild(refreshBtn);
  panel.appendChild(header);
  const summaryRow = document.createElement("div");
  summaryRow.className = "stats-summary";
  const summaryItems = [
    { label: "成功", value: summary.total_success || 0, cls: "success" },
    { label: "失败", value: summary.total_failed || 0, cls: "failed" },
    { label: "重试", value: summary.total_retry || 0, cls: "retry" },
  ];
  summaryItems.forEach((item) => {
    const cell = document.createElement("div");
    cell.className = `stats-summary-item stats-${item.cls}`;
    const valueEl = document.createElement("span");
    valueEl.className = "stats-value";
    valueEl.textContent = item.value;
    const labelEl = document.createElement("span");
    labelEl.className = "stats-label";
    labelEl.textContent = item.label;
    cell.appendChild(valueEl);
    cell.appendChild(labelEl);
    summaryRow.appendChild(cell);
  });
  panel.appendChild(summaryRow);
  const typeSection = document.createElement("div");
  typeSection.className = "stats-section";
  const typeTitle = document.createElement("div");
  typeTitle.className = "stats-section-title";
  typeTitle.textContent = "按类型统计";
  typeSection.appendChild(typeTitle);
  const typeGrid = document.createElement("div");
  typeGrid.className = "stats-type-grid";
  Object.keys(byType).forEach((typeId) => {
    const typeStat = byType[typeId];
    const card = document.createElement("div");
    card.className = "stats-type-card";
    const cardHeader = document.createElement("div");
    cardHeader.className = "stats-type-header";
    cardHeader.textContent = typeStat.label || typeId;
    card.appendChild(cardHeader);
    const cardBody = document.createElement("div");
    cardBody.className = "stats-type-body";
    const successEl = document.createElement("span");
    successEl.className = "stats-type-success";
    successEl.textContent = `成功 ${typeStat.success || 0}`;
    const failedEl = document.createElement("span");
    failedEl.className = "stats-type-failed";
    failedEl.textContent = `失败 ${typeStat.failed || 0}`;
    const retryEl = document.createElement("span");
    retryEl.className = "stats-type-retry";
    retryEl.textContent = `重试 ${typeStat.retry_count || 0}`;
    cardBody.appendChild(successEl);
    cardBody.appendChild(failedEl);
    cardBody.appendChild(retryEl);
    card.appendChild(cardBody);
    if (typeStat.has_chapter && typeStat.chapters && Object.keys(typeStat.chapters).length > 0) {
      const chapterToggle = document.createElement("button");
      chapterToggle.className = "stats-chapter-toggle";
      chapterToggle.textContent = "查看章节";
      chapterToggle.onclick = () => {
        card.classList.toggle("expanded");
        chapterToggle.textContent = card.classList.contains("expanded") ? "收起章节" : "查看章节";
      };
      card.appendChild(chapterToggle);
      const chapterList = document.createElement("div");
      chapterList.className = "stats-chapter-list";
      Object.keys(typeStat.chapters).forEach((chapter) => {
        const chStat = typeStat.chapters[chapter];
        const chRow = document.createElement("div");
        chRow.className = "stats-chapter-row";
        chRow.innerHTML = `<span class="stats-chapter-name">${chapter}</span>
          <span class="stats-chapter-stat">成功 ${chStat.success || 0}</span>
          <span class="stats-chapter-stat">失败 ${chStat.failed || 0}</span>
          <span class="stats-chapter-stat">重试 ${chStat.retry || 0}</span>`;
        chapterList.appendChild(chRow);
      });
      card.appendChild(chapterList);
    }
    typeGrid.appendChild(card);
  });
  typeSection.appendChild(typeGrid);
  panel.appendChild(typeSection);
  const chapterNames = Object.keys(byChapter);
  if (chapterNames.length > 0) {
    const chapterSection = document.createElement("div");
    chapterSection.className = "stats-section";
    const chapterTitle = document.createElement("div");
    chapterTitle.className = "stats-section-title";
    chapterTitle.textContent = "按章节汇总";
    chapterSection.appendChild(chapterTitle);
    const chapterGrid = document.createElement("div");
    chapterGrid.className = "stats-chapter-grid";
    chapterNames.forEach((chapter) => {
      const chStat = byChapter[chapter];
      const chCard = document.createElement("div");
      chCard.className = "stats-chapter-card";
      chCard.innerHTML = `
        <div class="stats-chapter-header">${chapter}</div>
        <div class="stats-chapter-body">
          <span class="stats-success">成功 ${chStat.success || 0}</span>
          <span class="stats-failed">失败 ${chStat.failed || 0}</span>
          <span class="stats-retry">重试 ${chStat.retry || 0}</span>
        </div>`;
      chapterGrid.appendChild(chCard);
    });
    chapterSection.appendChild(chapterGrid);
    panel.appendChild(chapterSection);
  }
  container.appendChild(panel);
}

function renderJobsTab(container) {
  if (state.jobsWithStatsLoading) {
    const loading = document.createElement("div");
    loading.className = "stats-loading";
    loading.textContent = "加载任务历史中...";
    container.appendChild(loading);
    return;
  }
  const jobs = state.jobsWithStats || [];
  if (jobs.length === 0) {
    const empty = document.createElement("div");
    empty.className = "stats-empty";
    empty.textContent = "暂无任务历史";
    container.appendChild(empty);
    return;
  }
  const panel = document.createElement("div");
  panel.className = "stats-panel";
  const header = document.createElement("div");
  header.className = "stats-header";
  const title = document.createElement("h3");
  title.textContent = "任务历史";
  header.appendChild(title);
  const refreshBtn = document.createElement("button");
  refreshBtn.className = "stats-refresh-btn";
  refreshBtn.textContent = "刷新";
  refreshBtn.onclick = loadJobsWithStats;
  header.appendChild(refreshBtn);
  panel.appendChild(header);
  const table = document.createElement("div");
  table.className = "stats-jobs-table";
  const thead = document.createElement("div");
  thead.className = "stats-jobs-thead";
  thead.innerHTML = `
    <span class="stats-jobs-col time">时间</span>
    <span class="stats-jobs-col status">状态</span>
    <span class="stats-jobs-col success">成功</span>
    <span class="stats-jobs-col failed">失败</span>
    <span class="stats-jobs-col retry">重试</span>
    <span class="stats-jobs-col action">操作</span>
  `;
  table.appendChild(thead);
  jobs.forEach((job) => {
    const row = document.createElement("div");
    row.className = "stats-jobs-row";
    const assetStats = job.asset_stats || {};
    const timeStr = job.log_display_name || formatTimestamp(job.created_at);
    const statusIcon = job.status === "success" ? "✅" : job.status === "error" ? "❌" : "⏳";
    row.innerHTML = `
      <span class="stats-jobs-col time">${timeStr}</span>
      <span class="stats-jobs-col status">${statusIcon} ${job.status || ""}</span>
      <span class="stats-jobs-col success">${assetStats.success || 0}</span>
      <span class="stats-jobs-col failed">${assetStats.failed || 0}</span>
      <span class="stats-jobs-col retry">${assetStats.retry_count || 0}</span>
      <span class="stats-jobs-col action">
        <button class="stats-job-detail-btn" data-job-id="${job.id}">详情</button>
      </span>
    `;
    row.querySelector(".stats-job-detail-btn").onclick = () => showJobDetail(job.id);
    table.appendChild(row);
  });
  panel.appendChild(table);
  container.appendChild(panel);
}

async function showJobDetail(jobId) {
  if (!state.selectedProject || !jobId) {
    return;
  }
  const modal = document.createElement("div");
  modal.className = "job-detail-modal";
  modal.innerHTML = `
    <div class="job-detail-content">
      <div class="job-detail-header">
        <h3>任务详情</h3>
        <button class="job-detail-close">&times;</button>
      </div>
      <div class="job-detail-body">
        <div class="job-detail-loading">加载中...</div>
      </div>
    </div>
  `;
  modal.querySelector(".job-detail-close").onclick = () => modal.remove();
  modal.onclick = (e) => {
    if (e.target === modal) {
      modal.remove();
    }
  };
  document.body.appendChild(modal);
  try {
    const data = await apiGet(`/api/projects/${state.selectedProject}/jobs/${jobId}`);
    renderJobDetailContent(modal.querySelector(".job-detail-body"), data);
  } catch (err) {
    modal.querySelector(".job-detail-body").innerHTML = `<div class="job-detail-error">加载失败: ${err.message}</div>`;
  }
}

function renderJobDetailContent(container, data) {
  const job = data.job || {};
  const assetStats = data.asset_stats || {};
  const results = data.results || [];
  container.innerHTML = "";
  const summary = document.createElement("div");
  summary.className = "job-detail-summary";
  summary.innerHTML = `
    <div class="job-detail-row">
      <span class="job-detail-label">任务ID:</span>
      <span class="job-detail-value">${job.id || ""}</span>
    </div>
    <div class="job-detail-row">
      <span class="job-detail-label">时间:</span>
      <span class="job-detail-value">${job.log_display_name || formatTimestamp(job.created_at)}</span>
    </div>
    <div class="job-detail-row">
      <span class="job-detail-label">状态:</span>
      <span class="job-detail-value">${job.status || ""}</span>
    </div>
    <div class="job-detail-stats">
      <div class="job-detail-stat success">
        <span class="stat-value">${assetStats.success || 0}</span>
        <span class="stat-label">成功</span>
      </div>
      <div class="job-detail-stat failed">
        <span class="stat-value">${assetStats.failed || 0}</span>
        <span class="stat-label">失败</span>
      </div>
      <div class="job-detail-stat retry">
        <span class="stat-value">${assetStats.retry_count || 0}</span>
        <span class="stat-label">重试</span>
      </div>
    </div>
  `;
  container.appendChild(summary);
  const byType = assetStats.by_type || {};
  if (Object.keys(byType).length > 0) {
    const typeSection = document.createElement("div");
    typeSection.className = "job-detail-section";
    typeSection.innerHTML = `<div class="job-detail-section-title">按类型统计</div>`;
    const typeList = document.createElement("div");
    typeList.className = "job-detail-type-list";
    Object.keys(byType).forEach((typeId) => {
      const typeStat = byType[typeId];
      const typeRow = document.createElement("div");
      typeRow.className = "job-detail-type-row";
      typeRow.innerHTML = `
        <span class="type-name">${typeId}</span>
        <span class="type-stat success">成功 ${typeStat.success || 0}</span>
        <span class="type-stat failed">失败 ${typeStat.failed || 0}</span>
        <span class="type-stat retry">重试 ${typeStat.retry || 0}</span>
      `;
      typeList.appendChild(typeRow);
    });
    typeSection.appendChild(typeList);
    container.appendChild(typeSection);
  }
  if (results.length > 0) {
    const resultsSection = document.createElement("div");
    resultsSection.className = "job-detail-section";
    resultsSection.innerHTML = `<div class="job-detail-section-title">资产明细</div>`;
    const resultsList = document.createElement("div");
    resultsList.className = "job-detail-results-list";
    results.forEach((item) => {
      const resultRow = document.createElement("div");
      resultRow.className = `job-detail-result-row ${item.status === "success" ? "success" : "failed"}`;
      const statusIcon = item.status === "success" ? "✅" : "❌";
      resultRow.innerHTML = `
        <span class="result-icon">${statusIcon}</span>
        <span class="result-type">${item.asset_type || ""}</span>
        <span class="result-id">${item.asset_id || ""}</span>
        <span class="result-reason">${item.reason || ""}</span>
      `;
      resultsList.appendChild(resultRow);
    });
    resultsSection.appendChild(resultsList);
    container.appendChild(resultsSection);
  }
}

function formatTimestamp(ts) {
  if (!ts) {
    return "";
  }
  const date = new Date(ts * 1000);
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function toggleAssetStatsPanel() {
  const container = qs("assetStatsPanel");
  if (!container) {
    return;
  }
  if (container.classList.contains("hidden")) {
    container.classList.remove("hidden");
    if (!state.assetStats) {
      loadAssetStats();
    } else {
      renderStatsContent();
    }
  } else {
    container.classList.add("hidden");
  }
}

function uploadNovelWithDialog() {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "modal-backdrop";
    overlay.style.position = "fixed";
    overlay.style.inset = "0";
    overlay.style.display = "flex";
    overlay.style.alignItems = "center";
    overlay.style.justifyContent = "center";
    const card = document.createElement("div");
    card.className = "modal-card";
    const title = document.createElement("div");
    title.className = "modal-title";
    title.textContent = "上传剧本并拆解";
    const textarea = document.createElement("textarea");
    textarea.className = "modal-text";
    textarea.placeholder = "粘贴或输入剧本文本";
    textarea.rows = 10;
    const configSection = buildAutoStoryboardConfigSection(state.autoStoryboardConfig || {}, {
      fields: ["chapter_size"]
    });
    const status = document.createElement("div");
    status.className = "status-inline hidden";
    const actions = document.createElement("div");
    actions.className = "modal-actions";
    const cancel = document.createElement("button");
    cancel.textContent = "取消";
    cancel.className = "button-secondary";
    const confirm = document.createElement("button");
    confirm.textContent = "上传并拆解";
    actions.appendChild(cancel);
    actions.appendChild(confirm);
    card.appendChild(title);
    card.appendChild(textarea);
    card.appendChild(configSection.settings);
    card.appendChild(status);
    card.appendChild(actions);
    overlay.appendChild(card);
    document.body.appendChild(overlay);
    const cleanup = () => {
      overlay.remove();
    };
    cancel.onclick = () => {
      cleanup();
      resolve(null);
    };
    overlay.onclick = (event) => {
      if (event.target === overlay) {
        cleanup();
        resolve(null);
      }
    };
    confirm.onclick = async () => {
      const text = textarea.value.trim();
      if (!text) {
        status.classList.remove("hidden");
        status.textContent = "请输入剧本文本";
        return;
      }
      status.classList.remove("hidden", "error");
      status.textContent = "上传中...";
      confirm.disabled = true;
      cancel.disabled = true;
      try {
        await apiPost(`/api/projects/${state.selectedProject}/novel`, { novel_text: text });
        status.textContent = "上传成功";
        const nextConfig = configSection.getConfig();
        state.autoStoryboardConfig = nextConfig;
        setTimeout(() => {
          cleanup();
          resolve({ ok: true, config: nextConfig });
        }, 300);
      } catch (err) {
        status.classList.add("error");
        status.textContent = "上传失败";
        confirm.disabled = false;
        cancel.disabled = false;
      }
    };
    textarea.focus();
  });
}

async function submitFlow(flow) {
  if (!state.selectedProject) {
    return;
  }
  if (isFlowBusy(flow)) {
    return;
  }
  if (flow === "auto_storyboard") {
    let payload = {};
    payload.novel_path = "";
    const result = await uploadNovelWithDialog();
    if (!result || !result.ok) {
      return;
    }
    setFlowTouched(state.selectedProject, flow);
    payload = { phase: "step_extract", ...payload, ...buildAutoStoryboardPayload(result.config) };
    try {
      await apiPost(`/api/projects/${state.selectedProject}/clean/${flow}`);
      await refreshAssets();
    } catch (err) {
      window.alert("清理阶段资产失败");
      return;
    }
    const job = await apiPost(`/api/projects/${state.selectedProject}/run/${flow}`, payload);
    setJobs([job, ...state.jobs]);
    renderJobs();
    pollJob(job.id);
    ensureFlowStatusPolling();
    return;
  }
  if (["visual_audio_assets", "fenjing_generate", "fenjing_upload", "video"].includes(flow)) {
    const existing = state.jobs.find(j => j.type === `run_${flow}`);
    if (existing) {
      return;
    }
    setFlowTouched(state.selectedProject, flow);
    await apiPost(`/api/projects/${state.selectedProject}/flow/${flow}/pending`);
    const pendingJob = {
      id: `pending_${flow}_${Date.now()}`,
      type: `run_${flow}`,
      project: state.selectedProject,
      status: "pending",
      created_at: Date.now() / 1000,
      updated_at: Date.now() / 1000,
    };
    setJobs([pendingJob, ...state.jobs]);
    renderJobs();
    ensureFlowStatusPolling();
    return;
  }
}

async function clearPendingFlow(flow) {
  if (!state.selectedProject) {
    return;
  }
  if (!["visual_audio_assets", "fenjing_generate", "fenjing_upload", "video"].includes(flow)) {
    return;
  }
  await apiPost(`/api/projects/${state.selectedProject}/flow/${flow}/pending/clear`);
}

async function executeFlowFull(flow, options) {
  if (!state.selectedProject) {
    return;
  }
  if (isFlowBusy(flow)) {
    return;
  }
  const flowStatus = state.flowStatus?.flows?.[flow]?.status;
  if (flowStatus === "completed") {
    return;
  }
  setFlowTouched(state.selectedProject, flow);
  await clearPendingFlow(flow);
  const phase = options && options.phase ? String(options.phase) : "";
  const skipClean = (flow === "video" && !!phase && phase !== "all");
  if (!skipClean) {
    try {
      await apiPost(`/api/projects/${state.selectedProject}/clean/${flow}`);
      await refreshAssets();
    } catch (err) {
      window.alert("清理阶段资产失败");
      return;
    }
  }
  const body = phase ? { phase } : {};
  const job = await apiPost(`/api/projects/${state.selectedProject}/run/${flow}`, body);
  state.jobs = state.jobs.filter(j => !j.id.startsWith(`pending_${flow}_`));
  setJobs([job, ...state.jobs]);
  renderJobs();
  pollJob(job.id);
  ensureFlowStatusPolling();
}

async function submitFlowPhase(flow, phase) {
  if (!state.selectedProject) {
    return;
  }
  if (flow === "auto_storyboard" && !phase) {
    window.alert("缺少阶段参数，无法运行")
    return;
  }
  setFlowTouched(state.selectedProject, flow);
  await clearPendingFlow(flow);
  const payload = phase ? { phase } : {};
  if (flow === "auto_storyboard") {
    Object.assign(payload, buildAutoStoryboardPayload(state.autoStoryboardConfig));
  }
  state.jobs = state.jobs.filter(j => !j.id.startsWith(`pending_${flow}_`));
  let job;
  try {
    job = await apiPost(`/api/projects/${state.selectedProject}/run/${flow}`, payload);
  } catch (err) {
    window.alert(`启动 ${flow} 失败: ${err.message}`);
    return;
  }
  setJobs([job, ...state.jobs]);
  renderJobs();
  pollJob(job.id);
  ensureFlowStatusPolling();
}

async function regenClothById(outfitId) {
  if (!state.selectedProject || !outfitId) {
    return;
  }
  const job = await apiPost(`/api/projects/${state.selectedProject}/regenerate/cloth`, {
    outfit_id: outfitId,
  });
  setJobs([job, ...state.jobs]);
  renderJobs();
  pollJob(job.id);
}

async function regenClothChangedByIds(characterId, outfitId) {
  if (!state.selectedProject || !characterId || !outfitId) {
    return;
  }
  const job = await apiPost(`/api/projects/${state.selectedProject}/regenerate/cloth-changed`, {
    character_id: characterId,
    outfit_id: outfitId,
  });
  setJobs([job, ...state.jobs]);
  renderJobs();
  pollJob(job.id);
}

async function regenLocationImageById(locationId, bgType) {
  if (!state.selectedProject || !locationId) {
    return;
  }
  const job = await apiPost(`/api/projects/${state.selectedProject}/regenerate/location-image`, {
    location_id: locationId,
    bg_type: bgType || "standing",
  });
  setJobs([job, ...state.jobs]);
  renderJobs();
  pollJob(job.id);
}

async function pollJob(jobId) {
  if (state.jobPolling[jobId]) {
    return;
  }
  const timer = setInterval(async () => {
    try {
      const data = await apiGet(`/api/jobs/${jobId}`);
      const idx = state.jobs.findIndex((j) => j.id === jobId);
      if (idx >= 0) {
        state.jobs[idx] = data;
        setJobs(state.jobs);
      } else {
        setJobs([data, ...state.jobs]);
      }
      renderJobs();
      if (data.status !== "running") {
        clearInterval(timer);
        delete state.jobPolling[jobId];
        await refreshAssets();
        await loadFlowStatus();
        renderJobs();
        ensureFlowStatusPolling();
      } else {
        ensureFlowStatusPolling();
      }
    } catch (err) {
      renderJobs();
      ensureFlowStatusPolling();
    }
  }, 4000);
  state.jobPolling[jobId] = timer;
}

async function submitNovel() {
  if (!state.selectedProject) {
    return;
  }
  const text = qs("novelText").value.trim();
  if (!text) {
    return;
  }
  await apiPost(`/api/projects/${state.selectedProject}/novel`, { novel_text: text });
}

async function createProject() {
  let name = "";
  const input = qs("projectName");
  if (input) {
    name = input.value.trim();
  }
  if (!name) {
    const prompted = window.prompt("请输入项目名（字母/数字/下划线/短横线）", "");
    if (prompted) {
      name = prompted.trim();
    }
  }
  if (!name) {
    return;
  }
  try {
    await apiPost("/api/projects", { project_name: name });
    state.selectedProject = name;
    saveProjectPreference(name);
    if (input) {
      input.value = "";
    }
    await refreshProjects();
  } catch (err) {
    const msg = err && err.message ? String(err.message) : "新建失败";
    if (msg.includes("invalid_project")) {
      window.alert("项目名仅支持字母/数字/下划线/短横线");
    } else {
      window.alert("新建失败");
    }
  }
}

async function regenSelectedFenjing() {
  const chapter = state.storyboardChapterTab;
  const id = state.selectedFenjingId;
  const promptText = qs("fenjingPromptInput").value.trim();
  if (!state.selectedProject || !chapter || !id) {
    return;
  }
  const job = await apiPost(`/api/projects/${state.selectedProject}/regenerate/fenjing`, {
    chapter_name: chapter,
    fenjing_id: id,
    prompt_text: promptText,
  });
  setJobs([job, ...state.jobs]);
  renderJobs();
  pollJob(job.id);
}

async function regenSelectedCharacter() {
  const id = state.selectedCharacterId;
  const promptText = qs("characterPromptInput").value.trim();
  if (!state.selectedProject || !id) {
    return;
  }
  const job = await apiPost(`/api/projects/${state.selectedProject}/regenerate/character`, {
    character_id: id,
    prompt_text: promptText,
  });
  setJobs([job, ...state.jobs]);
  renderJobs();
  pollJob(job.id);
}

async function regenSelectedClothChanged() {
  const item = state.selectedClothChangedItem;
  const promptText = qs("clothChangedPromptInput").value.trim();
  if (!state.selectedProject || !item) {
    return;
  }
  const job = await apiPost(`/api/projects/${state.selectedProject}/regenerate/cloth-changed`, {
    character_id: item.character_id,
    outfit_id: item.outfit_id,
    prompt_text: promptText,
  });
  setJobs([job, ...state.jobs]);
  renderJobs();
  pollJob(job.id);
}

async function publishSelectedCharacter() {
  const id = state.selectedCharacterId;
  const candidatePath = state.selectedCharacterCandidatePath;
  const statusBox = qs("characterPublishStatus");
  if (!state.selectedProject || !id || !candidatePath) {
    return;
  }
  let publishPath = candidatePath;
  if (!publishPath.includes("character_candidates")) {
    const fallback =
      state.selectedCharacterItem &&
      Array.isArray(state.selectedCharacterItem.candidate_images) &&
      state.selectedCharacterItem.candidate_images.find((p) => p && p.includes("character_candidates"));
    if (fallback) {
      publishPath = fallback;
      state.selectedCharacterCandidatePath = fallback;
    }
  }
  if (!publishPath.includes("character_candidates")) {
    if (statusBox) {
      statusBox.classList.remove("hidden");
      statusBox.classList.add("error");
      statusBox.textContent = "未找到候选图，请先重生";
    }
    return;
  }
  if (statusBox) {
    statusBox.classList.remove("hidden", "error");
    statusBox.textContent = "上传中...";
  }
  let deleteFailed = false;
  try {
    await apiPost(`/api/projects/${state.selectedProject}/characters/${id}/publish`, {
      candidate_path: publishPath,
    });
    try {
      await apiPost(`/api/projects/${state.selectedProject}/characters/${id}/candidate/delete`, {
        candidate_path: publishPath,
      });
    } catch (err) {
      deleteFailed = true;
    }
    bumpMediaVersion();
    state.selectedCharacterCandidatePath = "";
    await refreshAssets();
    const targetCard = document.querySelector(`.character-card[data-character-id="${id}"]`);
    if (targetCard) {
      targetCard.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    if (statusBox) {
      statusBox.textContent = deleteFailed ? "已上传，候选图删除失败" : "已上传并覆盖角色图";
    }
  } catch (err) {
    if (statusBox) {
      statusBox.classList.add("error");
      const msg = err && err.message ? String(err.message) : "上传失败";
      statusBox.textContent = msg.includes("candidate") ? "请选择候选图后再上传" : "上传失败";
    }
  }
}

async function publishSelectedClothChanged() {
  const item = state.selectedClothChangedItem;
  const candidatePath = state.selectedClothChangedCandidatePath;
  const statusBox = qs("clothChangedPublishStatus");
  if (!state.selectedProject || !item || !candidatePath) {
    return;
  }
  let publishPath = candidatePath;
  if (!publishPath.includes("cloth_changed_candidates")) {
    const fallback =
      item &&
      Array.isArray(item.candidate_images) &&
      item.candidate_images.find((p) => p && p.includes("cloth_changed_candidates"));
    if (fallback) {
      publishPath = fallback;
      state.selectedClothChangedCandidatePath = fallback;
    }
  }
  if (!publishPath.includes("cloth_changed_candidates")) {
    if (statusBox) {
      statusBox.classList.remove("hidden");
      statusBox.classList.add("error");
      statusBox.textContent = "未找到候选图，请先重生";
    }
    return;
  }
  if (statusBox) {
    statusBox.classList.remove("hidden", "error");
    statusBox.textContent = "上传中...";
  }
  let deleteFailed = false;
  try {
    await apiPost(
      `/api/projects/${state.selectedProject}/cloth-changed/${encodeURIComponent(
        item.character_id || ""
      )}/${encodeURIComponent(item.outfit_id || "")}/publish`,
      {
        candidate_path: publishPath,
      }
    );
    try {
      await apiPost(
        `/api/projects/${state.selectedProject}/cloth-changed/${encodeURIComponent(
          item.character_id || ""
        )}/${encodeURIComponent(item.outfit_id || "")}/candidate/delete`,
        { candidate_path: publishPath }
      );
    } catch (err) {
      deleteFailed = true;
    }
    bumpMediaVersion();
    state.selectedClothChangedCandidatePath = "";
    await refreshAssets();
    const targetCard = document.querySelector(
      `.character-card[data-cloth-changed-id="${item.cloth_changed_id}"]`
    );
    if (targetCard) {
      targetCard.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    if (statusBox) {
      statusBox.textContent = deleteFailed ? "已上传，候选图删除失败" : "已上传并覆盖换装图";
    }
  } catch (err) {
    if (statusBox) {
      statusBox.classList.add("error");
      const msg = err && err.message ? String(err.message) : "上传失败";
      statusBox.textContent = msg.includes("candidate") ? "请选择候选图后再上传" : "上传失败";
    }
  }
}

async function publishSelectedFenjing() {
  const chapter = state.storyboardChapterTab;
  const id = state.selectedFenjingId;
  const candidatePath = state.selectedCandidatePath;
  const statusBox = qs("fenjingPublishStatus");
  if (!state.selectedProject || !chapter || !id || !candidatePath) {
    return;
  }
  let publishPath = candidatePath;
  if (!publishPath.includes("fenjing_candidates")) {
    const fallback =
      state.selectedFenjingItem &&
      Array.isArray(state.selectedFenjingItem.candidate_images) &&
      state.selectedFenjingItem.candidate_images.find((p) => p && p.includes("fenjing_candidates"));
    if (fallback) {
      publishPath = fallback;
      state.selectedCandidatePath = fallback;
    }
  }
  if (!publishPath.includes("fenjing_candidates")) {
    if (statusBox) {
      statusBox.classList.remove("hidden");
      statusBox.classList.add("error");
      statusBox.textContent = "未找到候选图，请先重生";
    }
    return;
  }
  if (statusBox) {
    statusBox.classList.remove("hidden", "error");
    statusBox.textContent = "上传中...";
  }
  try {
    await apiPost(`/api/projects/${state.selectedProject}/chapters/${chapter}/fenjing/${id}/publish`, {
      candidate_path: publishPath,
    });
    bumpMediaVersion();
    state.selectedCandidatePath = "";
    await refreshAssets();
    const targetCard = document.querySelector(`.fenjing-card[data-fenjing-id="${id}"]`);
    if (targetCard) {
      targetCard.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    if (statusBox) {
      statusBox.textContent = "已上传并覆盖主图";
    }
  } catch (err) {
    if (statusBox) {
      statusBox.classList.add("error");
      const msg = err && err.message ? String(err.message) : "上传失败";
      statusBox.textContent = msg.includes("candidate") ? "请选择候选图后再上传" : "上传失败";
    }
  }
}

async function deleteSelectedClothChangedCandidate() {
  const item = state.selectedClothChangedItem;
  const candidatePath = state.selectedClothChangedCandidatePath;
  const statusBox = qs("clothChangedPublishStatus");
  if (!state.selectedProject || !item || !candidatePath) {
    return;
  }
  if (!candidatePath.includes("cloth_changed_candidates")) {
    if (statusBox) {
      statusBox.classList.remove("hidden");
      statusBox.classList.add("error");
      statusBox.textContent = "只能删除候选图";
    }
    return;
  }
  try {
    await apiPost(
      `/api/projects/${state.selectedProject}/cloth-changed/${encodeURIComponent(
        item.character_id || ""
      )}/${encodeURIComponent(item.outfit_id || "")}/candidate/delete`,
      {
        candidate_path: candidatePath,
      }
    );
    state.selectedClothChangedCandidatePath = "";
    await refreshAssets();
    if (statusBox) {
      statusBox.classList.remove("hidden", "error");
      statusBox.textContent = "已删除候选图";
    }
  } catch (err) {
    if (statusBox) {
      statusBox.classList.add("error");
      statusBox.textContent = "删除失败";
    }
  }
}

async function deleteSelectedFenjingCandidate() {
  const chapter = state.storyboardChapterTab;
  const id = state.selectedFenjingId;
  const candidatePath = state.selectedCandidatePath;
  const statusBox = qs("fenjingPublishStatus");
  if (!state.selectedProject || !chapter || !id || !candidatePath) {
    return;
  }
  if (!candidatePath.includes("fenjing_candidates")) {
    if (statusBox) {
      statusBox.classList.remove("hidden");
      statusBox.classList.add("error");
      statusBox.textContent = "只能删除候选图";
    }
    return;
  }
  try {
    await apiPost(`/api/projects/${state.selectedProject}/chapters/${chapter}/fenjing/${id}/candidate/delete`, {
      candidate_path: candidatePath,
    });
    state.selectedCandidatePath = "";
    await refreshAssets();
    if (statusBox) {
      statusBox.classList.remove("hidden", "error");
      statusBox.textContent = "已删除候选图";
    }
  } catch (err) {
    if (statusBox) {
      statusBox.classList.add("error");
      statusBox.textContent = "删除失败";
    }
  }
}

async function saveCharacterPrompt() {
  const id = state.selectedCharacterId;
  const promptText = qs("characterPromptInput").value.trim();
  if (!state.selectedProject || !id || !promptText) {
    return;
  }
  await apiPost(`/api/projects/${state.selectedProject}/characters/${id}/prompt`, {
    prompt_text: promptText,
  });
  if (state.assetsCache && Array.isArray(state.assetsCache.character_details)) {
    state.assetsCache.character_details = state.assetsCache.character_details.map((item) => {
      if (String(item.character_id) === String(id)) {
        return { ...item, prompt: promptText };
      }
      return item;
    });
  }
  renderCharactersPanel(state.assetsCache || {});
}

async function saveClothChangedPrompt() {
  const item = state.selectedClothChangedItem;
  const promptText = qs("clothChangedPromptInput").value.trim();
  if (!state.selectedProject || !item || !promptText) {
    return;
  }
  await apiPost(
    `/api/projects/${state.selectedProject}/cloth-changed/${encodeURIComponent(
      item.character_id || ""
    )}/${encodeURIComponent(item.outfit_id || "")}/prompt`,
    {
      prompt_text: promptText,
    }
  );
  if (state.assetsCache && Array.isArray(state.assetsCache.cloth_changed_details)) {
    state.assetsCache.cloth_changed_details = state.assetsCache.cloth_changed_details.map((row) => {
      if (String(row.cloth_changed_id) === String(item.cloth_changed_id)) {
        return { ...row, prompt: promptText };
      }
      return row;
    });
  }
  renderClothChangedPanel(state.assetsCache || {});
}

async function deleteSelectedCharacterCandidate() {
  const id = state.selectedCharacterId;
  const candidatePath = state.selectedCharacterCandidatePath;
  const statusBox = qs("characterPublishStatus");
  if (!state.selectedProject || !id || !candidatePath) {
    return;
  }
  if (!candidatePath.includes("character_candidates")) {
    if (statusBox) {
      statusBox.classList.remove("hidden");
      statusBox.classList.add("error");
      statusBox.textContent = "只能删除候选图";
    }
    return;
  }
  try {
    await apiPost(`/api/projects/${state.selectedProject}/characters/${id}/candidate/delete`, {
      candidate_path: candidatePath,
    });
    state.selectedCharacterCandidatePath = "";
    await refreshAssets();
    if (statusBox) {
      statusBox.classList.remove("hidden", "error");
      statusBox.textContent = "已删除候选图";
    }
  } catch (err) {
    if (statusBox) {
      statusBox.classList.add("error");
      statusBox.textContent = "删除失败";
    }
  }
}

async function saveVideoPrompt() {
  const chapter = state.videoChapterTab;
  const id = state.selectedVideoFenjingId;
  const promptText = qs("videoPromptInput").value.trim();
  if (!state.selectedProject || !chapter || !id || !promptText) {
    return;
  }
  await apiPost(`/api/projects/${state.selectedProject}/chapters/${chapter}/video/${id}/prompt`, {
    prompt_text: promptText,
  });
  if (!state.videoPromptCache[chapter]) {
    state.videoPromptCache[chapter] = {};
  }
  state.videoPromptCache[chapter][String(id)] = promptText;
  renderVideosPanel(state.assetsCache || { chapters: [] });
}

async function regenSelectedVideo() {
  const chapter = state.videoChapterTab;
  const id = state.selectedVideoFenjingId;
  const promptText = qs("videoPromptInput").value.trim();
  const modelVersion = qs("videoModelSelect").value;
  if (!state.selectedProject || !chapter || !id) {
    return;
  }
  if (promptText) {
    await apiPost(`/api/projects/${state.selectedProject}/chapters/${chapter}/video/${id}/prompt`, {
      prompt_text: promptText,
    });
    if (!state.videoPromptCache[chapter]) {
      state.videoPromptCache[chapter] = {};
    }
    state.videoPromptCache[chapter][String(id)] = promptText;
  }
  const job = await apiPost(`/api/projects/${state.selectedProject}/regenerate/video`, {
    chapter_name: chapter,
    fenjing_id: id,
    model: modelVersion,
  });
  setJobs([job, ...state.jobs]);
  renderJobs();
  pollJob(job.id);
}

async function publishSelectedVideo() {
  const chapter = state.videoChapterTab;
  const id = state.selectedVideoFenjingId;
  const candidatePath = state.selectedVideoPath;
  const statusBox = qs("videoPublishStatus");
  if (!state.selectedProject || !chapter || !id || !candidatePath) {
    return;
  }
  let publishPath = candidatePath;
  if (!publishPath.startsWith("video/")) {
    const items = buildVideoListForChapter(state.assetsCache || {}, chapter);
    const fallback = items.find(
      (p) => p && p.startsWith("video/") && String(extractVideoFenjingId(p)) === String(id)
    );
    if (fallback) {
      publishPath = fallback;
      state.selectedVideoPath = fallback;
    }
  }
  if (!publishPath.startsWith("video/")) {
    if (statusBox) {
      statusBox.classList.remove("hidden");
      statusBox.classList.add("error");
      statusBox.textContent = "未找到候选视频，请先重生";
    }
    return;
  }
  if (statusBox) {
    statusBox.classList.remove("hidden", "error");
    statusBox.textContent = "上传中...";
  }
  let deleteFailed = false;
  try {
    await apiPost(`/api/projects/${state.selectedProject}/chapters/${chapter}/video/${id}/publish`, {
      candidate_path: publishPath,
    });
    try {
      await apiPost(
        `/api/projects/${state.selectedProject}/chapters/${chapter}/video/${id}/candidate/delete`,
        { candidate_path: publishPath }
      );
    } catch (err) {
      deleteFailed = true;
    }
    bumpMediaVersion();
    await refreshAssets();
    if (statusBox) {
      statusBox.textContent = deleteFailed ? "已上传，候选视频删除失败" : "已上传并覆盖视频";
    }
  } catch (err) {
    if (statusBox) {
      statusBox.classList.add("error");
      statusBox.textContent = "上传失败";
    }
  }
}

async function deleteSelectedVideoCandidate() {
  const chapter = state.videoChapterTab;
  const id = state.selectedVideoFenjingId;
  const candidatePath = state.selectedVideoPath;
  const statusBox = qs("videoPublishStatus");
  if (!state.selectedProject || !chapter || !id || !candidatePath) {
    return;
  }
  if (!candidatePath.startsWith("video/")) {
    if (statusBox) {
      statusBox.classList.remove("hidden");
      statusBox.classList.add("error");
      statusBox.textContent = "只能删除候选视频";
    }
    return;
  }
  try {
    await apiPost(`/api/projects/${state.selectedProject}/chapters/${chapter}/video/${id}/candidate/delete`, {
      candidate_path: candidatePath,
    });
    await refreshAssets();
    if (statusBox) {
      statusBox.classList.remove("hidden", "error");
      statusBox.textContent = "候选视频已删除";
    }
  } catch (err) {
    if (statusBox) {
      statusBox.classList.add("error");
      statusBox.textContent = "删除失败";
    }
  }
}

async function saveFenjingPrompt() {
  const chapter = state.storyboardChapterTab;
  const id = state.selectedFenjingId;
  const promptText = qs("fenjingPromptInput").value.trim();
  if (!state.selectedProject || !chapter || !id || !promptText) {
    return;
  }
  await apiPost(`/api/projects/${state.selectedProject}/chapters/${chapter}/fenjing/${id}/prompt`, {
    prompt_text: promptText,
  });
  if (!state.fenjingPromptCache[chapter]) {
    state.fenjingPromptCache[chapter] = {};
  }
  state.fenjingPromptCache[chapter][String(id)] = promptText;
  if (state.assetsCache && state.assetsCache.fenjing_details && state.assetsCache.fenjing_details[chapter]) {
    state.assetsCache.fenjing_details[chapter] = state.assetsCache.fenjing_details[chapter].map((item) => {
      if (String(item.fenjing_id) === String(id)) {
        return { ...item, prompt: promptText };
      }
      return item;
    });
  }
  renderStoryboardsPanel(state.assetsCache || { chapters: [] });
}

function showLogModal() {
  const modal = qs("logModal");
  if (modal) {
    modal.classList.remove("hidden");
    preloadLogPages();
  }
}

function hideLogModal() {
  const modal = qs("logModal");
  if (modal) {
    modal.classList.add("hidden");
  }
}

async function preloadLogPages() {
  const jobs = state.jobs || [];
  await Promise.all(jobs.map((job) => ensureJobLogPage(job)));
  filterLogContent();
}

async function ensureJobLogPage(job) {
  if (!job || !job.id) {
    return;
  }
  if (state.logPageCache[job.id] || state.logPageLoading[job.id]) {
    return;
  }
  state.logPageLoading[job.id] = true;
  try {
    const page = await apiGet(`/api/jobs/${job.id}/logs?limit=200`);
    state.logPageCache[job.id] = {
      lines: Array.isArray(page.lines) ? page.lines : [],
      offset: page.offset || 0,
      prevOffset: page.prev_offset || 0,
      hasMore: !!page.has_more,
      displayName: page.log_display_name || "",
      createdAt: page.log_created_at || job.created_at,
    };
  } catch (err) {
    state.logPageCache[job.id] = {
      lines: Array.isArray(job.log_tail) ? job.log_tail : [],
      offset: 0,
      prevOffset: 0,
      hasMore: false,
      displayName: job.log_display_name || "",
      createdAt: job.log_created_at || job.created_at,
    };
  } finally {
    state.logPageLoading[job.id] = false;
  }
}

async function loadMoreLogs(jobId) {
  const cached = state.logPageCache[jobId];
  if (!cached || state.logPageLoading[jobId]) {
    return;
  }
  if (!cached.hasMore) {
    return;
  }
  state.logPageLoading[jobId] = true;
  try {
    const page = await apiGet(`/api/jobs/${jobId}/logs?limit=200&offset=${cached.prevOffset}`);
    const newLines = Array.isArray(page.lines) ? page.lines : [];
    cached.lines = newLines.concat(cached.lines || []);
    cached.offset = page.offset || cached.offset;
    cached.prevOffset = page.prev_offset || 0;
    cached.hasMore = !!page.has_more;
  } finally {
    state.logPageLoading[jobId] = false;
    filterLogContent();
  }
}

function filterLogContent() {
  const filter = qs("logStepFilter");
  const content = qs("logContent");
  if (!filter || !content) {
    return;
  }
  
  const selectedStep = filter.value;
  const jobs = state.jobs || [];
  
  let html = "";
  
  const filteredJobs = selectedStep 
    ? jobs.filter(job => {
        const flow = getFlowFromJob(job);
        return flow === selectedStep;
      })
    : jobs;
  
  if (filteredJobs.length === 0) {
    html = '<div class="log-entry info">暂无日志</div>';
  } else {
    filteredJobs.forEach(job => {
      const flow = getFlowFromJob(job);
      const flowName = formatJobType(job.type);
      const status = formatJobStatus(job.status);
      const time = formatJobTime(job.updated_at || job.created_at);
      const cached = state.logPageCache[job.id] || {};
      const displayName = cached.displayName || job.log_display_name || job.log_path || "";
      const logLines = Array.isArray(cached.lines)
        ? cached.lines
        : (Array.isArray(job.log_tail) ? job.log_tail : []);
      const hasMore = cached.hasMore;
      const isLoading = !!state.logPageLoading[job.id];
      
      let entryClass = "info";
      if (job.status === "error") {
        entryClass = "error";
      } else if (job.status === "completed" || job.status === "success") {
        entryClass = "success";
      }
      
      html += `<div class="log-entry ${entryClass}">`;
      html += `<div class="log-timestamp">${time}</div>`;
      html += `<div class="log-message"><strong>${flowName}</strong> · ${status}</div>`;
      
      if (job.project) {
        html += `<div class="log-message">项目：${job.project}</div>`;
      }

      if (displayName) {
        html += `<div class="log-message">日志文件：${displayName}</div>`;
      }
      
      if (job.error) {
        html += `<div class="log-message" style="color: #f43f5e;">错误：${job.error}</div>`;
      }
      
      const logs = logLines.join("\n");
      if (logs) {
        html += `<div class="log-message" style="white-space: pre-wrap; margin-top: 8px; font-size: 11px; color: #94a3b8;">${logs}</div>`;
      }

      if (hasMore) {
        html += `<div class="log-actions">`;
        html += `<button class="log-load-more" data-job="${job.id}" ${isLoading ? "disabled" : ""}>${isLoading ? "加载中" : "加载更多"}</button>`;
        html += `</div>`;
      }
      
      html += `</div>`;
    });
  }
  
  content.innerHTML = html;
  content.querySelectorAll(".log-load-more").forEach((btn) => {
    btn.onclick = () => loadMoreLogs(btn.dataset.job);
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  qs("createProject").onclick = createProject;
  const openAuthConfigBtn = qs("openAuthConfig");
  if (openAuthConfigBtn) {
    openAuthConfigBtn.onclick = () => {
      window.location.href = "/auth-config";
    };
  }
  const uploadNovelBtn = qs("uploadNovel");
  if (uploadNovelBtn) {
    uploadNovelBtn.onclick = submitNovel;
  }
  qs("backHome").onclick = () => {
    state.selectedProject = "";
    Object.values(state.jobPolling).forEach((timer) => clearInterval(timer));
    state.jobPolling = {};
    stopFlowStatusPolling();
    state.jobs = [];
    renderJobs();
    showHomeView();
    renderProjects();
    syncUrlState(false);
  };
  qs("regenFenjingDetail").onclick = regenSelectedFenjing;
  qs("publishFenjingImage").onclick = publishSelectedFenjing;
  qs("deleteFenjingCandidate").onclick = deleteSelectedFenjingCandidate;
  qs("saveFenjingPrompt").onclick = saveFenjingPrompt;
  qs("regenVideoDetail").onclick = regenSelectedVideo;
  qs("publishVideo").onclick = publishSelectedVideo;
  qs("deleteVideoCandidate").onclick = deleteSelectedVideoCandidate;
  qs("saveVideoPrompt").onclick = saveVideoPrompt;
  qs("regenCharacterDetail").onclick = regenSelectedCharacter;
  qs("publishCharacterImage").onclick = publishSelectedCharacter;
  qs("deleteCharacterCandidate").onclick = deleteSelectedCharacterCandidate;
  qs("saveCharacterPrompt").onclick = saveCharacterPrompt;
  qs("regenClothChangedDetail").onclick = regenSelectedClothChanged;
  qs("publishClothChangedImage").onclick = publishSelectedClothChanged;
  qs("deleteClothChangedCandidate").onclick = deleteSelectedClothChangedCandidate;
  qs("saveClothChangedPrompt").onclick = saveClothChangedPrompt;
  const flowLogBtn = qs("flowLogBtn");
  if (flowLogBtn) {
    flowLogBtn.onclick = showLogModal;
  }
  qs("logModalClose").onclick = hideLogModal;
  qs("logStepFilter").onchange = filterLogContent;
  qs("logModal").onclick = (event) => {
    if (event.target === qs("logModal")) {
      hideLogModal();
    }
  };
  document.querySelectorAll("[data-flow]").forEach((btn) => {
    btn.onclick = () => submitFlow(btn.dataset.flow);
  });
  document.querySelectorAll("#tableTabs .tab").forEach((btn) => {
    btn.onclick = () => setActiveTableTab(btn.dataset.tab);
  });
  document.querySelectorAll(".project-main-tabs .tab").forEach((btn) => {
    btn.onclick = () => setActiveMainTab(btn.dataset.mainTab);
  });
  const configScope = qs("configScope");
  if (configScope) {
    configScope.value = state.configScope;
    configScope.onchange = () => {
      state.configScope = configScope.value;
      renderConfigTable();
      renderAuthTable();
    };
  }
  const reloadConfigBtn = qs("reloadConfig");
  if (reloadConfigBtn) {
    reloadConfigBtn.onclick = loadConfigData;
  }
  const saveConfigBtn = qs("saveConfig");
  if (saveConfigBtn) {
    saveConfigBtn.onclick = saveConfigOverrides;
  }
  const resetConfigBtn = qs("resetConfig");
  if (resetConfigBtn) {
    resetConfigBtn.onclick = resetConfigOverrides;
  }
  const reloadAuthConfigBtn = qs("reloadAuthConfig");
  if (reloadAuthConfigBtn) {
    reloadAuthConfigBtn.onclick = loadAuthConfigData;
  }
  const saveAuthConfigBtn = qs("saveAuthConfig");
  if (saveAuthConfigBtn) {
    saveAuthConfigBtn.onclick = saveAuthConfigOverrides;
  }
  const resetAuthConfigBtn = qs("resetAuthConfig");
  if (resetAuthConfigBtn) {
    resetAuthConfigBtn.onclick = resetAuthConfigOverrides;
  }
  const handleArrowSwitch = (event) => {
    if (!state.selectedProject) {
      return;
    }
    if (state.mainTab !== "storyboards" && state.mainTab !== "locations" && state.mainTab !== "videos" && state.mainTab !== "characters") {
      return;
    }
    if (isEditableTarget(event.target || document.activeElement)) {
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      if (event.type === "keydown") {
        if (state.mainTab === "storyboards") {
          selectFenjingByOffset(-1);
        } else if (state.mainTab === "locations") {
          selectLocationByOffset(-1);
        } else if (state.mainTab === "characters") {
          selectCharacterByOffset(-1);
        } else {
          selectVideoByOffset(-1);
        }
      }
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      if (event.type === "keydown") {
        if (state.mainTab === "storyboards") {
          selectFenjingByOffset(1);
        } else if (state.mainTab === "locations") {
          selectLocationByOffset(1);
        } else if (state.mainTab === "characters") {
          selectCharacterByOffset(1);
        } else {
          selectVideoByOffset(1);
        }
      }
    }
  };
  window.addEventListener("keydown", handleArrowSwitch, { capture: true, passive: false });
  window.addEventListener("keyup", handleArrowSwitch, { capture: true, passive: false });

  const handleWindowScroll = () => {
    if (state.mainTab !== "storyboards" && state.mainTab !== "videos" && state.mainTab !== "characters") {
      return;
    }
    const leftContainer = document.querySelector(`#tab${state.mainTab === "storyboards" ? "Storyboards" : state.mainTab === "videos" ? "Videos" : "Characters"} .storyboard-left`);
    if (!leftContainer) {
      return;
    }
    leftContainer.style.transform = `translateY(${window.scrollY}px)`;
  };
  window.addEventListener("scroll", handleWindowScroll, { passive: true });

  const urlState = loadUrlState();
  state.savedProject = loadProjectPreference();
  state.flowTouched = loadFlowTouchedMap();
  if (urlState.project) {
    state.selectedProject = urlState.project;
    state.autoSelectProject = true;
  } else if (urlState.tab) {
    state.pendingTab = urlState.tab;
    state.autoSelectProject = true;
  } else {
    state.autoSelectProject = false;
  }
  if (urlState.tab) {
    state.mainTab = urlState.tab;
  } else {
    const savedMainTab = loadMainTabPreference();
    if (savedMainTab) {
      state.mainTab = savedMainTab;
    }
  }
  await refreshProjects();
});
