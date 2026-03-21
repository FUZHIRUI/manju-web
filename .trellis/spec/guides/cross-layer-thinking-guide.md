# Cross-Layer Thinking Guide

> **Purpose**: Think through data flow across layers before implementing.

---

## The Problem

**Most bugs happen at layer boundaries**, not within layers.

Common cross-layer bugs:
- API returns format A, frontend expects format B
- Database stores X, service transforms to Y, but loses data
- Multiple layers implement the same logic differently

---

## Before Implementing Cross-Layer Features

### Step 1: Map the Data Flow

Draw out how data moves:

```
Source → Transform → Store → Retrieve → Transform → Display
```

For each arrow, ask:
- What format is the data in?
- What could go wrong?
- Who is responsible for validation?

### Step 2: Identify Boundaries

| Boundary | Common Issues |
|----------|---------------|
| API ↔ Service | Type mismatches, missing fields |
| Service ↔ Database | Format conversions, null handling |
| Backend ↔ Frontend | Serialization, date formats |
| Component ↔ Component | Props shape changes |

### Step 3: Define Contracts

For each boundary:
- What is the exact input format?
- What is the exact output format?
- What errors can occur?

---

## Common Cross-Layer Mistakes

### Mistake 1: Implicit Format Assumptions

**Bad**: Assuming date format without checking

**Good**: Explicit format conversion at boundaries

### Mistake 2: Scattered Validation

**Bad**: Validating the same thing in multiple layers

**Good**: Validate once at the entry point

### Mistake 3: Leaky Abstractions

**Bad**: Component knows about database schema

**Good**: Each layer only knows its neighbors

---

## Checklist for Cross-Layer Features

Before implementation:
- [ ] Mapped the complete data flow
- [ ] Identified all layer boundaries
- [ ] Defined format at each boundary
- [ ] Decided where validation happens

After implementation:
- [ ] Tested with edge cases (null, empty, invalid)
- [ ] Verified error handling at each boundary
- [ ] Checked data survives round-trip

---

## When to Create Flow Documentation

Create detailed flow docs when:
- Feature spans 3+ layers
- Multiple teams are involved
- Data format is complex
- Feature has caused bugs before

---

# 项目专属跨层模式（Manju Web）

> 以下内容基于项目实际代码提炼，供 AI agent 和开发者在跨层任务中参考。

---

## Pattern 1: 统一 Job Type + Phase 模式

所有 workflow 使用 **统一 job type**，通过 `phase` 参数区分执行步骤。

### 标准模式

```
前端调用:   executeFlowFull("fenjing", { phase: "generate_images" })
HTTP 请求:  POST /api/projects/{project}/run/fenjing  body: { phase: "generate_images" }
Handler:    job_service.start_job("run_fenjing", project, callback, {"phase": phase})
Service:    workflow_service.run_fenjing(job_id, project, phase="generate_images")
```

### 已采用此模式的 workflow

| Workflow | Job Type | Phase 值 | 参考文件 |
|----------|----------|----------|----------|
| `fenjing` | `run_fenjing` | `generate_images`, `upload_assets`, `download_assets`, `all` | `job_handler.py:246-253` |
| `auto_storyboard` | `run_auto_storyboard` | `step1`, `step2`, `step3_upload`, `phase1`, `phase2`, `full` | `job_handler.py:171-213` |
| `visual_audio_assets` | `run_visual_audio_assets` | `all`, `character`, `location`, `fenjing`, `tts`, `cloth`, ... | `job_handler.py:214-245` |
| `video` | `run_video` | `prepare_prompts`, `generate_videos`, `upload_videos`, `all` | `job_handler.py:268-284` |

### 规则

1. **新增 workflow 时**，必须遵循 `run_{workflow}` + `phase` 参数模式
2. **不再创建**独立的 job type（如 ~~`run_fenjing_generate`~~）
3. Phase 默认值为 `"all"`，执行所有步骤
4. Phase 在 Handler 层做白名单校验

---

## Pattern 2: 三层状态管理

```
Flow Level   →  "fenjing": { status: "running" }
Step Level   →  "generate_images": "completed", "upload_assets": "waiting"
Job Level    →  { id: "uuid", type: "run_fenjing", status: "success" }
```

### 状态枚举

| 状态 | 含义 |
|------|------|
| `waiting` | 未开始 |
| `pending` | 已排队 |
| `running` | 执行中 |
| `partial_returned` | 部分返回 |
| `partial_completed` | 部分完成 |
| `completed` | 全部完成 |
| `error` | 失败 |

### 关键数据结构

**`_FLOW_STEPS`** (`status_service.py:30-56`): 定义每个 flow 包含哪些 step。

