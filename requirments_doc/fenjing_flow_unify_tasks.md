# 实现计划：Fenjing Flow 统一重构

## 任务列表

### 阶段 1: 后端状态服务修改 (status_service.py)

- [ ] **T1.1** 移除 `_FLOW_STEPS` 中的 `fenjing_generate` 和 `fenjing_upload` 定义
- [ ] **T1.2** 移除 `_PARTIAL_STEPS` 中的 `fenjing_generate` 条目
- [ ] **T1.3** 添加 `WORKFLOW_TO_FLOW_MAP` 映射常量
- [ ] **T1.4** 实现 `_migrate_fenjing_flows` 状态迁移函数
- [ ] **T1.5** 在 `_normalize_state` 中调用迁移函数
- [ ] **T1.6** 更新 `_resolve_step` 函数，移除 `fenjing_generate` 和 `fenjing_upload` 的处理分支
- [ ] **T1.7** 更新 `_resolve_steps` 函数，添加 workflow 到 flow 的映射
- [ ] **T1.8** 移除 `mark_fenjing_generate_partial` 函数（或更新为使用 `fenjing` flow）

### 阶段 2: 后端工作流服务修改 (workflow_service.py)

- [ ] **T2.1** 合并 `run_fenjing_generate` 和 `run_fenjing_upload` 的核心逻辑到 `run_fenjing`
- [ ] **T2.2** 更新 `run_fenjing` 函数支持 `phase` 参数（"generate", "upload", "all"）
- [ ] **T2.3** 更新状态更新调用，使用统一的 `fenjing` flow
- [ ] **T2.4** 移除或标记废弃 `run_fenjing_generate` 和 `run_fenjing_upload` 函数

### 阶段 3: 后端 Handler 修改

#### job_handler.py

- [ ] **T3.1** 更新 `_resolve_steps_from_phase` 函数，添加 workflow 到 flow 的映射
- [ ] **T3.2** 更新 `handle_post` 中的 workflow 白名单（保持兼容）
- [ ] **T3.3** 更新 workflow 路由逻辑，使用统一的 `fenjing` flow
- [ ] **T3.4** 更新 job 类型映射

#### project_handler.py

- [ ] **T3.5** 更新 flow 白名单，移除 `fenjing_generate` 和 `fenjing_upload`

### 阶段 4: 后端 Repository 修改

#### asset_repo.py

- [ ] **T4.1** 更新 `build_fenjing_asset_results` 函数中的 flow 名称映射
- [ ] **T4.2** 更新产物路径逻辑，使用统一的 `fenjing` flow

#### job_repo.py

- [ ] **T4.3** 更新 job 类型映射，移除或合并 `fenjing_generate` 和 `fenjing_upload`

### 阶段 5: 前端修改 (app.js, index.html)

- [ ] **T5.1** 添加 `WORKFLOW_TO_FLOW_MAP` 映射常量
- [ ] **T5.2** 添加 `getFlowFromWorkflow` 辅助函数
- [ ] **T5.3** 更新 `STAGE_TYPES` 常量（保持兼容，内部映射）
- [ ] **T5.4** 更新分镜生成按钮的状态读取逻辑
- [ ] **T5.5** 更新分镜上传按钮的状态读取逻辑
- [ ] **T5.6** 更新 job-item 卡片渲染逻辑
- [ ] **T5.7** 更新 flow 状态轮询逻辑
- [ ] **T5.8** 更新 `index.html` 中的按钮 data-flow 属性（可选，保持兼容）

### 阶段 6: 测试与验证

- [ ] **T6.1** 编写状态迁移单元测试
- [ ] **T6.2** 编写 workflow 到 flow 映射单元测试
- [ ] **T6.3** 编写 fenjing flow 状态计算单元测试
- [ ] **T6.4** 运行现有测试套件，确保无回归
- [ ] **T6.5** 手动测试前端分镜生成按钮
- [ ] **T6.6** 手动测试前端分镜上传按钮
- [ ] **T6.7** 验证多项目并发场景

### 阶段 7: 清理与文档

- [ ] **T7.1** 移除废弃的 `run_fenjing_generate` 和 `run_fenjing_upload` 函数
- [ ] **T7.2** 更新 API 文档
- [ ] **T7.3** 更新 README 或相关文档

## 任务依赖关系

```
T1.1 ─┬─> T1.4 ─> T1.5
T1.2 ─┤
T1.3 ─┘

T1.x ─> T2.x ─> T3.x ─> T4.x ─> T5.x ─> T6.x ─> T7.x
```

## 预估工作量

| 阶段 | 任务数 | 预估时间 |
|------|--------|----------|
| 阶段 1 | 8 | 30分钟 |
| 阶段 2 | 4 | 20分钟 |
| 阶段 3 | 5 | 15分钟 |
| 阶段 4 | 3 | 10分钟 |
| 阶段 5 | 8 | 25分钟 |
| 阶段 6 | 7 | 20分钟 |
| 阶段 7 | 3 | 10分钟 |
| **总计** | **38** | **~2小时** |

## 风险检查点

| 检查点 | 触发条件 | 处理方案 |
|--------|----------|----------|
| 状态迁移失败 | 迁移后状态不一致 | 回滚到备份状态 |
| 测试失败 | 单元测试或集成测试失败 | 修复后重新测试 |
| 前端异常 | 按钮无法点击或状态错误 | 检查 API 兼容性 |
| 并发问题 | 多项目执行时状态混乱 | 检查锁机制 |
