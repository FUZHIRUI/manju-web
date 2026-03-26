# 四流程状态管理统一审查报告

> 生成时间：2026-03-26
> 分析工具：python-abcoder (AST) + 手动代码审查
> 审查范围：auto_storyboard, visual_audio_assets, fenjing, video 四个流程的状态管理

---

## 1. 现状总览

### 1.1 状态常量（已统一 ✅）

`status_service.py` 定义了 7 个全局状态常量，四个流程共用：

| 状态 | 含义 |
|------|------|
| `waiting` | 未开始 |
| `pending` | 等待执行（用户点击后排队） |
| `running` | 执行中 |
| `partial_returned` | 部分结果返回（运行中） |
| `partial_completed` | 部分完成（已结束） |
| `completed` | 全部完成 |
| `error` | 出错 |

**结论**：状态值已统一，七个状态在四个流程中通用。

### 1.2 步骤定义（`_FLOW_STEPS`）现状

```python
_FLOW_STEPS = {
    "auto_storyboard": [
        "step1", "step1_extract",
        "step2", "step2_storyboard",
        "step3_upload", "step3_upload_assets",
    ],
    "visual_audio_assets": [
        "download_assets", "build_prompts", "generate_images",
        "generate_tts", "upload_assets",
        "character_prompts", "character_images",
        "location_prompts", "fenjing_prompts",
        "location_images", "cloth_images", "cloth_changed", "tts",
    ],
    "fenjing": ["download_assets", "generate_images", "upload_assets"],
    "fenjing_generate": ["download_assets", "generate_images"],
    "fenjing_upload": ["upload_fenjing_images"],
    "video": ["prepare", "phase1_video_prompts", "phase2_video_generation", "fenjing_video_upload"],
}
```

---

## 2. 核心问题分析

### 问题 1：步骤命名体系不统一 ❌

四个流程使用了完全不同的步骤命名规范：

| 流程 | 步骤命名风格 | 示例 |
|------|-------------|------|
| auto_storyboard | `step{N}` + `step{N}_{detail}` | `step1`, `step1_extract`, `step2`, `step2_storyboard` |
| visual_audio_assets | `{动作}_{对象}` 混合式 | `download_assets`, `character_prompts`, `cloth_changed` |
| fenjing | `{动作}_{对象}` | `download_assets`, `generate_images`, `upload_assets` |
| video | `{phase}_{detail}` 混合式 | `prepare`, `phase1_video_prompts`, `fenjing_video_upload` |

**问题**：
- auto_storyboard 用 `step1/step2/step3` 数字序号
- visual_audio_assets 用语义化命名，且父子步骤混在同一层
- video 用 `phase1_xxx/phase2_xxx` 前缀
- fenjing 用简单的三段式

**用户诉求**：所有流程统一使用 `step` 来表述。

### 问题 2：emit_event 中的 step 字段与 _FLOW_STEPS 定义严重不一致 ❌❌

这是**最严重的问题**。各模块 `emit_event()` 中发送的 `step=` 值，和 `_FLOW_STEPS` 中定义的 step 名称不一致，导致 `_resolve_step()` 需要做大量硬编码映射。

#### auto_storyboard emit_event 实际使用的 step 值：
```
"start", "storyboard", "ark_responses", "phase1", "phase1_api_call",
"phase2", "phase2_batch_progress", "upload", "phase_cleanup",
"assets_saved", "complete"
```

**vs _FLOW_STEPS 定义**：`step1, step1_extract, step2, step2_storyboard, step3_upload, step3_upload_assets`

→ emit_event 使用 `phase1/phase2/upload`，_FLOW_STEPS 使用 `step1/step2/step3_upload`，完全两套命名！

