# emit_event 迁移：step 参数统一替换

## Goal
将4个 flow 模块中 ~370 处 emit_event 调用的 step 参数替换为 _FLOW_STEPS 中定义的标准 step_ 前缀名称。

## Requirements
- 按顺序迁移：fenjing.py → auto_storyboard.py → video.py → visual_audio_assets.py
- 每个 emit_event 的 step= 参数替换为对应的新 step 名
- 去掉 emit_event 中多余的 phase= 参数（phase 概念合并到 step 中）
- 每个 flow 迁移完后，删除 _resolve_step() 中该 flow 的映射分支
- workflow_service.py 中的状态更新调用同步适配新 step 名

## Acceptance Criteria
- [ ] fenjing.py 所有 emit_event step 使用 step_download/step_generate/step_upload
- [ ] auto_storyboard.py 所有 emit_event step 使用 step_extract/step_storyboard/step_upload
- [ ] video.py 所有 emit_event step 使用 step_prepare/step_video_prompts/step_video_generation/step_video_upload
- [ ] visual_audio_assets.py 所有 emit_event step 使用 step_ 前缀标准名
- [ ] _resolve_step() 中所有旧映射分支已删除
- [ ] workflow_service.py 状态更新使用新 step 名

## Technical Notes
- 依赖 Task 1 完成
- 替换表见计划文件 `~/.claude/plans/whimsical-inventing-clover.md` 第二阶段
- step="general"/"start"/"complete" 等非状态性 step 需根据上下文归属到对应标准 step
