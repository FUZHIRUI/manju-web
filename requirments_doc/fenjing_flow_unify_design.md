# 系统设计文档：Fenjing Flow 统一重构

## 1. 架构概览

### 1.1 当前架构
```
┌─────────────────────────────────────────────────────────────┐
│                        前端 (app.js)                         │
├─────────────────────────────────────────────────────────────┤
│  fenjing_generate  │  fenjing_upload  │  fenjing (unused)   │
└─────────┬──────────┴────────┬──────────┴─────────┬──────────┘
          │                   │                    │
          ▼                   ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│                    后端 (status_service.py)                  │
├─────────────────────────────────────────────────────────────┤
│  fenjing_generate: [download_assets, generate_images]       │
│  fenjing_upload:   [upload_fenjing_images]                  │
│  fenjing:          [download_assets, generate_images, ...]  │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 目标架构
```
┌─────────────────────────────────────────────────────────────┐
│                        前端 (app.js)                         │
├─────────────────────────────────────────────────────────────┤
│                    fenjing (统一入口)                        │
│         generate_images 按钮  │  upload_assets 按钮          │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    后端 (status_service.py)                  │
├─────────────────────────────────────────────────────────────┤
│  fenjing: [download_assets, generate_images, upload_assets] │
└─────────────────────────────────────────────────────────────┘
```

## 2. 数据模型设计

### 2.1 Flow 状态结构

**修改前**:
```json
{
  "flows": {
    "fenjing": {
      "status": "waiting",
      "steps": {
        "download_assets": "waiting",
        "generate_images": "waiting",
        "upload_assets": "waiting"
      }
    },
    "fenjing_generate": {
      "status": "completed",
      "steps": {
        "download_assets": "completed",
        "generate_images": "completed"
      }
    },
    "fenjing_upload": {
      "status": "waiting",
      "steps": {
        "upload_fenjing_images": "waiting"
      }
    }
  }
}
```

**修改后**:
```json
{
  "flows": {
    "fenjing": {
      "status": "completed",
      "steps": {
        "download_assets": "completed",
        "generate_images": "completed",
        "upload_assets": "waiting"
      }
    }
  }
}
```

### 2.2 状态迁移规则

| 旧 Flow | 旧步骤 | 新 Flow | 新步骤 | 迁移逻辑 |
|---------|--------|---------|--------|----------|
| `fenjing_generate` | `download_assets` | `fenjing` | `download_assets` | 直接映射 |
| `fenjing_generate` | `generate_images` | `fenjing` | `generate_images` | 直接映射 |
| `fenjing_upload` | `upload_fenjing_images` | `fenjing` | `upload_assets` | 步骤名变更 |
| `fenjing` | 所有步骤 | `fenjing` | 所有步骤 | 保留原状 |

### 2.3 状态优先级（合并时）

当多个旧 flow 状态冲突时，按以下优先级取值：
1. `error` > `running` > `completed` > `partial_completed` > `waiting`

## 3. 接口设计

### 3.1 API 兼容性策略

**保持兼容**：前端继续使用 `fenjing_generate` 和 `fenjing_upload` 作为 workflow 参数，后端内部映射到 `fenjing` flow。

```python
# job_handler.py 内部映射
WORKFLOW_TO_FLOW_MAP = {
    "fenjing_generate": "fenjing",
    "fenjing_upload": "fenjing",
    "fenjing": "fenjing",
}

def get_flow_from_workflow(workflow: str) -> str:
    return WORKFLOW_TO_FLOW_MAP.get(workflow, workflow)
```

### 3.2 步骤映射

| 前端 workflow | 后端 flow | 执行步骤 |
|---------------|-----------|----------|
| `fenjing_generate` | `fenjing` | `generate_images` |
| `fenjing_upload` | `fenjing` | `upload_assets` |
| `fenjing` | `fenjing` | 全部步骤 |

## 4. 模块设计

### 4.1 status_service.py 修改

```python
# 修改前
_FLOW_STEPS = {
    "fenjing": ["download_assets", "generate_images", "upload_assets"],
    "fenjing_generate": ["download_assets", "generate_images"],
    "fenjing_upload": ["upload_fenjing_images"],
}