#### visual_audio_assets emit_event 实际使用的 step 值：
```
"download_assets", "character_prompts", "character_images",
"location_prompts", "location_images", "fenjing_prompts",
"cloth_images", "cloth_changed", "generate_cloth",
"generate_cloth_changed_images", "validate_cloth",
"phase_cloth_generation", "tts", "upload_assets",
"generate_images", "build_prompts", "general",
"start", "phase_assets_generation", "complete"
```

→ 有些值与 _FLOW_STEPS 一致（如 `download_assets`, `character_prompts`），但也有大量非标准值（`general`, `start`, `generate_cloth`, `validate_cloth`）

#### fenjing emit_event 实际使用的 step 值：
```
"download_assets", "generate_images", "upload_assets",
"fenjing_image", "build_fenjing_prompts", "upload",
"upload_fenjing_images", "start", "general", "complete", "error"
```

→ 混用 `fenjing_image` vs `generate_images`，`upload` vs `upload_assets` vs `upload_fenjing_images`

#### video emit_event 实际使用的 step 值：
```
"download_assets", "fenjing_prompts", "general",
"fenjing_video_task_create", "fenjing_video_polling",
"fenjing_video_download", "fenjing_video_upload",
"video_task_queue", "video_task_submit",
"prepare", "phase1_video_prompts", "phase2_video_generation",
"start", "complete"
```

→ 大量细粒度 step（如 `fenjing_video_polling`, `video_task_queue`）不在 _FLOW_STEPS 中定义

### 问题 3：_resolve_step() 硬编码映射过于庞大 ❌

`_resolve_step()` 函数（390-459行）是一个巨大的 if/elif 映射，将 emit_event 中的非标准 step/phase/event 映射到 _FLOW_STEPS 中定义的标准 step。这个函数是两套不一致命名系统之间的"胶水层"。

**问题**：
- 70行硬编码映射，极易遗漏
- 新增 step 必须同时修改 emit_event 调用和 _resolve_step()，否则状态丢失
- visual_audio_assets 需要单独的 `_resolve_steps()`（复数），因为一个事件可能更新多个步骤

### 问题 4：父子步骤结构不统一 ❌

| 流程 | 父子关系模式 | rollup 函数 |
|------|-------------|-------------|
| auto_storyboard | `step1 → [step1_extract]` | `_rollup_auto_storyboard_steps()` |
| visual_audio_assets | `build_prompts → [character_prompts, location_prompts, fenjing_prompts]` | `_rollup_visual_audio_steps()` |
| fenjing | 无父子关系，纯顺序 | `_rollup_fenjing_steps()` |
| video | 无父子关系，纯顺序 | `_rollup_video_steps()` |

**每个流程的 rollup 逻辑都独立实现**，但实质上只有两种模式：
1. **父子汇总**（auto_storyboard, visual_audio_assets）：子步骤状态汇总到父步骤
2. **顺序依赖**（fenjing, video）：前一步骤完成后才能开始下一步

这两种模式可以抽象为通用实现。

### 问题 5：fenjing 被拆分为三个独立 flow ❌

```python
"fenjing":          ["download_assets", "generate_images", "upload_assets"],
"fenjing_generate": ["download_assets", "generate_images"],
"fenjing_upload":   ["upload_fenjing_images"],
```

fenjing 实际上是一个流程，但被拆分为 3 个 flow（`fenjing`, `fenjing_generate`, `fenjing_upload`），导致：
- `_resolve_step()` 中 fenjing 有三段重复映射逻辑
- `WORKFLOW_TO_FLOW_MAP` 需要额外映射
- 前端需要同时跟踪多个 flow 的状态

### 问题 6：workflow_service.py 状态更新方式不统一 ❌

| 流程 | 成功时状态更新方式 |
|------|-------------------|
| auto_storyboard | 手动逐个调用 `update_step_status()` 设置每个子步骤 |
| visual_audio_assets | 通过 `resolve_visual_audio_steps()` 动态解析 → 批量 `update_step_status()` |
| fenjing | 直接调用 `mark_flow_completed()` |
| video (分步) | 逐步调用 `mark_step_completed()` |
| video (full) | 直接调用 `mark_flow_completed()` |

