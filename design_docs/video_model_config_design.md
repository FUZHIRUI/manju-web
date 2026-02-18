# 视频模型端点前端配置设计文档

## 1. 概述

### 1.1 背景
当前视频生成流程需要配置视频模型端点 (`VIDEO_MODEL_1_5_EP` 和 `VIDEO_MODEL_1_0_EP`)，但这些配置只能通过环境变量设置，导致用户体验不佳。本设计旨在通过前端配置页面提供动态配置能力。

### 1.2 目标
- 在 `/auth-config` 页面增加视频模型端点配置
- 支持实时生效，无需重启服务
- 保持与现有配置系统的兼容性

### 1.3 范围
- 前端：扩展配置页面UI
- 后端：扩展配置API和运行时同步
- 数据：配置持久化和读取

## 2. 架构设计

### 2.1 系统架构图

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   前端页面       │────▶│   后端API       │────▶│   配置存储       │
│  /auth-config   │     │ /api/config/auth│     │ global_config.json
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                       │                       │
         │                       ▼                       │
         │              ┌─────────────────┐              │
         │              │  runtime_config │◀─────────────┘
         │              │  (内存配置)      │
         │              └─────────────────┘
         │                       │
         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│  视频生成流程    │◀────│  video.py       │
│  (使用新配置)    │     │  (读取模型端点)  │
└─────────────────┘     └─────────────────┘
```

### 2.2 数据流

```
用户输入配置
    │
    ▼
┌─────────────┐
│ PATCH /api/ │
│ config/auth │
└─────────────┘
    │
    ▼
┌─────────────┐    ┌─────────────┐
│ config_repo │───▶│ global_config
│  (保存)      │    │ .json       │
└─────────────┘    └─────────────┘
    │
    ▼
┌─────────────┐
│runtime_config│
│  (同步更新)  │
└─────────────┘
    │
    ▼
┌─────────────┐
│ video.py    │
│ (读取使用)   │
└─────────────┘
```

## 3. 详细设计

### 3.1 后端设计

#### 3.1.1 配置定义扩展

**文件**: `backend/services/config_service.py`

```python
def _auth_definitions() -> List[Dict[str, Any]]:
    return [
        # ... 现有配置项 ...
        {
            "id": "auth.video_model_1_5_ep",
            "stage": "video",
            "key": "video_model_1_5_ep",
            "type": "string",
            "env": "VIDEO_MODEL_1_5_EP",
            "default": config_defaults.DEFAULT_VIDEO_MODEL_1_5_EP,
            "scope": "global",
            "description": "视频生成模型1.5端点ID (如: ep-20250101-xxxxx)",
            "sensitive": False,
        },
        {
            "id": "auth.video_model_1_0_ep",
            "stage": "video",
            "key": "video_model_1_0_ep",
            "type": "string",
            "env": "VIDEO_MODEL_1_0_EP",
            "default": config_defaults.DEFAULT_VIDEO_MODEL_1_0_EP,
            "scope": "global",
            "description": "视频生成模型1.0端点ID (如: ep-20250101-xxxxx)",
            "sensitive": False,
        },
    ]
```

#### 3.1.2 配置同步机制

**文件**: `backend/services/config_service.py`

```python
def _sync_to_runtime_config(key: str, value: Any) -> None:
    """将配置同步到运行时配置"""
    from .workflow_runtime import runtime_config
    
    if key == "auth.video_model_1_5_ep":
        runtime_config.VIDEO_MODEL_1_5_EP = value or ""
    elif key == "auth.video_model_1_0_ep":
        runtime_config.VIDEO_MODEL_1_0_EP = value or ""


