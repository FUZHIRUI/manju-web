# 前端状态同步

## Goal
前端 app.js 与后端新 step 命名对齐，修复已知 bug。

## Requirements
- 修复 isAssetGenerating("fenjing") 跨 flow 查错 step bug（app.js:3728）
- 更新 FLOW_TREE_CONFIG 中所有 step id 为新的 step_ 前缀命名
- 更新前端发送的 phase API 参数（step1→step_extract 等）
- 删除 `flow === "fenjing"` 死代码（app.js:5898）
- job_handler.py phase 白名单同步更新

## Acceptance Criteria
- [ ] isAssetGenerating("fenjing") 能正确检测 fenjing 工作状态
- [ ] FLOW_TREE_CONFIG 所有 step id 使用 step_ 前缀
- [ ] 前端 API 请求的 phase 参数使用新命名
- [ ] 死代码已清理
- [ ] 前端步骤进度卡片正确显示

## Technical Notes
- 依赖 Task 2 完成
- 前端修改文件：frontend/app.js（~400行 FLOW_TREE_CONFIG + API 调用）
- 后端同步文件：backend/handlers/job_handler.py（phase 白名单）