→ 同一个系统有 4 种不同的状态更新模式。

### 问题 7：旧命名兼容代码仍存在 ⚠️

`_normalize_state()` 中（118-137行）包含 auto_storyboard 旧命名（`phase1/phase2/upload`）到新命名（`step1/step2/step3_upload`）的兼容映射。

`workflow_service.py:run_auto_storyboard()` 中（140-145行）也包含反向映射：
```python
phase_mapping = {
    "step1": "phase1",
    "step2": "phase2",
    "step3_upload": "upload",
}
```

说明 auto_storyboard 的命名迁移**尚未完成**，内部仍使用 `phase1/phase2`。

---

## 3. 统一方案建议

### 3.1 统一步骤命名规范

建议所有流程统一使用 `step_{序号}_{语义}` 格式：

```python
_FLOW_STEPS = {
    "auto_storyboard": [
        "step_1_extract",       # Phase1: 提取角色/摘要/地点
        "step_2_storyboard",    # Phase2: 生成分镜剧本
        "step_3_upload",        # 上传到TOS
    ],
    "visual_audio_assets": [
        "step_1_download",      # 下载资产
        "step_2_prompts",       # 生成所有prompts (父步骤)
        "step_2a_char_prompts", # ├── 角色prompts
        "step_2b_loc_prompts",  # ├── 地点prompts
        "step_2c_fenj_prompts", # └── 分镜prompts
        "step_3_images",        # 生成图片 (父步骤)
        "step_3a_char_images",  # ├── 角色图片
        "step_3b_loc_images",   # └── 地点图片
        "step_4_cloth",         # 服装图片
        "step_5_cloth_changed", # 换装图片
        "step_6_tts",           # TTS语音生成
        "step_7_upload",        # 上传到TOS
    ],
    "fenjing": [
        "step_1_download",      # 下载资产
        "step_2_generate",      # 生成分镜图
        "step_3_upload",        # 上传到TOS
    ],
    "video": [
        "step_1_prepare",       # 准备环境
        "step_2_prompts",       # 生成视频prompts
        "step_3_generate",      # 视频生成
        "step_4_upload",        # 上传到TOS
    ],
}
```

### 3.2 统一 rollup 机制

将四个独立的 rollup 函数合并为一个通用实现：

```python
# 统一的父子步骤映射
_STEP_CHILDREN = {
    "visual_audio_assets": {
        "step_2_prompts": ["step_2a_char_prompts", "step_2b_loc_prompts", "step_2c_fenj_prompts"],
        "step_3_images": ["step_3a_char_images", "step_3b_loc_images"],
    },
    # 其他流程如果有父子关系也在这里定义
}

def _rollup_steps(state: Dict, flow: str) -> None:
    """通用的步骤状态汇总"""
    children_map = _STEP_CHILDREN.get(flow, {})
    steps = state["flows"][flow]["steps"]
    for parent, children in children_map.items():
        child_statuses = [steps.get(c, "waiting") for c in children]
        steps[parent] = _aggregate_statuses(child_statuses)
```

### 3.3 消除 _resolve_step() 映射层

**根本方案**：让 emit_event 中的 step 值直接使用 _FLOW_STEPS 中定义的标准名称。

修改四个流程模块中所有 `emit_event()` 调用，将非标准 step 值替换为标准值：
- `step="phase1"` → `step="step_1_extract"`
- `step="fenjing_image"` → `step="step_2_generate"`
- `step="video_task_submit"` → `step="step_3_generate"`
- 等等

修改完成后，`_resolve_step()` 可简化为：
```python
def _resolve_step(flow, event, step, phase):
    if step in _FLOW_STEPS.get(flow, []):
        return step
    return None
```

### 3.4 合并 fenjing 子流程

