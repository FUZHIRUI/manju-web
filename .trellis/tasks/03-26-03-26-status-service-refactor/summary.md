# Task 1 总结：status_service.py 核心重构

> 完成时间：2026-03-26

## 改动文件

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `backend/services/status_service.py` | 核心重构 | _FLOW_STEPS 重定义、迁移映射、rollup 合并、_resolve_step 简化 |
| `backend/services/workflow_service.py` | 适配 | 所有 step 引用更新为 step_ 前缀 |
| `backend/handlers/job_handler.py` | 适配 | _resolve_flow_steps 和 phase 白名单更新 |
| `backend/tests/test_flow_state_persistence.py` | 适配 | 测试用例 step 名更新 |

## 核心改动详情

### 1. _FLOW_STEPS 统一 step_ 前缀

**Before**:
```python
_FLOW_STEPS = {
    "auto_storyboard": ["step1", "step1_extract", "step2", "step2_storyboard", "step3_upload", "step3_upload_assets"],
    "visual_audio_assets": ["download_assets", "build_prompts", "generate_images", "generate_tts", "upload_assets", "character_prompts", ...],
    "fenjing": ["download_assets", "generate_images", "upload_assets"],
    "fenjing_generate": ["download_assets", "generate_images"],
    "fenjing_upload": ["upload_fenjing_images"],
    "video": ["prepare", "phase1_video_prompts", "phase2_video_generation", "fenjing_video_upload"],
}
```

**After**:
```python
_FLOW_STEPS = {
    "auto_storyboard": ["step_extract", "step_storyboard", "step_upload"],
    "visual_audio_assets": [
        "step_download", "step_character_prompts", "step_location_prompts", "step_fenjing_prompts",
        "step_character_images", "step_location_images", "step_cloth_images", "step_cloth_changed",
        "step_tts", "step_upload",
    ],
    "fenjing_generate": ["step_download", "step_generate"],
    "fenjing_upload": ["step_upload"],
    "video": ["step_prepare", "step_video_prompts", "step_video_generation", "step_video_upload"],
}
```

**关键决策**：
- 删除 `fenjing` flow（保留 `fenjing_generate` + `fenjing_upload`）
- auto_storyboard：6步 → 3步（移除冗余父子步骤）
- visual_audio_assets：移除虚拟父步骤（build_prompts/generate_images/generate_tts），只保留叶子步骤

### 2. _STEP_MIGRATION 迁移映射表

新增 `_STEP_MIGRATION` 字典，覆盖所有 5 个 flow 的旧→新 step 名映射，在 `_normalize_state()` 中自动迁移旧格式 flow_state.json。

旧的 auto_storyboard 专用兼容代码已删除，替换为通用迁移逻辑。

### 3. Rollup 函数合并

**Before**：4 个独立函数
- `_rollup_visual_audio_steps()` — 父子聚合
- `_rollup_auto_storyboard_steps()` — 父子聚合
- `_rollup_video_steps()` — 顺序依赖
- `_rollup_fenjing_steps()` — 顺序依赖

**After**：2 个通用函数 + 配置数据
- `_rollup_parent_child(state, flow)` — 由 `_ROLLUP_PARENT_CHILD` 配置驱动
- `_rollup_sequential(state, flow)` — 由 `_ROLLUP_SEQUENTIAL` 配置驱动
- `_rollup(state, flow)` — 统一入口，按 flow 名自动选择

```python
_ROLLUP_PARENT_CHILD = {
    "visual_audio_assets": {
        "step_prompts": ["step_character_prompts", "step_location_prompts", "step_fenjing_prompts"],
        "step_images": ["step_character_images", "step_location_images"],
    },
}

_ROLLUP_SEQUENTIAL = {
    "video": ["step_prepare", "step_video_prompts", "step_video_generation", "step_video_upload"],
    "fenjing_generate": ["step_download", "step_generate"],
}
```

### 4. _resolve_step 直通 + 迁移逻辑

在函数开头新增：
1. **直通**：step 已在 `_FLOW_STEPS[flow]` 中 → 直接返回
2. **迁移**：step 在 `_STEP_MIGRATION[flow]` 中 → 返回迁移后的新名
3. **旧映射保留**：原有的 event/phase 映射逻辑保留（过渡期兼容）

### 5. 其他清理

- `_normalize_phase_tokens()` → `_normalize_step_tokens()`，参数 `phase` → `step_filter`
- `resolve_visual_audio_steps(phase)` → `resolve_visual_audio_steps(step_filter)`，返回值全部为新 step 名
- 删除 `_expand_visual_audio_children()` 和 `_expand_auto_storyboard_children()`（不再有父子展开需求）
- 所有调用 rollup 的位置统一为 `_rollup(state, flow)`

### 6. workflow_service.py 适配

所有 `status_service.update_step_status()` / `mark_flow_error()` / `mark_step_completed()` 调用中的旧 step 名替换为新 step_ 前缀名。

auto_storyboard 的冗余双步骤更新合并（如 `step1` + `step1_extract` 合并为 `step_extract`）。

### 7. job_handler.py 适配

- `_resolve_flow_steps()` 返回值全部更新为新 step 名
- auto_storyboard phase 白名单添加新命名（step_extract/step_storyboard/step_upload）

## 过渡期兼容

- emit_event 调用端仍使用旧 step 名（Task 2 才改）
- `_resolve_step()` 通过直通 + 迁移 + 旧映射三层保证旧名正确映射到新名
- 旧格式 flow_state.json 通过 `_STEP_MIGRATION` 在读取时自动迁移

## 验证结果

- 语法检查：3 个文件全部通过
- 测试：15 个通过（test_flow_state_persistence + test_flow_state_frontend）

## 后续任务依赖

| 后续 Task | 依赖本 Task 的内容 |
|-----------|-------------------|
| Task 2: emit_event 迁移 | 使用 `_FLOW_STEPS` 中的新 step 名替换 ~370 处 emit_event 调用 |
| Task 3: 前端同步 | FLOW_TREE_CONFIG 对齐新 step 名 |
| Task 4: 清理 | 删除 `_resolve_step` 旧映射、`_STEP_MIGRATION`、`WORKFLOW_TO_FLOW_MAP` |