def update_auth_config(
    project: str, 
    scope: str, 
    updates: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """更新鉴权配置并同步到运行时"""
    # 1. 验证配置项
    definitions = {d["id"]: d for d in _auth_definitions()}
    
    # 2. 保存到存储
    storage_key = "global" if scope == "global" else project
    current = config_repo.load_auth_config(storage_key)
    
    for key, value in updates.items():
        if key not in definitions:
            continue
        
        # 验证值类型
        def_config = definitions[key]
        validated_value = _validate_value(value, def_config)
        
        # 更新存储
        if storage_key not in current:
            current[storage_key] = {}
        if validated_value is None or validated_value == def_config.get("default"):
            current[storage_key].pop(key, None)
        else:
            current[storage_key][key] = validated_value
        
        # 同步到运行时
        _sync_to_runtime_config(key, validated_value)
    
    # 3. 持久化
    config_repo.save_auth_config(storage_key, current)
    
    # 4. 返回更新后的配置
    return get_auth_config(project)
```

#### 3.1.3 配置加载同步

**文件**: `backend/services/config_service.py`

```python
def get_auth_config(project: str) -> List[Dict[str, Any]]:
    """获取鉴权配置，包括运行时值"""
    definitions = _auth_definitions()
    
    # 加载存储的配置
    global_config = config_repo.load_auth_config("global")
    project_config = config_repo.load_auth_config(project) if project else {}
    
    # 合并配置
    result = []
    for def_config in definitions:
        item = dict(def_config)
        item_id = def_config["id"]
        
        # 确定值来源
        if item_id in global_config.get("global", {}):
            item["value"] = global_config["global"][item_id]
            item["source"] = "global"
        elif item_id in project_config.get(project, {}):
            item["value"] = project_config[project][item_id]
            item["source"] = "project"
        else:
            # 从运行时配置读取
            item["value"] = _get_runtime_value(item_id)
            item["source"] = "env" if item["value"] else "default"
        
        result.append(item)
    
    return result


def _get_runtime_value(key: str) -> Any:
    """从运行时配置获取值"""
    from .workflow_runtime import runtime_config
    
    if key == "auth.video_model_1_5_ep":
        return runtime_config.VIDEO_MODEL_1_5_EP
    elif key == "auth.video_model_1_0_ep":
        return runtime_config.VIDEO_MODEL_1_0_EP
    return None
```

#### 3.1.4 初始化同步

**文件**: `backend/services/workflow_runtime/runtime_config.py`

在 `load()` 函数末尾增加：

```python
def load() -> None:
    # ... 现有加载逻辑 ...
    
    # 同步视频模型配置从存储到运行时
    _sync_video_model_config()


def _sync_video_model_config() -> None:
    """从配置存储同步视频模型配置到运行时"""
    from .. import config_service, config_repo
    
    global_config = config_repo.load_auth_config("global")
    global_items = global_config.get("global", {})
    
    # 同步 VIDEO_MODEL_1_5_EP
    key_1_5 = "auth.video_model_1_5_ep"
    if key_1_5 in global_items:
        global VIDEO_MODEL_1_5_EP
        VIDEO_MODEL_1_5_EP = global_items[key_1_5] or ""
    
    # 同步 VIDEO_MODEL_1_0_EP
    key_1_0 = "auth.video_model_1_0_ep"
    if key_1_0 in global_items:
        global VIDEO_MODEL_1_0_EP
        VIDEO_MODEL_1_0_EP = global_items[key_1_0] or ""
```

### 3.2 前端设计

#### 3.2.1 页面结构

**文件**: `frontend/auth_config.html`

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>配置</title>
    <link rel="stylesheet" href="/static/style.css">
    <style>
        /* 新增样式 */
        .config-section {
            margin-bottom: 30px;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 20px;
        }
        .config-section-title {
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 15px;
            color: #333;
        }
        .config-input {
            width: 100%;
            padding: 8px 12px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 14px;
        }
        .config-input:focus {
            border-color: #4CAF50;
            outline: none;
        }
        .config-help {
            font-size: 12px;
            color: #666;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <div class="app">
        <header class="header">
            <div class="title">配置</div>
            <div class="project-actions">
                <button id="backHome">返回主页</button>
            </div>
        </header>
        
        <div class="project-content">
            <!-- 鉴权配置区域 -->
            <div class="config-section">
                <div class="config-header">
                    <div class="config-title">鉴权与连接配置</div>
                    <div class="config-actions">
                        <button id="reloadAuthConfig">刷新</button>
                        <button id="saveAuthConfig">保存</button>
                        <button id="resetAuthConfig">重置覆盖</button>
                        <div id="authConfigStatus" class="status-inline hidden"></div>
                    </div>
                </div>
                <div class="config-table-wrap">
                    <table class="data-table" id="authConfigTable">
                        <thead>
                            <tr>
                                <th>阶段</th>
                                <th>配置项</th>
                                <th>当前值</th>
                                <th>来源</th>
                                <th>默认值</th>
                                <th>说明</th>
                            </tr>
                        </thead>
                        <tbody></tbody>
                    </table>
                </div>
            </div>
            
            <!-- 视频模型配置区域 (新增) -->
            <div class="config-section">
                <div class="config-header">
                    <div class="config-title">视频模型配置</div>
                    <div class="config-actions">
                        <button id="reloadVideoModelConfig">刷新</button>
                        <button id="saveVideoModelConfig">保存</button>
                        <button id="resetVideoModelConfig">重置</button>
                        <div id="videoModelConfigStatus" class="status-inline hidden"></div>
                    </div>
                </div>
                <div class="config-table-wrap">
                    <table class="data-table" id="videoModelConfigTable">
                        <thead>
                            <tr>
                                <th>配置项</th>
                                <th>当前值</th>
                                <th>来源</th>
                                <th>说明</th>
                            </tr>
                        </thead>
                        <tbody></tbody>
                    </table>
                </div>
                <div class="config-help">
                    提示：视频模型端点ID可从火山引擎ARK平台获取，格式为 ep-YYYYMMDD-xxxxx
                </div>
            </div>
        </div>
    </div>
    
    <script src="/static/auth_config.js"></script>
</body>
</html>
```

#### 3.2.2 JavaScript逻辑

**文件**: `frontend/auth_config.js`

```javascript
// 状态管理
const state = {
  authItems: [],
  videoModelItems: [],
};

// DOM查询工具
function qs(id) {
  return document.getElementById(id);
}

// API调用
async function apiGet(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function apiPatch(path, payload) {
  const res = await fetch(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// 状态显示
function showStatus(elementId, message, isError) {
  const box = qs(elementId);
  if (!box) return;
  
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

// 渲染鉴权配置表
function renderAuthTable() {
  const table = qs("authConfigTable");
  const tbody = table.querySelector("tbody");
  tbody.innerHTML = "";
  
  const items = state.authItems || [];
  items.forEach((item) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${item.stage || ""}</td>
      <td>${item.key || item.id || ""}</td>
      <td><input type="${item.sensitive ? 'password' : 'text'}" 
                 value="${item.value || ''}" 
                 data-auth-id="${item.id}"></td>
      <td>${item.source || ""}</td>
      <td>${item.default || ""}</td>
      <td>${item.description || ""}</td>
    `;
    tbody.appendChild(tr);
  });
}

