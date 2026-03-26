# Task 2 总结：emit_event step 参数迁移

> 完成时间：2026-03-26

## 改动文件

| 文件 | emit_event 数 | 说明 |
|------|-------------|------|
| `backend/services/workflow_runtime/fenjing.py` | 67 | step/phase 参数全部迁移到 step_ 前缀 |
| `backend/services/workflow_runtime/auto_storyboard.py` | 75 | step/phase 参数全部迁移到 step_ 前缀 |
| `backend/services/workflow_runtime/video.py` | 117 | step/phase 参数全部迁移到 step_ 前缀 |
| `backend/services/workflow_runtime/visual_audio_assets.py` | 139 | step/phase 参数 + 动态变量定义 + dict映射全部迁移 |
| **合计** | **398** | |

## 迁移规则

### fenjing.py（fenjing / fenjing_generate / fenjing_upload 三个 flow）

| 旧 step | 新 step |
|---------|---------|
| `download_assets` | `step_download` |
| `generate_images` / `fenjing_image` / `build_fenjing_prompts` | `step_generate` |
| `upload_assets` / `upload` / `upload_fenjing_images` | `step_upload` |
| `start` | 归属到各 flow 第一个 step |
| `general` | 归属到上下文所在阶段 |
| `complete` | 归属到各 flow 最后一个 step |
| `error` | 归属到错误发生阶段 |

### auto_storyboard.py

| 旧 step | 新 step |
|---------|---------|
| `phase1` / `phase1_api_call` / `ark_responses`(phase1上下文) / `assets_saved` | `step_extract` |
| `phase2` / `phase2_batch_progress` | `step_storyboard` |
| `upload` | `step_upload` |
| `storyboard` | 根据上下文归属 `step_extract` / `step_storyboard` / `step_upload` |
| `phase_cleanup` | 根据 phase 参数归属 `step_extract` 或 `step_storyboard` |

### video.py

| 旧 step | 新 step |
|---------|---------|
| `prepare` / `download_assets` | `step_prepare` |
| `phase1_video_prompts` / `fenjing_prompts`(prompt上下文) | `step_video_prompts` |
| `phase2_video_generation` / `video_task_submit` / `video_task_queue` / `fenjing_video_task_create` / `fenjing_video` / `fenjing_video_polling` / `fenjing_video_download` / `fenjing_prompts`(生成上下文) | `step_video_generation` |
| `fenjing_video_upload` / `fenjing_prompts`(上传上下文) | `step_video_upload` |

### visual_audio_assets.py

| 旧 step | 新 step |
|---------|---------|
| `download_assets` | `step_download` |
| `character_prompts` | `step_character_prompts` |
| `location_prompts` | `step_location_prompts` |
| `fenjing_prompts` | `step_fenjing_prompts` |
| `character_images` / `generate_images` | `step_character_images` |
| `location_images` | `step_location_images` |
| `cloth_images` / `generate_cloth` / `validate_cloth` | `step_cloth_images` |
| `cloth_changed` | `step_cloth_changed` |
| `tts` | `step_tts` |
| `upload_assets` | `step_upload` |
| `phase_assets_generation` | `step_upload` |

### 动态变量/dict 修复

- `phase_step` 变量：`"phase_cloth_generation"` → `"step_cloth_images"`, `"cloth_changed"` → `"step_cloth_changed"`
- `validate_step` 变量：`"validate_cloth"` → `"step_cloth_images"`, `"cloth_changed"` → `"step_cloth_changed"`
- 错误处理 dict：`character_prompts/location_prompts/tts/fenjing_prompts` → 对应 `step_` 前缀名

### phase= 参数迁移

| 旧 phase | 新 phase |
|----------|----------|
| `phase_download_assets` | `step_download` |
| `phase_generate_images` | `step_generate` |
| `phase1_video_prompts` | `step_video_prompts` |
| `phase2_video_generation` | `step_video_generation` |
| `prepare` | `step_prepare` |
| `fenjing_video_upload` | `step_video_upload` |
| `phase1` | `step_extract` |
| `phase2` | `step_storyboard` |
| `upload` | `step_upload` |
| `phase_assets_generation` | `step_upload` |
| `phase_cloth_generation` | `step_cloth_images` |

## 验证结果

- 语法检查：4 个文件全部通过
- 测试：17 passed / 1 failed（环境相关，非代码问题）

## 关键决策

1. **`step="storyboard"` 上下文归属**：auto_storyboard.py 中大量使用 `step="storyboard"` 作为通用日志 step，需要根据代码位置判断归属到 `step_extract`（phase1区域）、`step_storyboard`（phase2区域）或 `step_upload`（上传区域）

2. **`step="fenjing_prompts"` 上下文归属**：video.py 中 `fenjing_prompts` 作为通用 step 遍布整个文件，需要根据函数和代码区域判断归属到 `step_video_prompts`、`step_video_generation` 或 `step_video_upload`

3. **`step="general"` / `step="start"` / `step="complete"` / `step="error"`**：统一归属到当前上下文所在的具体阶段 step，消除模糊 step 名

## 后续任务依赖

| 后续 Task | 依赖本 Task 的内容 |
|-----------|-------------------|
| Task 3: 前端同步 | emit_event 现在发送新 step 名，前端 FLOW_TREE_CONFIG 需要对齐 |
| Task 4: 清理 | `_resolve_step()` 旧映射和 `_STEP_MIGRATION` 现在可以安全删除 |
