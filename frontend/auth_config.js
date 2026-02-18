const state = {
  authItems: [],
  videoModelItems: [],
};

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

function showVideoModelConfigStatus(message, isError) {
  const box = qs("videoModelConfigStatus");
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
  const items = state.authItems || [];
  if (!items.length) {
    return;
  }
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
    valueCell.appendChild(input);
    tr.appendChild(valueCell);
    const sourceCell = document.createElement("td");
    sourceCell.textContent = item.source || "";
    tr.appendChild(sourceCell);
    const defaultCell = document.createElement("td");
    defaultCell.textContent =
      item.default !== undefined && item.default !== null ? String(item.default) : "";
    tr.appendChild(defaultCell);
    const descCell = document.createElement("td");
    descCell.textContent = item.description || "";
    tr.appendChild(descCell);
    tbody.appendChild(tr);
  });
}

function renderVideoModelTable() {
  const table = qs("videoModelConfigTable");
  if (!table) {
    return;
  }
  const tbody = table.querySelector("tbody");
  if (!tbody) {
    return;
  }
  tbody.innerHTML = "";
  const items = state.videoModelItems || [];
  if (!items.length) {
    return;
  }
  items.forEach((item) => {
    const tr = document.createElement("tr");
    
    // 配置项名称
    const keyCell = document.createElement("td");
    keyCell.textContent = item.key || item.id || "";
    tr.appendChild(keyCell);
    
    // 当前值（输入框）
    const valueCell = document.createElement("td");
    const input = document.createElement("input");
    input.type = "text";
    input.className = "video-model-input";
    
    // 判断是否有值
    const hasValue = item.value !== undefined && item.value !== null && String(item.value).trim() !== "";
    
    // 判断是否已配置（source为global或runtime表示已配置）
    const isConfigured = item.source === "global" || item.source === "runtime" || item.source === "env";
    
    input.value = hasValue ? String(item.value) : "";
    
    // 设置placeholder：
    // - 如果已配置（source=global/runtime/env）显示"已设置"
    // - 否则显示默认值或格式提示
    if (isConfigured) {
      input.placeholder = "已设置";
    } else if (item.default) {
      input.placeholder = item.default;
    } else {
      input.placeholder = "ep-YYYYMMDD-xxxxx";
    }
    
    input.dataset.videoModelId = item.id;
    valueCell.appendChild(input);
    tr.appendChild(valueCell);
    
    // 来源
    const sourceCell = document.createElement("td");
    sourceCell.textContent = item.source || "";
    tr.appendChild(sourceCell);
    
    // 说明
    const descCell = document.createElement("td");
    descCell.textContent = item.description || "";
    tr.appendChild(descCell);
    
    tbody.appendChild(tr);
  });
}

async function loadAuthConfigData() {
  showAuthConfigStatus("加载中", false);
  showVideoModelConfigStatus("加载中", false);
  try {
    const data = await apiGet("/api/config/auth");
    const allItems = data.items || [];
    
    // 分离鉴权配置和视频模型配置
    state.authItems = allItems.filter(item => !item.id.startsWith("auth.video_model"));
    state.videoModelItems = allItems.filter(item => item.id.startsWith("auth.video_model"));
    
    renderAuthTable();
    renderVideoModelTable();
    
    showAuthConfigStatus("已刷新", false);
    showVideoModelConfigStatus("已刷新", false);
  } catch (err) {
    showAuthConfigStatus("加载失败", true);
    showVideoModelConfigStatus("加载失败", true);
  }
}

