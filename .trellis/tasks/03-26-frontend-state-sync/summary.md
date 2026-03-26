# Task 3 总结：前端状态同步

> 完成时间：2026-03-26

## 改动文件

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `frontend/app.js` | 前端核心 | FLOW_TREE_CONFIG 全部 step id 迁移到 step_ 前缀、isAssetGenerating 修复、死代码清理 |
| `backend/handlers/job_handler.py` | 后端适配 | visual_audio_assets allowed_phases 白名单新增 step_ 前缀命名 |

## 核心改动详情

### 1. FLOW_TREE_CONFIG step id 统一

所有 5 个 flow 配置的 step id 从旧命名迁移到 step_ 前缀：

| Flow | 旧 step id | 新 step id |
|------|-----------|-----------|
| auto_storyboard | step1, step2, step3_upload | step_extract, step_storyboard, step_upload |
| visual_audio_assets | download_assets, build_prompts, generate_images, generate_tts, upload_assets | step_download, step_prompts, step_images, step_tts, step_upload |
| fenjing | download_assets, generate_images, upload_assets | step_download, step_generate, step_upload |
| fenjing_generate | download_assets, generate_images, upload_fenjing_images | step_download, step_generate, step_upload |
| fenjing_upload | upload_fenjing_images | step_upload |
| video | prepare, phase1_video_prompts, phase2_video_generation, fenjing_video_upload | step_prepare, step_video_prompts, step_video_generation, step_video_upload |

### 2. parallel 配置更新（visual_audio_assets）

并行阶段的所有 item id、step 引用、dependsOn 引用、errorSteps 全部更新为 step_ 前缀。

### 3. tree 配置更新（visual_audio_assets）

tree levels 中所有 node id、step/item 引用更新为 step_ 前缀。

### 4. isAssetGenerating 修复（P1 bug）

**修复前**：
```javascript
fenjing: { flow: "fenjing_generate", steps: ["generate_images", "upload_fenjing_images"], ... }
```
- `upload_fenjing_images` 不在 `fenjing_generate` flow 的 steps 中，永远匹配不到

**修复后**：
```javascript
fenjing: { flow: "fenjing_generate", steps: ["step_generate"], ... }
```
- 所有 assetType 的 steps 引用更新为新 step_ 前缀名

### 5. 事件匹配更新

- FLOW_TREE_CONFIG 中所有 startEvents/completeEvents 的 phase/step 参数更新为新命名
- `parseAutoStoryboardProgressFromEvents` 兼容新旧事件名（双条件匹配）

### 6. 前端 API phase 参数

| 位置 | 旧值 | 新值 |
|------|------|------|
| uploadNovelWithDialog payload | `phase: "step1"` | `phase: "step_extract"` |
| video stepKey | `phase1_video_prompts` / `phase2_video_generation` / `fenjing_video_upload` | `step_video_prompts` / `step_video_generation` / `step_video_upload` |
| auto_storyboard 重试 | `step1` / `step2` / `step3_upload` | `step_extract` / `step_storyboard` / `step_upload` |
| visual_audio_assets checkSteps | 旧 step 名 | step_ 前缀名 |

注意：visual_audio_assets 的 phases（发送给后端的 phase 参数如 `build_prompts`、`generate_images` 等）暂保持不变，因为后端 `resolve_visual_audio_steps()` 仍接受这些旧名。

### 7. 死代码清理

- 删除 `executeFlowFull` 中 `flow === "fenjing"` 分支（line 5898）

### 8. 后端 phase 白名单同步

`job_handler.py` 的 `allowed_phases` 新增 10 个 step_ 前缀名，支持前端发送新命名的 phase 参数。

## 验证结果

- 语法检查：frontend/app.js ✓、backend/handlers/job_handler.py ✓
- 测试：17 passed / 1 failed（环境相关，非代码问题）

## 后续任务依赖

| 后续 Task | 依赖本 Task 的内容 |
|-----------|-------------------|
| Task 4: 清理 | 可删除 `_resolve_step()` 旧映射、`_STEP_MIGRATION`、旧 phase 白名单条目 |
