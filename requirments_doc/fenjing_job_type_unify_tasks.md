# 实现计划：Fenjing Job Type 统一重构

## 任务列表

### 阶段 1: 后端 job_handler.py 修改

- [ ] **T1.1** 修改 `_resolve_flow_steps` 函数，支持 `fenjing` workflow 的 phase 参数解析
- [ ] **T1.2** 修改 `handle_post` 函数中的 workflow 白名单，移除 `fenjing_generate` 和 `fenjing_upload`
- [ ] **T1.3** 合并 `fenjing_generate` 和 `fenjing_upload` 的路由逻辑到 `fenjing`
- [ ] **T1.4** 修改 job 创建逻辑，统一使用 `run_fenjing` job type

### 阶段 2: 后端 workflow_service.py 修改

- [ ] **T2.1** 修改 `run_fenjing` 函数，添加 `phase` 参数支持
- [ ] **T2.2** 在 `run_fenjing` 中根据 phase 调用对应的 workflow 函数
- [ ] **T2.3** 标记 `run_fenjing_generate` 和 `run_fenjing_upload` 为废弃（保留向后兼容）

### 阶段 3: 后端 status_service.py 修改

- [ ] **T3.1** 简化 `WORKFLOW_TO_FLOW_MAP`，移除冗余映射（保留向后兼容）
- [ ] **T3.2** 更新 `_resolve_step` 函数，支持新的 phase 参数

### 阶段 4: 前端 app.js 修改

- [ ] **T4.1** 简化 `STAGE_TYPES`，移除 `fenjing_generate` 和 `fenjing_upload`
- [ ] **T4.2** 移除 `WORKFLOW_TO_FLOW_MAP` 和 `getFlowFromWorkflow` 函数
- [ ] **T4.3** 修改 `executeFlowFull` 函数，支持 `options.phase` 参数
- [ ] **T4.4** 修改 `appendFenjingPhaseButtons` 函数，使用新的 API 调用方式
- [ ] **T4.5** 简化 `getFlowFromJob` 函数
- [ ] **T4.6** 更新 `setFlowTouched` 调用，移除 `getFlowFromWorkflow` 映射
- [ ] **T4.7** 更新 `renderJobs` 中的条件检查

### 阶段 5: 测试与验证

- [ ] **T5.1** 验证分镜图生成按钮可正常点击并执行
- [ ] **T5.2** 验证分镜上传按钮可正常点击并执行
- [ ] **T5.3** 验证 job-item 卡片状态正确显示
- [ ] **T5.4** 验证多项目并发场景

## 任务依赖关系

```
T1.x ─> T2.x ─> T3.x ─> T4.x ─> T5.x
```

## 预估工作量

| 阶段 | 任务数 | 预估时间 |
|------|--------|----------|
| 阶段 1 | 4 | 15分钟 |
| 阶段 2 | 3 | 10分钟 |
| 阶段 3 | 2 | 5分钟 |
| 阶段 4 | 7 | 15分钟 |
| 阶段 5 | 4 | 10分钟 |
| **总计** | **20** | **~55分钟** |

## 风险检查点

| 检查点 | 触发条件 | 处理方案 |
|--------|----------|----------|
| 后端 API 错误 | 调用新 API 返回错误 | 检查参数传递和路由逻辑 |
| 前端调用失败 | 按钮点击无响应 | 检查 API 调用路径 |
| 状态显示异常 | job-item 状态不正确 | 检查 getFlowFromJob 和状态映射 |