// 渲染视频模型配置表 (新增)
function renderVideoModelTable() {
  const table = qs("videoModelConfigTable");
  const tbody = table.querySelector("tbody");
  tbody.innerHTML = "";
  
  const items = state.videoModelItems || [];
  items.forEach((item) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${item.key || item.id || ""}</td>
      <td>
        <input type="text" 
               class="config-input"
               value="${item.value || ''}" 
               data-video-model-id="${item.id}"
               placeholder="${item.default || 'ep-YYYYMMDD-xxxxx'}">
      </td>
      <td>${item.source || ""}</td>
      <td>${item.description || ""}</td>
    `;
    tbody.appendChild(tr);
  });
}

// 加载配置数据
async function loadConfigData() {
  showStatus("authConfigStatus", "加载中...", false);
  showStatus("videoModelConfigStatus", "加载中...", false);
  
  try {
    const data = await apiGet("/api/config/auth");
    const allItems = data.items || [];
    
    // 分离配置项
    state.authItems = allItems.filter(item => 
      !item.id.startsWith("auth.video_model")
    );
    state.videoModelItems = allItems.filter(item => 
      item.id.startsWith("auth.video_model")
    );
    
    renderAuthTable();
    renderVideoModelTable();
    
    showStatus("authConfigStatus", "已刷新", false);
    showStatus("videoModelConfigStatus", "已刷新", false);
  } catch (err) {
    showStatus("authConfigStatus", "加载失败: " + err.message, true);
    showStatus("videoModelConfigStatus", "加载失败", true);
  }
}

// 收集鉴权配置更新
function collectAuthUpdates() {
  const updates = {};
  state.authItems.forEach((item) => {
    const input = document.querySelector(`input[data-auth-id="${item.id}"]`);
    if (!input) return;
    
    const raw = input.value.trim();
    if (raw && raw !== item.default) {
      updates[item.id] = raw;
    }
  });
  return updates;
}

// 收集视频模型配置更新 (新增)
function collectVideoModelUpdates() {
  const updates = {};
  state.videoModelItems.forEach((item) => {
    const input = document.querySelector(`input[data-video-model-id="${item.id}"]`);
    if (!input) return;
    
    const raw = input.value.trim();
    // 视频模型配置：空值表示使用默认值
    if (raw !== item.value) {
      updates[item.id] = raw;
    }
  });
  return updates;
}

// 保存鉴权配置
async function saveAuthConfig() {
  const updates = collectAuthUpdates();
  if (Object.keys(updates).length === 0) {
    showStatus("authConfigStatus", "没有变更", false);
    return;
  }
  
  try {
    await apiPatch("/api/config/auth", { scope: "global", items: updates });
    await loadConfigData();
    showStatus("authConfigStatus", "已保存", false);
  } catch (err) {
    showStatus("authConfigStatus", "保存失败: " + err.message, true);
  }
}

// 保存视频模型配置 (新增)
async function saveVideoModelConfig() {
  const updates = collectVideoModelUpdates();
  if (Object.keys(updates).length === 0) {
    showStatus("videoModelConfigStatus", "没有变更", false);
    return;
  }
  
  try {
    await apiPatch("/api/config/auth", { scope: "global", items: updates });
    await loadConfigData();
    showStatus("videoModelConfigStatus", "已保存", false);
  } catch (err) {
    showStatus("videoModelConfigStatus", "保存失败: " + err.message, true);
  }
}

// 重置鉴权配置
async function resetAuthConfig() {
  const updates = {};
  state.authItems.forEach((item) => {
    if (item.source === "global") {
      updates[item.id] = null;
    }
  });
  
  if (Object.keys(updates).length === 0) {
    showStatus("authConfigStatus", "没有可重置的", false);
    return;
  }
  
  try {
    await apiPatch("/api/config/auth", { scope: "global", items: updates });
    await loadConfigData();
    showStatus("authConfigStatus", "已重置", false);
  } catch (err) {
    showStatus("authConfigStatus", "重置失败: " + err.message, true);
  }
}

// 重置视频模型配置 (新增)
async function resetVideoModelConfig() {
  const updates = {};
  state.videoModelItems.forEach((item) => {
    if (item.source === "global") {
      updates[item.id] = null;
    }
  });
  
  if (Object.keys(updates).length === 0) {
    showStatus("videoModelConfigStatus", "没有可重置的", false);
    return;
  }
  
  try {
    await apiPatch("/api/config/auth", { scope: "global", items: updates });
    await loadConfigData();
    showStatus("videoModelConfigStatus", "已重置", false);
  } catch (err) {
    showStatus("videoModelConfigStatus", "重置失败: " + err.message, true);
  }
}

// 初始化
document.addEventListener("DOMContentLoaded", () => {
  // 返回主页
  qs("backHome")?.addEventListener("click", () => {
    window.location.href = "/";
  });
  
  // 鉴权配置按钮
  qs("reloadAuthConfig")?.addEventListener("click", loadConfigData);
  qs("saveAuthConfig")?.addEventListener("click", saveAuthConfig);
  qs("resetAuthConfig")?.addEventListener("click", resetAuthConfig);
  
  // 视频模型配置按钮 (新增)
  qs("reloadVideoModelConfig")?.addEventListener("click", loadConfigData);
  qs("saveVideoModelConfig")?.addEventListener("click", saveVideoModelConfig);
  qs("resetVideoModelConfig")?.addEventListener("click", resetVideoModelConfig);
  
  // 加载初始数据
  loadConfigData();
});
```

## 4. 数据模型

### 4.1 配置存储格式

**文件**: `config/global_config.json`

```json
{
  "defaults": {
    "auth.ark_base_url": "https://ark.cn-beijing.volces.com/api/v3",
    "auth.ark_api_key": "",
    "auth.video_model_1_5_ep": "",
    "auth.video_model_1_0_ep": ""
  },
  "items": {
    "global": {
      "auth.video_model_1_5_ep": "ep-20250101-abc123",
      "auth.video_model_1_0_ep": "ep-20250101-def456"
    }
  }
}
```

### 4.2 API数据模型

**请求**: `PATCH /api/config/auth`

```json
{
  "scope": "global",
  "items": {
    "auth.video_model_1_5_ep": "ep-20250101-abc123",
    "auth.video_model_1_0_ep": "ep-20250101-def456"
  }
}
```

**响应**: `GET /api/config/auth`

```json
{
  "items": [
    {
      "id": "auth.video_model_1_5_ep",
      "stage": "video",
      "key": "video_model_1_5_ep",
      "type": "string",
      "value": "ep-20250101-abc123",
      "source": "global",
      "default": "",
      "description": "视频生成模型1.5端点ID (如: ep-20250101-xxxxx)",
      "sensitive": false
    },
    {
      "id": "auth.video_model_1_0_ep",
      "stage": "video",
      "key": "video_model_1_0_ep",
      "type": "string",
      "value": "ep-20250101-def456",
      "source": "global",
      "default": "",
      "description": "视频生成模型1.0端点ID (如: ep-20250101-xxxxx)",
      "sensitive": false
    }
  ]
}
```

## 5. 接口设计

### 5.1 现有接口扩展

| 接口 | 方法 | 变更 | 说明 |
|------|------|------|------|
| `/api/config/auth` | GET | 扩展 | 响应中增加视频模型配置项 |
| `/api/config/auth` | PATCH | 扩展 | 支持更新视频模型配置项 |

### 5.2 接口详细规范

#### GET /api/config/auth

**请求参数**:
- `project` (可选): 项目名

**响应**:
```typescript
{
  items: Array<{
    id: string;           // 配置项ID
    stage: string;        // 阶段
    key: string;          // 配置键
    type: string;         // 类型
    value: string;        // 当前值
    source: string;       // 来源: env/default/global/project
    default: string;      // 默认值
    description: string;  // 说明
    sensitive: boolean;   // 是否敏感
  }>
}
```

#### PATCH /api/config/auth

**请求体**:
```typescript
{
  scope: "global" | "project";
  items: {
    [key: string]: string | null;  // key为配置项ID, null表示重置
  }
}
```

**响应**: 同 GET 响应

## 6. 错误处理

### 6.1 后端错误

| 错误场景 | HTTP状态码 | 错误信息 |
|----------|-----------|----------|
| 配置项不存在 | 400 | invalid_config_key |
| 值类型错误 | 400 | invalid_value_type |
| 存储失败 | 500 | storage_error |

### 6.2 前端错误

| 错误场景 | 处理方式 |
|----------|----------|
| API调用失败 | 显示错误状态，保留当前输入 |
| 网络中断 | 提示检查网络，支持重试 |
| 配置验证失败 | 高亮错误字段，显示具体错误 |

## 7. 安全考虑

### 7.1 数据验证
- 配置值类型验证（string）
- 配置项ID白名单验证
- 值长度限制（建议最大256字符）

### 7.2 访问控制
- 配置页面需要登录（如已有认证机制）
- 敏感操作（保存/重置）需要确认

## 8. 测试策略

### 8.1 单元测试

**后端**:
- 配置定义正确性
- 配置同步逻辑
- 配置验证逻辑

**前端**:
- 配置渲染
- 配置收集
- 状态管理

### 8.2 集成测试

- 端到端配置流程
- 配置持久化验证
- 运行时同步验证

### 8.3 验收测试

| 测试项 | 预期结果 |
|--------|----------|
| 打开配置页面 | 显示视频模型配置区域 |
| 输入端点ID并保存 | 配置保存成功，状态提示"已保存" |
| 刷新页面 | 显示已保存的配置值 |
| 触发视频生成 | 使用新配置的模型端点 |
| 重置配置 | 恢复默认值，状态提示"已重置" |

## 9. 部署计划

### 9.1 文件变更清单

**后端**:
1. `backend/services/config_service.py` - 新增配置定义和同步逻辑
2. `backend/services/workflow_runtime/runtime_config.py` - 初始化同步

**前端**:
1. `frontend/auth_config.html` - 新增视频模型配置区域
2. `frontend/auth_config.js` - 新增配置逻辑

### 9.2 部署步骤

1. 更新后端代码
2. 重启后端服务
3. 更新前端代码
4. 验证配置页面
5. 测试配置保存和生效

## 10. 附录

### 10.1 模型端点获取指南

**火山引擎ARK平台**:
1. 登录火山引擎控制台
2. 进入ARK服务
3. 创建视频生成模型端点
4. 复制端点ID（格式：ep-YYYYMMDD-xxxxx）

### 10.2 相关文档
- [需求文档](../requirements_doc/video_model_config_frontend.md)
- [视频生成TOS Presign修复文档](../requirements_doc/video_generation_tos_presign_fix.md)

### 10.3 术语表

| 术语 | 说明 |
|------|------|
| EP | Endpoint，模型端点 |
| ARK | 火山引擎大模型服务平台 |
| TOS | 火山引擎对象存储服务 |
| SDD | 技能驱动开发 (Skill-Driven Development) |
