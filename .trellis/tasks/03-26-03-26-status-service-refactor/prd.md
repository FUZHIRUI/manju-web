# status_service.py 核心重构

## Goal
统一四个流程的状态管理核心：新 _FLOW_STEPS 定义、旧→新迁移映射、合并 rollup 函数、简化 _resolve_step。

## Requirements
- 将 _FLOW_STEPS 中所有 step 统一为 `step_` 前缀命名
- 删除 `fenjing` flow，保留 `fenjing_generate` + `fenjing_upload`
- visual_audio_assets 移除父步骤（build_prompts/generate_images/generate_tts），只保留叶子步骤
- auto_storyboard 简化为3个步骤（step_extract/step_storyboard/step_upload）
- 新增 _STEP_MIGRATION 映射表，在 _normalize_state 中自动迁移旧状态
- 合并4个独立 rollup 函数为2个通用实现（父子聚合 + 顺序依赖）
- _resolve_step 开头加直通逻辑（step 已在 _FLOW_STEPS 则直接返回），保留旧映射兼容
- workflow_service.py 统一状态更新模式
- job_handler.py phase 白名单适配新 step 名

## Acceptance Criteria
- [ ] _FLOW_STEPS 所有 step 使用 step_ 前缀
- [ ] 旧格式 flow_state.json 读取时自动迁移到新格式
- [ ] 4个 rollup 函数合并为通用实现
- [ ] 现有测试 test_flow_state_*.py 通过（适配新命名后）
- [ ] emit_event 使用旧 step 名仍能正确映射（过渡期兼容）

## Technical Notes
- 参考审查报告：`.trellis/analysis/2026-03-26/state-management-review.md`
- 参考重构计划：`~/.claude/plans/whimsical-inventing-clover.md`
- 此 task 不修改 emit_event 调用，只改 status_service 内部