```python
_FLOW_STEPS = {
    "fenjing": ["download_assets", "generate_images", "upload_assets"],
    "auto_storyboard": ["step1", "step1_extract", "step2", ...],
    "visual_audio_assets": ["download_assets", "build_prompts", ...],
    "video": ["prepare", "phase1_video_prompts", ...],
}
```

**`flow_state.json`**: 项目级状态持久化文件。

```json
{
  "flows": {
    "fenjing": {
      "status": "running",
      "steps": {
        "download_assets": "completed",
        "generate_images": "running",
        "upload_assets": "waiting"
      }
    }
  }
}
```

### 线程安全

- 使用项目级锁 `_get_project_lock(project)` 保护状态操作（`status_service.py:18-27`）
- 使用 temp file + atomic rename 写入 `flow_state.json`（`status_repo.py`）
- 不同项目可并行更新，同一项目序列化

---

## Pattern 3: API 契约规范

### 请求格式

```
POST /api/projects/{project}/run/{flow}
Content-Type: application/json

{
  "phase": "generate_images"     // 可选，默认 "all"
  // ... 其他 workflow 特有参数
}
```

### 响应格式

```json
{
  "id": "job_uuid",
  "type": "run_fenjing",
  "status": "running",
  "log_path": "logs/job_uuid.log",
  "trace_id": "trace_uuid",
  "payload": { "phase": "generate_images" },
  "created_at": 1708329600.123
}
```

### 状态轮询

```
GET /api/projects/{project}/flow/status
→ 返回 flow_state.json 内容
```

前端通过 `getFlowStepStatus(flow, step)` 读取步骤状态，驱动 UI 按钮标签切换：
- `"completed"` → "重生"
- `"waiting"` / `"running"` → "执行"

---

## Pattern 4: 向后兼容模式

当统一旧的分散 workflow 时，使用映射表保持兼容：

```python
# status_service.py:65-68
WORKFLOW_TO_FLOW_MAP = {
    "fenjing_generate": "fenjing",
    "fenjing_upload": "fenjing",
}
```

### 兼容策略

1. **Handler 白名单**保留旧路由名（`job_handler.py:168`）
2. **旧路由内部**转发到统一 job type（`job_handler.py:254-267`）
3. **状态迁移函数** `_migrate_*_flows()` 自动转换旧格式状态
4. **前端** `STAGE_TYPES` 简化，移除旧名称（`app.js:56`）

### 迁移完成后

当确认无旧客户端使用时，可安全移除：
- Handler 白名单中的旧 workflow 名
- `WORKFLOW_TO_FLOW_MAP` 中的旧映射
- 状态迁移函数

---

## Pattern 5: 跨层修改 Checklist

当新增或修改一个 workflow 时，需要同步修改以下层：

### 前端 (`frontend/app.js`)

- [ ] `STAGE_TYPES` 常量 — 是否需要添加/移除 flow 名称
- [ ] `executeFlowFull()` 调用 — phase 参数是否正确传递
- [ ] `executeFlowFull()` 中 `skipClean` — 分步执行时是否需要跳过 clean（见 Gotcha 1）
- [ ] `getFlowStepStatus()` — UI 状态轮询是否覆盖新 step
- [ ] 按钮/fishbone 渲染 — 新 step 的显示逻辑

### Handler (`backend/handlers/job_handler.py`)

- [ ] 白名单 — workflow 名称加入校验列表（L168）
- [ ] `_resolve_flow_steps()` — phase → steps 映射（L110-138）
- [ ] `handle_post()` — phase 解析 + `job_service.start_job()` 调用
- [ ] `reset_steps` 逻辑 — 部分执行时是否重置其他步骤

### Workflow Service (`backend/services/workflow_service.py`)

- [ ] `run_{workflow}()` 函数 — phase 条件执行
- [ ] `status_service.mark_step_completed()` — 每步完成后标记
- [ ] 错误处理 — `job_repo.update_job(status="error")`

### Status Service (`backend/services/status_service.py`)

- [ ] `_FLOW_STEPS` — 注册新 flow 的所有 step
- [ ] `_PARTIAL_STEPS` — 支持部分重试的 step
- [ ] `WORKFLOW_TO_FLOW_MAP` — 如有旧名称需映射
- [ ] `mark_step_completed()` — 如有顺序约束，需添加 rollup 调用（见 Gotcha 2）

---

## Gotchas（踩坑记录）

### Gotcha 1: `executeFlowFull` 会在执行前调用 `clean/` 删除产物

**症状**：分步执行 workflow 时，后续步骤找不到前序步骤的产物（如视频文件被删除）。

**原因**：`executeFlowFull()` 在调用 `run/` 之前会先调用 `clean/{flow}` API，而 `clean_stage_assets()` 会删除该 flow 的所有本地产物目录（如 `video/`）。

**修复**：在 `executeFlowFull()` 的 `skipClean` 条件中，为分步执行的 phase 跳过 clean：