function collectAuthUpdates() {
  const updates = {};
  (state.authItems || []).forEach((item) => {
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

function collectAuthResetUpdates() {
  const updates = {};
  (state.authItems || []).forEach((item) => {
    if (item.source === "global") {
      updates[item.id] = null;
    }
  });
  return updates;
}

async function saveAuthConfigOverrides() {
  const updates = collectAuthUpdates();
  if (!updates || Object.keys(updates).length === 0) {
    showAuthConfigStatus("没有需要保存的变更", false);
    return;
  }
  try {
    await apiPatch("/api/config/auth", { scope: "global", items: updates });
    await loadAuthConfigData();
    showAuthConfigStatus("已保存并生效", false);
  } catch (err) {
    showAuthConfigStatus("保存失败", true);
  }
}

async function resetAuthConfigOverrides() {
  const updates = collectAuthResetUpdates();
  if (!updates || Object.keys(updates).length === 0) {
    showAuthConfigStatus("没有可重置的覆盖", false);
    return;
  }
  try {
    await apiPatch("/api/config/auth", { scope: "global", items: updates });
    await loadAuthConfigData();
    showAuthConfigStatus("已重置", false);
  } catch (err) {
    showAuthConfigStatus("重置失败", true);
  }
}

// 视频模型配置相关函数
function collectVideoModelUpdates() {
  const updates = {};
  (state.videoModelItems || []).forEach((item) => {
    const input = document.querySelector(`input[data-video-model-id="${item.id}"]`);
    if (!input) {
      return;
    }
    const raw = input.value.trim();
    // 如果值发生变化，则加入更新列表
    if (raw !== (item.value || "")) {
      updates[item.id] = raw;
    }
  });
  return updates;
}

function collectVideoModelResetUpdates() {
  const updates = {};
  (state.videoModelItems || []).forEach((item) => {
    if (item.source === "global") {
      updates[item.id] = null;
    }
  });
  return updates;
}

async function saveVideoModelConfigOverrides() {
  const updates = collectVideoModelUpdates();
  if (!updates || Object.keys(updates).length === 0) {
    showVideoModelConfigStatus("没有需要保存的变更", false);
    return;
  }
  showVideoModelConfigStatus("保存中...", false);
  try {
    await apiPatch("/api/config/auth", { scope: "global", items: updates });
    await loadAuthConfigData();
    
    // 检查是否有保存空值的情况，给用户明确提示
    const emptyUpdates = Object.entries(updates).filter(([key, value]) => !value || value.trim() === "");
    if (emptyUpdates.length > 0) {
      showVideoModelConfigStatus("已保存（空值将使用默认配置）", false);
    } else {
      showVideoModelConfigStatus("已保存并生效", false);
    }
  } catch (err) {
    showVideoModelConfigStatus("保存失败: " + err.message, true);
  }
}

async function resetVideoModelConfigOverrides() {
  const updates = collectVideoModelResetUpdates();
  if (!updates || Object.keys(updates).length === 0) {
    showVideoModelConfigStatus("没有可重置的覆盖", false);
    return;
  }
  showVideoModelConfigStatus("重置中...", false);
  try {
    await apiPatch("/api/config/auth", { scope: "global", items: updates });
    await loadAuthConfigData();
    showVideoModelConfigStatus("已重置", false);
  } catch (err) {
    showVideoModelConfigStatus("重置失败: " + err.message, true);
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  const backHomeBtn = qs("backHome");
  if (backHomeBtn) {
    backHomeBtn.onclick = () => {
      window.location.href = "/";
    };
  }
  // 鉴权配置按钮
  const reloadBtn = qs("reloadAuthConfig");
  if (reloadBtn) {
    reloadBtn.onclick = loadAuthConfigData;
  }
  const saveBtn = qs("saveAuthConfig");
  if (saveBtn) {
    saveBtn.onclick = saveAuthConfigOverrides;
  }
  const resetBtn = qs("resetAuthConfig");
  if (resetBtn) {
    resetBtn.onclick = resetAuthConfigOverrides;
  }
  
  // 视频模型配置按钮
  const reloadVideoModelBtn = qs("reloadVideoModelConfig");
  if (reloadVideoModelBtn) {
    reloadVideoModelBtn.onclick = loadAuthConfigData;
  }
  const saveVideoModelBtn = qs("saveVideoModelConfig");
  if (saveVideoModelBtn) {
    saveVideoModelBtn.onclick = saveVideoModelConfigOverrides;
  }
  const resetVideoModelBtn = qs("resetVideoModelConfig");
  if (resetVideoModelBtn) {
    resetVideoModelBtn.onclick = resetVideoModelConfigOverrides;
  }
  
  await loadAuthConfigData();
});
