# 分镜图生成步骤拆分系统设计

## 1. 技术方案

### 1.1 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                        前端 (app.js)                         │
├─────────────────────────────────────────────────────────────┤
│  submitFlow("fenjing_generate")  │  submitFlow("fenjing_upload")  │
└───────────────────┬─────────────────────┴─────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│                      后端 (server.py)                        │
├─────────────────────────────────────────────────────────────┤
│  /api/projects/{project}/run/fenjing_generate               │
│  /api/projects/{project}/run/fenjing_upload                 │
└───────────────────┬─────────────────────┬───────────────────┘
                    │                     │
                    ▼                     ▼
┌───────────────────────────────┐ ┌───────────────────────────┐
│   fenjing.py                  │ │   throttle_service.py     │
│   - run_fenjing_generate()    │ │   - 上传 QPS 限制          │
│   - run_fenjing_upload()      │ │   - 并发控制（跨项目共享）  │
└───────────────────────────────┘ └───────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│              status_service.py (状态管理)                    │
│   - 直接落盘到 flow_state.json                               │
│   - 参考 visual_audio_assets 状态机                          │
│   - generate/upload 状态独立                                 │
└─────────────────────────────────────────────────────────────┘
```

## 2. 状态管理设计

### 2.1 参考 visual_audio_assets 状态机

**现有状态常量**（来自 `status_service.py`）：
```python
_STATUS_WAITING = "waiting"
_STATUS_PENDING = "pending"
_STATUS_RUNNING = "running"
_STATUS_PARTIAL_RETURNED = "partial_returned"
_STATUS_PARTIAL_COMPLETED = "partial_completed"
_STATUS_COMPLETED = "completed"
_STATUS_ERROR = "error"
```

### 2.2 新增 fenjing_generate 和 fenjing_upload 流程

**修改 `_FLOW_STEPS`**：
```python
_FLOW_STEPS = {
    # ... 现有流程
    "fenjing": ["download_assets", "generate_images", "upload_assets"],
    "fenjing_generate": ["download_assets", "generate_images"],
    "fenjing_upload": ["upload_fenjing_images"],
}
```

**新增 `_PARTIAL_STEPS`**：
```python
_PARTIAL_STEPS = {
    "visual_audio_assets": ["character_images", "location_images", "tts", "cloth_images", "cloth_changed"],
    "fenjing_generate": ["generate_images"],  # 支持部分完成
    "video": ["phase2_video_generation"],
}
```

### 2.3 状态独立性设计

**关键原则**：
1. `fenjing_generate` 和 `fenjing_upload` 是两个独立的 flow
2. 各自的状态互不影响
3. 每次状态更新直接落盘到 `flow_state.json`

**状态结构**：
```json
{
  "project": "ms3",
  "updated_at": 1771417806.199469,
  "flows": {
    "fenjing_generate": {
      "status": "partial_completed",
      "steps": {
        "download_assets": "completed",
        "generate_images": "partial_completed"
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

### 2.4 状态更新函数

**新增函数**（在 `status_service.py`）：

```python
def mark_fenjing_generate_partial(project: str) -> None:
    """标记分镜生成部分完成"""
    state = get_flow_state(project)
    flow = "fenjing_generate"
    steps = state.get("flows", {}).get(flow, {}).get("steps", {})
    
    # 检查是否有部分完成的图片
    # 如果有成功生成的图片，标记为 partial_completed
    generate_status = steps.get("generate_images", _STATUS_WAITING)
    if generate_status == _STATUS_RUNNING:
        # 检查是否有成功生成的图片
        assets_dir = project_repo.storyboard_assets_dir(project)
        has_images = check_fenjing_images_exist(assets_dir)
        if has_images:
            steps["generate_images"] = _STATUS_PARTIAL_COMPLETED
            state["flows"][flow]["status"] = _STATUS_PARTIAL_COMPLETED
    
    state["updated_at"] = time.time()
    status_repo.write_flow_state(project, state)


def check_fenjing_images_exist(assets_dir: Path) -> bool:
    """检查是否存在分镜图片"""
    storyboards_dir = assets_dir / "storyboards"
    if not storyboards_dir.exists():
        return False
    for chapter_dir in storyboards_dir.iterdir():
        if chapter_dir.is_dir():
            fenjing_dir = chapter_dir / "fenjing"
            if fenjing_dir.exists():
                for img in fenjing_dir.glob("*.png"):
                    return True
    return False
```

## 3. 事件设计

### 3.1 分镜生成事件

| 事件名称 | 触发时机 | 状态更新 |
|---------|---------|---------|
| `fenjing_generate_start` | 开始生成 | `fenjing_generate.status = running` |
| `fenjing_generate_phase_start` | 阶段开始 | 对应 step = running |
| `fenjing_generate_phase_complete` | 阶段完成 | 对应 step = completed |
| `fenjing_generate_chapter_completed` | 章节完成 | - |
| `fenjing_generate_partial` | 部分完成 | `generate_images = partial_completed` |
| `fenjing_generate_complete` | 全部完成 | `fenjing_generate.status = completed` |
| `fenjing_generate_error` | 生成失败 | `fenjing_generate.status = error` |

### 3.2 上传事件

| 事件名称 | 触发时机 | 状态更新 |
|---------|---------|---------|
| `fenjing_upload_start` | 开始上传 | `fenjing_upload.status = running` |
| `fenjing_upload_progress` | 上传进度 | - |
| `fenjing_upload_chapter_completed` | 章节上传完成 | - |
| `fenjing_upload_complete` | 全部完成 | `fenjing_upload.status = completed` |
| `fenjing_upload_error` | 上传失败 | `fenjing_upload.status = error` |

### 3.3 事件处理函数

**修改 `_resolve_step` 函数**：
```python
def _resolve_step(flow: str, event: str, step: Optional[str], phase: Optional[str]) -> Optional[str]:
    # ... 现有代码
    
    if flow == "fenjing_generate":
        if event == "fenjing_generate_start":
            return "download_assets"
        if phase == "phase_download_assets":
            return "download_assets"
        if phase == "phase_generate_images":
            return "generate_images"
        if step in {"download_assets", "generate_images"}:
            return step
        return None
    
    if flow == "fenjing_upload":
        if event in {"fenjing_upload_start", "fenjing_upload_progress", "fenjing_upload_complete"}:
            return "upload_fenjing_images"
        return None
    
    return None
```

## 4. TOS 上传并发控制

### 4.1 参考生图并发控制

**现有实现**（`throttle_service.py`）：
```python
# 模型限流配置
model_limiters: Dict[str, AsyncLimiter] = {}

def configure_model_limiters(model_limits: Dict[str, Dict[str, float]]) -> None:
    global model_limiters
    for model_key, limits in model_limits.items():
        qps = limits.get("qps", 0)
        concurrency = limits.get("concurrency", 0)
        model_limiters[model_key] = _build_async_limiter(qps, concurrency)

async def acquire_model_limit(model_key: str) -> Optional[AsyncLimiter]:
    limiter = model_limiters.get(model_key)
    if not limiter:
        return None
    await limiter.acquire()
    return limiter
```

### 4.2 新增 TOS 上传限流配置

**在 `configure_model_limiters` 调用处添加**：
```python
model_limits = {
    # ... 现有配置
    "fenjing_upload": {
        "qps": 5,        # 每秒最多 5 次上传请求
        "concurrency": 10  # 最大并发上传数
    }
}
```

### 4.3 上传函数使用限流

**在 `fenjing.py` 中**：
```python
async def upload_fenjing_image_with_limit(file_path: Path, key: str, project: str) -> Optional[str]:
    """带限流的上传函数"""
    limiter = None
    try:
        limiter = await throttle_service.acquire_model_limit("fenjing_upload")
        return tos.upload_file(runtime_config.TOS_BUCKET, key, file_path)
    finally:
        if limiter:
            limiter.release()
```

### 4.4 多项目并行场景

**关键点**：
1. `model_limiters` 是全局字典，跨项目共享
2. 使用线程信号量（`threading.BoundedSemaphore`）实现并发控制
3. 所有项目的上传请求共享同一个限流器

**线程安全保证**：
```python
# AsyncLimiter 使用线程信号量
@dataclass
class AsyncLimiter:
    bucket: Optional[TokenBucket]
    semaphore_size: Optional[int]
    thread_semaphore: Optional[BoundedSemaphore] = None

    async def acquire(self) -> None:
        if self.bucket:
            await self.bucket.take(1)
        if self.thread_semaphore is None and self.semaphore_size:
            self.thread_semaphore = BoundedSemaphore(self.semaphore_size)
        if self.thread_semaphore:
            self.thread_semaphore.acquire()  # 线程安全

    def release(self) -> None:
        if self.thread_semaphore:
            self.thread_semaphore.release()  # 线程安全
```

## 5. 后端 API 设计

### 5.1 新增 API 端点

**位置**：`backend/server.py`

```python
# POST /api/projects/{project}/run/fenjing_generate
def handle_run_fenjing_generate(project: str, body: dict) -> dict:
    job_id = str(uuid.uuid4().hex)
    job = job_repo.create_job(job_id, "run_fenjing_generate", project, body)
    
    # 标记状态为 pending
    status_service.create_pending_state(project, "fenjing_generate")
    
    # 启动线程执行
    thread = threading.Thread(
        target=run_fenjing_generate_thread,
        args=(job_id, project, body)
    )
    thread.start()
    
    return job

# POST /api/projects/{project}/run/fenjing_upload
def handle_run_fenjing_upload(project: str, body: dict) -> dict:
    job_id = str(uuid.uuid4().hex)
    job = job_repo.create_job(job_id, "run_fenjing_upload", project, body)
    
    # 检查生成是否完成
    state = status_service.get_flow_state(project)
    generate_status = state.get("flows", {}).get("fenjing_generate", {}).get("status")
    if generate_status not in ["completed", "partial_completed"]:
        return {"error": "请先完成分镜图生成"}
    
    # 标记状态为 pending
    status_service.create_pending_state(project, "fenjing_upload")
    
    # 启动线程执行
    thread = threading.Thread(
        target=run_fenjing_upload_thread,
        args=(job_id, project, body)
    )
    thread.start()
    
    return job
```

### 5.2 Job 类型映射

**位置**：`backend/repositories/job_repo.py`

```python
mapping = {
    # ... 现有映射
    "run_fenjing_generate": ("image", "fenjing_generate"),
    "run_fenjing_upload": ("image", "fenjing_upload"),
}
```

## 6. 前端设计

### 6.1 按钮显示逻辑

**位置**：`frontend/index.html`

```html
<!-- 分镜图生成按钮 -->
<button data-flow="fenjing_generate" class="flow-btn">
    第一步：分镜图生成
</button>

<!-- 上传按钮（默认隐藏） -->
<button data-flow="fenjing_upload" class="flow-btn hidden">
    第二步：上传
</button>
```

### 6.2 按钮显示控制

**位置**：`frontend/app.js`

```javascript
function updateFenjingButtons(flowStatus) {
    const generateBtn = document.querySelector('[data-flow="fenjing_generate"]');
    const uploadBtn = document.querySelector('[data-flow="fenjing_upload"]');
    
    const generateStatus = flowStatus?.fenjing_generate?.status || "waiting";
    const uploadStatus = flowStatus?.fenjing_upload?.status || "waiting";
    
    // 生成按钮逻辑
    if (["completed", "partial_completed"].includes(generateStatus)) {
        generateBtn.classList.add("hidden");
    } else {
        generateBtn.classList.remove("hidden");
    }
    
    // 上传按钮逻辑：生成完成或部分完成时显示
    if (["completed", "partial_completed"].includes(generateStatus) && uploadStatus !== "completed") {
        uploadBtn.classList.remove("hidden");
    } else {
        uploadBtn.classList.add("hidden");
    }
}
```

### 6.3 FLOW_TREE_CONFIG

```javascript
fenjing_generate: {
    title: "分镜图生成",
    steps: [
        {
            id: "download_assets",
            label: "下载资产",
            desc: "下载提示词与参考图"
        },
        {
            id: "generate_images",
            label: "生成分镜图",
            desc: "生成到本地目录"
        }
    ]
},
fenjing_upload: {
    title: "上传分镜图",
    steps: [
        {
            id: "upload_fenjing_images",
            label: "上传到 TOS",
            desc: "上传分镜图到云存储"
        }
    ]
}
```

## 7. 兼容性设计

### 7.1 保留原 fenjing 流程

原 `POST /api/projects/{project}/run/fenjing` 保持不变，内部依次调用：
1. `run_fenjing_generate_workflow`
2. `run_fenjing_upload_workflow`

### 7.2 状态兼容

旧版状态读取时自动转换：
- `fenjing.generate_images = completed` → `fenjing_generate.status = completed`
- `fenjing.upload_assets = completed` → `fenjing_upload.status = completed`
