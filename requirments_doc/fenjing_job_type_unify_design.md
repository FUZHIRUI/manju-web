# 系统设计文档：Fenjing Job Type 统一重构

## 1. 架构概览

### 1.1 当前架构
```
┌─────────────────────────────────────────────────────────────┐
│                        前端 (app.js)                         │
├─────────────────────────────────────────────────────────────┤
│  executeFlowFull("fenjing_generate")  │  executeFlowFull("fenjing_upload")  │
│  POST /run/fenjing_generate           │  POST /run/fenjing_upload           │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    后端 (job_handler.py)                     │
├─────────────────────────────────────────────────────────────┤
│  job type: run_fenjing_generate  │  job type: run_fenjing_upload  │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 后端 (workflow_service.py)                   │
├─────────────────────────────────────────────────────────────┤
│  run_fenjing_generate()  │  run_fenjing_upload()            │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 后端 (status_service.py)                     │
├─────────────────────────────────────────────────────────────┤
│  WORKFLOW_TO_FLOW_MAP: fenjing_generate -> fenjing          │
│  WORKFLOW_TO_FLOW_MAP: fenjing_upload -> fenjing            │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 目标架构
```
┌─────────────────────────────────────────────────────────────┐
│                        前端 (app.js)                         │
├─────────────────────────────────────────────────────────────┤
│  executeFlowFull("fenjing", {phase: "generate_images"})     │
│  executeFlowFull("fenjing", {phase: "upload_assets"})       │
│  POST /run/fenjing?phase=generate_images                    │
│  POST /run/fenjing?phase=upload_assets                      │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    后端 (job_handler.py)                     │
├─────────────────────────────────────────────────────────────┤
│  job type: run_fenjing (统一)                               │
│  phase: generate_images | upload_assets | all               │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 后端 (workflow_service.py)                   │
├─────────────────────────────────────────────────────────────┤
│  run_fenjing(job_id, project, phase="generate_images")      │
│  run_fenjing(job_id, project, phase="upload_assets")        │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 后端 (status_service.py)                     │
├─────────────────────────────────────────────────────────────┤
│  移除 WORKFLOW_TO_FLOW_MAP 中的 fenjing_generate/upload     │
│  直接使用 fenjing flow                                      │
└─────────────────────────────────────────────────────────────┘
```

## 2. 后端设计

### 2.1 job_handler.py 修改

#### 2.1.1 _resolve_flow_steps 函数修改

```python
# 修改前
if workflow == "fenjing_generate":
    return ["generate_images"]
if workflow == "fenjing_upload":
    return ["upload_assets"]

# 修改后
if workflow == "fenjing":
    phase = str(phase_value or "").strip().lower() if phase_value else "all"
    if phase == "generate_images":
        return ["generate_images"]
    elif phase == "upload_assets":
        return ["upload_assets"]
    elif phase == "download_assets":
        return ["download_assets"]
    else:
        return ["download_assets", "generate_images", "upload_assets"]
```

#### 2.1.2 handle_post 函数修改

```python
# 修改前
elif workflow == "fenjing_generate":
    job = job_service.start_job(
        "run_fenjing_generate",
        project,
        lambda job_id: workflow_service.run_fenjing_generate(job_id, project),
        {},
    )
elif workflow == "fenjing_upload":
    job = job_service.start_job(
        "run_fenjing_upload",
        project,
        lambda job_id: workflow_service.run_fenjing_upload(job_id, project),
        {},
    )

# 修改后
elif workflow == "fenjing":
    phase = str(body.get("phase", "all")).strip().lower()
    job = job_service.start_job(
        "run_fenjing",
        project,
        lambda job_id: workflow_service.run_fenjing(job_id, project, phase=phase),
        {"phase": phase},
    )
```

#### 2.1.3 workflow 白名单修改

```python
# 修改前
if not project or workflow not in {"auto_storyboard", "visual_audio_assets", "fenjing", "fenjing_generate", "fenjing_upload", "video"}:

# 修改后
if not project or workflow not in {"auto_storyboard", "visual_audio_assets", "fenjing", "video"}:
```

### 2.2 workflow_service.py 修改

#### 2.2.1 run_fenjing 函数修改

```python
def run_fenjing(job_id: str, project: str, phase: str = "all") -> None:
    """
    统一的分镜工作流执行函数
    
    Args:
        job_id: 任务ID
        project: 项目名称
        phase: 执行阶段，可选 "generate_images", "upload_assets", "all"
    """
    job = job_repo.get_job(job_id)
    if not job:
        return
    log_path = job_repo.resolve_log_path(str(job["log_path"]))
    stage_limiter = throttle_service.acquire_stage_limit("fenjing")
    
    try:
        with ThreadLogRedirector(log_path):
            try:
                load_manju_context(project)
                
                if phase in ("all", "generate_images"):
                    job_repo.log_event("INFO", "run_fenjing_generate_start", ...)
                    call_with_project(fenjing.run_fenjing_generate_workflow, project_name=project)
                    status_service.mark_step_completed(project, "fenjing", "generate_images")
                
                if phase in ("all", "upload_assets"):
                    job_repo.log_event("INFO", "run_fenjing_upload_start", ...)
                    call_with_project(fenjing.run_fenjing_upload_workflow, project_name=project)
                    status_service.mark_step_completed(project, "fenjing", "upload_assets")
                
                job_repo.update_job(job_id, status="success")
            except Exception as exc:
                # 错误处理...
    finally:
        if stage_limiter:
            stage_limiter.release()