将 `fenjing`, `fenjing_generate`, `fenjing_upload` 合并为一个 flow `fenjing`，通过 phase 参数控制执行范围。与 video 使用 `phase="prepare_prompts/generate_videos/upload_videos"` 的模式对齐。

### 3.5 统一 workflow_service.py 状态更新模式

建议抽象为通用函数：

```python
def _mark_steps_completed(project: str, flow: str, steps: List[str]) -> None:
    """统一的步骤完成标记"""
    for step in steps:
        mark_step_completed(project, flow, step)
    # 自动 rollup + recalculate flow status
```

---

## 4. 问题严重程度排序

| 优先级 | 问题 | 影响 | 建议 |
|--------|------|------|------|
| P0 | emit_event step 与 _FLOW_STEPS 不一致 | 状态可能丢失，_resolve_step 极易遗漏 | 统一命名，消除映射层 |
| P1 | 步骤命名体系不统一 | 可读性差，新增流程无标准可循 | 统一 `step_{N}_{语义}` |
| P1 | 四个独立 rollup 函数 | 重复代码，逻辑不一致风险 | 抽象为通用 rollup |
| P2 | fenjing 三个 flow 冗余 | 复杂度高，前端跟踪困难 | 合并为一个 flow |
| P2 | workflow_service 状态更新模式不统一 | 维护困难 | 抽象通用函数 |
| P3 | 旧命名兼容代码 | 技术债务 | 迁移完成后清理 |

---

## 5. 量化统计

| 指标 | 数值 |
|------|------|
| emit_event 调用总数 | auto_storyboard: ~80, visual_audio: ~120, fenjing: ~70, video: ~100 |
| _resolve_step 映射行数 | 70行 |
| rollup 函数数量 | 4个独立实现 |
| 非标准 step 值数量 | auto_storyboard: ~10, visual_audio: ~8, fenjing: ~5, video: ~8 |
| 需要修改的 emit_event 调用 | 估计 ~150 处 |

---

## 6. 前端侧状态一致性审查

> 审查文件：`frontend/app.js`（6928行）

### 6.1 前端 Flow 定义 vs 后端

前端 `STAGE_TYPES`（第56行）：
```javascript
const STAGE_TYPES = ["auto_storyboard", "visual_audio_assets", "fenjing_generate", "video"];
```

后端 `_FLOW_STEPS` 有 6 个 flow key，前端只列了 4 个。`fenjing_upload` 和 `fenjing` 未在 STAGE_TYPES 中，但在其他位置有单独处理。

### 6.2 前后端 Step 一致性对比

#### auto_storyboard ⚠️

| 后端 step | 前端是否使用 | 备注 |
|-----------|-------------|------|
| `step1` | ✅ 有（851, 1147行） | 一致 |
| `step1_extract` | ❌ **无** | 前端忽略此子步骤 |
| `step2` | ✅ 有（854, 1149行） | 一致 |
| `step2_storyboard` | ❌ **无** | 前端忽略此子步骤 |
| `step3_upload` | ✅ 有（857, 1151行） | 一致 |
| `step3_upload_assets` | ❌ **无** | 前端忽略此子步骤 |

→ 前端只用父步骤（step1/step2/step3_upload），完全不展示子步骤进度。后端的父子 rollup 机制对前端来说是透明的。

#### visual_audio_assets ✅

所有 13 个后端 step 在前端都有对应引用，一致性最好。

#### fenjing_generate / fenjing_upload ✅

step 名称一致。

#### video ✅

`prepare`, `phase1_video_prompts`, `phase2_video_generation`, `fenjing_video_upload` 四个 step 前后端一致。

### 6.3 前端 Bug 发现

#### Bug #1：`flow === "fenjing"` 死代码（第5898行）

```javascript
if (flow === "fenjing") { ... }
```

后端 `_FLOW_STEPS` 中有 `fenjing` 这个 key，但前端 `STAGE_TYPES` 不包含它，且前端实际使用的是 `fenjing_generate` + `fenjing_upload`。这段代码的条件永远为 false，是残留的死代码。