_PARTIAL_STEPS = {
    "fenjing": ["generate_images"],
    "fenjing_generate": ["generate_images"],
}

# 修改后
_FLOW_STEPS = {
    "fenjing": ["download_assets", "generate_images", "upload_assets"],
}

_PARTIAL_STEPS = {
    "fenjing": ["generate_images"],
}

# 新增：workflow 到 flow 的映射
WORKFLOW_TO_FLOW_MAP = {
    "fenjing_generate": "fenjing",
    "fenjing_upload": "fenjing",
    "fenjing": "fenjing",
}
```

### 4.2 workflow_service.py 修改

```python
# 合并 run_fenjing_generate 和 run_fenjing_upload 到 run_fenjing

def run_fenjing(job_id: str, project: str, phase: str = "all") -> None:
    """
    统一的分镜工作流执行函数
    
    Args:
        job_id: 任务ID
        project: 项目名称
        phase: 执行阶段，可选 "generate", "upload", "all"
    """
    if phase in ("all", "generate"):
        # 执行生成逻辑
        _run_fenjing_generate_phase(job_id, project)
    
    if phase in ("all", "upload"):
        # 执行上传逻辑
        _run_fenjing_upload_phase(job_id, project)
```

### 4.3 job_handler.py 修改

```python
# 修改前
elif workflow == "fenjing_generate":
    steps = ["download_assets"]
    # ...
elif workflow == "fenjing_upload":
    steps = ["upload_fenjing_images"]
    # ...

# 修改后
elif workflow == "fenjing_generate":
    flow = "fenjing"
    steps = ["generate_images"]
    # ...
elif workflow == "fenjing_upload":
    flow = "fenjing"
    steps = ["upload_assets"]
    # ...
```

### 4.4 前端 app.js 修改

```javascript
// 修改前
const STAGE_TYPES = ["auto_storyboard", "visual_audio_assets", "fenjing_generate", "video"];

// 修改后 - 保持兼容，内部映射
const STAGE_TYPES = ["auto_storyboard", "visual_audio_assets", "fenjing_generate", "video"];

// 新增：workflow 到 flow 的映射
const WORKFLOW_TO_FLOW_MAP = {
    "fenjing_generate": "fenjing",
    "fenjing_upload": "fenjing",
    "fenjing": "fenjing",
};

function getFlowFromWorkflow(workflow) {
    return WORKFLOW_TO_FLOW_MAP[workflow] || workflow;
}