```javascript
// app.js - executeFlowFull()
const skipClean = (flow === "fenjing" && phase === "upload_assets")
    || (flow === "video" && !!phase && phase !== "all");
```

**规则**：新增支持分步执行的 workflow 时，**必须**将非 `all` 的 phase 加入 `skipClean` 条件。

### Gotcha 2: `mark_step_completed` 需要 rollup 调用

**症状**：单步完成后，flow 整体状态没有正确更新，前端显示不准确。

**原因**：`mark_step_completed()` 标记完单步后需要调用 rollup 函数来维护步骤间的顺序约束（如 step B 必须等 step A 完成才能开始），但 rollup 调用需要手动添加。

**修复**：在 `mark_step_completed()` 中为新 flow 添加 rollup 分支：

```python
# status_service.py - mark_step_completed()
if flow == "fenjing":
    _rollup_fenjing_steps(state)
elif flow == "video":
    _rollup_video_steps(state)
# 新增 flow 时必须在此添加对应的 rollup 调用
```

**规则**：每个有顺序约束的 flow 都需要 `_rollup_{flow}_steps()` 函数和 `mark_step_completed()` 中的调用。

---

## 完整数据流示例

用户点击"分镜生成"按钮的完整请求路径：

```
用户点击
  ↓
Frontend: executeFlowFull("fenjing", { phase: "generate_images" })
  ↓ POST /api/projects/my_project/run/fenjing  { phase: "generate_images" }
  ↓
Handler (job_handler.py):
  1. 白名单校验: "fenjing" ∈ allowed workflows ✓
  2. Phase 解析: body.get("phase", "all") → "generate_images"
  3. Job 创建: job_service.start_job("run_fenjing", ...)
  4. Steps 解析: _resolve_flow_steps("fenjing", "generate_images") → ["generate_images"]
  5. 状态标记: status_service.mark_flow_running(project, "fenjing", ["generate_images"])
  6. 超时调度: _schedule_job_timeout(...)
  7. 返回 Job JSON
  ↓
Workflow Service (workflow_service.py):
  run_fenjing(job_id, "my_project", phase="generate_images")
    → ThreadLogRedirector(log_path) 重定向日志
    → load_manju_context(project)
    → if phase in ("all", "generate_images"):
        fenjing.run_fenjing_generate_workflow(...)
        status_service.mark_step_completed(project, "fenjing", "generate_images")
    → job_repo.update_job(job_id, status="success")
  ↓
Frontend 轮询:
  GET /api/projects/my_project/flow/status
    → getFlowStepStatus("fenjing", "generate_images") === "completed"
    → 按钮标签从"执行"变为"重生"
```

---

## 新增 Workflow 模板

以下是新增一个跨层 workflow 的标准模板：

### 1. Status Service — 注册 Steps

```python
# status_service.py
_FLOW_STEPS["new_flow"] = ["step_a", "step_b", "step_c"]
_PARTIAL_STEPS["new_flow"] = ["step_b"]  # 可选：支持部分重试
```

### 2. Handler — 路由和 Phase 解析

```python
# job_handler.py - 白名单
workflow not in {"auto_storyboard", ..., "new_flow"}

# _resolve_flow_steps
if workflow == "new_flow":
    token = str(phase or "").strip().lower()
    if token == "step_a":
        return ["step_a"]
    elif token == "step_b":
        return ["step_b"]
    return ["step_a", "step_b", "step_c"]  # all

# handle_post
elif workflow == "new_flow":
    phase = str(body.get("phase", "all")).strip().lower()
    job = job_service.start_job(
        "run_new_flow", project,
        lambda job_id, p=phase: workflow_service.run_new_flow(job_id, project, phase=p),
        {"phase": phase},
    )
```

### 3. Workflow Service — 执行逻辑

```python
def run_new_flow(job_id: str, project: str, phase: str = "all") -> None:
    job = job_repo.get_job(job_id)
    log_path = job_repo.resolve_log_path(str(job["log_path"]))
    stage_limiter = throttle_service.acquire_stage_limit("new_flow")
    try:
        with ThreadLogRedirector(log_path):
            load_manju_context(project)
            if phase in ("all", "step_a"):
                # ... execute step_a
                status_service.mark_step_completed(project, "new_flow", "step_a")
            if phase in ("all", "step_b"):
                # ... execute step_b
                status_service.mark_step_completed(project, "new_flow", "step_b")
            job_repo.update_job(job_id, status="success")
    except Exception as exc:
        job_repo.update_job(job_id, status="error", error=str(exc))
    finally:
        if stage_limiter:
            stage_limiter.release()
```

### 4. Frontend — UI 集成

```javascript
// app.js
const STAGE_TYPES = [..., "new_flow"];

// 按钮绑定
appendTreeAction(container, "Step A", "执行", () => {
    executeFlowFull("new_flow", { phase: "step_a" });
});
```