```

#### 2.2.2 移除旧函数

```python
# 移除或标记废弃
# def run_fenjing_generate(job_id: str, project: str) -> None: ...
# def run_fenjing_upload(job_id: str, project: str) -> None: ...
```

### 2.3 status_service.py 修改

#### 2.3.1 移除 WORKFLOW_TO_FLOW_MAP 中的冗余映射

```python
# 修改前
WORKFLOW_TO_FLOW_MAP = {
    "fenjing_generate": "fenjing",
    "fenjing_upload": "fenjing",
    "fenjing": "fenjing",
}

# 修改后 - 移除冗余映射
# WORKFLOW_TO_FLOW_MAP 不再需要 fenjing_generate 和 fenjing_upload
# 因为前端不再使用这些 workflow 名称
WORKFLOW_TO_FLOW_MAP = {
    # 保留用于向后兼容，但不再主动使用
    "fenjing_generate": "fenjing",
    "fenjing_upload": "fenjing",
}
```

## 3. 前端设计

### 3.1 app.js 修改

#### 3.1.1 STAGE_TYPES 简化

```javascript
// 修改前
const STAGE_TYPES = ["auto_storyboard", "visual_audio_assets", "fenjing", "fenjing_generate", "fenjing_upload", "video"];

// 修改后
const STAGE_TYPES = ["auto_storyboard", "visual_audio_assets", "fenjing", "video"];
```

#### 3.1.2 移除 WORKFLOW_TO_FLOW_MAP

```javascript
// 修改前
const WORKFLOW_TO_FLOW_MAP = {
    "fenjing_generate": "fenjing",
    "fenjing_upload": "fenjing",
    "fenjing": "fenjing",
};

function getFlowFromWorkflow(workflow) {
    return WORKFLOW_TO_FLOW_MAP[workflow] || workflow;
}

// 修改后 - 移除映射，直接使用 fenjing
// 不再需要 WORKFLOW_TO_FLOW_MAP
```

#### 3.1.3 executeFlowFull 函数修改

```javascript
// 修改前
async function executeFlowFull(flow) {
    // ...
    const job = await apiPost(`/api/projects/${state.selectedProject}/run/${flow}`, {});
    // ...
}

// 修改后
async function executeFlowFull(flow, options = {}) {
    // ...
    const payload = options.phase ? { phase: options.phase } : {};
    const job = await apiPost(`/api/projects/${state.selectedProject}/run/${flow}`, payload);
    // ...
}
```

#### 3.1.4 appendFenjingPhaseButtons 函数修改

```javascript
// 修改前
appendTreeAction(container, generateLabel, generateActionLabel, () => {
    if (generateCompleted) return;
    executeFlowFull("fenjing_generate");
}, { disabled: isPending ? false : generateDisabled, breathing: generateRunning });

appendTreeAction(container, uploadLabel, uploadActionLabel, () => {
    if (uploadCompleted) return;
    executeFlowFull("fenjing_upload");
}, { disabled: uploadDisabled, breathing: uploadRunning });

// 修改后
appendTreeAction(container, generateLabel, generateActionLabel, () => {
    if (generateCompleted) return;
    executeFlowFull("fenjing", { phase: "generate_images" });
}, { disabled: isPending ? false : generateDisabled, breathing: generateRunning });

appendTreeAction(container, uploadLabel, uploadActionLabel, () => {
    if (uploadCompleted) return;
    executeFlowFull("fenjing", { phase: "upload_assets" });
}, { disabled: uploadDisabled, breathing: uploadRunning });
```

#### 3.1.5 getFlowFromJob 函数简化

```javascript
// 修改前
function getFlowFromJob(job) {
    if (!job || !job.type || !String(job.type).startsWith("run_")) {
        return "";
    }
    const flow = String(job.type).replace("run_", "");
    if (STAGE_TYPES.includes(flow)) {
        return getFlowFromWorkflow(flow);
    }
    return "";
}

// 修改后
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
```

## 4. API 设计

### 4.1 新 API

| 方法 | 路径 | 参数 | 说明 |
|------|------|------|------|
| POST | `/api/projects/{project}/run/fenjing` | `phase=generate_images` | 执行分镜图生成 |
| POST | `/api/projects/{project}/run/fenjing` | `phase=upload_assets` | 执行分镜图上传 |
| POST | `/api/projects/{project}/run/fenjing` | `phase=all` 或不传 | 执行完整流程 |

### 4.2 向后兼容

旧的 API 调用方式仍然支持（通过内部映射）：

| 旧 API | 映射到 |
|--------|--------|
| `POST /run/fenjing_generate` | `POST /run/fenjing?phase=generate_images` |
| `POST /run/fenjing_upload` | `POST /run/fenjing?phase=upload_assets` |

## 5. 文件修改清单

| 文件 | 修改类型 | 修改量 |
|------|----------|--------|
| `backend/handlers/job_handler.py` | 修改 | ~30 行 |
| `backend/services/workflow_service.py` | 修改 | ~40 行 |
| `backend/services/status_service.py` | 修改 | ~10 行 |
| `frontend/app.js` | 修改 | ~20 行 |

## 6. 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 旧 API 调用失败 | 低 | 中 | 保持向后兼容映射 |
| 前端调用遗漏 | 中 | 低 | 全面搜索代码中的调用点 |
| 状态显示异常 | 低 | 中 | 充分测试 job-item 渲染 |
