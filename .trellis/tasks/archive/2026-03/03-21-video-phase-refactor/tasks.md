# Video Step Refactor — 任务列表

> 基于 prd.md，将 video 工作流拆分为 3 个可独立触发的 step，前端三按钮 UI。
> 术语：使用 `step` 表示用户可触发的执行单元（API 参数名保持 `phase` 以兼容跨层模式）。

---

## Step 映射

| Step token | 内部 steps 标记 | 前端按钮 |
|---|---|---|
| `prepare_prompts` | `prepare` + `phase1_video_prompts` | "第一步：视频提示词生成" |
| `generate_videos` | `phase2_video_generation` | "第二步：视频生成" |
| `upload_videos` | `fenjing_video_upload` | "第三步：上传" |
| `all`（默认） | 全部 4 个 | （顺序执行全部） |

---

## Task 1: video.py — 拆分 step 函数 + 支持跳过上传

**文件**: `backend/services/workflow_runtime/video.py`
**优先级**: P0（其他任务依赖此项）

- [ ] 1.1 `process_single_video_independent` 增加 `skip_upload: bool = False` 参数
  - 当 `skip_upload=True` 时，下载视频到本地后直接返回，跳过 TOS 上传（line 924-1032）
  - 默认 `False`，保持原有行为不变

- [ ] 1.2 新增 `run_video_prepare_prompts()` 异步函数
  - 从 `run_video_workflow_multi` 提取 lines 1382-1554
  - 覆盖：项目名提取 → 章节发现 → fenjing_prompts 下载 → 视频提示词并发生成
  - 返回 `List[Dict]`（chapter_entries + video_prompts_path）
  - 保留原有 emit_event 调用（flow_start, prepare phase_complete 等）

- [ ] 1.3 新增 `run_video_generate_only()` 异步函数
  - 扫描文件系统中已存在 `shipin_prompts.jsonl` 的章节目录
  - 为每个章节创建 asyncio task，调用视频生成逻辑（传入 `skip_upload=True`）
  - 视频生成 + 下载到本地，但 **不上传 TOS**
  - 返回 `(success_count, error_count)` 元组

- [ ] 1.4 新增 `run_video_upload_only()` 异步函数
  - 扫描各章节 `video/` 目录下已下载的 `fenjing_*_video.mp4` 文件
  - 为每个文件执行 TOS 上传（复用现有 TOS 上传逻辑）
  - emit 对应的 upload 事件
  - 返回 `(success_count, error_count)` 元组

- [ ] 1.5 `run_video_workflow` 和 `run_video_workflow_multi` 保持不变（`step="all"` 路径零改动）

---

## Task 2: status_service.py — 修复 rollup 调用缺失

**文件**: `backend/services/status_service.py`
**优先级**: P0（状态正确性保障）

- [ ] 2.1 在 `mark_step_completed()` 中增加 video rollup 调用
  - line 765-766 处，`if flow == "fenjing"` 后增加 `elif flow == "video": _rollup_video_steps(state)`
  - `_rollup_video_steps` 已存在（lines 588-611），仅需补充调用

---

## Task 3: workflow_service.py — 添加 step 分发

**文件**: `backend/services/workflow_service.py`
**优先级**: P0（核心路由逻辑）
**依赖**: Task 1

- [ ] 3.1 修改 `run_video` 函数签名，增加 `phase: str = "all"` 参数
- [ ] 3.2 实现 step 条件分发逻辑
  - `phase == "all"`：保持现有行为不变（调用 `run_video_workflow_multi`）
  - `phase == "prepare_prompts"`：调用 `video.run_video_prepare_prompts`
    - 完成后标记 `prepare` + `phase1_video_prompts`
  - `phase == "generate_videos"`：调用 `video.run_video_generate_only`
    - 构建 asset results，标记 `phase2_video_generation`
    - 保留 partial failure 处理
  - `phase == "upload_videos"`：调用 `video.run_video_upload_only`
    - 完成后标记 `fenjing_video_upload`
- [ ] 3.3 每个 step 路径实现错误处理（参照 `run_fenjing` 模式）
  - 成功：`mark_step_completed` + `job_repo.update_job(status="success")`
  - 部分失败：`update_step_partial` + `mark_flow_partial`
  - 异常：`mark_flow_error` + `job_repo.update_job(status="error")`

---

## Task 4: job_handler.py — Step 路由

**文件**: `backend/handlers/job_handler.py`
**优先级**: P0（API 入口）
**依赖**: Task 3

- [ ] 4.1 更新 `_resolve_flow_steps()` 中 video 分支
  - `"prepare_prompts"` → `["prepare", "phase1_video_prompts"]`
  - `"generate_videos"` → `["phase2_video_generation"]`
  - `"upload_videos"` → `["fenjing_video_upload"]`
  - 默认 → 全部 4 个 steps

- [ ] 4.2 更新 `handle_post` 中 video 处理块
  - 解析 `body.get("phase", "all")`
  - `start_job` 使用 `lambda job_id, p=phase:` 捕获 phase 值
  - payload 传入 `{"phase": phase}`

- [ ] 4.3 增加 `reset_steps` 逻辑
  - 当 step 为 `"prepare_prompts"` / `"generate_videos"` / `"upload_videos"` 时，`reset_steps = False`

---

## Task 5: frontend/app.js — 三按钮 UI

**文件**: `frontend/app.js`
**优先级**: P1（用户交互层）
**依赖**: Task 4

- [ ] 5.1 重写 `appendVideoPhaseButtons` 函数（替换 lines 992-1002）
  - 按钮 1："第一步：视频提示词生成" → `executeFlowFull("video", { phase: "prepare_prompts" })`
    - 状态取 `phase1_video_prompts` step
  - 按钮 2："第二步：视频生成" → `executeFlowFull("video", { phase: "generate_videos" })`
    - 状态取 `phase2_video_generation` step
  - 按钮 3："第三步：上传" → `executeFlowFull("video", { phase: "upload_videos" })`
    - 状态取 `fenjing_video_upload` step
  - 参照 `appendFenjingPhaseButtons`（lines 948-990）的状态检查模式

- [ ] 5.2 每个按钮根据 step 状态显示
  - `waiting` → "执行"
  - `running` → "执行中" + breathing 动画
  - `completed` / `partial_completed` → "已完成" + ✓ 标记 + disabled

---

## Task 6: 验证

**优先级**: P1
**依赖**: Task 1-5 全部完成

- [ ] 6.1 向后兼容：`POST /run/video` 无 body → 行为不变（phase 默认 "all"）
- [ ] 6.2 Step 1 单独执行：`{"phase":"prepare_prompts"}` → flow_state 前 2 步 completed，后 2 步 waiting
- [ ] 6.3 Step 2 单独执行：Step 1 完成后 `{"phase":"generate_videos"}` → `phase2_video_generation` completed
- [ ] 6.4 Step 3 单独执行：Step 2 完成后 `{"phase":"upload_videos"}` → `fenjing_video_upload` completed，flow 整体 completed
- [ ] 6.5 Rollup 验证：Step 1 完成后，Step 2/3 保持 waiting（顺序约束生效）
- [ ] 6.6 Python 语法检查通过