#### Bug #2：`isAssetGenerating("fenjing")` 跨 flow 查询（第3728行）

```javascript
fenjing: { flow: "fenjing_generate", steps: ["generate_images", "upload_fenjing_images"], ... }
```

`upload_fenjing_images` 属于 `fenjing_upload` flow 的 step，但这里配置在 `fenjing_generate` flow 下查询。`getFlowStepStatus("fenjing_generate", "upload_fenjing_images")` 永远返回空——因为后端 `fenjing_generate` 的 steps 只有 `["download_assets", "generate_images"]`。

**影响**：当 fenjing_upload 正在上传时，`isAssetGenerating` 无法正确检测到 fenjing 处于工作状态。

### 6.4 前端 API 发送的 phase 值

| API | 前端发送的 phase | 后端对应 step |
|-----|-----------------|--------------|
| `run/auto_storyboard` | `step1` / `step2` / `step3_upload` | → 映射为 `phase1` / `phase2` / `upload` 后执行 |
| `run/visual_audio_assets` | `build_prompts` / `generate_images` / `generate_tts` / `upload_assets` / `cloth_images` / `cloth_changed` | 直接作为 phase 传入 |
| `run/video` | `prepare_prompts` / `generate_videos` / `upload_videos` | → 后端按 phase 分发到不同子函数 |
| `run/fenjing_generate` | 无 phase | 执行整个 flow |
| `run/fenjing_upload` | 无 phase | 执行整个 flow |

注意 auto_storyboard 的前端发送 `step1` → 后端 `workflow_service.py` 再映射回 `phase1` 给 `auto_storyboard.run_workflow()`，这是双重映射的典型案例。

### 6.5 前端状态值处理

前端通过 `getFlowStepStatus(flow, step)` 读取后端返回的 step 状态，并映射到 CSS class：

| 后端状态 | 前端 CSS class | UI 表现 |
|----------|---------------|---------|
| `running` | `running` | 旋转动画 |
| `completed` | `completed` | 绿色勾 |
| `error` | `error` | 红色叉 |
| `partial_returned` | （无特殊处理） | 归入默认样式 |
| `partial_completed` | （无特殊处理） | 归入默认样式 |
| `pending` | `pending` | 等待样式 |
| `waiting` | （无/空） | 灰色默认 |

**问题**：`partial_returned` 和 `partial_completed` 在前端没有对应的视觉区分，用户无法区分"部分完成"和"未开始"。

### 6.6 前端侧问题严重程度

| 优先级 | 问题 | 影响 |
|--------|------|------|
| **P1** | Bug #2：isAssetGenerating 跨 flow 查错 step | fenjing 上传时 UI 无法正确检测工作状态 |
| P2 | Bug #1：`flow === "fenjing"` 死代码 | 不影响功能，但增加混淆 |
| P3 | partial_returned/partial_completed 无 UI 区分 | 用户无法区分部分完成状态 |

---

## 7. 总结

当前状态管理系统的**状态值（7种状态）已经统一**，这是好的基础。但**步骤命名、事件映射、rollup 机制**三个维度完全不统一：

1. **步骤命名**：四种不同风格（数字序号/语义化/phase前缀/混合）
2. **事件映射**：emit_event 和 _FLOW_STEPS 两套命名系统需要 70 行硬编码映射
3. **rollup 机制**：四个独立实现，本质只有两种模式

统一改造的核心工作量在于修改四个流程模块中 ~350 处 `emit_event()` 调用的 step 参数，使其与 _FLOW_STEPS 定义的标准名称一致。这是一次性的大改动，但改完后可以：
- 删除 `_resolve_step()` 的 70 行映射
- 合并 4 个 rollup 函数为 1 个
- 消除旧命名兼容代码
- 大幅降低新增步骤时的出错概率