// 状态读取时使用映射
function getFenjingStatus() {
    return getFlowStatus("fenjing");
}
```

## 5. 状态迁移设计

### 5.1 迁移函数

```python
def _migrate_fenjing_flows(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    迁移旧的 fenjing_generate 和 fenjing_upload 状态到统一的 fenjing flow
    """
    flows = state.get("flows", {})
    
    # 收集所有 fenjing 相关 flow 的状态
    fenjing_generate = flows.pop("fenjing_generate", {})
    fenjing_upload = flows.pop("fenjing_upload", {})
    fenjing = flows.get("fenjing", {})
    
    # 确保 fenjing flow 存在
    if "fenjing" not in flows:
        flows["fenjing"] = {
            "status": _STATUS_WAITING,
            "steps": {step: _STATUS_WAITING for step in _FLOW_STEPS["fenjing"]}
        }
    
    fenjing_steps = flows["fenjing"].get("steps", {})
    
    # 迁移 fenjing_generate 的步骤状态
    gen_steps = fenjing_generate.get("steps", {})
    for step in ["download_assets", "generate_images"]:
        if step in gen_steps:
            fenjing_steps[step] = gen_steps[step]
    
    # 迁移 fenjing_upload 的步骤状态（步骤名变更）
    upload_steps = fenjing_upload.get("steps", {})
    if "upload_fenjing_images" in upload_steps:
        fenjing_steps["upload_assets"] = upload_steps["upload_fenjing_images"]
    
    # 重新计算 fenjing flow 的整体状态
    flows["fenjing"]["status"] = _recalculate_flow_status("fenjing", fenjing_steps)
    flows["fenjing"]["steps"] = fenjing_steps
    
    return state
```

### 5.2 迁移时机

在 `_normalize_state` 函数中调用迁移函数：

```python
def _normalize_state(project: str, data: Dict[str, Any]) -> Dict[str, Any]:
    base = _default_flow_state(project)
    # ... 现有逻辑 ...
    
    # 迁移旧的 fenjing flows
    merged = _migrate_fenjing_flows(merged)
    
    return merged
```

## 6. 线程安全设计

### 6.1 现有锁机制

```python
_project_locks: Dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()

def _get_project_lock(project: str) -> threading.Lock:
    with _locks_lock:
        if project not in _project_locks:
            _project_locks[project] = threading.Lock()
        return _project_locks[project]
```

### 6.2 迁移过程的线程安全

迁移在 `_normalize_state` 中执行，该函数在 `get_flow_state` 中调用，而 `get_flow_state` 已被项目锁保护。

```python
def get_flow_state(project: str) -> Dict[str, Any]:
    # 此函数在锁保护下调用
    path = status_repo.flow_state_path(project)
    data = status_repo.read_flow_state(project)
    normalized = _normalize_state(project, data)  # 迁移在此执行
    # ...
```

## 7. 测试策略

### 7.1 单元测试

| 测试项 | 测试内容 |
|--------|----------|
| 状态迁移 | 验证旧状态正确迁移到新格式 |
| 状态计算 | 验证 `_recalculate_flow_status` 对 fenjing flow 的计算 |
| 步骤映射 | 验证 workflow 到 flow 的映射正确 |
| 线程安全 | 验证并发场景下状态一致性 |

### 7.2 集成测试

| 测试项 | 测试内容 |
|--------|----------|
| 前端按钮 | 验证分镜生成/上传按钮可正常触发 |
| 状态同步 | 验证前端状态与后端一致 |
| 多项目并发 | 验证多项目同时执行无竞态 |

## 8. 回滚方案

### 8.1 状态回滚

保留迁移前的状态备份：

```python
def _migrate_fenjing_flows(state: Dict[str, Any]) -> Dict[str, Any]:
    # 备份原始状态
    state["_migration_backup"] = {
        "fenjing_generate": deepcopy(state.get("flows", {}).get("fenjing_generate")),
        "fenjing_upload": deepcopy(state.get("flows", {}).get("fenjing_upload")),
        "fenjing": deepcopy(state.get("flows", {}).get("fenjing")),
    }
    # ... 迁移逻辑 ...
```

### 8.2 代码回滚

使用 Git 版本控制，可快速回滚到重构前版本。

## 9. 实施顺序

1. **后端修改**：先修改后端代码，保持 API 兼容
2. **状态迁移**：实现自动迁移逻辑
3. **前端适配**：修改前端代码使用新的 flow 结构
4. **测试验证**：执行单元测试和集成测试
5. **清理代码**：移除不再需要的旧代码

## 10. 附录

### 10.1 文件修改清单

| 文件 | 修改类型 | 修改量 |
|------|----------|--------|
| `status_service.py` | 修改 | ~50 行 |
| `workflow_service.py` | 修改 | ~30 行 |
| `job_handler.py` | 修改 | ~20 行 |
| `project_handler.py` | 修改 | ~10 行 |
| `asset_repo.py` | 修改 | ~15 行 |
| `job_repo.py` | 修改 | ~5 行 |
| `app.js` | 修改 | ~40 行 |
| `index.html` | 修改 | ~5 行 |

### 10.2 风险缓解措施

| 风险 | 缓解措施 |
|------|----------|
| 状态迁移失败 | 保留备份，提供回滚脚本 |
| 前端兼容性 | 保持 API 兼容，渐进式更新 |
| 并发竞态 | 使用项目级锁，充分测试 |
