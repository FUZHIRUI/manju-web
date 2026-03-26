# 状态管理清理与全量验证

## Goal
清理所有旧代码残留，全量验证重构正确性。

## Requirements
- 删除 _resolve_step() / _resolve_steps() 函数（已无调用）
- 删除 WORKFLOW_TO_FLOW_MAP
- 删除 _normalize_state() 中旧步骤兼容代码
- 删除4个旧 rollup 函数
- 运行全量测试
- 手动验证前端步骤进度

## Acceptance Criteria
- [ ] 无旧代码残留
- [ ] 全量测试通过
- [ ] 前端步骤进度卡片正确显示 running → completed 变化

## Technical Notes
- 依赖 Task 3 完成
- 这是最终清理阶段，确认无旧状态文件后再删除迁移映射
